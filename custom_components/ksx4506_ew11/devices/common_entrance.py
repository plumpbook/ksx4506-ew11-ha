"""KS X 4506 common entrance door helpers."""

from __future__ import annotations

from typing import Any

from ..frame import Frame

COMMON_ENTRANCE_DEVICE_ID = 0x40

STATUS_REQUEST = 0x02
STATUS_RESPONSE = 0x82
CALL_EVENT = 0x10
OPEN_REQUEST = 0x22

OBSERVED_CALL_PAYLOAD = bytes.fromhex("62 02 00 00 00 00")


def build_common_entrance_open_request(sub_id: int = 0x02) -> Frame:
    """Build the observed common entrance open request frame.

    This helper is intentionally not wired to a Home Assistant control entity
    yet because it opens a shared building entrance.
    """

    _validate_common_entrance_sub_id(sub_id)
    return Frame(
        device_id=COMMON_ENTRANCE_DEVICE_ID,
        sub_id=sub_id,
        command_type=OPEN_REQUEST,
    )


def decode_common_entrance_state(
    payload: bytes,
    *,
    command_type: int,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "value_hex": payload.hex(),
        "last_command_type": command_type,
    }

    if command_type == CALL_EVENT:
        state["event"] = "call_detected"
        state["call_detected"] = payload == OBSERVED_CALL_PAYLOAD
        if len(payload) >= 2:
            state["call_type"] = payload[0]
            state["line"] = payload[1]
        return state

    state["call_detected"] = False

    if command_type == STATUS_REQUEST:
        state["event"] = "status_request"
        return state

    if command_type == STATUS_RESPONSE:
        state["event"] = "status_response"
        if len(payload) >= 1:
            state["error_code"] = payload[0]
        if len(payload) >= 2:
            state["status_byte"] = payload[1]
        return state

    if command_type == OPEN_REQUEST:
        state["event"] = "open_request"
        return state

    state["event"] = "unknown"
    return state


def _validate_common_entrance_sub_id(sub_id: int) -> None:
    if not isinstance(sub_id, int):
        raise TypeError("common entrance sub_id must be an int")
    if sub_id < 0x01 or sub_id > 0x0E:
        raise ValueError("common entrance sub_id must be in 0x01..0x0E")
