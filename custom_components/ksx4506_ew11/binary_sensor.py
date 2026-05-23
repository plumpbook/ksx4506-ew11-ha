from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .entity_base import KsxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            if d.kind == "gas_valve":
                out.extend(_gas_binary_sensors(coordinator, d))
        return out

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e._attr_unique_id for e in init_ents)

    @callback
    def on_added(dev_key: str):
        d = coordinator.registry.devices.get(dev_key)
        if not d or d.kind != "gas_valve":
            return

        new_entities = []
        for ent in _gas_binary_sensors(coordinator, d):
            if ent._attr_unique_id in added_keys:
                continue
            new_entities.append(ent)
            added_keys.add(ent._attr_unique_id)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


def _gas_binary_sensors(coordinator, dev):
    return [
        KsxGasLeakSensor(coordinator, dev),
        KsxGasValveMovingSensor(coordinator, dev),
    ]


class _KsxGasBinarySensor(KsxEntity, BinarySensorEntity):
    _state_key = ""

    def __init__(self, coordinator, dev) -> None:
        super().__init__(coordinator, dev)
        self._attr_unique_id = f"ksx4506_{self.dev_key}_{self._state_key}"

    @property
    def is_on(self) -> bool | None:
        if self._state_key not in self.dev.state:
            return None
        return bool(self.dev.state[self._state_key])


class KsxGasLeakSensor(_KsxGasBinarySensor):
    _attr_name = "Gas Leak"
    _attr_device_class = BinarySensorDeviceClass.GAS
    _state_key = "leak"


class KsxGasValveMovingSensor(_KsxGasBinarySensor):
    _attr_name = "Gas Valve Moving"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _state_key = "moving"
