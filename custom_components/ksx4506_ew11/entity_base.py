from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import Ksx4506Coordinator
from .discovery import DeviceState


class KsxEntity(CoordinatorEntity[Ksx4506Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Ksx4506Coordinator, dev: DeviceState) -> None:
        super().__init__(coordinator)
        self.dev_key = dev.key
        self.addr = dev.addr
        self.kind = dev.kind
        self._attr_unique_id = f"ksx4506_{self.dev_key}"
        self._attr_device_info = {
            "identifiers": {("ksx4506_ew11", self.dev_key)},
            "name": f"KSX {self.kind} {self.addr:02X}",
            "manufacturer": "KS X 4506",
            "model": "EW11/RS485",
        }

    @property
    def dev(self):
        return self.coordinator.registry.devices[self.dev_key]
