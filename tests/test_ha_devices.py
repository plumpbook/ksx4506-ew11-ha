from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402


common_entrance = load_integration_module("devices.common_entrance")
gas = load_integration_module("devices.gas")
entrance = load_integration_module("devices.entrance")
lighting = load_integration_module("devices.lighting")
meter = load_integration_module("devices.meter")
outlet = load_integration_module("devices.outlet")
thermostat = load_integration_module("devices.thermostat")


def test_lighting_decodes_state_byte():
    assert lighting.decode_light_state_byte(0xA3) == {
        "on": True,
        "dimmable": True,
        "brightness_step": 10,
    }


def test_gas_helpers_build_standard_frames_and_decode_status():
    assert gas.build_gas_close_request(0x01).to_bytes() == bytes.fromhex(
        "F7 12 01 41 01 01 A5 F2"
    )
    assert gas.build_gas_buzzer_stop_request(0x05).to_bytes() == bytes.fromhex(
        "F7 12 05 41 01 02 A2 F4"
    )
    assert gas.build_gas_close_payload() == b"\x01"

    closed = gas.decode_gas_state(bytes.fromhex("00 02"))
    opened_with_leak = gas.decode_gas_state(bytes.fromhex("00 11"))

    assert closed["on"] is False
    assert closed["closed"] is True
    assert opened_with_leak["on"] is True
    assert opened_with_leak["leak"] is True


def test_common_entrance_decodes_call_event_and_builds_open_request():
    assert common_entrance.build_common_entrance_open_request().to_bytes() == bytes.fromhex(
        "F7 40 02 22 00 97 F2"
    )

    call = common_entrance.decode_common_entrance_state(
        bytes.fromhex("62 02 00 00 00 00"),
        command_type=0x10,
    )
    status = common_entrance.decode_common_entrance_state(
        bytes.fromhex("00 00"),
        command_type=0x82,
    )

    assert call["event"] == "call_detected"
    assert call["call_detected"] is True
    assert call["call_type"] == 0x62
    assert call["line"] == 0x02

    assert status["event"] == "status_response"
    assert status["error_code"] == 0x00
    assert status["status_byte"] == 0x00


def test_common_entrance_formats_readable_packet_log():
    message = common_entrance.format_common_entrance_packet_log(
        0x02,
        0x10,
        bytes.fromhex("62 02 00 00 00 00"),
        direction="RX",
    )

    assert "Common entrance RX packet" in message
    assert "source=0x40" in message
    assert "unit=0x02" in message
    assert "command=0x10" in message
    assert "event=call_detected" in message
    assert "call_detected=true" in message
    assert "call_type=0x62" in message
    assert "line=0x02" in message
    assert "payload_len=6" in message
    assert "620200000000" not in message
    assert "F740021006620200000000C376" not in message.replace(" ", "").upper()


def test_entrance_panel_decodes_observed_status_bits():
    idle = entrance.decode_entrance_panel_state(bytes.fromhex("00 04 00"))
    elevator = entrance.decode_entrance_panel_state(bytes.fromhex("00 24 00"))
    batch = entrance.decode_entrance_panel_state(bytes.fromhex("00 00 00"))
    auxiliary = entrance.decode_entrance_panel_state(bytes.fromhex("00 06 00"))

    assert idle["status_byte"] == 0x04
    assert idle["batch_idle_marker"] is True
    assert idle["all_lights_off_active"] is False
    assert idle["elevator_call_active"] is False

    assert elevator["elevator_call_active"] is True
    assert elevator["elevator_down_active"] is True

    assert batch["all_lights_off_active"] is True
    assert auxiliary["auxiliary_input_active"] is True


def test_entrance_panel_decodes_elevator_event_packets():
    call_ack = entrance.decode_entrance_panel_state(
        bytes.fromhex("10"),
        command_type=0x43,
    )
    arrived = entrance.decode_entrance_panel_state(
        bytes.fromhex("80"),
        command_type=0x43,
    )
    unknown = entrance.decode_entrance_panel_state(
        bytes.fromhex("55"),
        command_type=0x43,
    )

    assert call_ack["last_panel_event"] == "elevator_call_ack"
    assert call_ack["last_elevator_event"] == "elevator_call_ack"
    assert call_ack["elevator_status"] == "calling"
    assert call_ack["last_panel_event_payload"] == "10"

    assert arrived["last_panel_event"] == "elevator_arrived"
    assert arrived["last_elevator_event"] == "elevator_arrived"
    assert arrived["elevator_status"] == "arrived"
    assert arrived["last_panel_event_payload"] == "80"

    assert unknown["last_panel_event"] == "unknown_event"
    assert unknown["last_panel_event_payload"] == "55"


