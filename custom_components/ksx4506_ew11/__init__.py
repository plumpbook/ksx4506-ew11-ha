from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import Ksx4506Coordinator
from .devices.meter import meter_device_name

_LOGGER = logging.getLogger(__name__)

_LEGACY_OUTLET_GROUP_ENTITY_RE = re.compile(
    r"^ksx4506_39[0-9A-F]F_switch_ch\d+(?:_.+)?$",
)
_LEGACY_OUTLET_GROUP_DEVICE_RE = re.compile(r"^39[0-9A-F]F_switch_ch\d+$")
_LEGACY_THERMOSTAT_TARGET_NUMBER_ENTITY_RE = re.compile(
    r"^ksx4506_36[0-9A-F]{2}_climate(?:_ch\d+)?_target_temperature$",
)
_LEGACY_THERMOSTAT_INDIVIDUAL_ENTITY_RE = re.compile(
    r"^ksx4506_36[1-9A-E][1-9A-E]_climate(?:_ch\d+)?(?:_heat|_target_temperature)?$",
)
_LEGACY_THERMOSTAT_INDIVIDUAL_DEVICE_RE = re.compile(
    r"^36[1-9A-E][1-9A-E]_climate(?:_ch\d+)?$",
)
_METER_DEVICE_RE = re.compile(r"^30([0-9A-F]{2})_sensor$")
_THERMOSTAT_CLIMATE_ENTITY_RE = re.compile(
    r"^ksx4506_36[0-9A-F]{2}_climate(?:_ch\d+)?$",
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


def _async_prune_legacy_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Remove obsolete registry entries that are no longer exposed.

    Older builds exposed 39-xF grouped outlet packets as pseudo devices such as
    391F_switch_ch1. The current model only exposes physical outlets like
    3911_switch and 3912_switch.

    Older thermostat builds also exposed target temperature as a separate
    number entity. Climate entities now own target temperature control directly.
    If a previous build renamed the climate entity to "Target Temperature",
    restore the standard entity original name to "Climate".

    Individual thermostat ACK/status packets such as 36-11 are merged into the
    group status device, e.g. 36-1F Zone 1. Older builds could briefly expose
    those ACK packets as separate devices and must be removed.

    Older meter devices used generic names such as "KSX 30-03". The current
    model uses explicit names such as "Electric Meter 30-03".
    """

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for entity_entry in _entity_entries_for_cleanup(ent_reg, entry):
        if _is_legacy_outlet_group_entity(
            entity_entry
        ) or _is_legacy_thermostat_entity(entity_entry):
            ent_reg.async_remove(entity_entry.entity_id)
            continue
        if _is_thermostat_climate_entity_with_legacy_name(entity_entry):
            ent_reg.async_update_entity(
                entity_entry.entity_id,
                original_name="Climate",
            )

    for device_entry in _device_entries_for_cleanup(dev_reg, entry):
        if _is_legacy_outlet_group_device(
            device_entry
        ) or _is_legacy_thermostat_individual_device(device_entry):
            dev_reg.async_update_device(
                device_entry.id,
                remove_config_entry_id=entry.entry_id,
            )
            continue
        meter_name = _meter_device_name_for_entry(device_entry)
        if meter_name and _meter_device_name_needs_update(device_entry, meter_name):
            _LOGGER.debug(
                "Updating meter device name device_id=%s name=%s",
                device_entry.id,
                meter_name,
            )
            dev_reg.async_update_device(
                device_entry.id,
                name=meter_name,
            )


def _entity_entries_for_cleanup(ent_reg, entry: ConfigEntry) -> list:
    entries = list(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
    seen = {
        getattr(entity_entry, "entity_id", id(entity_entry))
        for entity_entry in entries
    }

    registry_entities = getattr(ent_reg, "entities", {})
    values = registry_entities.values() if hasattr(registry_entities, "values") else ()
    for entity_entry in values:
        key = getattr(entity_entry, "entity_id", id(entity_entry))
        if key in seen:
            continue
        if getattr(entity_entry, "platform", None) != DOMAIN:
            continue
        if (
            _is_legacy_outlet_group_entity(entity_entry)
            or _is_legacy_thermostat_entity(entity_entry)
            or _is_thermostat_climate_entity_with_legacy_name(entity_entry)
        ):
            entries.append(entity_entry)
            seen.add(key)

    return entries


def _device_entries_for_cleanup(dev_reg, entry: ConfigEntry) -> list:
    entries = list(dr.async_entries_for_config_entry(dev_reg, entry.entry_id))
    seen = {
        getattr(device_entry, "id", id(device_entry))
        for device_entry in entries
    }

    registry_devices = getattr(dev_reg, "devices", {})
    values = registry_devices.values() if hasattr(registry_devices, "values") else ()
    for device_entry in values:
        key = getattr(device_entry, "id", id(device_entry))
        if key in seen:
            continue
        config_entries = getattr(device_entry, "config_entries", ())
        if entry.entry_id not in config_entries:
            continue
        if _is_legacy_outlet_group_device(
            device_entry
        ) or _is_legacy_thermostat_individual_device(
            device_entry
        ) or _meter_device_name_for_entry(device_entry):
            entries.append(device_entry)
            seen.add(key)

    return entries


def _async_prune_legacy_outlet_group_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    _async_prune_legacy_registry_entries(hass, entry)


def _is_legacy_outlet_group_entity(entity_entry) -> bool:
    unique_id = getattr(entity_entry, "unique_id", None)
    return isinstance(unique_id, str) and bool(
        _LEGACY_OUTLET_GROUP_ENTITY_RE.match(unique_id)
    )


def _is_legacy_thermostat_entity(entity_entry) -> bool:
    unique_id = getattr(entity_entry, "unique_id", None)
    return isinstance(unique_id, str) and (
        bool(_LEGACY_THERMOSTAT_TARGET_NUMBER_ENTITY_RE.match(unique_id))
        or bool(_LEGACY_THERMOSTAT_INDIVIDUAL_ENTITY_RE.match(unique_id))
    )


def _is_thermostat_climate_entity_with_legacy_name(entity_entry) -> bool:
    unique_id = getattr(entity_entry, "unique_id", None)
    original_name = getattr(entity_entry, "original_name", None)
    return (
        isinstance(unique_id, str)
        and bool(_THERMOSTAT_CLIMATE_ENTITY_RE.match(unique_id))
        and original_name == "Target Temperature"
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


def _is_legacy_thermostat_individual_device(device_entry) -> bool:
    for domain, identifier in getattr(device_entry, "identifiers", set()):
        if domain != DOMAIN:
            continue
        if isinstance(
            identifier,
            str,
        ) and _LEGACY_THERMOSTAT_INDIVIDUAL_DEVICE_RE.match(identifier):
            return True
    return False


def _meter_device_name_for_entry(device_entry) -> str | None:
    for domain, identifier in getattr(device_entry, "identifiers", set()):
        if domain != DOMAIN:
            continue
        if not isinstance(identifier, str):
            continue
        match = _METER_DEVICE_RE.match(identifier)
        if not match:
            continue
        return meter_device_name(int(match.group(1), 16))
    return None


def _meter_device_name_needs_update(device_entry, expected_name: str) -> bool:
    if getattr(device_entry, "name_by_user", None):
        return False
    return getattr(device_entry, "name", None) != expected_name
