import asyncio  # noqa: ANYIO_OK - isolated Home Assistant runtime
from datetime import datetime, timezone
import tempfile
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.components import persistent_notification as pn
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from custom_components.ksx4506_ew11.alert_policy import Endpoint
from custom_components.ksx4506_ew11.const import DOMAIN
from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11.device_alerts import DeviceAlerts
from custom_components.ksx4506_ew11.diagnostic_sensors import KsxEw11LinkSensor
from custom_components.ksx4506_ew11.recovery import CommandStatus


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ew11-auto-reconnect-") as config_dir:
        hass = HomeAssistant(config_dir)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(
            domain=DOMAIN, title="Test bridge", data={}, options={}, source="user",
            version=1, minor_version=1, unique_id="auto-reconnect",
            discovery_keys=MappingProxyType({}), subentries_data=None,
        )
        hass.config_entries._entries[entry.entry_id] = entry
        await ar.async_load(hass)
        await dr.async_load(hass)
        await er.async_load(hass)
        coordinator = Ksx4506Coordinator(hass, {
            "host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0,
        }, entry=entry)
        clock = [1000.0]
        health = {"state": "receiving", "running": True, "connected": True,
                  "connect_attempts": 1, "seconds_since_valid_rx": 0.1,
                  "transport_failures_since_rx": 0,
                  "seconds_since_transport_fault": None,
                  "connect_attempts_since_transport_fault": 0}
        coordinator._client.health_report = lambda: health.copy()

        async def reconnect() -> None:
            health["connect_attempts"] += 1

        coordinator._client.async_reconnect = AsyncMock(side_effect=reconnect)
        coordinator._power_cycle = AsyncMock()
        async def no_response(addr, sub_id, **kwargs):
            coordinator.state_query_results[(addr, sub_id)] = {'result': 'no_response'}
            return None
        coordinator.async_request_f7_state_until = AsyncMock(side_effect=no_response)
        responses = {"0x0E/0x11": 1000.0, "0x39/0x11": 1000.0,
                     "0x60/0x01": 1000.0}
        sensor = KsxEw11LinkSensor(coordinator, entry)
        try:
            with patch("custom_components.ksx4506_ew11.device_alerts.time",
                       SimpleNamespace(time=lambda: clock[0])), \
                 patch("custom_components.ksx4506_ew11.device_alerts.monotonic",
                       lambda: clock[0]):
                alerts = DeviceAlerts(coordinator, entry.entry_id)
                alerts._labels = lambda: {key: key for key in responses}
                alerts._endpoints = lambda labels: tuple(
                    Endpoint(key, (key,), 3, stamp, True, max(0, clock[0] - stamp))
                    for key, stamp in responses.items()
                )
                alerts.policy.known = responses.copy()
                await alerts.async_load()
                alerts.policy.known = responses.copy()
                for stamp in (1000, 1180, 1210, 1240, 1419):
                    clock[0] = stamp
                    await alerts.async_tick()
                coordinator._client.async_reconnect.assert_not_awaited()
                async with coordinator._transaction_lock:
                    clock[0] = 1420
                    await alerts.async_tick()
                coordinator._client.async_reconnect.assert_not_awaited()
                clock[0] = 1421
                await alerts.async_tick()
                coordinator._client.async_reconnect.assert_awaited_once()
                assert sensor.extra_state_attributes["auto_reconnect_state"] == "awaiting_confirmed_responses"
                assert sensor.extra_state_attributes["fault_category"] == "shared_response_outage"
                notification = pn._async_get_or_create_notifications(hass)[coordinator.recovery_notification_id]
                assert notification["title"] == "여러 주소 응답 점검 필요"
                assert "공통 중단" in notification["message"]
                assert "소켓 재연결을 1회 요청" in notification["message"]
                await alerts.async_save()
                reloaded = DeviceAlerts(coordinator, entry.entry_id)
                reloaded._labels = alerts._labels
                reloaded._endpoints = alerts._endpoints
                await reloaded.async_load()
                clock[0] = 2000
                await reloaded.async_tick()
                coordinator._client.async_reconnect.assert_awaited_once()
                responses["0x0E/0x11"] = 2001
                clock[0] = 2001
                await reloaded.async_tick()
                assert sensor.extra_state_attributes["auto_reconnect_state"] == "awaiting_confirmed_responses"
                responses["0x39/0x11"] = 2002
                clock[0] = 2002
                await reloaded.async_tick()
                assert sensor.extra_state_attributes["auto_reconnect_state"] == "last_attempt_verified"
                for stamp in (2032, 2062):
                    clock[0] = stamp
                    await reloaded.async_tick()
                assert sensor.extra_state_attributes["fault_category"] == "endpoint_no_response"
                assert sensor.extra_state_attributes["fault_peer_confirmed"] is True
                assert "다른 주소 응답 확인" in pn._async_get_or_create_notifications(hass)[
                    coordinator.recovery_notification_id]["message"]
                assert sensor.extra_state_attributes["auto_reconnect_verified_at"] == (
                    datetime.fromtimestamp(2002, timezone.utc).isoformat()
                )
                responses["0x60/0x01"] = 2063
                clock[0] = 2063
                await reloaded.async_tick()
                coordinator.recovery.status["0x0E/0x11"] = CommandStatus(
                    (0x0E, 0x11), lambda frame: False,
                    state="failed", reason="state_not_confirmed",
                )
                await reloaded.async_tick()
                assert sensor.extra_state_attributes["fault_category"] == "control_unconfirmed"
                assert pn._async_get_or_create_notifications(hass)[
                    coordinator.recovery_notification_id]["title"] == "제어 결과 점검 필요 · 1개 기기"
                coordinator._power_cycle.assert_not_awaited()
            print("real HA auto reconnect: complete outage, busy guard, one socket reset, "
                  "reload lockout, two-response verification, no power cycle: passed")
        finally:
            await hass.async_stop()


if __name__ == "__main__":
    asyncio.run(main())
