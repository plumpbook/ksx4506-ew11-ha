"""KS X 4506 integrated metering helpers."""

from __future__ import annotations

from typing import Any

from ..frame import Frame

METER_DEVICE_ID = 0x30
STATUS_REQUEST = 0x01
STATUS_RESPONSE = 0x81
CHARACTERISTIC_REQUEST = 0x0F
CHARACTERISTIC_RESPONSE = 0x8F

METER_TYPE_SUB_IDS = {
    "all": 0x0F,
    "water": 0x01,
    "gas": 0x02,
    "electricity": 0x03,
    "hot-water": 0x04,
    "hot_water": 0x04,
    "heat": 0x05,
}

METER_TYPES = {
    0x01: ("water", "m3", 3, 1),
    0x02: ("gas", "m3", 3, 1),
    0x03: ("electricity", "W", 0, 1),
    0x04: ("hot_water", "m3", 3, 1),
    0x05: ("heat", "MW", 3, 2),
}

METER_WHOLE_ORDER = [0x01, 0x02, 0x03, 0x04, 0x05]
VALID_METER_SUB_IDS = frozenset(METER_TYPE_SUB_IDS.values())


def build_meter_status_request(sub_id: int) -> Frame:
    _validate_meter_sub_id(sub_id)
    return Frame(
        device_id=METER_DEVICE_ID,
        sub_id=sub_id,
        command_type=STATUS_REQUEST,
    )


def build_meter_characteristic_request(sub_id: int = 0x0F) -> Frame:
    _validate_meter_sub_id(sub_id)
    return Frame(
        device_id=METER_DEVICE_ID,
        sub_id=sub_id,
        command_type=CHARACTERISTIC_REQUEST,
    )


def decode_meter_state(
    payload: bytes,
    *,
    sub_id: int,
    command_type: int,
) -> dict[str, Any]:
    if command_type == CHARACTERISTIC_RESPONSE:
        return _decode_meter_characteristic(payload)

    if command_type != STATUS_RESPONSE:
        return {}

    if sub_id in METER_TYPES and len(payload) in (6, 7, 8):
        has_error = len(payload) in (7, 8)
        meter_data = payload[1:] if has_error else payload
        return _decode_meter_values(
            sub_id,
            meter_data,
            error=payload[0] if has_error else None,
        )

    return _decode_meter_chunks(payload)


def iter_meter_states(
    payload: bytes,
    *,
    sub_id: int,
    command_type: int,
) -> list[tuple[int, dict[str, Any]]]:
    """Return individual meter states carried by a status response."""

    if command_type != STATUS_RESPONSE:
        return []

    if sub_id in METER_TYPES and len(payload) in (6, 7, 8):
        decoded = decode_meter_state(
            payload,
            sub_id=sub_id,
            command_type=command_type,
        )
        return [(sub_id, decoded)] if decoded.get("meter") else []

    error, meter_data = _meter_data_without_error(payload)
    if not meter_data or len(meter_data) % 6:
        return []

    states: list[tuple[int, dict[str, Any]]] = []
    for index in range(0, len(meter_data), 6):
        meter_index = index // 6
        if meter_index >= len(METER_WHOLE_ORDER):
            break
        meter_sub_id = METER_WHOLE_ORDER[meter_index]
        decoded = _decode_meter_values(
            meter_sub_id,
            meter_data[index : index + 6],
            error=error if index == 0 else None,
        )
        if decoded:
            states.append((meter_sub_id, decoded))
    return states


def meter_sub_id_for_type(meter_type: str) -> int:
    try:
        return METER_TYPE_SUB_IDS[meter_type]
    except KeyError as exc:
        choices = ", ".join(sorted(METER_TYPE_SUB_IDS))
        raise ValueError(f"meter --type must be one of: {choices}") from exc


def _decode_meter_characteristic(payload: bytes) -> dict[str, Any]:
    if len(payload) != 2:
        return {}

    flags = payload[1]
    enabled = [
        METER_TYPES[sub_id][0]
        for sub_id in METER_WHOLE_ORDER
        if flags & (1 << (sub_id - 1))
    ]
    return {
        "error": payload[0],
        "enabled_meters": enabled,
    }


def _decode_meter_chunks(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {}

    error, meter_data = _meter_data_without_error(payload)

    if not meter_data or len(meter_data) % 6:
        return {}

    meters: dict[str, Any] = {}
    for index in range(0, len(meter_data), 6):
        meter_index = index // 6
        if meter_index >= len(METER_WHOLE_ORDER):
            break
        decoded = _decode_meter_values(
            METER_WHOLE_ORDER[meter_index],
            meter_data[index : index + 6],
            error=None,
        )
        meters[decoded["meter"]] = decoded

    state: dict[str, Any] = {"meters": meters}
    if error is not None:
        state["error"] = error
    return state


def _meter_data_without_error(payload: bytes) -> tuple[int | None, bytes]:
    if len(payload) % 6 and (len(payload) - 1) % 6 == 0:
        return payload[0], payload[1:]
    return None, payload


def _decode_meter_values(
    meter_sub_id: int,
    data: bytes,
    *,
    error: int | None,
) -> dict[str, Any]:
    if meter_sub_id not in METER_TYPES or len(data) < 6:
        return {}

    meter_name, instant_unit, instant_decimals, total_decimals = METER_TYPES[meter_sub_id]
    instant = _decode_bcd_decimal(data[:3], decimal_places=instant_decimals)
    total_data = data[3:]
    if meter_sub_id == 0x03 and len(total_data) == 4:
        total_decimals = 2
    total = _decode_bcd_decimal(total_data, decimal_places=total_decimals)
    total_unit = "kWh" if meter_sub_id == 0x03 else instant_unit

    state: dict[str, Any] = {
        "meter": meter_name,
        "instant": instant,
        "instant_unit": instant_unit,
        "total": total,
        "total_unit": total_unit,
        "value": total,
        "unit": total_unit,
    }
    if error is not None:
        state["error"] = error
    return state


def _decode_bcd_decimal(data: bytes, *, decimal_places: int) -> float:
    digits = []
    for byte in data:
        digits.append(str(byte >> 4))
        digits.append(str(byte & 0x0F))

    value = int("".join(digits))
    return value / (10 ** decimal_places)


def _validate_meter_sub_id(sub_id: int) -> None:
    if not isinstance(sub_id, int):
        raise TypeError("meter sub_id must be an int")
    if sub_id not in VALID_METER_SUB_IDS:
        raise ValueError("meter sub_id must be one of 0x01..0x05 or 0x0F")
