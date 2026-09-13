"""Staged hub recovery; ordinary device retries remain in CommandRecovery."""
from __future__ import annotations

import asyncio  # noqa: ANYIO_OK - HA lifecycle owns and awaits the watchdog
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import Ksx4506Coordinator

_LOGGER = logging.getLogger(__name__)


class HubRecovery:
    def __init__(self, coordinator: Ksx4506Coordinator) -> None:
        self.coordinator = coordinator
        self.probed_zero = False
        self.notified = False

    async def run(self) -> None:
        while True:
            await asyncio.sleep(15)
            await self.tick()

    async def _probe(self) -> bool:
        coordinator = self.coordinator
        targets = coordinator._known_state_request_targets()
        if len(targets) < 2:
            return False
        responses = 0
        async with asyncio.timeout(45):
            await asyncio.sleep(2)
            for addr, sub_id in targets:
                matched = await coordinator.async_request_f7_state_until(
                    addr, sub_id, max_attempts=1, interval=0.5,
                )
                coordinator.device_vitality.record_probe(
                    addr, sub_id, success=matched is not None,
                )
                responses += matched is not None
        return responses == 0

    async def tick(self) -> None:
        coordinator = self.coordinator
        policy = coordinator.hub_recovery
        commands = coordinator.recovery
        try:
            health = coordinator._client.health_report()
            report = coordinator.device_vitality_report()
            responders = sum(
                1 for device in report["devices"]
                if device["seconds_since_response"] is not None
                and device["seconds_since_response"] < 60
            )
            failed_endpoints = commands.failed_endpoints(window=600) | {
                (int(device["device_id"], 16), int(device["sub_id"], 16))
                for device in report["devices"]
                if device["consecutive_failures"] >= 2
                and device["last_probe_success"] is False
            }
            action = policy.action(
                now=asyncio.get_running_loop().time(),
                link_failed=health["state"] != "receiving",
                failed_endpoints=len(failed_endpoints), responders=responders,
                power_enabled=(coordinator._power_cycle is not None
                               and health["connected"] and self.probed_zero),
            )
            if action is not None:
                await commands.stop()
                self.probed_zero = False
                try:
                    if action == "reconnect":
                        _LOGGER.warning("EW11 recovery reconnect after sustained failure")
                        async with coordinator._transaction_lock:
                            await coordinator._client.async_reconnect()
                    elif action == "power_cycle" and coordinator._power_cycle is not None:
                        _LOGGER.warning("EW11 recovery attempting configured power cycle")
                        async with coordinator._transaction_lock:
                            await coordinator._client.stop()
                            try:
                                powered = await coordinator._power_cycle()
                            finally:
                                await coordinator._client.start()
                        if not powered:
                            policy.state = "failed"
                        await asyncio.sleep(60)
                    self.probed_zero = await self._probe()
                finally:
                    commands.resume()
            problems = commands.report()
            failure = policy.state == "failed" or any(
                item["control_status"] == "failed" for item in problems.values()
            )
            if failure and not self.notified:
                self._notify_failure()
            if not problems and policy.state == "idle":
                self.notified = False
                self.probed_zero = False
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BROAD_EXCEPT_OK - supervised HA task boundary
            _LOGGER.exception("EW11 automatic recovery failed")
            policy.state = "failed"
            self._notify_failure()
        finally:
            coordinator._publish_registry_state()

    def _notify_failure(self) -> None:
        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            self.coordinator.hass,
            "EW11 기기 제어 또는 자동 복구를 확인하지 못했습니다. "
            "RS485 Device Vitality의 control_problems와 HA 로그를 확인하세요. "
            "전원 복구 중 오류가 났다면 전원 스위치가 켜졌는지도 확인해야 합니다. "
            "전체 수신 상태가 receiving이어도 개별 제어는 실패할 수 있습니다.",
            title="EW11 제어 확인 필요",
            notification_id=self.coordinator.recovery_notification_id,
        )
        self.notified = True
