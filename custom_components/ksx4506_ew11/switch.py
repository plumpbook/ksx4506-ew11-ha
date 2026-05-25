from __future__ import annotations

import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.outlet import (
    CONTROL_RESPONSE as F7_OUTLET_CONTROL_RESPONSE,
    GENERIC_SWITCH_COMMAND,
    OUTLET_DEVICE_ID,
    CONTROL_REQUEST as F7_OUTLET_CONTROL_REQUEST,
    STATUS_RESPONSE as F7_OUTLET_STATUS_RESPONSE,
    build_outlet_control_request,
    build_generic_switch_payload,
    decode_outlet_state,
)
from .devices.thermostat import (
    HEAT_CONTROL_REQUEST,
    THERMOSTAT_DEVICE_ID,
    build_thermostat_heat_request,
    thermostat_target_sub_id,
)
from .entity_base import KsxEntity
from .protocol import KsFrame


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            out.extend(_switch_entities_for_device(coordinator, d))
        return out

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e._attr_unique_id for e in init_ents)

    @callback
    def on_added(dev_key: str):
        d = coordinator.registry.devices.get(dev_key)
        if not d:
            return

        new_entities = []
        for ent in _switch_entities_for_device(coordinator, d):
            if ent._attr_unique_id in added_keys:
                continue
            new_entities.append(ent)
            added_keys.add(ent._attr_unique_id)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


def _switch_entities_for_device(coordinator, dev):
    if dev.kind == "climate" and dev.addr == THERMOSTAT_DEVICE_ID:
        channels = _thermostat_channels(dev)
        if channels:
            return [
                KsxThermostatHeatSwitch(coordinator, dev, channel=channel)
                for channel in channels
            ]
        return [KsxThermostatHeatSwitch(coordinator, dev)]

    if dev.kind != "switch":
        return []

    if dev.addr == OUTLET_DEVICE_ID:
        if "control_sub_id" in dev.state:
            return [KsxOutletSwitch(coordinator, dev)]
        return [
            KsxOutletChannelSwitch(
                coordinator,
                dev,
                channel=channel,
                source_channel=source_channel,
            )
            for channel, source_channel in _outlet_display_channels(dev)
        ]

    return [KsxSwitch(coordinator, dev)]


def _outlet_display_channels(dev):
    channels = [(1, None)]
    channels.extend(
        (channel["channel"] + 1, channel["channel"])
        for channel in dev.state.get("channels", [])
        if isinstance(channel, dict) and isinstance(channel.get("channel"), int)
    )
    return channels


def _thermostat_channels(dev):
    zones = dev.state.get("zones", [])
    return [
        zone["channel"]
        for zone in zones
        if isinstance(zone, dict) and isinstance(zone.get("channel"), int)
    ]


class KsxSwitch(KsxEntity, SwitchEntity):
    _attr_name = "Switch"

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command(
            self.addr,
            GENERIC_SWITCH_COMMAND,
            build_generic_switch_payload(turn_on=True),
        )

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(
            self.addr,
            GENERIC_SWITCH_COMMAND,
            build_generic_switch_payload(turn_on=False),
        )


