from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_LIGHT = 0x11
CMD_F7_SET_ONE = 0x41


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

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    async def async_turn_on(self, **kwargs):
        if self.addr == 0x0E and self.channel is not None:
            payload = bytes([self.channel & 0xFF, 0x01, 0x00])
            await self.coordinator.async_send_f7_command(self.addr, self.sub_id, CMD_F7_SET_ONE, payload)
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x01")

    async def async_turn_off(self, **kwargs):
        if self.addr == 0x0E and self.channel is not None:
            payload = bytes([self.channel & 0xFF, 0x00, 0x00])
            await self.coordinator.async_send_f7_command(self.addr, self.sub_id, CMD_F7_SET_ONE, payload)
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x00")
