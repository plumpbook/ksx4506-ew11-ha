from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeRegistry:
    def __init__(self, dev):
        self.devices = {dev.key: dev}


class _FakeCoordinator:
    def __init__(self, dev):
        self.registry = _FakeRegistry(dev)


def test_outlet_power_sensor_exposes_decoded_watts():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    sensor = load_integration_module("sensor")

    dev = discovery.DeviceState(
        key="3911_switch",
        addr=0x39,
        sub_id=0x11,
        kind="switch",
        state={
            "on": True,
            "power_w": 10.2,
            "status_sub_id": 0x1F,
            "status_channel": 1,
            "control_sub_id": 0x11,
        },
    )
    coordinator = _FakeCoordinator(dev)

    entities = sensor._sensor_entities_for_device(coordinator, dev)

    assert len(entities) == 1
    ent = entities[0]
    assert isinstance(ent, sensor.KsxOutletPowerSensor)
    assert ent._attr_unique_id == "ksx4506_3911_switch_power"
    assert ent._attr_device_info["identifiers"] == {("ksx4506_ew11", "3911_switch")}
    assert ent.native_value == 10.2
    assert ent._attr_device_class == "power"
    assert ent._attr_native_unit_of_measurement == "W"
    assert ent._attr_state_class == "measurement"
