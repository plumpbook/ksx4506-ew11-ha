"""Use real HA state/storage/notifications, without setting up transport or devices."""
import asyncio  # noqa: ANYIO_OK - isolated Home Assistant runtime
import tempfile
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.components import persistent_notification as pn
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from custom_components.ksx4506_ew11.const import DOMAIN
from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11 import ew11_client as client_module
from custom_components.ksx4506_ew11.device_alerts import DeviceAlerts
from custom_components.ksx4506_ew11.diagnostic_sensors import KsxEw11LinkSensor
from custom_components.ksx4506_ew11.hub_recovery import HubRecovery
from custom_components.ksx4506_ew11.ew11_health import LinkInspectionPolicy


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ew11-inspection-runtime-") as config_dir:
        hass = HomeAssistant(config_dir)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(domain=DOMAIN, title="Test bridge", data={}, options={},
                            source="user", version=1, minor_version=1, unique_id="inspection",
                            discovery_keys=MappingProxyType({}), subentries_data=None)
        hass.config_entries._entries[entry.entry_id] = entry
        await ar.async_load(hass)
        await dr.async_load(hass)
        await er.async_load(hass)
        config = {"host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0}
        coordinator = Ksx4506Coordinator(hass, config, entry=entry)
        other = Ksx4506Coordinator(hass, config, entry=entry)
        assert coordinator.recovery_notification_id == other.recovery_notification_id
        sensor = KsxEw11LinkSensor(coordinator, entry)
        assert sensor.unique_id == f"ksx4506_{entry.entry_id}_ew11_link"
        clock = [1000.0]
        health = {"state": "disconnected", "running": True, "connected": False,
                  "connect_attempts": 8, "seconds_since_valid_rx": None,
                  "transport_failures_since_rx": 8, "seconds_since_transport_fault": 180,
                  "connect_attempts_since_transport_fault": 7}
        coordinator._client.health_report = lambda: health.copy()
        coordinator._power_cycle = AsyncMock()
        coordinator._client.async_reconnect = AsyncMock()
        forbidden_calls = []
        hass.services.async_register("switch", "turn_off", lambda call: forbidden_calls.append("off"))
        hass.services.async_register("switch", "turn_on", lambda call: forbidden_calls.append("on"))
        try:
            with patch("custom_components.ksx4506_ew11.device_alerts.time",
                       SimpleNamespace(time=lambda: clock[0])), \
                 patch("custom_components.ksx4506_ew11.device_alerts.monotonic", lambda: clock[0]), \
                 patch.object(pn, "async_create", wraps=pn.async_create) as create:
                alerts = DeviceAlerts(coordinator, entry.entry_id)
                await alerts.async_load()
                watchdog = HubRecovery(coordinator)
                watchdog.alerts = alerts
                notifications = pn._async_get_or_create_notifications(hass)
                for stamp in (1000, 1179):
                    clock[0] = stamp
                    await watchdog.tick()
                    assert not notifications
                    assert not sensor.extra_state_attributes["inspection_needed"]
                clock[0] = 1180
                await watchdog.tick()
                assert create.call_count == 1 and len(notifications) == 1
                assert sensor.native_value == "disconnected"
                assert sensor.extra_state_attributes["inspection_needed"]
                first = notifications[coordinator.recovery_notification_id]
                assert first["title"] == "EW11·네트워크 점검 필요"
                assert "원인은 확정되지 않았습니다" in first["message"]
                clock[0] = 1200
                await watchdog.tick()
                assert create.call_count == 1
                await alerts.async_save()
                clock[0] = 1201
                reloaded = DeviceAlerts(coordinator, entry.entry_id)
                await reloaded.async_load()
                watchdog.alerts = reloaded
                assert reloaded.link_problem == alerts.link_problem
                await watchdog.tick()
                assert notifications[coordinator.recovery_notification_id] is first
                clock[0] = 1381
                await watchdog.tick()
                assert sensor.extra_state_attributes["inspection_needed"]
                assert create.call_count == 1
                assert sensor.extra_state_attributes["notification_cooldown_remaining_seconds"] == 99
                clock[0] = 1480
                await watchdog.tick()
                assert create.call_count == 2 and len(notifications) == 1
                health.update(state="receiving", connected=True, seconds_since_valid_rx=0,
                              transport_failures_since_rx=0, seconds_since_transport_fault=None,
                              connect_attempts_since_transport_fault=0)
                clock[0] = 1481
                await watchdog.tick()
                assert not sensor.extra_state_attributes["inspection_needed"]
                assert create.call_count == 3
                assert "최근 정상 패킷 수신" in notifications[coordinator.recovery_notification_id]["message"]
                assert "기기 동작 성공을 보증" in notifications[coordinator.recovery_notification_id]["message"]
                # Another confirmed incident within the five-minute cooldown is
                # visible in the existing sensor while notice delivery is delayed.
                health.update(state="disconnected", connected=False, seconds_since_valid_rx=201,
                              transport_failures_since_rx=8, seconds_since_transport_fault=200,
                              connect_attempts_since_transport_fault=7)
                clock[0] = 1682
                await watchdog.tick()
                assert sensor.extra_state_attributes["inspection_needed"] and create.call_count == 3
                clock[0] = 1780
                await watchdog.tick()
                assert create.call_count == 4 and len(notifications) == 1
                pn.async_dismiss(hass, coordinator.recovery_notification_id)
                await watchdog.tick()
                assert not notifications and create.call_count == 4
                health["running"] = False
                await watchdog.tick()
                assert not sensor.extra_state_attributes["inspection_needed"]
                assert "감시 중지 · 복구 판정 아님" in notifications[coordinator.recovery_notification_id]["message"]
                coordinator._power_cycle.assert_not_awaited()
                coordinator._client.async_reconnect.assert_not_awaited()
                assert not forbidden_calls
            print("real HA inspection: grace, existing entity/id, sustained failure, one notice, "
                  "reload/cooldown, valid receive, recurrence, dismissal, stop, no device commands: passed")
        finally:
            await hass.async_stop()


async def lifecycle_case() -> None:
    """Call the coordinator's real start/stop methods; park every IO worker."""
    with tempfile.TemporaryDirectory(prefix="ew11-lifecycle-runtime-") as config_dir:
        hass = HomeAssistant(config_dir)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(domain=DOMAIN, title="Lifecycle test", data={}, options={},
                            source="user", version=1, minor_version=1, unique_id="lifecycle",
                            discovery_keys=MappingProxyType({}), subentries_data=None)
        hass.config_entries._entries[entry.entry_id] = entry
        await ar.async_load(hass)
        await dr.async_load(hass)
        await er.async_load(hass)
        coordinator = Ksx4506Coordinator(hass, {
            "host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0,
        }, entry=entry)
        sensor = KsxEw11LinkSensor(coordinator, entry)
        clock = [0.0]

        async def park() -> None:
            await asyncio.Event().wait()

        coordinator._client._run_loop = park
        coordinator.async_probe_meter_states = AsyncMock()
        coordinator.async_monitor_known_device_states = AsyncMock()
        try:
            with patch.object(client_module, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                 patch("custom_components.ksx4506_ew11.device_alerts.monotonic", lambda: clock[0]), \
                 patch("custom_components.ksx4506_ew11.device_alerts.time",
                       SimpleNamespace(time=lambda: 1000 + clock[0])), \
                 patch.object(HubRecovery, "run", AsyncMock(side_effect=park)), \
                 patch("asyncio.open_connection", AsyncMock(side_effect=AssertionError("network forbidden"))) as connection:
                await coordinator.async_start()
                assert sensor.extra_state_attributes["inspection_state"] == "starting"
                assert not sensor.extra_state_attributes["inspection_needed"]
                await asyncio.sleep(0)
                alerts = DeviceAlerts(coordinator, entry.entry_id)
                await alerts.async_load()
                coordinator._client._mark_connected()
                coordinator._client._mark_rx()
                for stamp in (10, 30, 60):
                    clock[0] = stamp
                    coordinator._client._connection_stats.record_attempt()
                    coordinator._client._record_transport_failure()
                coordinator._client._connected = False
                clock[0] = 200
                await alerts.async_tick()
                assert sensor.extra_state_attributes["inspection_needed"]
                notifications = pn._async_get_or_create_notifications(hass)
                assert notifications[coordinator.recovery_notification_id]["title"] == "EW11·네트워크 점검 필요"
                await coordinator.async_stop()
                stopped = sensor.extra_state_attributes
                assert not stopped["running"] and not stopped["inspection_needed"]
                assert stopped["inspection_state"] == "stopped"
                assert "복구 판정 아님" in stopped["inspection_summary"]
                assert stopped["manual_restart_consideration"] is None
                assert coordinator.recovery_notification_id not in notifications
                assert coordinator._recovery_task is None
                assert coordinator._client._task is None and coordinator._client._worker_task is None
                # Display/notification cleanup must retain the unresolved journal.
                reloaded = DeviceAlerts(coordinator, entry.entry_id)
                await reloaded.async_load()
                assert reloaded.link_problem == "repeated_transport_failure"
                assert reloaded.last_link_notice_at == alerts.last_link_notice_at
                await coordinator.async_start()
                assert sensor.extra_state_attributes["running"]
                assert sensor.extra_state_attributes["inspection_state"] == "starting"
                assert not sensor.extra_state_attributes["inspection_needed"]
                await asyncio.sleep(0)
                for stamp in (200, 379):
                    clock[0] = stamp
                    await reloaded.async_tick()
                    assert not sensor.extra_state_attributes["inspection_needed"]
                    assert coordinator.recovery_notification_id not in notifications
                clock[0] = 380
                await reloaded.async_tick()
                assert sensor.extra_state_attributes["inspection_needed"]
                coordinator._client._mark_rx()
                clock[0] = 381
                await reloaded.async_tick()
                assert not sensor.extra_state_attributes["inspection_needed"]
                assert "최근 정상 패킷 수신" in notifications[coordinator.recovery_notification_id]["message"]
                await coordinator.async_stop()
                await coordinator.async_stop()
                assert sensor.extra_state_attributes["inspection_state"] == "stopped"
                assert coordinator.recovery_notification_id not in notifications
                connection.assert_not_awaited()
            print("real coordinator lifecycle: start grace, actual stop, notice close, preserved journal, "
                  "restart grace, valid receive, repeated stop, zero network calls: passed")
        finally:
            await coordinator.async_stop()
            await hass.async_stop()


async def startup_history_case() -> None:
    """Historical device notice must not masquerade as current shared inspection."""
    with tempfile.TemporaryDirectory(prefix="ew11-startup-history-") as config_dir:
        hass = HomeAssistant(config_dir)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(domain=DOMAIN, title="History test", data={}, options={},
                            source="user", version=1, minor_version=1, unique_id="history",
                            discovery_keys=MappingProxyType({}), subentries_data=None)
        hass.config_entries._entries[entry.entry_id] = entry
        coordinator = Ksx4506Coordinator(hass, {
            "host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0,
        }, entry=entry)
        clock = [0.0]
        try:
            with patch("custom_components.ksx4506_ew11.device_alerts.monotonic", lambda: clock[0]), \
                 patch("custom_components.ksx4506_ew11.device_alerts.time",
                       SimpleNamespace(time=lambda: 1000 + clock[0])):
                alerts = DeviceAlerts(coordinator, entry.entry_id)
                alerts.link_problem = "repeated_transport_failure"
                alerts.last_link_notice_at = 700
                alerts.previous = {"synthetic_device": "이전 미확인 제어 기록"}
                labels = {"synthetic_device": "합성 기기"}
                alerts._notify(alerts.previous.copy(), labels, coordinator.link_inspection)
                notices = pn._async_get_or_create_notifications(hass)
                historical = notices[coordinator.recovery_notification_id]
                assert historical["title"] == "EW11 확인 필요 · 1개 기기"
                assert "이전 통신 장애 · 시작 후 재확인 중" in historical["message"]
                assert alerts.last_link_notice_at == 700
                clock[0] = 200
                inspection = LinkInspectionPolicy(started=0).evaluate({
                    "running": True, "seconds_since_valid_rx": None,
                    "transport_failures_since_rx": 3, "seconds_since_transport_fault": 190,
                    "connect_attempts_since_transport_fault": 2,
                }, now=clock[0], failed_endpoints=0)
                assert inspection["inspection_needed"]
                alerts._notify(alerts.previous.copy(), labels, inspection)
                current = notices[coordinator.recovery_notification_id]
                assert current is not historical
                assert current["title"] == "EW11·네트워크 점검 필요"
                alerts._notify(alerts.previous.copy(), labels, inspection)
                assert notices[coordinator.recovery_notification_id] is current
                await coordinator.async_stop()
                assert coordinator.recovery_notification_id not in notices
            print("startup history: saved device notice differs from current shared inspection, "
                  "new evidence updates unchanged membership, unchanged current notice suppressed: passed")
        finally:
            await hass.async_stop()


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(lifecycle_case())
    asyncio.run(startup_history_case())
