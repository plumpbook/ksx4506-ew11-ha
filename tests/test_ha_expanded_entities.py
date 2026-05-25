from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402


def _install_homeassistant_stubs():
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")

    climate = types.ModuleType("homeassistant.components.climate")

    class ClimateEntity:
        pass

    class ClimateEntityFeature:
        TARGET_TEMPERATURE = 1

    climate.ClimateEntity = ClimateEntity
    climate.ClimateEntityFeature = ClimateEntityFeature

    climate_const = types.ModuleType("homeassistant.components.climate.const")

    class HVACMode:
        OFF = "off"
        HEAT = "heat"

    class HVACAction:
        OFF = "off"
        IDLE = "idle"
        HEATING = "heating"

    climate_const.HVACAction = HVACAction
    climate_const.HVACMode = HVACMode

    sensor = types.ModuleType("homeassistant.components.sensor")

    class SensorDeviceClass:
        ENERGY = "energy"
        POWER = "power"

    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    class SensorEntity:
        pass

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = SensorEntity
    sensor.SensorStateClass = SensorStateClass

    switch = types.ModuleType("homeassistant.components.switch")

    class SwitchEntity:
        pass

    switch.SwitchEntity = SwitchEntity

    light = types.ModuleType("homeassistant.components.light")

    class ColorMode:
        BRIGHTNESS = "brightness"
        ONOFF = "onoff"

    class LightEntity:
        pass

    light.ColorMode = ColorMode
    light.LightEntity = LightEntity

    number = types.ModuleType("homeassistant.components.number")

    class NumberDeviceClass:
        TEMPERATURE = "temperature"

    class NumberEntity:
        pass

    number.NumberDeviceClass = NumberDeviceClass
    number.NumberEntity = NumberEntity

    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")

    class BinarySensorDeviceClass:
        GAS = "gas"
        RUNNING = "running"

    class BinarySensorEntity:
        pass

    binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
    binary_sensor.BinarySensorEntity = BinarySensorEntity

    const = types.ModuleType("homeassistant.const")

    class UnitOfEnergy:
        KILO_WATT_HOUR = "kWh"

    class UnitOfPower:
        WATT = "W"

    class UnitOfTemperature:
        CELSIUS = "C"

    const.UnitOfEnergy = UnitOfEnergy
    const.UnitOfPower = UnitOfPower
    const.UnitOfTemperature = UnitOfTemperature

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

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor
    sys.modules["homeassistant.components.climate"] = climate
    sys.modules["homeassistant.components.climate.const"] = climate_const
    sys.modules["homeassistant.components.light"] = light
    sys.modules["homeassistant.components.number"] = number
    sys.modules["homeassistant.components.sensor"] = sensor
    sys.modules["homeassistant.components.switch"] = switch
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
        self.sent = []
        self.sent_f7 = []
        self.state_requests = []

    async def async_send_command(self, addr, cmd, payload, *, guard=False):
        self.sent.append((addr, cmd, payload, guard))
        return True

    async def async_send_f7_command(self, dev_id, sub_id, cmd, payload, *, guard=False):
        self.sent_f7.append((dev_id, sub_id, cmd, payload, guard))
        return True

    async def async_request_f7_state(self, dev_id, sub_id):
        self.state_requests.append((dev_id, sub_id))
        return True


def test_light_control_uses_standard_group_channel_sub_id():
    _install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    light = load_integration_module("light")

    group1 = discovery.DeviceState(
        key="0E1F_light_1",
        addr=0x0E,
        sub_id=0x1F,
        channel=1,
        kind="light",
        state={
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x11,
            "control_sub_id": 0x11,
        },
    )
    coordinator = _FakeCoordinator(group1)
    entity = light.KsxLight(coordinator, group1)

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x11, 0x41, b"\x00", False),
    ]
    assert coordinator.state_requests == [(0x0E, 0x11)]

    group1_ch2 = discovery.DeviceState(
        key="0E1F_light_2",
        addr=0x0E,
        sub_id=0x1F,
        channel=2,
        kind="light",
        state={
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x12,
            "control_sub_id": 0x12,
        },
    )
    coordinator = _FakeCoordinator(group1_ch2)
    entity = light.KsxLight(coordinator, group1_ch2)

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x12, 0x41, b"\x00", False),
    ]
    assert coordinator.state_requests == [(0x0E, 0x12)]

    group2_ch1 = discovery.DeviceState(
        key="0E2F_light_1",
        addr=0x0E,
        sub_id=0x2F,
        channel=1,
        kind="light",
        state={
            "on": False,
            "dimmable": False,
            "status_sub_id": 0x21,
            "control_sub_id": 0x21,
        },
    )
    coordinator = _FakeCoordinator(group2_ch1)
    entity = light.KsxLight(coordinator, group2_ch1)

    asyncio.run(entity.async_turn_on())

    assert coordinator.sent_f7 == [
        (0x0E, 0x21, 0x41, b"\x01", False),
    ]
    assert coordinator.state_requests == [(0x0E, 0x21)]

    group3 = discovery.DeviceState(
        key="0E3F_light_1",
        addr=0x0E,
        sub_id=0x3F,
        channel=1,
        kind="light",
        state={
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x31,
            "control_sub_id": 0x31,
        },
    )
    coordinator = _FakeCoordinator(group3)
    entity = light.KsxLight(coordinator, group3)

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x31, 0x41, b"\x00", False),
    ]
    assert coordinator.state_requests == [(0x0E, 0x31)]


