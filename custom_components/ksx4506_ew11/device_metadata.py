from __future__ import annotations

from typing import Any

from .devices.meter import METER_DEVICE_ID

DEVICE_MANUFACTURER = "KS X 4506"
DEVICE_MODEL = "EW11/RS485"

METER_DISPLAY_NAMES = {
    0x01: "Water Meter",
    0x02: "Gas Meter",
    0x03: "Electric Meter",
    0x04: "Hot Water Meter",
    0x05: "Heat Meter",
}

_DEVICE_NAME_PREFIXES = {
    0x0E: "Light",
    0x36: "Thermostat",
    0x39: "Outlet",
}


def meter_device_name(sub_id: int) -> str | None:
    display_name = METER_DISPLAY_NAMES.get(sub_id)
    if display_name is None:
        return None
    return f"{display_name} {METER_DEVICE_ID:02X}-{sub_id:02X}"


def format_device_name(
    addr: int,
    sub_id: int,
    *,
    channel: int | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    prefix = _DEVICE_NAME_PREFIXES.get(addr)
    if prefix is None:
        if addr == METER_DEVICE_ID:
            name = meter_device_name(sub_id)
            if name is not None:
                return name
        name = f"KSX {addr:02X}-{sub_id:02X}"
        if channel is not None:
            return f"{name} ch{channel}"
        return name

    display_sub_id = _display_sub_id(addr, sub_id, state)
    name = f"{prefix} {addr:02X}-{display_sub_id:02X}"

    if addr == 0x36 and channel is not None:
        return f"{name} Zone {channel}"
    if channel is not None and display_sub_id == sub_id:
        return f"{name} Channel {channel}"
    return name


def _display_sub_id(addr: int, sub_id: int, state: dict[str, Any] | None) -> int:
    if addr in {0x0E, 0x39} and isinstance(state, dict):
        control_sub_id = state.get("control_sub_id")
        if isinstance(control_sub_id, int):
            return control_sub_id
    return sub_id
