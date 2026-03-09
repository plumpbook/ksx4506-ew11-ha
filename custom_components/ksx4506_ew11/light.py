from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_LIGHT = 0x11


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        return [KsxLight(coordinator, d) for d in coordinator.registry.devices.values() if d.kind == "light"]

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e.dev_key for e in init_ents)

    @callback
    def on_added(dev_key: str):
        if dev_key in added_keys:
            return
        d = coordinator.registry.devices.get(dev_key)
        if not d or d.kind != "light":
            return
        ent = KsxLight(coordinator, d)
        async_add_entities([ent])
        added_keys.add(dev_key)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxLight(KsxEntity, LightEntity):
    _attr_name = "Light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x01")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x00")
