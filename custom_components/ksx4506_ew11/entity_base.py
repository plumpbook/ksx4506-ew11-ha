from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import Ksx4506Coordinator
from .device_metadata import (
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    format_device_name,
)
from .discovery import DeviceState
from .ew11_health import ew11_health_report_from_coordinator

_MISSING_HEALTH_ERROR = "EW11 client health is unavailable"


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
    def available(self) -> bool:
        if not getattr(super(), "available", True):
            return False
        report = ew11_health_report_from_coordinator(self.coordinator)
        if (
            report.get("state") == "unknown"
            and report.get("last_error") == _MISSING_HEALTH_ERROR
        ):
            return True
        return report.get("state") == "receiving"

    @property
    def dev(self):
        return self.coordinator.registry.devices[self.dev_key]