def test_thermostat_group_payload_exposes_zone_climates_and_controls_zone():
    _install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    climate = load_integration_module("climate")
    number = load_integration_module("number")
    switch = load_integration_module("switch")

    dev = discovery.DeviceState(
        key="361F_climate",
        addr=0x36,
        sub_id=0x1F,
        kind="climate",
        state={
            "zones": [
                {"channel": 1, "on": True, "target_temp": 23, "current_temp": 23},
                {"channel": 2, "on": True, "target_temp": 24, "current_temp": 24},
            ],
            "on": True,
            "target_temp": 24,
            "current_temp": 24,
        },
    )
    coordinator = _FakeCoordinator(dev)

    entities = climate._climate_entities_for_device(coordinator, dev)
    zone1 = entities[0]

    assert len(entities) == 2
    assert zone1._attr_unique_id == "ksx4506_361F_climate_ch1"
    assert zone1._attr_name == "Climate"
    assert zone1._attr_device_info["identifiers"] == {("ksx4506_ew11", "361F_climate_ch1")}
    assert zone1._attr_device_info["name"] == "KSX 36-1F ch1"
    assert zone1.target_temperature == 23
    assert zone1.current_temperature == 23
    assert zone1.hvac_mode == "heat"
    assert zone1.hvac_action == "idle"

    asyncio.run(zone1.async_set_temperature(temperature=25.5))
    asyncio.run(zone1.async_set_hvac_mode("off"))

    assert coordinator.sent_f7 == [
        (0x36, 0x11, 0x44, b"\x99", False),
        (0x36, 0x11, 0x43, b"\x00", False),
    ]

    heat_switch = switch._switch_entities_for_device(coordinator, dev)[0]
    target_number = number._number_entities_for_device(coordinator, dev)[0]

    assert heat_switch._attr_unique_id == "ksx4506_361F_climate_ch1_heat"
    assert heat_switch._attr_device_info["identifiers"] == {
        ("ksx4506_ew11", "361F_climate_ch1")
    }
    assert heat_switch.is_on is True
    assert target_number._attr_unique_id == "ksx4506_361F_climate_ch1_target_temperature"
    assert target_number.native_value == 23

    asyncio.run(heat_switch.async_turn_off())
    asyncio.run(target_number.async_set_native_value(21.5))

    assert coordinator.sent_f7[-2:] == [
        (0x36, 0x11, 0x43, b"\x00", False),
        (0x36, 0x11, 0x44, b"\x95", False),
    ]


