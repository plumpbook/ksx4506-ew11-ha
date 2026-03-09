from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_CLIMATE = 0x31


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        return [KsxClimate(coordinator, d) for d in coordinator.registry.devices.values() if d.kind == "climate"]

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e.dev_key for e in init_ents)

    @callback
    def on_added(dev_key: str):
        if dev_key in added_keys:
            return
        d = coordinator.registry.devices.get(dev_key)
        if not d or d.kind != "climate":
            return
        ent = KsxClimate(coordinator, d)
        async_add_entities([ent])
        added_keys.add(dev_key)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxClimate(KsxEntity, ClimateEntity):
    _attr_name = "Climate"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

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
