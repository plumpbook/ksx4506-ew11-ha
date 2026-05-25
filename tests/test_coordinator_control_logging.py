from pathlib import Path
import asyncio
import logging
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402


def _install_homeassistant_stubs():
    homeassistant = types.ModuleType("homeassistant")

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    core.HomeAssistant = HomeAssistant

    helpers = types.ModuleType("homeassistant.helpers")

    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_send = lambda *args, **kwargs: None

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __init__(self, *args, **kwargs):
            pass

        def __class_getitem__(cls, item):
            return cls

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


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
    _install_homeassistant_stubs()
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
    _install_homeassistant_stubs()
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
