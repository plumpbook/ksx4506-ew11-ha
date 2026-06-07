from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeRegistry:
    def __init__(self, dev):
        self.devices = {dev.key: dev}


class _FakeCoordinator:
    def __init__(self, dev, *, matched_frame=None, matched_frames=None, max_attempts=10):
        self.registry = _FakeRegistry(dev)
        self.sent = []
        self.sent_f7 = []
        self.state_requests = []
        self.matched_frames = list(matched_frames or [])
        if matched_frame is not None:
            self.matched_frames.append(matched_frame)
        self.max_attempts = max_attempts

    async def async_send_command(self, addr, cmd, payload, *, guard=False):
        self.sent.append((addr, cmd, payload, guard))
        return True

    async def async_send_f7_command(self, dev_id, sub_id, cmd, payload, *, guard=False):
        self.sent_f7.append((dev_id, sub_id, cmd, payload, guard))
        return True

    async def async_send_f7_command_until(
        self,
        dev_id,
        sub_id,
        cmd,
        payload,
        matcher,
        *,
        max_attempts=None,
        interval=0.1,
        guard=False,
    ):
        for _ in range(max_attempts or self.max_attempts):
            self.sent_f7.append((dev_id, sub_id, cmd, payload, guard))
            for index, frame in enumerate(self.matched_frames):
                if matcher(frame):
                    return self.matched_frames.pop(index)
        return None

    async def async_request_f7_state(self, dev_id, sub_id):
        self.state_requests.append((dev_id, sub_id))
        return True


def test_light_control_uses_suroup_module_channel_payload():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    light = load_integration_module("light")

    group1 = discovery.DeviceState(
        key="0E11_light_1",
        addr=0x0E,
        sub_id=0x11,
        channel=1,
        kind="light",
        state={
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x11,
            "control_sub_id": 0x11,
            "control_channel": 1,
        },
    )
    coordinator = _FakeCoordinator(group1)
    entity = light.KsxLight(coordinator, group1)
    assert entity._attr_device_info["name"] == "Light 0E-11 Channel 1"

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x11, 0x41, b"\x01\x00\x00", False),
    ] * 10
    assert coordinator.state_requests == [(0x0E, 0x11)]

    group1_ch2 = discovery.DeviceState(
        key="0E11_light_2",
        addr=0x0E,
        sub_id=0x11,
        channel=2,
        kind="light",
        state={
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x11,
            "control_sub_id": 0x11,
            "control_channel": 2,
        },
    )
    coordinator = _FakeCoordinator(group1_ch2)
    entity = light.KsxLight(coordinator, group1_ch2)
    assert entity._attr_device_info["name"] == "Light 0E-11 Channel 2"

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x11, 0x41, b"\x02\x00\x00", False),
    ] * 10
    assert coordinator.state_requests == [(0x0E, 0x11)]

    group2_ch1 = discovery.DeviceState(
        key="0E12_light_1",
        addr=0x0E,
        sub_id=0x12,
        channel=1,
        kind="light",
        state={
            "on": False,
            "dimmable": False,
            "status_sub_id": 0x12,
            "control_sub_id": 0x12,
            "control_channel": 1,
        },
    )
    coordinator = _FakeCoordinator(group2_ch1)
    entity = light.KsxLight(coordinator, group2_ch1)

    asyncio.run(entity.async_turn_on())

    assert coordinator.sent_f7 == [
        (0x0E, 0x12, 0x41, b"\x01\x01\x00", False),
    ] * 10
    assert coordinator.state_requests == [(0x0E, 0x12)]

    group3 = discovery.DeviceState(
        key="0E13_light_1",
        addr=0x0E,
        sub_id=0x13,
        channel=1,
        kind="light",
        state={
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x13,
            "control_sub_id": 0x13,
            "control_channel": 1,
        },
    )
    coordinator = _FakeCoordinator(group3)
    entity = light.KsxLight(coordinator, group3)

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x13, 0x41, b"\x01\x00\x00", False),
    ] * 10
    assert coordinator.state_requests == [(0x0E, 0x13)]


def test_light_control_stops_when_status_response_matches():
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
    matched = types.SimpleNamespace(
        addr=0x0E,
        sub_id=0x11,
        cmd=0x81,
        payload=b"\x00\x01\x00\x00",
    )
    coordinator = _FakeCoordinator(dev, matched_frame=matched)
    entity = light.KsxLight(coordinator, dev)

    asyncio.run(entity.async_turn_on())

    assert coordinator.sent_f7 == [(0x0E, 0x11, 0x41, b"\x01\x01\x00", False)]
    assert coordinator.state_requests == []


