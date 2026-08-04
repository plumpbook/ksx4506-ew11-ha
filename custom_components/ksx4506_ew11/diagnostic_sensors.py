from __future__ import annotations

from time import monotonic

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config import effective_config
from .const import CONF_EXPOSE_PACKET_SAMPLES, DOMAIN
from .coordinator import Ksx4506Coordinator
from .device_metadata import DEVICE_MANUFACTURER, DEVICE_MODEL
from .ew11_health import ew11_health_report_from_coordinator

_FRAME_UPDATE_INTERVAL_SECONDS = 1.0


class _KsxDiagnosticSensor(
    CoordinatorEntity[Ksx4506Coordinator],
    SensorEntity,
):
    def __init__(self, coordinator: Ksx4506Coordinator) -> None:
        super().__init__(coordinator)
        self._last_update_at: float | None = None

    def _handle_coordinator_update(self) -> None:
        now = monotonic()
        changed_device_keys = getattr(
            self.coordinator,
            "_last_changed_device_keys",
            None,
        )
        if (
            changed_device_keys is not None
            and self._last_update_at is not None
            and now - self._last_update_at < _FRAME_UPDATE_INTERVAL_SECONDS
        ):
            return

        self._last_update_at = now
        update_handler = getattr(super(), "_handle_coordinator_update", None)
        if update_handler is not None:
            update_handler()
            return

        write_state = getattr(self, "async_write_ha_state", None)
        if write_state is not None:
            write_state()


class KsxEw11LinkSensor(_KsxDiagnosticSensor):
    _attr_has_entity_name = True
    _attr_name = "EW11 Link"
    _attr_entity_registry_enabled_default = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_ew11_link"
        self._attr_device_info = _ew11_device_info(entry)

    @property
    def native_value(self):
        return ew11_health_report_from_coordinator(self.coordinator)["state"]

    @property
    def extra_state_attributes(self):
        return ew11_health_report_from_coordinator(self.coordinator)


class KsxUnsupportedPacketsSensor(_KsxDiagnosticSensor):
    _attr_has_entity_name = True
    _attr_name = "Unsupported Packets"
    _attr_entity_registry_enabled_default = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._include_packet_samples = bool(
            effective_config(entry).get(CONF_EXPOSE_PACKET_SAMPLES, False)
        )
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_unsupported_packets"
        self._attr_device_info = _ew11_device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.registry.unsupported_packet_report(
            limit=0,
            include_packet_samples=self._include_packet_samples,
        )["unique_signatures"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.registry.unsupported_packet_report(
            limit=20,
            include_packet_samples=self._include_packet_samples,
        )


class KsxPacketCaptureSensor(_KsxDiagnosticSensor):
    _attr_has_entity_name = True
    _attr_name = "Packet Capture"
    _attr_entity_registry_enabled_default = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._include_packet_samples = bool(
            effective_config(entry).get(CONF_EXPOSE_PACKET_SAMPLES, False)
        )
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_packet_capture"
        self._attr_device_info = _ew11_device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.packet_capture_report(
            include_packet_samples=self._include_packet_samples
        )["count"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.packet_capture_report(
            include_packet_samples=self._include_packet_samples
        )


class KsxPacketQualitySensor(_KsxDiagnosticSensor):
    _attr_has_entity_name = True
    _attr_name = "Packet Quality"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._include_packet_samples = bool(
            effective_config(entry).get(CONF_EXPOSE_PACKET_SAMPLES, False)
        )
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_packet_quality"
        self._attr_device_info = _ew11_device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.packet_quality_report(
            include_packet_samples=self._include_packet_samples
        )["state"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.packet_quality_report(
            include_packet_samples=self._include_packet_samples
        )


def _ew11_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=DEVICE_MANUFACTURER,
        model=DEVICE_MODEL,
    )
