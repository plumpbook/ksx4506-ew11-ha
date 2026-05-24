"""KS X 4506 lighting command helpers."""

from __future__ import annotations

LIGHT_DEVICE_ID = 0x0E
STATUS_REQUEST = 0x01
STATUS_RESPONSE = 0x81
CONTROL_REQUEST = 0x41
CONTROL_RESPONSE = 0xC1


def decode_light_state_byte(state_byte: int) -> dict[str, bool | int]:
    dimmable = bool(state_byte & 0x02)
    return {
        "on": bool(state_byte & 0x01),
        "dimmable": dimmable,
        "brightness_step": (state_byte >> 4) & 0x0F if dimmable else 0,
    }


def build_light_control_payload(
    *,
    turn_on: bool,
    brightness_step: int | None = None,
) -> bytes:
    """Build the standard one-byte lighting control payload."""

    if brightness_step is not None:
        if not turn_on:
            raise ValueError("brightness can only be used when turning on")
        if brightness_step < 1 or brightness_step > 15:
            raise ValueError("brightness_step must be in 1..15")

    control = 0x01 if turn_on else 0x00
    if brightness_step is not None:
        control |= (brightness_step & 0x0F) << 4
    return bytes([control])


def build_vendor_channel_control_payload(
    *,
    channel: int,
    turn_on: bool,
) -> bytes:
    """Build the observed Suroup group-channel fallback payload."""

    if channel < 1 or channel > 0x0E:
        raise ValueError("channel must be in 1..14")
    return bytes([channel & 0xFF, 0x01 if turn_on else 0x00, 0x00])


def f7_individual_sub_id(group_sub_id: int, channel: int | None) -> int:
    """Return the individual control sub-id for a grouped light entity."""

    if channel is not None and (group_sub_id & 0x0F) == 0x0F:
        if channel < 1 or channel > 0x0E:
            raise ValueError("channel must be in 1..14")
        return (group_sub_id & 0xF0) | (channel & 0x0F)
    return group_sub_id
