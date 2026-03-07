from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def build():
        out = []
        for d in coordinator.registry.devices.values():
            if d.kind == "sensor":
                out.append(KsxSensor(coordinator, d))
            if d.kind == "unknown":
                out.append(KsxUnknownDiagnostic(coordinator, d))
        return out

    async_add_entities(build())

    @hass.callback
    def on_added(_key: str):
        ents = build()
        if ents:
            async_add_entities(ents)

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
