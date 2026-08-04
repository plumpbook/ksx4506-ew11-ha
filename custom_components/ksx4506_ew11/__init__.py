from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .config import effective_config
from .const import DOMAIN, PLATFORMS
from .coordinator import Ksx4506Coordinator
from .registry_cleanup import (
    async_prune_legacy_outlet_group_registry_entries as _async_prune_legacy_outlet_group_registry_entries,
    async_prune_legacy_registry_entries as _async_prune_legacy_registry_entries,
    async_remove_entry,
)
from .registry_bootstrap import async_restore_registry_devices_from_ha

__all__ = (
    "_async_prune_legacy_outlet_group_registry_entries",
    "async_remove_entry",
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _async_prune_legacy_registry_entries(hass, entry)

    coordinator = Ksx4506Coordinator(hass, effective_config(entry))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    setup_complete = False
    try:
        await async_restore_registry_devices_from_ha(hass, entry, coordinator.registry)
        await coordinator.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await _async_prune_legacy_registry_entries(hass, entry)
        setup_complete = True
    finally:
        if not setup_complete:
            await coordinator.async_stop()
            hass.data[DOMAIN].pop(entry.entry_id, None)
    entry.async_on_unload(entry.add_update_listener(_async_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    coordinator: Ksx4506Coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


async def _async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
