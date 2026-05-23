"""KS X 4506 gas valve helpers."""

from __future__ import annotations

from typing import Any

from ..frame import Frame

GAS_DEVICE_ID = 0x12
STATUS_REQUEST = 0x01
STATUS_RESPONSE = 0x81
CONTROL_REQUEST = 0x41
CONTROL_RESPONSE = 0xC1

GAS_CLOSE = 0x01
GAS_BUZZER_STOP = 0x02


def build_gas_status_request(sub_id: int) -> Frame:
    _validate_gas_sub_id(sub_id)
    return Frame(
        device_id=GAS_DEVICE_ID,
        sub_id=sub_id,
        command_type=STATUS_REQUEST,
    )


def build_gas_close_request(sub_id: int) -> Frame:
    return _build_gas_control_request(sub_id, GAS_CLOSE)


def build_gas_close_payload() -> bytes:
    return bytes([GAS_CLOSE])


def build_gas_buzzer_stop_request(sub_id: int) -> Frame:
    return _build_gas_control_request(sub_id, GAS_BUZZER_STOP)


def decode_gas_state(payload: bytes) -> dict[str, Any]:
    """Decode gas status/control response payload into HA-friendly state."""

    if not payload:
        return {}

    if len(payload) < 2:
        return {"on": bool(payload[0] & 0x01)}

    status = payload[1]
    state: dict[str, Any] = {
        "error": payload[0],
        "open": bool(status & 0x01),
        "closed": bool(status & 0x02),
        "moving": bool(status & 0x04),
        "buzzer": bool(status & 0x08),
        "leak": bool(status & 0x10),
    }

    if status & 0x01:
        state["on"] = True
    elif status & 0x02:
        state["on"] = False

    return state


def _build_gas_control_request(sub_id: int, control: int) -> Frame:
    _validate_gas_sub_id(sub_id)
    return Frame(
        device_id=GAS_DEVICE_ID,
        sub_id=sub_id,
        command_type=CONTROL_REQUEST,
        data=bytes([control]),
    )


def _validate_gas_sub_id(sub_id: int) -> None:
    if not isinstance(sub_id, int):
        raise TypeError("gas sub_id must be an int")
    if sub_id < 0x01 or sub_id > 0x0E:
        raise ValueError("gas sub_id must be in 0x01..0x0E")