def test_light_control_uses_configured_max_attempts():
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
            "on": True,
            "dimmable": False,
            "status_sub_id": 0x11,
            "control_sub_id": 0x11,
            "control_channel": 1,
        },
    )
    coordinator = _FakeCoordinator(dev, max_attempts=3)
    entity = light.KsxLight(coordinator, dev)

    asyncio.run(entity.async_turn_off())

    assert coordinator.sent_f7 == [
        (0x0E, 0x11, 0x41, b"\x01\x00\x00", False),
    ] * 3
    assert coordinator.state_requests == [(0x0E, 0x11)]


def test_thermostat_group_payload_exposes_zone_climates_and_controls_zone():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    climate = load_integration_module("climate")
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
    coordinator = _FakeCoordinator(
        dev,
        matched_frames=[
            types.SimpleNamespace(
                addr=0x36,
                sub_id=0x1F,
                cmd=0x81,
                payload=bytes.fromhex("00 03 00 00 00 19 17 18 18"),
            ),
            types.SimpleNamespace(
                addr=0x36,
                sub_id=0x11,
                cmd=0xC3,
                payload=bytes.fromhex("00 00 01 00 00 17 17"),
            ),
        ],
    )

    entities = climate._climate_entities_for_device(coordinator, dev)
    zone1 = entities[0]

    assert len(entities) == 2
    assert zone1._attr_unique_id == "ksx4506_361F_climate_ch1"
    assert zone1._attr_name == "Climate"
    assert zone1._attr_target_temperature_step == 1.0
    assert zone1._attr_device_info["identifiers"] == {("ksx4506_ew11", "361F_climate_ch1")}
    assert zone1._attr_device_info["name"] == "Thermostat 36-1F Zone 1"
    assert zone1.target_temperature == 23
    assert zone1.current_temperature == 23
    assert zone1.hvac_mode == "heat"

    asyncio.run(zone1.async_set_temperature(temperature=25))
    asyncio.run(zone1.async_set_hvac_mode("off"))

    assert coordinator.sent_f7 == [
        (0x36, 0x11, 0x44, b"\x19", False),
        (0x36, 0x11, 0x43, b"\x00", False),
    ]
    assert coordinator.state_requests == [(0x36, 0x1F)]

    heat_switch = switch._switch_entities_for_device(coordinator, dev)[0]

    assert heat_switch._attr_unique_id == "ksx4506_361F_climate_ch1_heat"
    assert heat_switch._attr_device_info["identifiers"] == {
        ("ksx4506_ew11", "361F_climate_ch1")
    }
    assert heat_switch.is_on is True

    asyncio.run(heat_switch.async_turn_off())

    assert coordinator.sent_f7[-1:] == [
        (0x36, 0x11, 0x43, b"\x00", False),
    ]
    assert coordinator.state_requests == [(0x36, 0x1F), (0x36, 0x1F)]


def test_meter_and_outlet_sensor_entities_are_expanded():
    install_homeassistant_stubs()
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
    assert meter_entities[0]._attr_device_info["identifiers"] == {
        ("ksx4506_ew11", "3003_sensor")
    }
    assert meter_entities[0]._attr_device_info["name"] == "Electric Meter 30-03"
    assert meter_entities[0]._attr_name == "Instant"
    assert meter_entities[0].native_value == 687.0
    assert meter_entities[0].device_class == "power"
    assert meter_entities[1]._attr_device_info["name"] == "Electric Meter 30-03"
    assert meter_entities[1]._attr_name == "Total"
    assert meter_entities[1].native_value == 3506.37
    assert meter_entities[1].device_class == "energy"

    outlet = discovery.DeviceState(
        key="3911_switch",
        addr=0x39,
        sub_id=0x11,
        kind="switch",
        state={
            "power_w": 10.5,
            "threshold_w": 13.1,
            "status_sub_id": 0x1F,
            "status_channel": 1,
            "control_sub_id": 0x11,
        },
    )
    outlet_entities = sensor._sensor_entities_for_device(_FakeCoordinator(outlet), outlet)
    ids = [ent._attr_unique_id for ent in outlet_entities]

    assert ids == [
        "ksx4506_3911_switch_power",
        "ksx4506_3911_switch_threshold",
    ]
    power = next(
        ent
        for ent in outlet_entities
        if ent._attr_unique_id == "ksx4506_3911_switch_power"
    )
    assert power.native_value == 10.5
    assert power._attr_device_info["identifiers"] == {("ksx4506_ew11", "3911_switch")}
    assert power._attr_device_info["name"] == "Outlet 39-11"
    assert power._attr_name == "Power"


def test_outlet_group_device_without_control_subid_is_not_exposed():
    install_homeassistant_stubs()
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

    assert entities == []


