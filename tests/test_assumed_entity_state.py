from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeRegistry:
    def __init__(self, dev):
        self.devices = {dev.key: dev}


class _FakeCoordinator:
    def __init__(self, dev):
        self.registry = _FakeRegistry(dev)
        self.ew11_state = "receiving"

    def ew11_health_report(self):
        return {
            "state": self.ew11_state,
            "connected": True,
            "running": True,
            "last_error": None,
        }


def test_light_uses_assumed_off_when_last_state_is_not_usable():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    light = load_integration_module("light")

    dev = discovery.DeviceState(
        key="0E11_light_1",
        addr=0x0E,
        sub_id=0x11,
        channel=1,
        kind="light",
        state={
            "dimmable": False,
            "status_sub_id": 0x11,
            "control_sub_id": 0x11,
            "control_channel": 1,
        },
    )
    entity = light.KsxLight(_FakeCoordinator(dev), dev)
    entity._last_state = types.SimpleNamespace(state="unknown")

    asyncio.run(entity.async_added_to_hass())

    assert entity.is_on is False
    assert entity.assumed_state is True
    assert dev.state["on"] is False


def test_light_assumed_state_stops_after_real_status_packet():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    light = load_integration_module("light")

    reg = discovery.DeviceRegistry()
    restored = reg.restore_device_from_key("0E11_light_1")
    assert restored is not None
    dev, _ = restored
    entity = light.KsxLight(_FakeCoordinator(dev), dev)
    entity._last_state = types.SimpleNamespace(state="unknown")
    asyncio.run(entity.async_added_to_hass())

    reg.upsert_from_frame(
        0x0E,
        0x11,
        0x81,
        bytes.fromhex("00 01 00 00"),
        "f70e118104000100006d08",
    )

    assert entity.is_on is True
    assert entity.assumed_state is False


def test_outlet_switch_uses_assumed_off_when_last_state_is_not_usable():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    switch = load_integration_module("switch")

    dev = discovery.DeviceState(
        key="3911_switch",
        addr=0x39,
        sub_id=0x11,
        kind="switch",
        state={
            "status_sub_id": 0x1F,
            "status_channel": 1,
            "control_sub_id": 0x11,
        },
    )
    entity = switch._switch_entities_for_device(_FakeCoordinator(dev), dev)[0]
    entity._last_state = types.SimpleNamespace(state="unknown")

    asyncio.run(entity.async_added_to_hass())

    assert entity.is_on is False
    assert entity.assumed_state is True
    assert dev.state["on"] is False


def test_outlet_switch_assumed_state_stops_after_real_status_packet():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    switch = load_integration_module("switch")

    reg = discovery.DeviceRegistry()
    restored = reg.restore_device_from_key("3911_switch")
    assert restored is not None
    dev, _ = restored
    entity = switch._switch_entities_for_device(_FakeCoordinator(dev), dev)[0]
    entity._last_state = types.SimpleNamespace(state="unknown")
    asyncio.run(entity.async_added_to_hass())

    reg.upsert_from_frame(
        0x39,
        0x1F,
        0x81,
        bytes.fromhex("00 10 00 79 00 00 26"),
        "f7...",
    )

    assert entity.is_on is True
    assert entity.assumed_state is False
