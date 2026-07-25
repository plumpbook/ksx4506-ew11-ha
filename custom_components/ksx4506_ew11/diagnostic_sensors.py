from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config import effective_config
from .const import CONF_EXPOSE_PACKET_SAMPLES, DOMAIN
from .coordinator import Ksx4506Coordinator
from .device_metadata import DEVICE_MANUFACTURER, DEVICE_MODEL
from .ew11_health import ew11_health_report_from_coordinator


class KsxEw11LinkSensor(CoordinatorEntity[Ksx4506Coordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "EW11 Link"
    _attr_entity_registry_enabled_default = True

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


class KsxUnsupportedPacketsSensor(CoordinatorEntity[Ksx4506Coordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Unsupported Packets"
    _attr_entity_registry_enabled_default = True

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


class KsxPacketCaptureSensor(CoordinatorEntity[Ksx4506Coordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Packet Capture"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_packet_capture"
        self._attr_device_info = _ew11_device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.packet_capture_report()["count"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.packet_capture_report()


class KsxPacketQualitySensor(CoordinatorEntity[Ksx4506Coordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Packet Quality"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_packet_quality"
        self._attr_device_info = _ew11_device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.packet_quality_report()["state"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.packet_quality_report()


def _ew11_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=DEVICE_MANUFACTURER,
        model=DEVICE_MODEL,
    )
