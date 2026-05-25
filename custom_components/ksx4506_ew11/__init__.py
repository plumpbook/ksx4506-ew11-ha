from __future__ import annotations

import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import Ksx4506Coordinator

_LEGACY_OUTLET_GROUP_ENTITY_RE = re.compile(
    r"^ksx4506_39[0-9A-F]F_switch_ch\d+(?:_.+)?$",
)
_LEGACY_OUTLET_GROUP_DEVICE_RE = re.compile(r"^39[0-9A-F]F_switch_ch\d+$")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _async_prune_legacy_outlet_group_registry_entries(hass, entry)

    coordinator = Ksx4506Coordinator(hass, entry.data)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_prune_legacy_outlet_group_registry_entries(hass, entry)
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


def _async_prune_legacy_outlet_group_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Remove obsolete outlet group-channel registry entries.

    Older builds exposed 39-xF grouped outlet packets as pseudo devices such as
    391F_switch_ch1. The current model only exposes physical outlets like
    3911_switch and 3912_switch.
    """

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if _is_legacy_outlet_group_entity(entity_entry):
            ent_reg.async_remove(entity_entry.entity_id)

    for device_entry in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if _is_legacy_outlet_group_device(device_entry):
            dev_reg.async_update_device(
                device_entry.id,
                remove_config_entry_id=entry.entry_id,
            )


def _is_legacy_outlet_group_entity(entity_entry) -> bool:
    unique_id = getattr(entity_entry, "unique_id", None)
    return isinstance(unique_id, str) and bool(
        _LEGACY_OUTLET_GROUP_ENTITY_RE.match(unique_id)
    )


def _is_legacy_outlet_group_device(device_entry) -> bool:
    for domain, identifier in getattr(device_entry, "identifiers", set()):
        if domain != DOMAIN:
            continue
        if isinstance(identifier, str) and _LEGACY_OUTLET_GROUP_DEVICE_RE.match(
            identifier
        ):
            return True
    return False
