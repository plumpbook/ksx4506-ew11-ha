from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402


def _install_homeassistant_stubs():
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")

    sensor = types.ModuleType("homeassistant.components.sensor")

    class SensorDeviceClass:
        POWER = "power"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    class SensorEntity:
        pass

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = SensorEntity
    sensor.SensorStateClass = SensorStateClass

    const = types.ModuleType("homeassistant.const")

    class UnitOfPower:
        WATT = "W"

    const.UnitOfPower = UnitOfPower

    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        pass

    config_entries.ConfigEntry = ConfigEntry

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    def callback(func):
        return func

    core.HomeAssistant = HomeAssistant
    core.callback = callback

    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_connect = lambda *args, **kwargs: None
    dispatcher.async_dispatcher_send = lambda *args, **kwargs: None

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

    class DataUpdateCoordinator:
        def __init__(self, *args, **kwargs):
            pass

        def __class_getitem__(cls, item):
            return cls

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator

    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.components", components)
    sys.modules["homeassistant.components.sensor"] = sensor
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


class _FakeRegistry:
    def __init__(self, dev):
        self.devices = {dev.key: dev}


class _FakeCoordinator:
    def __init__(self, dev):
        self.registry = _FakeRegistry(dev)


def test_outlet_power_sensor_exposes_decoded_watts():
    _install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    sensor = load_integration_module("sensor")

    dev = discovery.DeviceState(
        key="391F_switch",
        addr=0x39,
        sub_id=0x1F,
        kind="switch",
        state={"on": True, "power_w": 10.2, "channel_count": 2},
    )
    coordinator = _FakeCoordinator(dev)

    entities = sensor._sensor_entities_for_device(coordinator, dev)

    assert len(entities) == 1
    ent = entities[0]
    assert isinstance(ent, sensor.KsxOutletPowerSensor)
    assert ent._attr_unique_id == "ksx4506_391F_switch_power"
    assert ent.native_value == 10.2
    assert ent._attr_device_class == "power"
    assert ent._attr_native_unit_of_measurement == "W"
    assert ent._attr_state_class == "measurement"
