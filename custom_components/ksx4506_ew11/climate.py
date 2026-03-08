from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_CLIMATE = 0x31


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def build():
        return [KsxClimate(coordinator, d) for d in coordinator.registry.devices.values() if d.kind == "climate"]

    async_add_entities(build())

    @callback
    def on_added(_key: str):
        ents = build()
        if ents:
            async_add_entities(ents)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxClimate(KsxEntity, ClimateEntity):
    _attr_name = "Climate"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]

    @property
    def target_temperature(self):
        return self.dev.state.get("target_temp")

    @property
    def current_temperature(self):
        return self.dev.state.get("current_temp")

    @property
    def hvac_mode(self):
        return HVACMode.HEAT if self.dev.state.get("target_temp", 0) > 0 else HVACMode.OFF

    async def async_set_temperature(self, **kwargs):
        temp = int(kwargs.get("temperature", 22))
        await self.coordinator.async_send_command(self.addr, CMD_SET_CLIMATE, bytes([temp & 0xFF]))
