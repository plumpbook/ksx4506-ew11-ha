"""KS X 4506 entrance panel helpers."""

from __future__ import annotations

from typing import Any

ENTRANCE_PANEL_DEVICE_ID = 0x33
EVENT_RESPONSE = 0x43
EVENT_ELEVATOR_CALL_ACK = 0x10
EVENT_ELEVATOR_ARRIVED = 0x80

# Observed/reference state shape: payload [error, status, reserved].
ELEVATOR_DOWN_MASK = 0x20
ELEVATOR_UP_MASK = 0x10
BATCH_IDLE_MASK = 0x04
AUXILIARY_MASK = 0x02


def decode_entrance_panel_state(
    payload: bytes,
    *,
    command_type: int | None = None,
) -> dict[str, Any]:
    """Decode the observed entrance panel status payload.

    Current captures identify 0x33 as the entrance-side panel family. The
    second data byte carries momentary panel function bits; the exact auxiliary
    function can vary by apartment wiring.
    """

    state: dict[str, Any] = {
        "value_hex": payload.hex(),
    }
    if not payload:
        return state

    if command_type == EVENT_RESPONSE:
        event_code = payload[0]
        event_name = _entrance_panel_event_name(event_code)
        state.update(
            {
                "last_panel_event": event_name,
                "last_panel_event_command": f"0x{command_type:02X}",
                "last_panel_event_code": f"0x{event_code:02X}",
                "last_panel_event_payload": payload.hex().upper(),
            }
        )
        if event_name in {"elevator_call_ack", "elevator_arrived"}:
            state["last_elevator_event"] = event_name
            state["elevator_status"] = (
                "arrived" if event_name == "elevator_arrived" else "calling"
            )
        return state

    state["error_code"] = payload[0]
    if len(payload) < 2:
        return state

    status = payload[1]
    elevator_call_active = bool(status & (ELEVATOR_DOWN_MASK | ELEVATOR_UP_MASK))
    state.update(
        {
            "status_byte": status,
            "elevator_status": "calling" if elevator_call_active else "idle",
            "elevator_call_active": elevator_call_active,
            "elevator_down_active": bool(status & ELEVATOR_DOWN_MASK),
            "elevator_up_active": bool(status & ELEVATOR_UP_MASK),
            # Reference packets use 0x04 as the idle marker. In those captures,
            # all-off clears this bit, so expose it as a candidate active flag.
            "batch_idle_marker": bool(status & BATCH_IDLE_MASK),
            "all_lights_off_active": not bool(status & BATCH_IDLE_MASK),
            "auxiliary_input_active": bool(status & AUXILIARY_MASK),
        }
    )

    if len(payload) >= 3:
        state["reserved_byte"] = payload[2]

    return state


def _entrance_panel_event_name(event_code: int) -> str:
    if event_code == EVENT_ELEVATOR_CALL_ACK:
        return "elevator_call_ack"
    if event_code == EVENT_ELEVATOR_ARRIVED:
        return "elevator_arrived"
    return "unknown_event"
