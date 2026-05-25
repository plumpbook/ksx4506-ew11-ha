from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import Ksx4506Coordinator
from .registry_cleanup import (
    async_prune_legacy_outlet_group_registry_entries as _async_prune_legacy_outlet_group_registry_entries,
    async_prune_legacy_registry_entries as _async_prune_legacy_registry_entries,
    async_remove_entry,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _async_prune_legacy_registry_entries(hass, entry)

    coordinator = Ksx4506Coordinator(hass, entry.data)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_prune_legacy_registry_entries(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: Ksx4506Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
