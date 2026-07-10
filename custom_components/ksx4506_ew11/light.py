from __future__ import annotations

import asyncio

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.lighting import (
    CONTROL_RESPONSE as F7_LIGHT_CONTROL_RESPONSE,
    CONTROL_REQUEST as F7_LIGHT_CONTROL_REQUEST,
    LIGHT_DEVICE_ID,
    STATUS_RESPONSE as F7_LIGHT_STATUS_RESPONSE,
    build_light_control_payload,
    build_vendor_channel_control_payload,
)
from .protocol import KsFrame
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


class KsxLight(KsxEntity, RestoreEntity, LightEntity):
    _attr_name = "Light"

    async def async_added_to_hass(self) -> None:
        parent = getattr(super(), "async_added_to_hass", None)
        if parent is not None:
            await parent()
        await self._async_restore_last_on_state()

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
    def is_on(self) -> bool | None:
        if "on" not in self.dev.state:
            return None
        return bool(self.dev.state.get("on"))

    def _target_sub_id(self) -> int:
        return int(self.dev.state.get("control_sub_id", self.sub_id))

    def _status_sub_id(self) -> int:
        return int(self.dev.state.get("status_sub_id", self._target_sub_id()))

    def _control_payload(self, *, turn_on: bool, brightness_step: int | None = None) -> bytes:
        control_channel = self.dev.state.get("control_channel")
        if control_channel is not None:
            return build_vendor_channel_control_payload(
                channel=int(control_channel),
                turn_on=turn_on,
            )
        return build_light_control_payload(
            turn_on=turn_on,
            brightness_step=brightness_step,
        )

    def _status_payload_index(self) -> int:
        control_channel = self.dev.state.get("control_channel")
        if control_channel is not None:
            return int(control_channel)
        if self.channel is not None:
            return int(self.channel)
        return 1

    def _control_success_matcher(
        self,
        *,
        target_sub: int,
        status_sub: int,
        turn_on: bool,
    ):
        expected_on = bool(turn_on)
        status_index = self._status_payload_index()

        def matcher(frame: KsFrame) -> bool:
            if frame.addr != self.addr:
                return False
            if frame.sub_id == target_sub and frame.cmd == F7_LIGHT_CONTROL_RESPONSE:
                return True
            if frame.sub_id != status_sub or frame.cmd != F7_LIGHT_STATUS_RESPONSE:
                return False
            if len(frame.payload) <= status_index:
                return False
            return bool(frame.payload[status_index] & 0x01) == expected_on

        return matcher

    async def _async_send_light_control(self, target_sub: int, payload: bytes, *, turn_on: bool) -> None:
        status_sub = self._status_sub_id()
        send_until = getattr(self.coordinator, "async_send_f7_command_until", None)
        if send_until is None:
            await self.coordinator.async_send_f7_command(
                self.addr,
                target_sub,
                F7_LIGHT_CONTROL_REQUEST,
                payload,
            )
            matched = None
        else:
            matched = await send_until(
                self.addr,
                target_sub,
                F7_LIGHT_CONTROL_REQUEST,
                payload,
                self._control_success_matcher(
                    target_sub=target_sub,
                    status_sub=status_sub,
                    turn_on=turn_on,
                ),
            )

        if matched is None or matched.cmd != F7_LIGHT_STATUS_RESPONSE:
            await asyncio.sleep(0.12)
            await self.coordinator.async_request_f7_state(self.addr, status_sub)

    async def async_turn_on(self, **kwargs):
        if self.addr == LIGHT_DEVICE_ID:
            brightness_step = None
            if self.dev.state.get("dimmable"):
                bri = kwargs.get("brightness")
                if bri is None:
                    brightness_step = int(self.dev.state.get("brightness_step", 1) or 1)
                else:
                    brightness_step = max(1, min(15, round((int(bri) * 15) / 255)))

            target_sub = self._target_sub_id()
            await self._async_send_light_control(
                target_sub,
                self._control_payload(
                    turn_on=True,
                    brightness_step=brightness_step,
                ),
                turn_on=True,
            )
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x01")

    async def async_turn_off(self, **kwargs):
        if self.addr == LIGHT_DEVICE_ID:
            target_sub = self._target_sub_id()
            await self._async_send_light_control(
                target_sub,
                self._control_payload(turn_on=False),
                turn_on=False,
            )
            return
        await self.coordinator.async_send_command(self.addr, CMD_SET_LIGHT, b"\x00")
