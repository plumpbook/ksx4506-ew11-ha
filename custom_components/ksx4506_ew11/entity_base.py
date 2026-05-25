from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import Ksx4506Coordinator
from .device_metadata import (
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    format_device_name,
)
from .discovery import DeviceState


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
            "manufacturer": DEVICE_MANUFACTURER,
            "model": DEVICE_MODEL,
        }

    @property
    def dev(self):
        return self.coordinator.registry.devices[self.dev_key]
