from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.outlet import (
    GENERIC_SWITCH_COMMAND,
    OUTLET_DEVICE_ID,
    CONTROL_REQUEST as F7_OUTLET_CONTROL_REQUEST,
    build_outlet_control_request,
    build_generic_switch_payload,
)
from .entity_base import KsxEntity


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
    if dev.kind != "switch":
        return []

    out = [KsxSwitch(coordinator, dev)]
    if dev.addr == OUTLET_DEVICE_ID:
        out.extend(
            KsxOutletChannelSwitch(coordinator, dev, channel=channel)
            for channel in _outlet_channels(dev)
        )
    return out


def _outlet_channels(dev):
    channels = dev.state.get("channels", [])
    return [
        channel["channel"]
        for channel in channels
        if isinstance(channel, dict) and isinstance(channel.get("channel"), int)
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


class KsxOutletChannelSwitch(KsxSwitch):
    def __init__(self, coordinator, dev, *, channel: int) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._attr_name = f"Switch ch{channel}"
        self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}"

    @property
    def is_on(self) -> bool | None:
        channel = self._channel_state
        if channel is None:
            return None
        return bool(channel.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self._async_set_channel(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set_channel(False)

    async def _async_set_channel(self, turn_on: bool):
        kwargs = {"channel": self._channel} if self.sub_id & 0x0F == 0x0F else {}
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
            if channel.get("channel") == self._channel:
                return channel
        return None
