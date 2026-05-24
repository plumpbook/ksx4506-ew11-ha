from __future__ import annotations

import asyncio

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.lighting import (
    CONTROL_REQUEST as F7_LIGHT_CONTROL_REQUEST,
    LIGHT_DEVICE_ID,
    build_light_control_payload,
    build_vendor_channel_control_payload,
    f7_individual_sub_id,
)
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
        return int(self.dev.state.get("control_sub_id", f7_individual_sub_id(self.sub_id, self.channel)))

    def _status_sub_id(self) -> int:
        return int(self.dev.state.get("status_sub_id", self.sub_id))

    def _control_payload(self, *, turn_on: bool, **kwargs) -> bytes:
        control_channel = self.dev.state.get("control_channel")
        if isinstance(control_channel, int):
            return build_vendor_channel_control_payload(
                channel=control_channel,
                turn_on=turn_on,
            )

        brightness_step = None
        if turn_on and self.dev.state.get("dimmable"):
            bri = kwargs.get("brightness")
            if bri is None:
                brightness_step = int(self.dev.state.get("brightness_step", 1) or 1)
            else:
                brightness_step = max(1, min(15, round((int(bri) * 15) / 255)))
        return build_light_control_payload(
            turn_on=turn_on,
            brightness_step=brightness_step,
        )

    async def async_turn_on(self, **kwargs):
        if self.addr == LIGHT_DEVICE_ID:
            await self.coordinator.async_send_f7_command(
                self.addr,
                self._target_sub_id(),
                F7_LIGHT_CONTROL_REQUEST,
                self._control_payload(turn_on=True, **kwargs),
            )

            await asyncio.sleep(0.12)
            await self.coordinator.async_request_f7_state(self.addr, self._status_sub_id())
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x01")

    async def async_turn_off(self, **kwargs):
        if self.addr == LIGHT_DEVICE_ID:
            await self.coordinator.async_send_f7_command(
                self.addr,
                self._target_sub_id(),
                F7_LIGHT_CONTROL_REQUEST,
                self._control_payload(turn_on=False),
            )

            await asyncio.sleep(0.12)
            await self.coordinator.async_request_f7_state(self.addr, self._status_sub_id())
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x00")
