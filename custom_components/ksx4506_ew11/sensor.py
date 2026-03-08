from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            if d.kind == "sensor":
                out.append(KsxSensor(coordinator, d))
            if d.kind == "unknown":
                out.append(KsxUnknownDiagnostic(coordinator, d))
        return out

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e.dev_key for e in init_ents)

    @callback
    def on_added(dev_key: str):
        if dev_key in added_keys:
            return
        d = coordinator.registry.devices.get(dev_key)
        if not d:
            return
        if d.kind == "sensor":
            ent = KsxSensor(coordinator, d)
        elif d.kind == "unknown":
            ent = KsxUnknownDiagnostic(coordinator, d)
        else:
            return
        async_add_entities([ent])
        added_keys.add(dev_key)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxSensor(KsxEntity, SensorEntity):
    _attr_name = "Sensor"

    @property
    def native_value(self):
        return self.dev.state.get("value_hex")


class KsxUnknownDiagnostic(KsxEntity, SensorEntity):
    _attr_name = "Unknown Diagnostic"
    _attr_entity_registry_enabled_default = True

    @property
    def native_value(self):
        return self.dev.last_raw_hex
