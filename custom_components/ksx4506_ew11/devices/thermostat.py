"""KS X 4506 thermostat helpers."""

from __future__ import annotations

from typing import Any

from ..frame import Frame

THERMOSTAT_DEVICE_ID = 0x36
STATUS_REQUEST = 0x01
STATUS_RESPONSE = 0x81
HEAT_CONTROL_REQUEST = 0x43
TEMPERATURE_CONTROL_REQUEST = 0x44
AWAY_CONTROL_REQUEST = 0x45
SCHEDULE_CONTROL_REQUEST = 0x46
HOT_WATER_CONTROL_REQUEST = 0x47
CONTROL_RESPONSE_OFFSET = 0x80

GENERIC_CLIMATE_COMMAND = 0x31
DEFAULT_THERMOSTAT_SUB_ID = 0x1F

STATE_RESPONSE_COMMANDS = {
    STATUS_RESPONSE,
    HEAT_CONTROL_REQUEST | CONTROL_RESPONSE_OFFSET,
    TEMPERATURE_CONTROL_REQUEST | CONTROL_RESPONSE_OFFSET,
    AWAY_CONTROL_REQUEST | CONTROL_RESPONSE_OFFSET,
    SCHEDULE_CONTROL_REQUEST | CONTROL_RESPONSE_OFFSET,
    HOT_WATER_CONTROL_REQUEST | CONTROL_RESPONSE_OFFSET,
}


def build_generic_temperature_payload(temperature: float) -> bytes:
    """Build the current STX fallback thermostat payload used by the HA entity."""

    return bytes([int(temperature) & 0xFF])


def build_thermostat_status_request(sub_id: int = DEFAULT_THERMOSTAT_SUB_ID) -> Frame:
    _validate_thermostat_sub_id(sub_id)
    return Frame(
        device_id=THERMOSTAT_DEVICE_ID,
        sub_id=sub_id,
        command_type=STATUS_REQUEST,
    )


def build_thermostat_heat_request(sub_id: int, *, turn_on: bool) -> Frame:
    return _build_thermostat_bool_control(
        sub_id,
        command_type=HEAT_CONTROL_REQUEST,
        turn_on=turn_on,
    )


def build_thermostat_temperature_request(sub_id: int, *, temperature: float) -> Frame:
    _validate_thermostat_sub_id(sub_id)
    return Frame(
        device_id=THERMOSTAT_DEVICE_ID,
        sub_id=sub_id,
        command_type=TEMPERATURE_CONTROL_REQUEST,
        data=bytes([encode_thermostat_temperature(temperature)]),
    )


def build_thermostat_away_request(sub_id: int, *, turn_on: bool) -> Frame:
    return _build_thermostat_bool_control(
        sub_id,
        command_type=AWAY_CONTROL_REQUEST,
        turn_on=turn_on,
    )


def build_thermostat_schedule_request(sub_id: int, *, turn_on: bool) -> Frame:
    return _build_thermostat_bool_control(
        sub_id,
        command_type=SCHEDULE_CONTROL_REQUEST,
        turn_on=turn_on,
    )


def build_thermostat_hot_water_request(sub_id: int, *, turn_on: bool) -> Frame:
    return _build_thermostat_bool_control(
        sub_id,
        command_type=HOT_WATER_CONTROL_REQUEST,
        turn_on=turn_on,
    )


def thermostat_target_sub_id(sub_id: int, channel: int | None) -> int:
    _validate_thermostat_sub_id(sub_id)
    if channel is None:
        return sub_id
    _validate_thermostat_channel(channel)
    if sub_id & 0x0F == 0x0F:
        return (sub_id & 0xF0) | (channel & 0x0F)
    return sub_id


def decode_thermostat_state(payload: bytes, *, sub_id: int | None = None) -> dict[str, Any]:
    if len(payload) >= 7 and (len(payload) - 5) % 2 == 0:
        return _decode_standard_thermostat_state(payload, sub_id=sub_id)

    if len(payload) >= 2:
        return {
            "target_temp": payload[-2],
            "current_temp": payload[-1],
        }

    return {}


def encode_thermostat_temperature(temperature: float) -> int:
    if not isinstance(temperature, (int, float)):
        raise TypeError("thermostat temperature must be a number")
    doubled = temperature * 2
    if doubled != int(doubled):
        raise ValueError("thermostat temperature must use 0.5 degree increments")
    if temperature < 0 or temperature > 127.5:
        raise ValueError("thermostat temperature must be in 0..127.5")

    whole = int(temperature)
    half = int(doubled) % 2
    return whole | (0x80 if half else 0x00)


def decode_thermostat_temperature(value: int) -> float:
    return (value & 0x7F) + (0.5 if value & 0x80 else 0.0)


def _decode_standard_thermostat_state(
    payload: bytes,
    *,
    sub_id: int | None,
) -> dict[str, Any]:
    heating = payload[1]
    away = payload[2]
    schedule = payload[3]
    hot_water = payload[4]
    thermostat_count = (len(payload) - 5) // 2

    zones = []
    for index in range(thermostat_count):
        bit = 1 << index
        zones.append(
            {
                "channel": index + 1,
                "on": bool(heating & bit),
                "away": bool(away & bit),
                "schedule": bool(schedule & bit),
                "target_temp": decode_thermostat_temperature(payload[5 + index * 2]),
                "current_temp": decode_thermostat_temperature(payload[6 + index * 2]),
            }
        )

    selected = _select_thermostat_index(thermostat_count, sub_id=sub_id)
    if selected is None:
        selected = thermostat_count - 1

    zone = zones[selected]
    return {
        "error": payload[0],
        "hot_water": bool(hot_water & 0x01),
        "zones": zones,
        "on": zone["on"],
        "away": zone["away"],
        "schedule": zone["schedule"],
        "target_temp": zone["target_temp"],
        "current_temp": zone["current_temp"],
    }


def _select_thermostat_index(count: int, *, sub_id: int | None) -> int | None:
    if count == 1:
        return 0
    if sub_id is None:
        return None

    unit = sub_id & 0x0F
    if unit != 0x0F and 1 <= unit <= count:
        return unit - 1
    return None


def _build_thermostat_bool_control(
    sub_id: int,
    *,
    command_type: int,
    turn_on: bool,
) -> Frame:
    _validate_thermostat_sub_id(sub_id)
    return Frame(
        device_id=THERMOSTAT_DEVICE_ID,
        sub_id=sub_id,
        command_type=command_type,
        data=bytes([0x01 if turn_on else 0x00]),
    )


def _validate_thermostat_sub_id(sub_id: int) -> None:
    if not isinstance(sub_id, int):
        raise TypeError("thermostat sub_id must be an int")
    if sub_id < 0x01 or sub_id > 0xEF:
        raise ValueError("thermostat sub_id must be in 0x01..0xEF")


def _validate_thermostat_channel(channel: int) -> None:
    if not isinstance(channel, int):
        raise TypeError("thermostat channel must be an int")
    if channel < 1 or channel > 0x0E:
        raise ValueError("thermostat channel must be in 1..14")
