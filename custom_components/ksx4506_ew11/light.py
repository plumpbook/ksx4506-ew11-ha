from __future__ import annotations

import asyncio

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
        if self.dev.state.get("dimmable"):
            return {ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.BRIGHTNESS if self.dev.state.get("dimmable") else ColorMode.ONOFF

    @property
    def brightness(self) -> int | None:
        if not self.dev.state.get("dimmable"):
            return None
        step = int(self.dev.state.get("brightness_step", 0))
        if step <= 0:
            return 0
        return max(1, min(255, round(step * 255 / 15)))

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    def _target_sub_id(self) -> int:
        # Group response subId often ends with 0xF (e.g., 0x1F), while individual control
        # uses low nibble as channel id (e.g., 0x12 for group1-channel2).
        if self.channel is not None and (self.sub_id & 0x0F) == 0x0F:
            return (self.sub_id & 0xF0) | (self.channel & 0x0F)
        return self.sub_id

    async def async_turn_on(self, **kwargs):
        if self.addr == 0x0E:
            data0 = 0x01
            if self.dev.state.get("dimmable"):
                bri = kwargs.get("brightness")
                if bri is None:
                    step = int(self.dev.state.get("brightness_step", 1) or 1)
                else:
                    step = max(1, min(15, round((int(bri) * 15) / 255)))
                data0 = ((step & 0x0F) << 4) | 0x01

            target_sub = self._target_sub_id()
            await self.coordinator.async_send_f7_command(self.addr, target_sub, CMD_F7_SET_ONE, bytes([data0]))

            # Fallback for field variants that keep group sub_id and use channel in DATA.
            if self.channel is not None and target_sub != self.sub_id:
                await asyncio.sleep(0.08)
                await self.coordinator.async_send_f7_command(
                    self.addr,
                    self.sub_id,
                    CMD_F7_SET_ONE,
                    bytes([self.channel & 0xFF, 0x01, 0x00]),
                )

            await asyncio.sleep(0.12)
            await self.coordinator.async_request_f7_state(self.addr, self.sub_id)
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x01")

    async def async_turn_off(self, **kwargs):
        if self.addr == 0x0E:
            target_sub = self._target_sub_id()
            await self.coordinator.async_send_f7_command(self.addr, target_sub, CMD_F7_SET_ONE, b"\x00")

            if self.channel is not None and target_sub != self.sub_id:
                await asyncio.sleep(0.08)
                await self.coordinator.async_send_f7_command(
                    self.addr,
                    self.sub_id,
                    CMD_F7_SET_ONE,
                    bytes([self.channel & 0xFF, 0x00, 0x00]),
                )

            await asyncio.sleep(0.12)
            await self.coordinator.async_request_f7_state(self.addr, self.sub_id)
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x00")
