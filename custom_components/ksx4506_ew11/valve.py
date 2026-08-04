from __future__ import annotations

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.gas import (
    CONTROL_REQUEST as F7_GAS_CONTROL_REQUEST,
    CONTROL_RESPONSE as F7_GAS_CONTROL_RESPONSE,
    STATUS_RESPONSE as F7_GAS_STATUS_RESPONSE,
    build_gas_close_payload,
    decode_gas_state,
)
from .entity_base import KsxEntity
from .protocol import KsFrame


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

    @property
    def supported_features(self) -> ValveEntityFeature:
        if not self.coordinator.gas_unlocked:
            return ValveEntityFeature(0)
        return ValveEntityFeature.CLOSE

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
        if not self.coordinator.gas_unlocked:
            raise HomeAssistantError(
                "Gas valve control is locked; enable the gas_unlock option first"
            )

        matched = await self.coordinator.async_send_f7_command_and_confirm(
            self.addr,
            self.sub_id,
            F7_GAS_CONTROL_REQUEST,
            build_gas_close_payload(),
            self._close_response_matcher,
            status_sub_id=self.sub_id,
            confirmation_matcher=_gas_frame_is_closed,
            interval=0.5,
            confirmation_interval=0.5,
            guard=True,
        )
        if matched is None:
            raise HomeAssistantError("Gas valve close state could not be confirmed")

    def _close_response_matcher(self, frame: KsFrame) -> bool:
        if frame.addr != self.addr or frame.sub_id != self.sub_id:
            return False
        if frame.cmd == F7_GAS_CONTROL_RESPONSE:
            return True
        return frame.cmd == F7_GAS_STATUS_RESPONSE and _gas_frame_is_closed(frame)


def _gas_frame_is_closed(frame: KsFrame) -> bool:
    if frame.cmd not in {F7_GAS_CONTROL_RESPONSE, F7_GAS_STATUS_RESPONSE}:
        return False
    state = decode_gas_state(frame.payload)
    if "closed" in state:
        return bool(state["closed"])
    if "on" in state:
        return not bool(state["on"])
    return False
