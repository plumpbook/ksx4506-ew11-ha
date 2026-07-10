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
_RESTORED_ON_STATES = {
    "on": True,
    "off": False,
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

    async def _async_restore_last_on_state(
        self,
        *,
        default_on: bool | None = None,
    ) -> bool:
        if "on" in self.dev.state:
            return False

        get_last_state = getattr(self, "async_get_last_state", None)
        if get_last_state is None:
            return False

        last_state = await get_last_state()
        restored = _RESTORED_ON_STATES.get(getattr(last_state, "state", None))
        if restored is None and default_on is None:
            return False

        self.dev.state["on"] = bool(default_on if restored is None else restored)
        self.dev.state["state_assumed"] = True
        self.dev.state["state_assumed_raw_hex"] = self.dev.last_raw_hex
        write_state = getattr(self, "async_write_ha_state", None)
        if write_state is not None:
            write_state()
        return True

    @property
    def _on_state_is_assumed(self) -> bool:
        return bool(self.dev.state.get("state_assumed", False)) and (
            self.dev.last_raw_hex == self.dev.state.get("state_assumed_raw_hex")
        )