def test_outlet_helpers_build_standard_frames_and_decode_status():
    assert outlet.build_outlet_control_request(0x01, turn_on=True).to_bytes() == bytes.fromhex(
        "F7 39 01 41 01 11 9E 22"
    )
    assert outlet.build_outlet_control_request(0x1F, turn_on=True, channel=2).to_bytes() == bytes.fromhex(
        "F7 39 1F 41 02 00 11 83 26"
    )
    assert outlet.build_generic_switch_payload(turn_on=True) == b"\x01"
    assert outlet.build_generic_switch_payload(turn_on=False) == b"\x00"

    state = outlet.decode_outlet_state(bytes.fromhex("00 91 36 78"), unit=0x0F)
    assert state["on"] is True
    assert state["power_w"] == 1367.8
    assert state["auto_cut"] is True

    group = outlet.decode_outlet_state(
        bytes.fromhex("00 80 00 10 10 00 20 90 00 30"),
        unit=0x0F,
    )
    assert group["channel_count"] == 3
    assert group["on"] is True
    assert group["channels"][1]["on"] is True


def test_meter_helpers_build_standard_frames_and_decode_values():
    assert meter.build_meter_status_request(0x03).to_bytes() == bytes.fromhex(
        "F7 30 03 01 00 C5 F0"
    )
    assert meter.build_meter_characteristic_request().to_bytes() == bytes.fromhex(
        "F7 30 0F 0F 00 C7 0C"
    )

    water = meter.decode_meter_state(
        bytes.fromhex("00 00 12 34 12 34 56"),
        sub_id=0x01,
        command_type=0x81,
    )
    electricity = meter.decode_meter_state(
        bytes.fromhex("00 00 06 55 00 34 81 67"),
        sub_id=0x03,
        command_type=0x81,
    )
    characteristic = meter.decode_meter_state(
        bytes.fromhex("00 07"),
        sub_id=0x0F,
        command_type=0x8F,
    )

    assert water["meter"] == "water"
    assert water["instant"] == 1.234
    assert water["total"] == 12345.6
    assert water["unit"] == "m3"
    assert electricity["instant"] == 655
    assert electricity["total"] == 3481.67
    assert electricity["unit"] == "kWh"
    assert characteristic["enabled_meters"] == ["water", "gas", "electricity"]

    whole = meter.iter_meter_states(
        bytes.fromhex(
            "00"
            " 00 12 34 12 34 56"
            " 00 00 45 00 01 23"
        ),
        sub_id=0x0F,
        command_type=0x81,
    )
    assert [(sub_id, state["meter"]) for sub_id, state in whole] == [
        (0x01, "water"),
        (0x02, "gas"),
    ]


def test_thermostat_helpers_build_standard_frames_and_decode_state():
    assert thermostat.build_thermostat_status_request().to_bytes() == bytes.fromhex(
        "F7 36 1F 01 00 DF 2C"
    )
    assert thermostat.build_thermostat_temperature_request(0x11, temperature=25).to_bytes() == bytes.fromhex(
        "F7 36 11 44 01 19 8C 28"
    )
    assert thermostat.build_generic_temperature_payload(22) == b"\x16"
    assert thermostat.encode_thermostat_temperature(25) == 0x19
    with pytest.raises(ValueError, match="whole degree"):
        thermostat.encode_thermostat_temperature(25.5)

    group_state = thermostat.decode_thermostat_state(
        bytes.fromhex("00 03 00 00 00 17 17 18 18"),
        sub_id=0x1F,
    )
    channel_state = thermostat.decode_thermostat_state(
        bytes.fromhex("00 03 00 00 00 17 17 18 18"),
        sub_id=0x11,
    )

    assert group_state["target_temp"] == 24
    assert group_state["current_temp"] == 24
    assert group_state["on"] is True
    assert len(group_state["zones"]) == 2
    assert channel_state["target_temp"] == 23
    assert channel_state["current_temp"] == 23