def test_outlet_individual_switch_controls_suroup_subid():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    switch = load_integration_module("switch")

    dev = discovery.DeviceState(
        key="3911_switch",
        addr=0x39,
        sub_id=0x11,
        kind="switch",
        state={
            "on": False,
            "status_sub_id": 0x1F,
            "status_channel": 1,
            "control_sub_id": 0x11,
        },
    )
    coordinator = _FakeCoordinator(dev, max_attempts=3)

    entities = switch._switch_entities_for_device(coordinator, dev)
    entity = entities[0]

    assert len(entities) == 1
    assert entity._attr_unique_id == "ksx4506_3911_switch"
    assert entity._attr_device_info["identifiers"] == {("ksx4506_ew11", "3911_switch")}
    assert entity._attr_device_info["name"] == "Outlet 39-11"

    asyncio.run(entity.async_turn_on())

    assert coordinator.sent_f7 == [(0x39, 0x11, 0x41, b"\x11", False)] * 3
    assert coordinator.state_requests == [(0x39, 0x1F)]


def test_outlet_individual_switch_stops_when_status_matches():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    switch = load_integration_module("switch")

    dev = discovery.DeviceState(
        key="3912_switch",
        addr=0x39,
        sub_id=0x12,
        kind="switch",
        state={
            "on": False,
            "status_sub_id": 0x1F,
            "status_channel": 2,
            "control_sub_id": 0x12,
        },
    )
    matched = types.SimpleNamespace(
        addr=0x39,
        sub_id=0x1F,
        cmd=0x81,
        payload=bytes.fromhex("00 00 00 00 10 00 01"),
    )
    coordinator = _FakeCoordinator(dev, matched_frame=matched)
    entity = switch._switch_entities_for_device(coordinator, dev)[0]

    asyncio.run(entity.async_turn_on())

    assert coordinator.sent_f7 == [(0x39, 0x12, 0x41, b"\x11", False)]
    assert coordinator.state_requests == []


def test_outlet_individual_switch_stops_when_control_ack_matches():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    switch = load_integration_module("switch")

    dev = discovery.DeviceState(
        key="3911_switch",
        addr=0x39,
        sub_id=0x11,
        kind="switch",
        state={
            "on": False,
            "status_sub_id": 0x1F,
            "status_channel": 1,
            "control_sub_id": 0x11,
        },
    )
    matched = types.SimpleNamespace(
        addr=0x39,
        sub_id=0x11,
        cmd=0xC1,
        payload=bytes.fromhex("00 01"),
    )
    coordinator = _FakeCoordinator(dev, matched_frame=matched)
    entity = switch._switch_entities_for_device(coordinator, dev)[0]

    asyncio.run(entity.async_turn_on())

    assert coordinator.sent_f7 == [(0x39, 0x11, 0x41, b"\x11", False)]
    assert coordinator.state_requests == [(0x39, 0x1F)]


def test_outlet_and_entrance_binary_sensors_are_expanded():
    install_homeassistant_stubs()
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
        key="3911_switch",
        addr=0x39,
        sub_id=0x11,
        kind="switch",
        state={
            "auto_cut": True,
            "under_threshold": False,
            "overload": False,
            "status_sub_id": 0x1F,
            "status_channel": 1,
            "control_sub_id": 0x11,
        },
    )
    outlet_entities = binary_sensor._binary_sensors_for_device(_FakeCoordinator(outlet), outlet)
    ids = [ent._attr_unique_id for ent in outlet_entities]

    assert ids == [
        "ksx4506_3911_switch_auto_cut",
        "ksx4506_3911_switch_under_threshold",
        "ksx4506_3911_switch_overload",
    ]
    channel_entity = next(
        ent
        for ent in outlet_entities
        if ent._attr_unique_id == "ksx4506_3911_switch_under_threshold"
    )
    assert channel_entity._attr_device_info["identifiers"] == {("ksx4506_ew11", "3911_switch")}
    assert channel_entity._attr_name == "Under Threshold"


def test_entrance_panel_elevator_status_sensor_is_expanded():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    sensor = load_integration_module("sensor")

    entrance = discovery.DeviceState(
        key="3301_entrance_panel",
        addr=0x33,
        sub_id=0x01,
        kind="entrance_panel",
        state={
            "elevator_status": "arrived",
            "last_elevator_event": "elevator_arrived",
            "last_panel_event_payload": "80",
            "last_panel_event_seq": 3,
        },
    )
    entities = sensor._sensor_entities_for_device(_FakeCoordinator(entrance), entrance)
    ids = [ent._attr_unique_id for ent in entities]

    assert ids == [
        "ksx4506_3301_entrance_panel",
        "ksx4506_3301_entrance_panel_elevator_status",
    ]
    assert entities[1].native_value == "arrived"
    assert entities[1].extra_state_attributes == {
        "last_elevator_event": "elevator_arrived",
        "last_panel_event_payload": "80",
        "last_panel_event_seq": 3,
    }
