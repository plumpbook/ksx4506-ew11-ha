"""Run with the real installed HA runtime in a process isolated from test stubs.

Run from the repository root: .venv/bin/python -m tests.runtime_recovery_smoke
"""
import asyncio  # noqa: ANYIO_OK - real Home Assistant event loop
import socket
import tempfile
from types import SimpleNamespace

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11.discovery import DeviceState
from custom_components.ksx4506_ew11.light import KsxLight
from custom_components.ksx4506_ew11.protocol import Ksx4506Codec
from custom_components.ksx4506_ew11.power_recovery import async_configure_power_recovery


async def main() -> None:
    controls = 0
    done = asyncio.Event()

    async def wallpad(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal controls
        codec = Ksx4506Codec()
        try:
            while data := await reader.read(1024):
                for frame in codec.feed(data):
                    if frame.addr != 14:
                        continue
                    if frame.cmd == 0x41:
                        controls += 1
                        writer.write(codec.build_f7(14, 17, 0xC1, frame.payload))
                    else:
                        payload = bytes([0, 0, 0, int(controls < 2)])
                        writer.write(codec.build_f7(14, 17, 0x81, payload))
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            done.set()

    server = await asyncio.start_server(wallpad, "localhost", 0, family=socket.AF_INET)
    host, port = server.sockets[0].getsockname()[:2]
    with tempfile.TemporaryDirectory(prefix="ew11-runtime-test-") as config_dir:
        hass = HomeAssistant(config_dir)
        coordinator = Ksx4506Coordinator(hass, {
            "host": host, "port": port, "timeout": 0.1, "retry": 0, "max_attempts": 1,
        })
        coordinator.recovery.delays = (0, 0)
        dev = DeviceState(
            key="0E11_light_3", addr=14, sub_id=17, channel=3, kind="light",
            state={"on": True, "status_sub_id": 17, "control_sub_id": 17, "control_channel": 3},
        )
        coordinator.registry.devices[dev.key] = dev
        entity = KsxLight(coordinator, dev)
        try:
            await coordinator.async_start()
            await asyncio.wait_for(entity.async_turn_off(), 8)
            assert controls == 2
            assert entity.extra_state_attributes["control_status"] == "healthy"
            assert not entity.assumed_state
            assert not coordinator._frame_waiters
            assert coordinator._client.health_report()["state"] == "receiving"
            await er.async_load(hass)
            registry = er.async_get(hass)
            power_entity = registry.async_get_or_create("switch", "recovery_test", "power")
            hass.states.async_set(power_entity.entity_id, "on")
            switched = []

            async def switch_service(call: ServiceCall) -> None:
                state = "on" if call.service == "turn_on" else "off"
                switched.append(state)
                hass.states.async_set(power_entity.entity_id, state)

            hass.services.async_register("switch", "turn_on", switch_service)
            hass.services.async_register("switch", "turn_off", switch_service)
            entry = SimpleNamespace(entry_id="runtime_test", data={}, options={
                "recovery_power_switch": power_entity.entity_id,
            })
            await async_configure_power_recovery(hass, entry, coordinator)
            assert coordinator._power_cycle is not None
            assert await coordinator._power_cycle()
            await async_configure_power_recovery(hass, entry, coordinator)
            assert not await coordinator._power_cycle()
            assert switched == ["off", "on"]
        finally:
            await coordinator.async_stop()
            await asyncio.wait_for(done.wait(), 2)
            await hass.async_stop()
            server.close()
            await server.wait_closed()
        assert coordinator._recovery_task is None
        assert not coordinator.recovery._tasks
        print("real HA runtime + loopback recovery + persisted power cooldown + unload: passed")


if __name__ == "__main__":
    asyncio.run(main())
