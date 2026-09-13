"""Real TCP/codec/coordinator path with a deterministic simulated wallpad."""
import asyncio  # noqa: ANYIO_OK - real transport test
import socket
import types

import pytest

from ._integration_loader import load_integration_module
from .ha_stubs import install_homeassistant_stubs


@pytest.mark.parametrize("recover_on_retry", [True, False])
def test_light_state_is_confirmed_or_failure_survives_other_channel(recover_on_retry):
    asyncio.run(_scenario(recover_on_retry))


async def _scenario(recover_on_retry):
    install_homeassistant_stubs()
    module = load_integration_module("coordinator")
    light_module = load_integration_module("light")
    discovery = load_integration_module("discovery")
    codec_type = load_integration_module("protocol").Ksx4506Codec
    controls = []
    commands = []
    done = asyncio.Event()
    state = b"\x00\x00\x00\x01"

    async def wallpad(reader, writer):
        nonlocal state
        codec = codec_type()
        try:
            while data := await reader.read(1024):
                for frame in codec.feed(data):
                    commands.append(frame.cmd)
                    if frame.cmd == 0x41:
                        controls.append(frame.payload)
                        if len(controls) > 1 and recover_on_retry:
                            state = b"\x00\x00\x00\x00"
                        # ACK alone must never prove that light 3 turned off.
                        writer.write(codec.build_f7(14, 17, 0xC1, frame.payload))
                    else:
                        writer.write(codec.build_f7(14, 17, 0x81, state))
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            done.set()

    server = await asyncio.start_server(wallpad, "localhost", 0, family=socket.AF_INET)
    host, port = server.sockets[0].getsockname()[:2]
    coordinator = module.Ksx4506Coordinator(types.SimpleNamespace(), {
        "host": host, "port": port, "timeout": 0.1, "retry": 0, "max_attempts": 1,
    })
    coordinator.hass = types.SimpleNamespace()
    coordinator.recovery.delays = (0, 0)
    dev = discovery.DeviceState(
        key="0E11_light_3", addr=14, sub_id=17, channel=3, kind="light",
        state={"on": True, "status_sub_id": 17, "control_sub_id": 17, "control_channel": 3},
    )
    coordinator.registry.devices[dev.key] = dev
    entity = light_module.KsxLight(coordinator, dev)
    try:
        await coordinator._client.start()
        if recover_on_retry:
            await asyncio.wait_for(entity.async_turn_off(), 5)
            assert entity.extra_state_attributes["control_status"] == "healthy"
            assert controls == [b"\x03\x00\x00"] * 2
        else:
            with pytest.raises(light_module.HomeAssistantError):
                await asyncio.wait_for(entity.async_turn_off(), 5)
            await coordinator._on_frame(codec_type().feed(
                codec_type().build_f7(14, 17, 0x81, b"\x00\x01\x00\x01")
            )[0])
            assert entity.extra_state_attributes["control_status"] == "failed"
            assert entity.assumed_state
            assert coordinator.device_vitality_report()["state"] == "unresponsive"
            assert len(controls) == 3
        assert coordinator._client.health_report()["state"] == "receiving"
        assert commands[0:2] == [0x41, 0x01]
        assert not coordinator._frame_waiters
    finally:
        await coordinator.async_stop()
        await asyncio.wait_for(done.wait(), 2)
        server.close()
        await server.wait_closed()
