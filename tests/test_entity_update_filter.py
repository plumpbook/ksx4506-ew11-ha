from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeRegistry:
    def __init__(self, dev):
        self.devices = {dev.key: dev}


class _FakeCoordinator:
    def __init__(self, dev, changed_device_keys):
        self.registry = _FakeRegistry(dev)
        self._last_changed_device_keys = changed_device_keys

    def ew11_health_report(self):
        return {
            "state": "receiving",
            "connected": True,
            "running": True,
            "last_error": None,
        }


def _light_entity(changed_device_keys):
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
            "on": False,
            "dimmable": False,
            "status_sub_id": 0x11,
            "control_sub_id": 0x11,
            "control_channel": 1,
        },
    )
    coordinator = _FakeCoordinator(dev, changed_device_keys)
    entity = light.KsxLight(coordinator, dev)
    writes = []
    entity.async_write_ha_state = lambda: writes.append(entity.dev_key)
    return entity, writes


def test_ksx_entity_skips_coordinator_update_when_other_device_changed():
    entity, writes = _light_entity(frozenset({"3911_switch"}))

    entity._handle_coordinator_update()

    assert writes == []


def test_ksx_entity_writes_coordinator_update_when_own_device_changed():
    entity, writes = _light_entity(frozenset({"0E11_light_1"}))

    entity._handle_coordinator_update()

    assert writes == ["0E11_light_1"]


def test_ksx_entity_writes_coordinator_update_when_change_scope_is_global():
    entity, writes = _light_entity(None)

    entity._handle_coordinator_update()

    assert writes == ["0E11_light_1"]