def test_meter_and_outlet_sensor_entities_are_expanded():
    _install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    sensor = load_integration_module("sensor")

    meter = discovery.DeviceState(
        key="3003_sensor",
        addr=0x30,
        sub_id=0x03,
        kind="sensor",
        state={
            "meter": "electricity",
            "instant": 687.0,
            "instant_unit": "W",
            "total": 3506.37,
            "total_unit": "kWh",
            "value": 3506.37,
            "unit": "kWh",
        },
    )
    meter_entities = sensor._sensor_entities_for_device(_FakeCoordinator(meter), meter)

    assert [ent._attr_unique_id for ent in meter_entities] == [
        "ksx4506_3003_sensor_instant",
        "ksx4506_3003_sensor_total",
    ]
    assert meter_entities[0].native_value == 687.0
    assert meter_entities[0].device_class == "power"
    assert meter_entities[1].native_value == 3506.37
    assert meter_entities[1].device_class == "energy"

    outlet = discovery.DeviceState(
        key="391F_switch",
        addr=0x39,
        sub_id=0x1F,
        kind="switch",
        state={
            "power_w": 10.5,
            "channels": [
                {"channel": 1, "power_w": 8.0},
                {"channel": 2, "power_w": 2.5},
            ],
            "thresholds": [
                {"channel": 1, "threshold_w": 13.1},
                {"channel": 2, "threshold_w": 20.0},
            ],
        },
    )
    outlet_entities = sensor._sensor_entities_for_device(_FakeCoordinator(outlet), outlet)
    ids = [ent._attr_unique_id for ent in outlet_entities]

    assert "ksx4506_391F_switch_ch1_power" in ids
    assert "ksx4506_391F_switch_ch2_power" in ids
    assert "ksx4506_391F_switch_ch3_power" in ids
    assert "ksx4506_391F_switch_ch2_threshold" in ids
    aggregate_power = next(
        ent
        for ent in outlet_entities
        if ent._attr_unique_id == "ksx4506_391F_switch_ch1_power"
    )
    assert aggregate_power.native_value == 10.5
    channel_power = next(
        ent
        for ent in outlet_entities
        if ent._attr_unique_id == "ksx4506_391F_switch_ch2_power"
    )
    assert channel_power.native_value == 8.0
    assert channel_power._attr_device_info["identifiers"] == {
        ("ksx4506_ew11", "391F_switch_ch2")
    }
    assert channel_power._attr_name == "Power"


def test_outlet_channel_switch_controls_specific_channel():
    _install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    switch = load_integration_module("switch")

    dev = discovery.DeviceState(
        key="391F_switch",
        addr=0x39,
        sub_id=0x1F,
        kind="switch",
        state={
            "channels": [
                {"channel": 1, "on": False},
                {"channel": 2, "on": True},
            ],
        },
    )
    coordinator = _FakeCoordinator(dev)

    entities = switch._switch_entities_for_device(coordinator, dev)
    channel1 = entities[0]
    channel3 = entities[2]

    assert len(entities) == 3
    assert channel1._attr_unique_id == "ksx4506_391F_switch_ch1"
    assert channel1._attr_name == "Switch"
    assert channel1._attr_device_info["identifiers"] == {("ksx4506_ew11", "391F_switch_ch1")}
    assert channel1._attr_device_info["name"] == "KSX 39-1F ch1"
    assert channel1.is_on is False
    assert channel3._attr_unique_id == "ksx4506_391F_switch_ch3"
    assert channel3._attr_device_info["identifiers"] == {("ksx4506_ew11", "391F_switch_ch3")}
    assert channel3.is_on is True

    asyncio.run(channel1.async_turn_on())
    asyncio.run(channel3.async_turn_off())

    assert coordinator.sent == [
        (0x39, 0x21, b"\x01", False),
    ]
    assert coordinator.sent_f7 == [
        (0x39, 0x1F, 0x41, bytes.fromhex("00 10"), False),
    ]


def test_outlet_and_entrance_binary_sensors_are_expanded():
    _install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    binary_sensor = load_integration_module("binary_sensor")

    entrance = discovery.DeviceState(
        key="3301_entrance_panel",
        addr=0x33,
        sub_id=0x01,
        kind="entrance_panel",
        state={
            "all_lights_off_active": True,
            "elevator_call_active": False,
            "elevator_down_active": True,
            "auxiliary_input_active": False,
        },
    )
    entrance_entities = binary_sensor._binary_sensors_for_device(
        _FakeCoordinator(entrance),
        entrance,
    )

    assert len(entrance_entities) == 4
    assert entrance_entities[0]._attr_unique_id == "ksx4506_3301_entrance_panel_all_lights_off_active"
    assert entrance_entities[0].is_on is True

    outlet = discovery.DeviceState(
        key="391F_switch",
        addr=0x39,
        sub_id=0x1F,
        kind="switch",
        state={
            "auto_cut": True,
            "under_threshold": False,
            "overload": False,
            "channels": [
                {"channel": 1, "auto_cut": False, "under_threshold": True, "overload": False}
            ],
        },
    )
    outlet_entities = binary_sensor._binary_sensors_for_device(_FakeCoordinator(outlet), outlet)
    ids = [ent._attr_unique_id for ent in outlet_entities]

    assert "ksx4506_391F_switch_ch1_auto_cut" in ids
    assert "ksx4506_391F_switch_ch2_under_threshold" in ids
    channel_entity = next(
        ent
        for ent in outlet_entities
        if ent._attr_unique_id == "ksx4506_391F_switch_ch2_under_threshold"
    )
    assert channel_entity._attr_device_info["identifiers"] == {
        ("ksx4506_ew11", "391F_switch_ch2")
    }
    assert channel_entity._attr_name == "Under Threshold"
