from __future__ import annotations

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_LIGHT = 0x11


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def build():
        return [KsxLight(coordinator, d) for d in coordinator.registry.devices.values() if d.kind == "light"]

    async_add_entities(build())

    @hass.callback
    def on_added(_key: str):
        ents = build()
        if ents:
            async_add_entities(ents)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxLight(KsxEntity, LightEntity):
    _attr_name = "Light"

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x01")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x00")
