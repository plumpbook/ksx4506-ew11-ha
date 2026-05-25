from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import Ksx4506Coordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = Ksx4506Coordinator(hass, entry.data)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: Ksx4506Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove HA registry entries owned by a deleted EW11 config entry."""

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    entity_entries = list(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
    device_entries = list(dr.async_entries_for_config_entry(dev_reg, entry.entry_id))

    for entity_entry in entity_entries:
        ent_reg.async_remove(entity_entry.entity_id)

    for device_entry in device_entries:
        dev_reg.async_update_device(
            device_entry.id,
            remove_config_entry_id=entry.entry_id,
        )