class KsxOutletSwitch(KsxSwitch):
    _attr_name = "Switch"

    @property
    def is_on(self) -> bool | None:
        if "on" not in self.dev.state:
            return None
        return bool(self.dev.state.get("on"))

    async def async_turn_on(self, **kwargs):
        await self._async_set_outlet(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set_outlet(False)

    async def _async_set_outlet(self, turn_on: bool) -> None:
        target_sub = int(self.dev.state.get("control_sub_id", self.sub_id))
        status_sub = int(self.dev.state.get("status_sub_id", target_sub))
        frame = build_outlet_control_request(target_sub, turn_on=turn_on)

        send_until = getattr(self.coordinator, "async_send_f7_command_until", None)
        if send_until is None:
            await self.coordinator.async_send_f7_command(
                self.addr,
                frame.sub_id,
                F7_OUTLET_CONTROL_REQUEST,
                frame.data,
            )
            matched = None
        else:
            matched = await send_until(
                self.addr,
                frame.sub_id,
                F7_OUTLET_CONTROL_REQUEST,
                frame.data,
                self._control_success_matcher(
                    target_sub=target_sub,
                    status_sub=status_sub,
                    turn_on=turn_on,
                ),
            )

        if matched is None or matched.cmd != F7_OUTLET_STATUS_RESPONSE:
            await asyncio.sleep(0.12)
            await self.coordinator.async_request_f7_state(self.addr, status_sub)

    def _control_success_matcher(
        self,
        *,
        target_sub: int,
        status_sub: int,
        turn_on: bool,
    ):
        status_channel = int(self.dev.state.get("status_channel", 1))

        def matcher(frame: KsFrame) -> bool:
            if frame.addr != self.addr:
                return False
            if frame.sub_id == target_sub and frame.cmd == F7_OUTLET_CONTROL_RESPONSE:
                return True
            if frame.sub_id != status_sub or frame.cmd != F7_OUTLET_STATUS_RESPONSE:
                return False
            state = decode_outlet_state(
                frame.payload,
                unit=target_sub & 0x0F,
                channel=status_channel,
                command_type=frame.cmd,
            )
            return state.get("on") is bool(turn_on)

        return matcher


class KsxOutletChannelSwitch(KsxSwitch):
    def __init__(self, coordinator, dev, *, channel: int, source_channel: int | None = None) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._source_channel = source_channel
        self._attr_name = "Switch"
        self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}"
        self._set_ksx_device_info(
            device_key=f"{self.dev_key}_ch{channel}",
            name=f"KSX {self.addr:02X}-{self.sub_id:02X} ch{channel}",
        )

    @property
    def is_on(self) -> bool | None:
        if self._source_channel is None:
            return bool(self.dev.state.get("on", False))
        channel = self._channel_state
        if channel is None:
            return None
        return bool(channel.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self._async_set_channel(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set_channel(False)

    async def _async_set_channel(self, turn_on: bool):
        if self._source_channel is None:
            if turn_on:
                await super().async_turn_on()
            else:
                await super().async_turn_off()
            return

        kwargs = {"channel": self._source_channel} if self.sub_id & 0x0F == 0x0F else {}
        frame = build_outlet_control_request(self.sub_id, turn_on=turn_on, **kwargs)
        await self.coordinator.async_send_f7_command(
            self.addr,
            frame.sub_id,
            F7_OUTLET_CONTROL_REQUEST,
            frame.data,
        )

    @property
    def _channel_state(self):
        for channel in self.dev.state.get("channels", []):
            if channel.get("channel") == self._source_channel:
                return channel
        return None


class KsxThermostatHeatSwitch(KsxEntity, SwitchEntity):
    _attr_name = "Heating"

    def __init__(self, coordinator, dev, *, channel: int | None = None) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        if channel is not None:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_heat"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=f"KSX {self.addr:02X}-{self.sub_id:02X} ch{channel}",
            )
        else:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_heat"

    @property
    def is_on(self) -> bool | None:
        state = self._state
        if not state:
            return None
        return bool(state.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self._async_set_heat(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set_heat(False)

    async def _async_set_heat(self, turn_on: bool):
        frame = build_thermostat_heat_request(
            thermostat_target_sub_id(self.sub_id, self._channel),
            turn_on=turn_on,
        )
        await self.coordinator.async_send_f7_command(
            self.addr,
            frame.sub_id,
            HEAT_CONTROL_REQUEST,
            frame.data,
        )

    @property
    def _state(self):
        if self._channel is None:
            return self.dev.state
        for zone in self.dev.state.get("zones", []):
            if zone.get("channel") == self._channel:
                return zone
        return {}
