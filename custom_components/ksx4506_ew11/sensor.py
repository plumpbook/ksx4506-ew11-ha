from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config import effective_config
from .const import CONF_EXPOSE_PACKET_SAMPLES, DOMAIN, SIGNAL_DEVICE_ADDED
from .device_metadata import DEVICE_MANUFACTURER, DEVICE_MODEL, format_device_name
from .devices.meter import METER_DEVICE_ID
from .devices.outlet import OUTLET_DEVICE_ID
from .entity_base import KsxEntity

_SOURCE_SAME = object()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            out.extend(_sensor_entities_for_device(coordinator, d))
        return out

    init_ents = [
        KsxUnsupportedPacketsSensor(coordinator, entry),
        KsxPacketCaptureSensor(coordinator, entry),
        *build_all(),
    ]
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e._attr_unique_id for e in init_ents)

    @callback
    def on_added(dev_key: str):
        d = coordinator.registry.devices.get(dev_key)
        if not d:
            return

        new_entities = []
        for ent in _sensor_entities_for_device(coordinator, d):
            if ent._attr_unique_id in added_keys:
                continue
            new_entities.append(ent)
            added_keys.add(ent._attr_unique_id)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


def _sensor_entities_for_device(coordinator, dev):
    out = []
    if dev.kind == "sensor":
        if dev.addr == METER_DEVICE_ID:
            out.extend(_meter_sensors(coordinator, dev))
        else:
            out.append(KsxSensor(coordinator, dev))
    if dev.kind == "entrance_panel":
        out.append(KsxEntrancePanelSensor(coordinator, dev))
    if dev.kind == "common_entrance":
        out.append(KsxCommonEntranceSensor(coordinator, dev))
    if dev.kind == "unknown":
        out.append(KsxUnknownDiagnostic(coordinator, dev))
    if dev.kind == "switch" and dev.addr == OUTLET_DEVICE_ID:
        if "control_sub_id" in dev.state:
            if "power_w" in dev.state:
                out.append(KsxOutletPowerSensor(coordinator, dev))
            if "threshold_w" in dev.state:
                out.append(KsxOutletThresholdSensor(coordinator, dev))
    return out


def _meter_sensors(coordinator, dev):
    out = []
    if "instant" in dev.state:
        out.append(KsxMeterInstantSensor(coordinator, dev))
    if "total" in dev.state:
        out.append(KsxMeterTotalSensor(coordinator, dev))
    return out


class KsxSensor(KsxEntity, SensorEntity):
    _attr_name = "Sensor"

    @property
    def native_value(self):
        return self.dev.state.get("value", self.dev.state.get("value_hex"))

    @property
    def native_unit_of_measurement(self):
        return self.dev.state.get("unit")

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self.dev.state.items()
            if key not in {"value", "unit"}
        }


class KsxEntrancePanelSensor(KsxEntity, SensorEntity):
    _attr_name = "Entrance Panel"

    @property
    def native_value(self):
        status = self.dev.state.get("status_byte")
        if status is None:
            return self.dev.state.get("value_hex")
        return f"0x{int(status):02X}"

    @property
    def extra_state_attributes(self):
        return dict(self.dev.state)


class KsxCommonEntranceSensor(KsxEntity, SensorEntity):
    _attr_name = "Common Entrance"

    @property
    def native_value(self):
        return self.dev.state.get("event", self.dev.state.get("value_hex"))

    @property
    def extra_state_attributes(self):
        return dict(self.dev.state)


class KsxMeterInstantSensor(KsxEntity, SensorEntity):
    _attr_name = "Instant"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, dev) -> None:
        super().__init__(coordinator, dev)
        self._attr_unique_id = f"ksx4506_{self.dev_key}_instant"

    @property
    def native_value(self):
        return self.dev.state.get("instant")

    @property
    def native_unit_of_measurement(self):
        return self.dev.state.get("instant_unit")

    @property
    def device_class(self):
        if self.native_unit_of_measurement == UnitOfPower.WATT:
            return SensorDeviceClass.POWER
        return None

    @property
    def extra_state_attributes(self):
        return _meter_attributes(self.dev.state)


class KsxMeterTotalSensor(KsxEntity, SensorEntity):
    _attr_name = "Total"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, dev) -> None:
        super().__init__(coordinator, dev)
        self._attr_unique_id = f"ksx4506_{self.dev_key}_total"

    @property
    def native_value(self):
        return self.dev.state.get("total")

    @property
    def native_unit_of_measurement(self):
        return self.dev.state.get("total_unit")

    @property
    def device_class(self):
        if self.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR:
            return SensorDeviceClass.ENERGY
        return None

    @property
    def extra_state_attributes(self):
        return _meter_attributes(self.dev.state)


