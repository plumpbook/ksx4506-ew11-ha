"""KS X 4506 outlet and generic switch helpers."""

from __future__ import annotations

from typing import Any

from ..frame import Frame

OUTLET_DEVICE_ID = 0x39
STATUS_REQUEST = 0x01
STATUS_RESPONSE = 0x81
CONTROL_REQUEST = 0x41
CONTROL_RESPONSE = 0xC1

GENERIC_SWITCH_COMMAND = 0x21

CHANNEL_STATE_MASK = 0x10
AUTO_CUT_MASK = 0x20
CHANNEL_ON = 0x01
AUTO_CUT_ON = 0x02


def build_generic_switch_payload(*, turn_on: bool) -> bytes:
    """Build the current STX fallback switch payload used by the HA entity."""

    return bytes([0x01 if turn_on else 0x00])


def build_outlet_status_request(sub_id: int) -> Frame:
    _validate_outlet_sub_id(sub_id)
    return Frame(
        device_id=OUTLET_DEVICE_ID,
        sub_id=sub_id,
        command_type=STATUS_REQUEST,
    )


def build_outlet_control_request(
    sub_id: int,
    *,
    turn_on: bool,
    channel: int | None = None,
) -> Frame:
    control = CHANNEL_STATE_MASK | (CHANNEL_ON if turn_on else 0x00)
    if channel is None:
        _validate_outlet_control_sub_id(sub_id)
        data = bytes([control])
    else:
        _validate_outlet_channel_control_sub_id(sub_id)
        _validate_outlet_channel(channel)
        payload = bytearray(channel)
        payload[channel - 1] = control
        data = bytes(payload)

    return Frame(
        device_id=OUTLET_DEVICE_ID,
        sub_id=sub_id,
        command_type=CONTROL_REQUEST,
        data=data,
    )


def decode_switch_state(payload: bytes) -> dict[str, Any]:
    """Decode the current generic switch status shape."""

    if not payload:
        return {}

    state_bytes = payload[1:] if len(payload) > 1 else payload
    return {"on": any((byte & 0x0F) > 0 for byte in state_bytes)}


def decode_outlet_state(
    payload: bytes,
    *,
    unit: int | None = None,
    channel: int | None = None,
) -> dict[str, Any]:
    """Decode outlet status/control response payloads.

    Status responses carry 3 bytes per channel after the error byte. Control
    responses carry one compact status byte per channel after the error byte.
    """

    if not payload:
        return {}

    if len(payload) >= 4 and (len(payload) - 1) % 3 == 0:
        return _decode_outlet_status_payload(payload, unit=unit, channel=channel)

    if len(payload) >= 2:
        statuses = payload[1:]
        state: dict[str, Any] = {
            "error": payload[0],
            "channel_count": len(statuses),
            "channels": [
                {
                    "channel": index,
                    "on": bool(status & CHANNEL_ON),
                    "auto_cut": bool(status & AUTO_CUT_ON),
                }
                for index, status in enumerate(statuses, start=1)
            ],
        }
        selected = _select_channel_index(len(statuses), unit=unit, channel=channel)
        if selected is None:
            state["on"] = any(status & CHANNEL_ON for status in statuses)
        else:
            state["on"] = bool(statuses[selected] & CHANNEL_ON)
            state["auto_cut"] = bool(statuses[selected] & AUTO_CUT_ON)
        return state

    return decode_switch_state(payload)


def _decode_outlet_status_payload(
    payload: bytes,
    *,
    unit: int | None,
    channel: int | None,
) -> dict[str, Any]:
    chunks = [payload[index : index + 3] for index in range(1, len(payload), 3)]
    state: dict[str, Any] = {
        "error": payload[0],
        "channel_count": len(chunks),
        "channels": [
            {"channel": index, **_decode_outlet_channel(chunk)}
            for index, chunk in enumerate(chunks, start=1)
        ],
    }

    selected = _select_channel_index(len(chunks), unit=unit, channel=channel)
    if selected is None:
        state["on"] = any(chunk[0] & CHANNEL_STATE_MASK for chunk in chunks)
        state["power_w"] = sum(_decode_outlet_watts(chunk) for chunk in chunks)
    else:
        state.update(_decode_outlet_channel(chunks[selected]))

    return state


def _decode_outlet_channel(data: bytes) -> dict[str, Any]:
    status = data[0]
    return {
        "on": bool(status & CHANNEL_STATE_MASK),
        "power_w": _decode_outlet_watts(data),
        "auto_cut": bool(status & 0x80),
        "under_threshold": bool(status & 0x40),
        "overload": bool(status & 0x20),
    }


def _decode_outlet_watts(data: bytes) -> float:
    digits = [
        data[0] & 0x0F,
        data[1] >> 4,
        data[1] & 0x0F,
        data[2] >> 4,
        data[2] & 0x0F,
    ]
    return _decimal_from_digits(digits, decimal_places=1)


def _decimal_from_digits(digits: list[int], *, decimal_places: int) -> float:
    value = int("".join(str(digit) for digit in digits))
    return value / (10 ** decimal_places)


def _select_channel_index(
    count: int,
    *,
    unit: int | None,
    channel: int | None,
) -> int | None:
    if channel is not None:
        _validate_outlet_channel(channel)
        index = channel - 1
        return index if index < count else None

    if count == 1:
        return 0
    if unit is not None and unit != 0x0F and 1 <= unit <= count:
        return unit - 1
    return None


def _validate_outlet_sub_id(sub_id: int) -> None:
    if not isinstance(sub_id, int):
        raise TypeError("outlet sub_id must be an int")
    if sub_id < 0x01 or sub_id > 0xEF:
        raise ValueError("outlet sub_id must be in 0x01..0xEF")


def _validate_outlet_control_sub_id(sub_id: int) -> None:
    _validate_outlet_sub_id(sub_id)
    if sub_id & 0x0F == 0x0F:
        raise ValueError("outlet individual control cannot target an all-channel sub_id")


def _validate_outlet_channel_control_sub_id(sub_id: int) -> None:
    _validate_outlet_sub_id(sub_id)
    if sub_id & 0x0F != 0x0F:
        raise ValueError("outlet channel control requires an all-channel sub_id")


def _validate_outlet_channel(channel: int) -> None:
    if not isinstance(channel, int):
        raise TypeError("outlet channel must be an int")
    if channel < 1 or channel > 0x0E:
        raise ValueError("outlet channel must be in 1..14")
