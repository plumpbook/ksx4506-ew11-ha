from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.thermostat import (
    TEMPERATURE_CONTROL_REQUEST,
    THERMOSTAT_DEVICE_ID,
    build_thermostat_temperature_request,
    thermostat_target_sub_id,
)
from .entity_base import KsxEntity, format_device_name


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            out.extend(_number_entities_for_device(coordinator, d))
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
        for ent in _number_entities_for_device(coordinator, d):
            if ent._attr_unique_id in added_keys:
                continue
            new_entities.append(ent)
            added_keys.add(ent._attr_unique_id)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


def _number_entities_for_device(coordinator, dev):
    if dev.kind != "climate" or dev.addr != THERMOSTAT_DEVICE_ID:
        return []

    channels = _thermostat_channels(dev)
    if channels:
        return [
            KsxThermostatTargetTemperatureNumber(coordinator, dev, channel=channel)
            for channel in channels
        ]
    return [KsxThermostatTargetTemperatureNumber(coordinator, dev)]


def _thermostat_channels(dev):
    zones = dev.state.get("zones", [])
    return [
        zone["channel"]
        for zone in zones
        if isinstance(zone, dict) and isinstance(zone.get("channel"), int)
    ]


class KsxThermostatTargetTemperatureNumber(KsxEntity, NumberEntity):
    _attr_name = "Target Temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = 5
    _attr_native_max_value = 40
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, dev, *, channel: int | None = None) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        if channel is not None:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_target_temperature"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=format_device_name(
                    self.addr,
                    self.sub_id,
                    channel=channel,
                    state=dev.state,
                ),
            )
        else:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_target_temperature"

    @property
    def native_value(self):
        return self._state.get("target_temp")

    async def async_set_native_value(self, value: float) -> None:
        frame = build_thermostat_temperature_request(
            thermostat_target_sub_id(self.sub_id, self._channel),
            temperature=value,
        )
        await self.coordinator.async_send_f7_command(
            self.addr,
            frame.sub_id,
            TEMPERATURE_CONTROL_REQUEST,
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