class KsxOutletPowerSensor(KsxEntity, SensorEntity):
    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator,
        dev,
        *,
        channel: int | None = None,
        source_channel=_SOURCE_SAME,
    ) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._source_channel = channel if source_channel is _SOURCE_SAME else source_channel
        if channel is None:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_power"
        else:
            self._attr_name = "Power"
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_power"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=format_device_name(
                    self.addr,
                    self.sub_id,
                    channel=channel,
                    state=dev.state,
                ),
            )

    @property
    def native_value(self):
        if self._channel is not None:
            if self._source_channel is None:
                return self.dev.state.get("power_w")
            channel = self._channel_state
            if channel is None:
                return None
            return channel.get("power_w")
        return self.dev.state.get("power_w")

    @property
    def extra_state_attributes(self):
        if self._channel is not None:
            if self._source_channel is None:
                return {
                    key: value
                    for key, value in self.dev.state.items()
                    if key in {"channel_count", "channels", "auto_cut", "under_threshold", "overload"}
                }
            channel = self._channel_state
            return dict(channel) if channel is not None else {}
        return {
            key: value
            for key, value in self.dev.state.items()
            if key in {"channel_count", "channels", "auto_cut", "under_threshold", "overload"}
        }

    @property
    def _channel_state(self):
        for channel in self.dev.state.get("channels", []):
            if channel.get("channel") == self._source_channel:
                return channel
        return None


class KsxOutletThresholdSensor(KsxEntity, SensorEntity):
    _attr_name = "Cutoff Threshold"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator,
        dev,
        *,
        channel: int | None = None,
        source_channel=_SOURCE_SAME,
    ) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._source_channel = channel if source_channel is _SOURCE_SAME else source_channel
        if channel is None:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_threshold"
        else:
            self._attr_name = "Cutoff Threshold"
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_threshold"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=format_device_name(
                    self.addr,
                    self.sub_id,
                    channel=channel,
                    state=dev.state,
                ),
            )

    @property
    def native_value(self):
        if self._channel is not None:
            if self._source_channel is None:
                return self.dev.state.get("threshold_w")
            threshold = self._channel_threshold
            if threshold is None:
                return None
            return threshold.get("threshold_w")
        return self.dev.state.get("threshold_w")

    @property
    def extra_state_attributes(self):
        if self._channel is not None:
            if self._source_channel is None:
                return {
                    key: value
                    for key, value in self.dev.state.items()
                    if key in {"threshold_count", "thresholds"}
                }
            threshold = self._channel_threshold
            return dict(threshold) if threshold is not None else {}
        return {
            key: value
            for key, value in self.dev.state.items()
            if key in {"threshold_count", "thresholds"}
        }

    @property
    def _channel_threshold(self):
        for threshold in self.dev.state.get("thresholds", []):
            if threshold.get("channel") == self._source_channel:
                return threshold
        return None


class KsxUnknownDiagnostic(KsxEntity, SensorEntity):
    _attr_name = "Unknown Diagnostic"
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self):
        return self.dev.state.get("payload_len")

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self.dev.state.items()
            if key not in {"value_hex"}
        }


class KsxUnsupportedPacketsSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Unsupported Packets"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._include_packet_samples = bool(
            effective_config(entry).get(CONF_EXPOSE_PACKET_SAMPLES, False)
        )
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_unsupported_packets"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": DEVICE_MANUFACTURER,
            "model": DEVICE_MODEL,
        }

    @property
    def native_value(self):
        return self.coordinator.registry.unsupported_packet_report(
            limit=0,
            include_packet_samples=self._include_packet_samples,
        )["total_seen"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.registry.unsupported_packet_report(
            limit=20,
            include_packet_samples=self._include_packet_samples,
        )


class KsxPacketCaptureSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Packet Capture"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"ksx4506_{entry.entry_id}_packet_capture"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": DEVICE_MANUFACTURER,
            "model": DEVICE_MODEL,
        }

    @property
    def native_value(self):
        return self.coordinator.packet_capture_report()["count"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.packet_capture_report()


def _meter_attributes(state):
    return {
        key: value
        for key, value in state.items()
        if key in {"meter", "error", "instant", "instant_unit", "total", "total_unit"}
    }
