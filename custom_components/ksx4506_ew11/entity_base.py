from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import Ksx4506Coordinator
from .discovery import DeviceState

_DEVICE_NAME_PREFIXES = {
    0x0E: "Light",
    0x36: "Thermostat",
    0x39: "Outlet",
}


class KsxEntity(CoordinatorEntity[Ksx4506Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Ksx4506Coordinator, dev: DeviceState) -> None:
        super().__init__(coordinator)
        self.dev_key = dev.key
        self.addr = dev.addr
        self.sub_id = dev.sub_id
        self.channel = dev.channel
        self.kind = dev.kind
        self._attr_unique_id = f"ksx4506_{self.dev_key}"

        self._set_ksx_device_info(
            device_key=self.dev_key,
            name=format_device_name(
                self.addr,
                self.sub_id,
                channel=self.channel,
                state=dev.state,
            ),
        )

    def _set_ksx_device_info(self, *, device_key: str, name: str) -> None:
        self._attr_device_info = {
            "identifiers": {("ksx4506_ew11", device_key)},
            "name": name,
            "manufacturer": "KS X 4506",
            "model": "EW11/RS485",
        }

    @property
    def dev(self):
        return self.coordinator.registry.devices[self.dev_key]


def format_device_name(
    addr: int,
    sub_id: int,
    *,
    channel: int | None = None,
    state: dict | None = None,
) -> str:
    prefix = _DEVICE_NAME_PREFIXES.get(addr)
    if prefix is None:
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


def _display_sub_id(addr: int, sub_id: int, state: dict | None) -> int:
    if addr in {0x0E, 0x39} and isinstance(state, dict):
        control_sub_id = state.get("control_sub_id")
        if isinstance(control_sub_id, int):
            return control_sub_id
    return sub_id
