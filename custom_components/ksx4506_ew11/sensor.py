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

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .diagnostic_sensors import (
    KsxEw11LinkSensor,
    KsxPacketCaptureSensor,
    KsxPacketQualitySensor,
    KsxUnsupportedPacketsSensor,
)
from .devices.meter import METER_DEVICE_ID
from .devices.outlet import OUTLET_DEVICE_ID
from .entity_base import KsxEntity
from .outlet_sensors import KsxOutletPowerSensor, KsxOutletThresholdSensor


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            out.extend(_sensor_entities_for_device(coordinator, d))
        return out

    init_ents = [
        KsxEw11LinkSensor(coordinator, entry),
        KsxUnsupportedPacketsSensor(coordinator, entry),
        KsxPacketCaptureSensor(coordinator, entry),
        KsxPacketQualitySensor(coordinator, entry),
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
        out.append(KsxEntrancePanelElevatorStatusSensor(coordinator, dev))
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


class KsxEntrancePanelElevatorStatusSensor(KsxEntity, SensorEntity):
    _attr_name = "Elevator Status"

    def __init__(self, coordinator, dev) -> None:
        super().__init__(coordinator, dev)
        self._attr_unique_id = f"ksx4506_{self.dev_key}_elevator_status"

    @property
    def native_value(self):
        return self.dev.state.get("elevator_status", "unknown")

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self.dev.state.items()
            if key
            in {
                "elevator_call_active",
                "elevator_down_active",
                "elevator_up_active",
                "last_elevator_event",
                "last_panel_event",
                "last_panel_event_code",
                "last_panel_event_command",
                "last_panel_event_payload",
                "last_panel_event_seq",
            }
        }


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


def _meter_attributes(state):
    return {
        key: value
        for key, value in state.items()
        if key in {"meter", "error", "instant", "instant_unit", "total", "total_unit"}
    }
