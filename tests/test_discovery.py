from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402

_module = load_integration_module("discovery")
DeviceRegistry = _module.DeviceRegistry


def test_light_single_subid_multichannel_payload_expands_channels():
    reg = DeviceRegistry()
    # vendor variant: sub_id(0x01) + multi-channel payload [err, ch1, ch2, ch3]
    changes = reg.upsert_from_frame(0x0E, 0x01, 0x81, bytes([0x00, 0x01, 0x00, 0x01]), "f7...")

    assert len(changes) == 3
    keys = sorted(k for k in reg.devices.keys())
    assert keys == ["0E1F_light_1", "0E1F_light_2", "0E1F_light_3"]
    assert reg.devices["0E1F_light_1"].state["on"] is True
    assert reg.devices["0E1F_light_1"].state["dimmable"] is False
    assert reg.devices["0E1F_light_2"].state["on"] is False
    assert reg.devices["0E1F_light_3"].state["on"] is True


def test_light_status_byte_dimming_decode():
    reg = DeviceRegistry()
    # [err=0x00, state=0xA3] => dim step 10, dimmable, ON
    reg.upsert_from_frame(0x0E, 0x01, 0x81, bytes([0x00, 0xA3]), "f7...")
    d = reg.devices["0E1F_light_1"]
    assert d.state["on"] is True
    assert d.state["dimmable"] is True
    assert d.state["brightness_step"] == 0x0A


def test_gas_standard_status_decodes_closed_as_off():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x12, 0x01, 0x81, bytes.fromhex("00 02"), "f7...")

    d = reg.devices["1201_gas_valve"]
    assert d.state["on"] is False
    assert d.state["closed"] is True
    assert d.state["open"] is False


def test_outlet_standard_status_decodes_supply_and_power():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x39, 0x01, 0x81, bytes.fromhex("00 91 36 78"), "f7...")

    d = reg.devices["3901_switch"]
    assert d.state["on"] is True
    assert d.state["power_w"] == 1367.8
    assert d.state["auto_cut"] is True


def test_meter_status_is_sensor_with_parsed_value():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x30, 0x01, 0x81, bytes.fromhex("00 00 12 34 12 34 56"), "f7...")

    d = reg.devices["3001_sensor"]
    assert d.kind == "sensor"
    assert d.state["meter"] == "water"
    assert d.state["instant"] == 1.234
    assert d.state["value"] == 12345.6
    assert d.state["unit"] == "m3"


def test_thermostat_group_status_preserves_tail_zone_for_entity():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x36, 0x1F, 0x81, bytes.fromhex("00 03 00 00 00 17 17 18 18"), "f7...")

    d = reg.devices["361F_climate"]
    assert d.state["target_temp"] == 24
    assert d.state["current_temp"] == 24
    assert d.state["on"] is True
