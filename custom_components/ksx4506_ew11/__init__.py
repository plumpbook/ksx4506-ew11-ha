from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from .config import effective_config
from .const import DOMAIN, PLATFORMS
from .coordinator import Ksx4506Coordinator
from .registry_cleanup import (
    async_prune_legacy_outlet_group_registry_entries as _async_prune_legacy_outlet_group_registry_entries,
    async_prune_legacy_registry_entries as _async_prune_legacy_registry_entries,
    async_remove_entry,
)
from .registry_bootstrap import async_restore_registry_devices_from_ha
from .power_recovery import CONF_RECOVERY_POWER_SWITCH, async_configure_power_recovery
from .discovery_setup import async_prepare_discovery, async_stop_discovery, start_discovery

__all__ = (
    "_async_prune_legacy_outlet_group_registry_entries",
    "async_remove_entry",
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = Ksx4506Coordinator(hass, effective_config(entry), entry=entry)
    coordinator.recovery_notification_id = f"ew11_recovery_{entry.entry_id}"
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    setup_complete = False
    try:
        await async_prepare_discovery(hass, entry, coordinator)
        if effective_config(entry).get(CONF_RECOVERY_POWER_SWITCH):
            try:
                await async_configure_power_recovery(hass, entry, coordinator)
            except (TimeoutError, HomeAssistantError) as exc:
                raise ConfigEntryNotReady("Recovery power restoration is not ready") from exc
        await async_restore_registry_devices_from_ha(hass, entry, coordinator.registry)
        await coordinator.async_start()
        start_discovery(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        setup_complete = True
    finally:
        if not setup_complete:
            await coordinator.async_stop()
            await async_stop_discovery(hass, entry)
            hass.data[DOMAIN].pop(entry.entry_id, None)
    entry.async_on_unload(entry.add_update_listener(_async_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    coordinator: Ksx4506Coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()
    await async_stop_discovery(hass, entry)
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


async def _async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
