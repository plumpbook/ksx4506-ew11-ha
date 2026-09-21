"""Real HA storage, services, registries and TCP; no physical bridge is used."""
import asyncio  # noqa: ANYIO_OK - isolated Home Assistant runtime
import socket
import tempfile
import time
from types import MappingProxyType
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification as pn
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util.file import WriteError

from custom_components.ksx4506_ew11.const import DOMAIN, SIGNAL_DEVICE_ADDED
from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11.discovery_setup import (
    DATA_KEY, async_prepare_discovery, async_stop_discovery, start_discovery,
)
from custom_components.ksx4506_ew11.registry_bootstrap import async_restore_registry_devices_from_ha
from custom_components.ksx4506_ew11.diagnostics import async_get_config_entry_diagnostics
from custom_components.ksx4506_ew11.protocol import Ksx4506Codec


async def main() -> None:
    commands: list[int] = []
    done = asyncio.Event()
    ignore_probes = False

    async def wallpad(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        codec = Ksx4506Codec()
        try:
            while data := await reader.read(1024):
                for frame in codec.feed(data):
                    commands.append(frame.cmd)
                    if not ignore_probes:
                        state = b"\x00\x01\x00" if frame.sub_id == 79 else b"\x00\x01"
                        writer.write(codec.build_f7(frame.addr, frame.sub_id, 129, state))
                        await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            done.set()

    server = await asyncio.start_server(wallpad, "localhost", 0, family=socket.AF_INET)
    host, port = server.sockets[0].getsockname()[:2]
    with tempfile.TemporaryDirectory(prefix="ew11-discovery-") as directory:
        hass = HomeAssistant(directory)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(domain=DOMAIN, title="Test bridge", data={"host": host}, options={},
                            source="user", version=1, minor_version=1, unique_id="discovery",
                            discovery_keys=MappingProxyType({}), subentries_data=None)
        hass.config_entries._entries[entry.entry_id] = entry
        await dr.async_load(hass)
        await er.async_load(hass)
        devices, entities = dr.async_get(hass), er.async_get(hass)
        for channel in (1, 2, 3):
            key = f"0E11_light_{channel}"
            device = devices.async_get_or_create(config_entry_id=entry.entry_id,
                                                 identifiers={(DOMAIN, key)}, name=f"Existing {channel}")
            devices.async_update_device(device.id, name_by_user=f"Confirmed {channel}")
            entities.async_get_or_create("light", DOMAIN, f"ksx4506_{key}",
                                         config_entry=entry, device_id=device.id)
        unverified = devices.async_get_or_create(config_entry_id=entry.entry_id,
                                                  identifiers={(DOMAIN, "0E9F_light_1")}, name="Unverified")
        before = set(devices.devices)
        coordinator = Ksx4506Coordinator(hass, {
            "host": host, "port": port, "timeout": 0.1, "retry": 0, "max_attempts": 1,
        }, entry=entry)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        await async_prepare_discovery(hass, entry, coordinator)
        runtime = hass.data[DATA_KEY][entry.entry_id]
        clock = [time.time() - 3600]
        runtime.guard.now = lambda: clock[0]
        runtime.guard.evidence.now = lambda: clock[0]
        await async_restore_registry_devices_from_ha(hass, entry, coordinator.registry)
        added: list[str] = []
        unsub = async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, added.append)
        try:
            await coordinator._client.start()
            # A burst produces pending evidence but no device additions.
            for _ in range(10):
                await coordinator.async_request_f7_state_until(14, 79, max_attempts=1)
            assert "0E/4F" in runtime.guard.pending
            assert not added
            await coordinator.async_request_f7_state_until(14, 19, max_attempts=1)
            await runtime.async_tick()
            assert runtime.guard.pending["0E/13"].probes == 1
            clock[0] += 600
            await runtime.async_tick()
            assert runtime.guard.pending["0E/13"].probes == 2
            clock[0] += 60
            await coordinator.async_request_f7_state_until(14, 19, max_attempts=1)
            await hass.async_block_till_done()
            assert added == ["0E13_light_1"], added
            # The grouped response remains untrusted even while other devices work.
            assert "0E4F_light_1" not in coordinator.registry.devices
            notifications = pn._async_get_or_create_notifications(hass)
            assert runtime.notification_id in notifications
            # A timeout never removes previously registered devices.
            ignore_probes = True
            await coordinator.async_probe_known_device_states(delay=0, interval=0.01, max_attempts=1)
            assert before == set(devices.devices)
            assert all(f"0E11_light_{c}" in coordinator.registry.devices for c in (1, 2, 3))
            ignore_probes = False
            # A failed approval save cannot allow a subsequent packet to register.
            with patch.object(type(runtime.store), "_write_prepared_data", side_effect=WriteError("disk full")):
                try:
                    await hass.services.async_call(DOMAIN, "review_discovery", {
                        "entry_id": entry.entry_id, "endpoint": "0E/4F", "approve": True,
                    }, blocking=True)
                except OSError:
                    pass
                else:
                    raise AssertionError("Expected evidence storage failure")
            assert runtime.guard.verification_enabled is False
            await coordinator.async_request_f7_state_until(14, 79, max_attempts=1)
            assert "0E4F_light_1" not in coordinator.registry.devices
            # Review is a real HA service, scoped to a current candidate.
            await hass.services.async_call(DOMAIN, "review_discovery", {
                "entry_id": entry.entry_id, "endpoint": "0E/4F", "approve": False,
            }, blocking=True)
            assert "0E/4F" in runtime.guard.blocked_until
            diagnostics = await async_get_config_entry_diagnostics(hass, entry)
            guard_report = diagnostics["discovery_guard"]
            assert guard_report["registered_devices_auto_delete"] is False
            assert "raw_hex" not in repr(guard_report)
            assert [r["device_id"] for r in guard_report["registered_review"]] == [unverified.id]
            # Persist, close, reload: evidence and block remain; progress does not.
            await async_stop_discovery(hass, entry)
            await async_prepare_discovery(hass, entry, coordinator)
            reloaded = hass.data[DATA_KEY][entry.entry_id]
            assert not reloaded.guard.pending
            assert "0E/4F" in reloaded.guard.blocked_until
            assert any(e.action == "admitted_by_probe" for e in reloaded.guard.evidence.events)
            assert any(e.raw_hex for e in reloaded.guard.evidence.events)
            start_discovery(hass, entry)
            assert reloaded.task is not None
            assert set(commands) == {1}, commands
            assert before == set(devices.devices)
        finally:
            unsub()
            await coordinator.async_stop()
            await async_stop_discovery(hass, entry)
            await asyncio.wait_for(done.wait(), 2)
            await hass.async_stop()
            server.close()
            await server.wait_closed()
        print("HA discovery admission, read-only TCP probes, services, storage and lifecycle passed")


if __name__ == "__main__":
    asyncio.run(main())
