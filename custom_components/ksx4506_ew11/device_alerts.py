"""One evidence-based HA notification per EW11 entry; no power actions."""
from __future__ import annotations

import asyncio  # noqa: ANYIO_OK - HA serial transactions use its asyncio loop
from datetime import datetime
import time
from typing import TYPE_CHECKING, NotRequired, TypedDict

from homeassistant.components import persistent_notification
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from .alert_policy import AlertPolicy, Endpoint
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import Ksx4506Coordinator


class AlertStorage(TypedDict):
    known: dict[str, float]
    problems: NotRequired[dict[str, str]]
    controls: NotRequired[list[str]]


class DeviceAlerts:
    def __init__(self, coordinator: Ksx4506Coordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.entry_id = entry_id
        self.policy = AlertPolicy(started=time.time())
        self.store = Store[AlertStorage](self.hass, 1, f"{DOMAIN}.{entry_id}.device_alerts")
        self.previous: dict[str, str] = {}
        self.controls: set[str] = set()
        self.announced = False
        self.saved_at = time.time()

    async def async_load(self) -> None:
        saved = await self.store.async_load()
        if saved:
            self.policy.known = saved["known"]
            self.previous = saved.get("problems", {})
            self.controls = set(saved.get("controls", []))

    async def async_save(self) -> None:
        await self.store.async_save({"known": self.policy.known.copy(),
                                     "problems": self.previous.copy(),
                                     "controls": sorted(self.controls)})
        self.saved_at = time.time()

    def _labels(self) -> dict[str, str]:
        devices = dr.async_get(self.hass)
        entities = er.async_get(self.hass)
        areas = ar.async_get(self.hass)
        labels: dict[str, str] = {}
        keys = set(self.coordinator.registry.devices)
        for key, state in self.coordinator.registry.devices.items():
            for zone in state.state.get("zones", []):
                channel = zone.get("channel")
                if isinstance(channel, int):
                    keys.add(f"{key}_ch{channel}")
        for key in sorted(keys):
            device = devices.async_get_device(identifiers={(DOMAIN, key)})
            if device is None or device.disabled_by is not None:
                continue
            members = er.async_entries_for_device(entities, device.id)
            enabled = [e for e in members if e.config_entry_id == self.entry_id
                       and e.disabled_by is None]
            if not enabled:
                continue
            primary = next((e for e in enabled if e.entity_category is None), enabled[0])
            name = device.name_by_user or primary.name or device.name or key
            area_id = primary.area_id or device.area_id
            area = areas.async_get_area(area_id) if area_id else None
            labels[key] = f"{area.name if area else '영역 미지정'} · {name}"
        return labels

    def _endpoints(self, labels: dict[str, str]) -> tuple[Endpoint, ...]:
        targets = set(self.coordinator._known_state_request_targets())
        result: list[Endpoint] = []
        for device in self.coordinator.device_vitality_report()["devices"]:
            keys = tuple(key for key in labels if any(
                key == base or key.startswith(f"{base}_ch")
                for base in device["device_keys"]
            ))
            if not keys:
                continue
            stamp = device["last_response_at"]
            result.append(Endpoint(
                device["endpoint"], keys, device["response_count"],
                datetime.fromisoformat(stamp).timestamp() if stamp else None,
                (int(device["device_id"], 16), int(device["sub_id"], 16)) in targets,
            ))
        return tuple(result)

    async def async_tick(self) -> None:
        previous = self.previous.copy()
        previous_controls = self.controls.copy()
        labels = self._labels()
        endpoints = self._endpoints(labels)
        scan = self.policy.scan(endpoints, now=time.time())
        for key in scan.probes:
            # User commands have priority; a busy bus is not device failure.
            if self.coordinator._transaction_lock.locked():
                break
            addr, sub_id = (int(part, 16) for part in key.split("/"))
            try:
                async with asyncio.timeout(2):
                    matched = await self.coordinator.async_request_f7_state_until(
                        addr, sub_id, max_attempts=1, interval=0.5,
                    )
                success = matched is not None
            except (TimeoutError, OSError):
                success = False
            self.coordinator.device_vitality.record_probe(addr, sub_id, success=success)
            self.policy.record_probe(key, success=success, now=time.time())
        # Responses received during probing must be considered before notifying.
        endpoints = self._endpoints(labels)
        scan = self.policy.scan(endpoints, now=time.time())
        problems: dict[str, str] = {}
        for alert in scan.alerts:
            reason = ("상태 응답 없음 · 확인 요청 3회 이상 실패"
                      if alert.reason == "no_response" else
                      "15분 이상 상태 갱신 없음 · 제어 고장으로 단정할 수 없음")
            for key in alert.device_keys:
                problems[key] = f"{labels[key]} — {reason}"
        for key, status in self.coordinator.recovery.status.items():
            if key not in labels:
                continue
            if status.state == "failed" and status.reason != "superseded_or_stopped":
                problems[key] = f"{labels[key]} — 요청한 제어 결과를 확인하지 못함"
                self.controls.add(key)
            elif status.state == "healthy":
                self.controls.discard(key)
            elif status.state != "healthy" and key in self.previous:
                problems[key] = self.previous[key]
        fresh = {key for endpoint in endpoints
                 if endpoint.last_response is not None and endpoint.last_response > self.policy.started
                 for key in endpoint.device_keys}
        fresh.update(key for key, status in self.coordinator.recovery.status.items()
                     if status.state == "healthy")
        for key, text in self.previous.items():
            if key in labels and (key in self.controls or key not in fresh):
                problems.setdefault(key, text)
        self.controls.intersection_update(labels)
        self._notify(problems, labels)
        if (previous != self.previous or previous_controls != self.controls
                or time.time() - self.saved_at >= 300):
            await self.async_save()

    def _notify(self, problems: dict[str, str], labels: dict[str, str]) -> None:
        if problems == self.previous and (self.announced or not problems):
            return
        removed = self.previous.keys() - problems.keys()
        recovered = [labels[key] for key in sorted(removed) if key in labels]
        excluded = len(removed - labels.keys())
        lines = [f"- {text}" for _, text in sorted(problems.items())]
        if recovered:
            lines += ["", "응답/제어 상태 재확인: " + ", ".join(recovered)]
        if excluded:
            lines += ["", f"삭제·비활성화 등으로 감시 제외: {excluded}개 (복구 판정 아님)"]
        if problems:
            lines += ["", "전체 패킷이 수신 중이어도 개별 기기는 응답하지 않을 수 있습니다.",
                      "자동 재시작은 하지 않았습니다. 연결과 기기 전원을 먼저 확인하세요.",
                      "여러 기기가 함께 멈췄다면 월패드 재시작을 검토하세요. "
                      "재시작 중에는 연결된 모든 기기의 제어가 중단됩니다. "
                      "필요할 때만 전용 전원 스위치를 직접 조작하세요."]
        else:
            lines += ["", "현재 감시 대상에 남은 감지 장애가 없습니다. "
                      "실제 기기 동작 성공을 보증하는 것은 아닙니다."]
        lines += ["", f"[EW11 기기 확인](/config/integrations/integration/{DOMAIN})"]
        persistent_notification.async_create(
            self.hass, "\n".join(lines),
            title=f"EW11 확인 필요 · {len(problems)}개 기기" if problems else "EW11 감시 상태 갱신",
            notification_id=self.coordinator.recovery_notification_id,
        )
        self.previous = problems.copy()
        self.announced = True
