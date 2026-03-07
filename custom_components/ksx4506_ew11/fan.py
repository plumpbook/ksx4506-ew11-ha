from __future__ import annotations

from homeassistant.components.fan import FanEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_FAN = 0x41


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def build():
        return [KsxFan(coordinator, d) for d in coordinator.registry.devices.values() if d.kind == "fan"]

    async_add_entities(build())

    @hass.callback
    def on_added(_key: str):
        ents = build()
        if ents:
            async_add_entities(ents)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxFan(KsxEntity, FanEntity):
    _attr_name = "Fan"

    @property
    def is_on(self):
        return bool(self.dev.state.get("on", False))

    @property
    def percentage(self):
        speed = int(self.dev.state.get("speed", 0))
        return min(speed * 33, 100)

    async def async_turn_on(self, percentage=None, **kwargs):
        speed = 1 if percentage is None else max(1, min(3, round(percentage / 33)))
        await self.coordinator.async_send_command(self.addr, CMD_SET_FAN, bytes([speed]))

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_FAN, b"\x00")
