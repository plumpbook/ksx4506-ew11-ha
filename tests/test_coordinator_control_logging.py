from pathlib import Path
import asyncio
import logging
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeCoordinator:
    def __init__(self, matched_frame, *, match_after_attempts=2):
        self.max_attempts = 3
        self._frame_waiters = []
        self.sent = []
        self._matched_frame = matched_frame
        self._match_after_attempts = match_after_attempts

    async def async_send_f7_command(self, dev_id, sub_id, cmd, payload, *, guard=False):
        self.sent.append((dev_id, sub_id, cmd, payload, guard))
        if len(self.sent) < self._match_after_attempts:
            return True

        for matcher, fut in tuple(self._frame_waiters):
            if not fut.done() and matcher(self._matched_frame):
                fut.set_result(self._matched_frame)
        return True


def test_send_f7_command_until_logs_control_attempts(caplog):
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    matched = protocol_module.KsFrame(
        addr=0x39,
        sub_id=0x11,
        cmd=0xC1,
        payload=b"\x00\x01",
        checksum=0,
        raw=bytes.fromhex("f73911c10200011d22"),
    )
    fake = _FakeCoordinator(matched)
    fake.async_send_f7_command_until = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
        fake,
    )

    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11.coordinator")

    result = asyncio.run(
        fake.async_send_f7_command_until(
            0x39,
            0x11,
            0x41,
            b"\x11",
            lambda frame: frame.addr == 0x39
            and frame.sub_id == 0x11
            and frame.cmd == 0xC1,
        )
    )

    assert result is matched
    assert len(fake.sent) == 2
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "TX F7 control attempt dev=0x39 sub=0x11 cmd=0x41 attempt=1/3" in messages
    assert "TX F7 control wait timeout dev=0x39 sub=0x11 cmd=0x41 attempt=1/3" in messages
    assert "TX F7 control matched dev=0x39 sub=0x11 cmd=0x41 attempt=2/3" in messages


def test_meter_startup_probe_requests_whole_and_individual_meter_states():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")

    class FakeCoordinator:
        def __init__(self):
            self.state_requests = []

        async def async_request_f7_state(self, dev_id, sub_id):
            self.state_requests.append((dev_id, sub_id))
            return True

    fake = FakeCoordinator()
    fake.async_probe_meter_states = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_probe_meter_states,
        fake,
    )

    asyncio.run(fake.async_probe_meter_states(delay=0, interval=0))

    assert fake.state_requests == [
        (0x30, 0x0F),
        (0x30, 0x01),
        (0x30, 0x02),
        (0x30, 0x03),
        (0x30, 0x04),
        (0x30, 0x05),
    ]


def test_known_device_startup_probe_retries_until_status_response():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    discovery_module = load_integration_module("discovery")
    protocol_module = load_integration_module("protocol")

    matched = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0x11,
        cmd=0x81,
        payload=b"\x00\x01\x00\x00",
        checksum=0,
        raw=bytes.fromhex("f70e11810400010000a5f6"),
    )
    fake = _FakeCoordinator(matched)
    fake.registry = discovery_module.DeviceRegistry()
    fake.registry.restore_device_from_key("0E11_light_1")
    fake.async_send_f7_command_until = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
        fake,
    )
    fake.async_request_f7_state_until = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_request_f7_state_until,
        fake,
    )
    fake.async_probe_known_device_states = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_probe_known_device_states,
        fake,
    )
    fake._known_state_request_targets = types.MethodType(
        coordinator_module.Ksx4506Coordinator._known_state_request_targets,
        fake,
    )

    asyncio.run(fake.async_probe_known_device_states(delay=0, interval=0))

    assert fake.sent == [
        (0x0E, 0x11, 0x01, b"", False),
        (0x0E, 0x11, 0x01, b"", False),
    ]


def test_coordinator_publishes_registry_state_on_ew11_health_change():
    asyncio.run(_assert_coordinator_publishes_registry_state_on_ew11_health_change())


async def _assert_coordinator_publishes_registry_state_on_ew11_health_change():
    install_homeassistant_stubs()
    const_module = load_integration_module("const")
    coordinator_module = load_integration_module("coordinator")

    coordinator = coordinator_module.Ksx4506Coordinator(
        object(),
        {
            const_module.CONF_HOST: "ew11.example.invalid",
            const_module.CONF_PORT: 8899,
            const_module.CONF_TIMEOUT: 3.0,
            const_module.CONF_RETRY: 2,
            const_module.CONF_STX: const_module.DEFAULT_STX,
            const_module.CONF_ETX: const_module.DEFAULT_ETX,
            const_module.CONF_CHECKSUM: const_module.DEFAULT_CHECKSUM,
        },
    )
    coordinator.registry.devices["light:sample"] = types.SimpleNamespace(
        state={"is_on": True}
    )

    coordinator._client._mark_connected()

    assert coordinator.data == {"light:sample": {"is_on": True}}


def test_common_entrance_call_info_log_does_not_expose_raw_packet(caplog):
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    class FakeCoordinator:
        def __init__(self):
            self.registry = coordinator_module.DeviceRegistry()
            self.hass = object()
            self.data = None

        def async_set_updated_data(self, data):
            self.data = data

        def _notify_frame_waiters(self, frame):
            return None

    fake = FakeCoordinator()
    fake._on_frame = types.MethodType(coordinator_module.Ksx4506Coordinator._on_frame, fake)
    fake._publish_registry_state = types.MethodType(
        coordinator_module.Ksx4506Coordinator._publish_registry_state,
        fake,
    )
    frame = protocol_module.KsFrame(
        addr=0x40,
        sub_id=0x02,
        cmd=0x10,
        payload=bytes.fromhex("62 02 00 00 00 00"),
        checksum=0,
        raw=bytes.fromhex("F7 40 02 10 06 62 02 00 00 00 00 C3 76"),
    )

    caplog.set_level(logging.INFO, logger="custom_components.ksx4506_ew11.coordinator")

    asyncio.run(fake._on_frame(frame))

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "Common entrance call event sub=0x02 detected=True" in messages
    assert "F740021006620200000000C376" not in messages.upper()
    assert "620200000000" not in messages
