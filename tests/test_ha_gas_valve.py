from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402


def _install_homeassistant_stubs():
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")

    valve = types.ModuleType("homeassistant.components.valve")

    class ValveDeviceClass:
        GAS = "gas"

    class ValveEntityFeature:
        OPEN = 1
        CLOSE = 2
        SET_POSITION = 4
        STOP = 8

    class ValveEntity:
        pass

    valve.ValveDeviceClass = ValveDeviceClass
    valve.ValveEntity = ValveEntity
    valve.ValveEntityFeature = ValveEntityFeature

    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")

    class BinarySensorDeviceClass:
        GAS = "gas"
        RUNNING = "running"

    class BinarySensorEntity:
        pass

    binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
    binary_sensor.BinarySensorEntity = BinarySensorEntity

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
    sys.modules["homeassistant.components.valve"] = valve
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor
    sys.modules["homeassistant.config_entries"] = config_entries
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
        self.sent = []

    async def async_send_f7_command(self, dev_id, sub_id, cmd, payload, *, guard=False):
        self.sent.append((dev_id, sub_id, cmd, payload, guard))
        return True


def test_gas_valve_is_close_only_and_reports_open_closed():
    _install_homeassistant_stubs()
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

    assert ent._attr_supported_features == valve.ValveEntityFeature.CLOSE
    assert "async_open_valve" not in valve.KsxGasValve.__dict__
    assert ent.is_closed is False
    assert ent.is_closing is False

    dev.state.update({"open": False, "closed": True})
    assert ent.is_closed is True

    asyncio.run(ent.async_close_valve())

    assert coordinator.sent == [(0x12, 0x01, 0x41, b"\x01", True)]


def test_gas_binary_sensors_expose_leak_and_moving_flags():
    _install_homeassistant_stubs()
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
