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


def format_common_entrance_packet_log(
    sub_id: int,
    command_type: int,
    payload: bytes,
    *,
    direction: str = "RX",
) -> str:
    """Return a concise field log for observed common entrance packets."""

    state = decode_common_entrance_state(payload, command_type=command_type)
    parts = [
        f"Common entrance {direction} packet",
        f"source=0x{COMMON_ENTRANCE_DEVICE_ID:02X}",
        f"unit=0x{sub_id:02X}",
        f"command=0x{command_type:02X}",
        f"event={state['event']}",
    ]

    if command_type == CALL_EVENT:
        parts.append(f"call_detected={_bool_text(state.get('call_detected', False))}")
        if "call_type" in state:
            parts.append(f"call_type=0x{state['call_type']:02X}")
        if "line" in state:
            parts.append(f"line=0x{state['line']:02X}")
    elif command_type == STATUS_RESPONSE:
        if "error_code" in state:
            parts.append(f"error=0x{state['error_code']:02X}")
        if "status_byte" in state:
            parts.append(f"status=0x{state['status_byte']:02X}")

    parts.append(f"payload_len={len(payload)}")
    return " ".join(parts)


def _validate_common_entrance_sub_id(sub_id: int) -> None:
    if not isinstance(sub_id, int):
        raise TypeError("common entrance sub_id must be an int")
    if sub_id < 0x01 or sub_id > 0x0E:
        raise ValueError("common entrance sub_id must be in 0x01..0x0E")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
