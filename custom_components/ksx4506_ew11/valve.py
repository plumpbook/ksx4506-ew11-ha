from __future__ import annotations

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.gas import CONTROL_REQUEST as F7_GAS_CONTROL_REQUEST
from .devices.gas import build_gas_close_payload
from .entity_base import KsxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        return [
            KsxGasValve(coordinator, d)
            for d in coordinator.registry.devices.values()
            if d.kind == "gas_valve"
        ]

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e.dev_key for e in init_ents)

    @callback
    def on_added(dev_key: str):
        if dev_key in added_keys:
            return
        d = coordinator.registry.devices.get(dev_key)
        if not d or d.kind != "gas_valve":
            return
        ent = KsxGasValve(coordinator, d)
        async_add_entities([ent])
        added_keys.add(dev_key)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


class KsxGasValve(KsxEntity, ValveEntity):
    _attr_name = "Gas Valve"
    _attr_device_class = ValveDeviceClass.GAS
    _attr_reports_position = False
    _attr_supported_features = ValveEntityFeature.CLOSE

    @property
    def is_closed(self) -> bool | None:
        if "closed" in self.dev.state:
            return bool(self.dev.state["closed"])
        if "open" in self.dev.state:
            return not bool(self.dev.state["open"])
        if "on" in self.dev.state:
            return not bool(self.dev.state["on"])
        return None

    @property
    def is_closing(self) -> bool | None:
        return bool(self.dev.state.get("moving", False))

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self.dev.state.items()
            if key in {"error", "open", "closed", "moving", "buzzer", "leak"}
        }

    async def async_close_valve(self) -> None:
        await self.coordinator.async_send_f7_command(
            self.addr,
            self.sub_id,
            F7_GAS_CONTROL_REQUEST,
            build_gas_close_payload(),
            guard=True,
        )
