from pathlib import Path
import asyncio
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeRegistry:
    def __init__(self, dev):
        self.devices = {dev.key: dev}


class _FakeCoordinator:
    def __init__(self, dev, *, gas_unlocked=False, matched_frames=None):
        self.registry = _FakeRegistry(dev)
        self.gas_unlocked = gas_unlocked
        self.matched_frames = list(matched_frames or [])
        self.sent = []
        self.state_requests = []

    async def async_send_f7_command_and_confirm(
        self,
        dev_id,
        sub_id,
        cmd,
        payload,
        response_matcher,
        *,
        status_sub_id,
        confirmation_matcher,
        interval,
        confirmation_interval,
        guard=False,
    ):
        _ = (interval, confirmation_interval)
        self.sent.append((dev_id, sub_id, cmd, payload, guard))
        for index, frame in enumerate(self.matched_frames):
            if response_matcher(frame):
                matched = self.matched_frames.pop(index)
                if confirmation_matcher(matched):
                    return matched
                break
        self.state_requests.append((dev_id, status_sub_id))
        for index, frame in enumerate(self.matched_frames):
            if confirmation_matcher(frame):
                return self.matched_frames.pop(index)
        return None


def test_gas_valve_reports_state_but_hides_control_while_locked():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    valve = load_integration_module("valve")

    dev = discovery.DeviceState(
        key="1201_gas_valve",
        addr=0x12,
        sub_id=0x01,
        kind="gas_valve",
        state={"open": True, "closed": False, "moving": False, "leak": False},
    )
    coordinator = _FakeCoordinator(dev)
    ent = valve.KsxGasValve(coordinator, dev)

    assert ent.supported_features == valve.ValveEntityFeature(0)
    assert "async_open_valve" not in valve.KsxGasValve.__dict__
    assert ent.is_closed is False
    assert ent.is_closing is False

    dev.state.update({"open": False, "closed": True})
    assert ent.is_closed is True

    with pytest.raises(valve.HomeAssistantError, match="locked"):
        asyncio.run(ent.async_close_valve())

    assert coordinator.sent == []


def test_gas_valve_close_requires_a_confirmed_response():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    protocol = load_integration_module("protocol")
    valve = load_integration_module("valve")

    dev = discovery.DeviceState(
        key="1201_gas_valve",
        addr=0x12,
        sub_id=0x01,
        kind="gas_valve",
        state={"open": True, "closed": False},
    )
    closed = protocol.KsFrame(
        addr=0x12,
        sub_id=0x01,
        cmd=0xC1,
        payload=b"\x00\x02",
        checksum=0,
        raw=b"",
    )
    coordinator = _FakeCoordinator(dev, gas_unlocked=True, matched_frames=[closed])
    ent = valve.KsxGasValve(coordinator, dev)

    assert ent.supported_features == valve.ValveEntityFeature.CLOSE

    asyncio.run(ent.async_close_valve())

    assert coordinator.sent == [(0x12, 0x01, 0x41, b"\x01", True)]


def test_gas_valve_close_raises_when_no_response_arrives():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    valve = load_integration_module("valve")

    dev = discovery.DeviceState(
        key="1201_gas_valve",
        addr=0x12,
        sub_id=0x01,
        kind="gas_valve",
        state={"open": True, "closed": False},
    )
    coordinator = _FakeCoordinator(dev, gas_unlocked=True)
    ent = valve.KsxGasValve(coordinator, dev)

    with pytest.raises(valve.HomeAssistantError, match="could not be confirmed"):
        asyncio.run(ent.async_close_valve())


def test_gas_valve_close_uses_status_after_nonfinal_control_ack():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    protocol = load_integration_module("protocol")
    valve = load_integration_module("valve")

    dev = discovery.DeviceState(
        key="1201_gas_valve",
        addr=0x12,
        sub_id=0x01,
        kind="gas_valve",
        state={"open": True, "closed": False},
    )
    ack = protocol.KsFrame(
        addr=0x12,
        sub_id=0x01,
        cmd=0xC1,
        payload=b"\x00\x01",
        checksum=0,
        raw=b"",
    )
    closed = protocol.KsFrame(
        addr=0x12,
        sub_id=0x01,
        cmd=0x81,
        payload=b"\x00\x02",
        checksum=0,
        raw=b"",
    )
    coordinator = _FakeCoordinator(
        dev,
        gas_unlocked=True,
        matched_frames=[ack, closed],
    )

    asyncio.run(valve.KsxGasValve(coordinator, dev).async_close_valve())

    assert coordinator.state_requests == [(0x12, 0x01)]


def test_gas_binary_sensors_expose_leak_and_moving_flags():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    binary_sensor = load_integration_module("binary_sensor")

    dev = discovery.DeviceState(
        key="1201_gas_valve",
        addr=0x12,
        sub_id=0x01,
        kind="gas_valve",
        state={"leak": True, "moving": False},
    )
    coordinator = _FakeCoordinator(dev)

    leak = binary_sensor.KsxGasLeakSensor(coordinator, dev)
    moving = binary_sensor.KsxGasValveMovingSensor(coordinator, dev)

    assert leak.is_on is True
    assert moving.is_on is False
    assert leak._attr_unique_id == "ksx4506_1201_gas_valve_leak"
    assert moving._attr_unique_id == "ksx4506_1201_gas_valve_moving"
