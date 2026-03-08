from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity

CMD_SET_SWITCH = 0x21
CMD_SET_GAS = 0x61


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            if d.kind == "switch":
                out.append(KsxSwitch(coordinator, d))
            elif d.kind == "gas_valve":
                out.append(KsxGasValve(coordinator, d))
        return out

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e.dev_key for e in init_ents)

    @callback
    def on_added(dev_key: str):
        if dev_key in added_keys:
            return
        d = coordinator.registry.devices.get(dev_key)
        if not d:
            return
        if d.kind == "switch":
            ent = KsxSwitch(coordinator, d)
        elif d.kind == "gas_valve":
            ent = KsxGasValve(coordinator, d)
        else:
            return
        async_add_entities([ent])
        added_keys.add(dev_key)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxSwitch(KsxEntity, SwitchEntity):
    _attr_name = "Switch"

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_SWITCH, b"\x01")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_SWITCH, b"\x00")


class KsxGasValve(KsxEntity, SwitchEntity):
    _attr_name = "Gas Valve"

    @property
    def is_on(self) -> bool:
        return bool(self.dev.state.get("on", False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_GAS, b"\x01", guard=True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(self.addr, CMD_SET_GAS, b"\x00", guard=True)
