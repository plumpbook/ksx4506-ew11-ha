from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.thermostat import (
    HEAT_CONTROL_REQUEST,
    TEMPERATURE_CONTROL_REQUEST,
    build_thermostat_heat_request,
    build_thermostat_temperature_request,
    thermostat_target_sub_id,
)
from .entity_base import KsxEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            out.extend(_climate_entities_for_device(coordinator, d))
        return out

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e._attr_unique_id for e in init_ents)

    @callback
    def on_added(dev_key: str):
        d = coordinator.registry.devices.get(dev_key)
        if not d or d.kind != "climate":
            return

        new_entities = []
        for ent in _climate_entities_for_device(coordinator, d):
            if ent._attr_unique_id in added_keys:
                continue
            new_entities.append(ent)
            added_keys.add(ent._attr_unique_id)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


def _climate_entities_for_device(coordinator, dev):
    if dev.kind != "climate":
        return []

    entities = []
    for zone in dev.state.get("zones", []):
        channel = zone.get("channel")
        if isinstance(channel, int):
            entities.append(KsxClimate(coordinator, dev, channel=channel))
    if entities:
        return entities

    entities.append(KsxClimate(coordinator, dev))
    return entities


class KsxClimate(KsxEntity, ClimateEntity):
    _attr_name = "Climate"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, dev, *, channel: int | None = None) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        if channel is not None:
            self._attr_name = "Climate"
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=f"KSX {self.addr:02X}-{self.sub_id:02X} ch{channel}",
            )

    @property
    def target_temperature(self):
        return self._state.get("target_temp")

    @property
    def current_temperature(self):
        return self._state.get("current_temp")

    @property
    def hvac_mode(self):
        return HVACMode.HEAT if self._state.get("on", False) else HVACMode.OFF

    @property
    def hvac_action(self):
        if not self._state.get("on", False):
            return HVACAction.OFF

        target = self.target_temperature
        current = self.current_temperature
        if target is None or current is None:
            return HVACAction.IDLE
        return HVACAction.HEATING if current < target else HVACAction.IDLE

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self._state.items()
            if key in {"channel", "away", "schedule", "hot_water", "error"}
        }

    async def async_set_temperature(self, **kwargs):
        temp = float(kwargs.get("temperature", 22))
        frame = build_thermostat_temperature_request(
            self._target_sub_id(),
            temperature=temp,
        )
        await self.coordinator.async_send_f7_command(
            self.addr,
            frame.sub_id,
            TEMPERATURE_CONTROL_REQUEST,
            frame.data,
        )

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self._attr_hvac_modes:
            return
        frame = build_thermostat_heat_request(
            self._target_sub_id(),
            turn_on=hvac_mode == HVACMode.HEAT,
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

    def _target_sub_id(self) -> int:
        return thermostat_target_sub_id(self.sub_id, self._channel)
