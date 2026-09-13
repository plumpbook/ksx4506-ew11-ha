"""Exercise real HA registries, storage and notifications without network/device IO."""
import asyncio  # noqa: ANYIO_OK - isolated Home Assistant runtime
from datetime import datetime, timezone
import tempfile
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.components import persistent_notification as pn
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from custom_components.ksx4506_ew11.const import DOMAIN
from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11.device_alerts import DeviceAlerts
from custom_components.ksx4506_ew11.device_vitality import DeviceVitalityMonitor
from custom_components.ksx4506_ew11.discovery import DeviceState
from custom_components.ksx4506_ew11.hub_recovery import HubRecovery
from custom_components.ksx4506_ew11.recovery import CommandStatus
from custom_components.ksx4506_ew11.protocol_types import KsFrame


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ew11-alert-runtime-") as config_dir:
        hass = HomeAssistant(config_dir)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(domain=DOMAIN, title="Test bridge", data={}, options={},
                            source="user", version=1, minor_version=1, unique_id="alerts",
                            discovery_keys=MappingProxyType({}), subentries_data=None)
        # Add registry context without setting up the integration or opening a socket.
        hass.config_entries._entries[entry.entry_id] = entry
        await ar.async_load(hass)
        await dr.async_load(hass)
        await er.async_load(hass)
        devices, entities, areas = dr.async_get(hass), er.async_get(hass), ar.async_get(hass)
        room = areas.async_create("거실")
        kitchen = areas.async_create("주방")
        coordinator = Ksx4506Coordinator(hass, {
            "host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0,
        }, entry=entry)
        clock = [1000.0]
        coordinator.device_vitality = DeviceVitalityMonitor(
            now=lambda: datetime.fromtimestamp(clock[0], timezone.utc),
        )
        definitions = (
            ("0E11_light_1", 14, 17, "light", "조명1"),
            ("0E11_light_3", 14, 17, "light", "조명3"),
            ("6001_sensor", 96, 1, "sensor", "환경 센서"),
            ("3911_switch", 57, 17, "switch", "콘센트"),
            ("361F_climate", 54, 31, "climate", "난방"),
            ("0E15_light_1", 14, 21, "light", "과거 기기"),
        )
        entity_ids: dict[str, str] = {}
        for key, addr, sub_id, kind, name in definitions:
            coordinator.registry.devices[key] = DeviceState(
                key=key, addr=addr, sub_id=sub_id, channel=None, kind=kind,
                state={"zones": [{"channel": 1}, {"channel": 2}]} if kind == "climate" else {},
            )
            members = [f"{key}_ch1", f"{key}_ch2"] if kind == "climate" else [key]
            for index, member in enumerate(members):
                device = devices.async_get_or_create(
                    config_entry_id=entry.entry_id, identifiers={(DOMAIN, member)}, name=name,
                )
                devices.async_update_device(device.id, area_id=room.id)
                entity = entities.async_get_or_create(
                    kind, DOMAIN, f"ksx4506_{member}", config_entry=entry, device_id=device.id,
                )
                if index == 1:
                    entities.async_update_entity(entity.entity_id, area_id=kitchen.id, name="주방 난방")
                entity_ids[member] = entity.entity_id

        def response(addr: int, sub_id: int) -> None:
            coordinator.device_vitality.observe(KsFrame(addr, 0x81, b"", 0, b"", sub_id))

        for addr, sub_id in {(d[1], d[2]) for d in definitions[:-1]}:
            for _ in range(3):
                response(addr, sub_id)
        power = AsyncMock(return_value=True)
        coordinator._power_cycle = power
        service_calls: list[str] = []
        hass.services.async_register("switch", "turn_off", lambda call: service_calls.append("off"))
        hass.services.async_register("switch", "turn_on", lambda call: service_calls.append("on"))
        try:
            with patch("custom_components.ksx4506_ew11.device_alerts.time",
                       SimpleNamespace(time=lambda: clock[0])):
                alerts = DeviceAlerts(coordinator, entry.entry_id)
                await alerts.async_load()
                watchdog = HubRecovery(coordinator)
                watchdog.alerts = alerts
                notifications = pn._async_get_or_create_notifications(hass)
                targets = [(14, 17), (96, 1), (57, 17), (54, 31)]
                with patch.object(coordinator, "async_request_f7_state_until", AsyncMock(return_value=None)) as probe, \
                     patch.object(coordinator, "_known_state_request_targets", return_value=targets):
                    await watchdog.tick()
                    assert not notifications
                    for stamp in (1180, 1210, 1240):
                        clock[0] = stamp
                        await watchdog.tick()
                    assert probe.await_count == 12, (probe.await_args_list, alerts.policy.known)
                    assert len(notifications) == 1
                    notification = notifications[coordinator.recovery_notification_id]
                    assert "6개 기기" in (notification["title"] or "")
                    assert "거실 · 조명3" in notification["message"]
                    assert "주방 · 주방 난방" in notification["message"]
                    assert "과거 기기" not in notification["message"]
                    assert "자동 재시작은 하지 않았습니다" in notification["message"]
                    await watchdog.tick()
                    assert notifications[coordinator.recovery_notification_id] is notification

                    clock[0] = 1241
                    response(14, 17)
                    await watchdog.tick()
                    assert "4개 기기" in (notifications[coordinator.recovery_notification_id]["title"] or "")
                    failed = CommandStatus((14, 17), lambda frame: False,
                                           state="failed", reason="state_not_confirmed")
                    coordinator.recovery.status["0E11_light_3"] = failed
                    await watchdog.tick()
                    assert "5개 기기" in (notifications[coordinator.recovery_notification_id]["title"] or "")
                    failed.state = "pending"
                    await watchdog.tick()
                    assert "5개 기기" in (notifications[coordinator.recovery_notification_id]["title"] or "")
                    failed.state = "failed"
                    failed.reason = "superseded_or_stopped"
                    await watchdog.tick()
                    assert "5개 기기" in (notifications[coordinator.recovery_notification_id]["title"] or "")
                    failed.state = "healthy"
                    response(96, 1)
                    response(57, 17)
                    response(54, 31)
                    await watchdog.tick()
                    assert not alerts.previous
                    assert "재확인" in notifications[coordinator.recovery_notification_id]["message"]

                    # Disabled entries leave monitoring; that is not a physical recovery.
                    failed.state = "failed"
                    failed.reason = "state_not_confirmed"
                    await watchdog.tick()
                    entities.async_update_entity(entity_ids["0E11_light_3"], disabled_by=er.RegistryEntryDisabler.USER)
                    await watchdog.tick()
                    message = notifications[coordinator.recovery_notification_id]["message"]
                    assert "복구 판정 아님" in message
                    assert "응답/제어 상태 재확인" not in message
                    await alerts.async_save()
                    reloaded = DeviceAlerts(coordinator, entry.entry_id)
                    await reloaded.async_load()
                    assert reloaded.policy.known == alerts.policy.known
                    assert reloaded.policy.scan(alerts._endpoints(alerts._labels()), now=clock[0]).alerts == ()
                    pn.async_dismiss(hass, coordinator.recovery_notification_id)
                    await watchdog.tick()
                    assert not notifications
                    # A busy user transaction does not count as another missed reply.
                    clock[0] = 1500
                    before = probe.await_count
                    async with coordinator._transaction_lock:
                        await watchdog.tick()
                    assert probe.await_count == before
                    # An unresolved command survives reload; unrelated fresh packets
                    # cannot turn the previous requested result into a success.
                    coordinator.recovery.status["361F_climate_ch2"] = CommandStatus(
                        (54, 31), lambda frame: False, state="failed", reason="state_not_confirmed",
                    )
                    await watchdog.tick()
                    coordinator.recovery.status.clear()
                    pn.async_dismiss(hass, coordinator.recovery_notification_id)
                    reload_with_failure = DeviceAlerts(coordinator, entry.entry_id)
                    await reload_with_failure.async_load()
                    clock[0] = 1501
                    response(54, 31)
                    await reload_with_failure.async_tick()
                    assert "361F_climate_ch2" in reload_with_failure.previous
                    assert len(notifications) == 1
                    coordinator.recovery.status["361F_climate_ch2"] = CommandStatus(
                        (54, 31), lambda frame: True, state="healthy",
                    )
                    await reload_with_failure.async_tick()
                    assert "361F_climate_ch2" not in reload_with_failure.previous
                    power.assert_not_awaited()
                    assert not service_calls
                # A transient store read error must not kill monitoring or overwrite
                # the old journal. Cancellation after a successful load saves once.
                adapter = SimpleNamespace(
                    async_load=AsyncMock(side_effect=[OSError("test read failure"), None]),
                    async_save=AsyncMock(), async_tick=AsyncMock(),
                )
                with patch("custom_components.ksx4506_ew11.device_alerts.DeviceAlerts", return_value=adapter), \
                     patch("custom_components.ksx4506_ew11.hub_recovery.asyncio.sleep",
                           AsyncMock(side_effect=[None, None, asyncio.CancelledError()])):
                    try:
                        await HubRecovery(coordinator).run()
                    except asyncio.CancelledError:
                        pass
                assert adapter.async_load.await_count == 2
                adapter.async_tick.assert_awaited_once()
                adapter.async_save.assert_awaited_once()
            print("real HA alerts: six devices, grouped zones, areas, ghosts, recovery, "
                  "deduplication, disable, reload, dismissal, busy bus, no power: passed")
        finally:
            await hass.async_stop()


if __name__ == "__main__":
    asyncio.run(main())
