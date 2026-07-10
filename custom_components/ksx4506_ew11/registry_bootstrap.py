from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .discovery import DeviceRegistry

_PREFIX = "ksx4506_"
_LIGHT_RE = re.compile(r"^(0E[0-9A-F]{2}_light(?:_\d+)?)$", re.IGNORECASE)
_OUTLET_RE = re.compile(
    r"^(39[0-9A-F]{2}_switch)(?:_(power|threshold|auto_cut|under_threshold|overload))?$",
    re.IGNORECASE,
)
_METER_RE = re.compile(r"^(30[0-9A-F]{2}_sensor)_(instant|total)$", re.IGNORECASE)
_GENERIC_SENSOR_RE = re.compile(r"^(60[0-9A-F]{2}_sensor)$", re.IGNORECASE)
_GAS_RE = re.compile(
    r"^(12[0-9A-F]{2}_gas_valve)(?:_(leak|moving))?$",
    re.IGNORECASE,
)
_ENTRANCE_RE = re.compile(
    r"^(33[0-9A-F]{2}_entrance_panel)(?:_[a-z0-9_]+)?$",
    re.IGNORECASE,
)
_COMMON_ENTRANCE_RE = re.compile(
    r"^(40[0-9A-F]{2}_common_entrance)$",
    re.IGNORECASE,
)
_CLIMATE_RE = re.compile(
    r"^(36[0-9A-F]{2}_climate)(?:_ch(\d+))?(?:_(heat|target_temperature))?$",
    re.IGNORECASE,
)
_DEVICE_IDENTIFIER_RE = re.compile(
    r"^([0-9A-F]{4}_(?:light(?:_\d+)?|switch|sensor|gas_valve|entrance_panel|common_entrance|climate)(?:_ch\d+)?)$",
    re.IGNORECASE,
)


@dataclass
class RegistryDeviceHint:
    key: str
    state_hints: set[str] = field(default_factory=set)
    channel_hints: set[int] = field(default_factory=set)


async def async_restore_registry_devices_from_ha(
    hass: HomeAssistant,
    entry: ConfigEntry,
    registry: DeviceRegistry,
) -> int:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    hints = [
        *_hints_from_entity_entries(
            er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        ),
        *_hints_from_device_entries(
            dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        ),
    ]
    return restore_registry_devices_from_hints(registry, hints)


def restore_registry_devices_from_hints(
    registry: DeviceRegistry,
    hints: Iterable[RegistryDeviceHint],
) -> int:
    restored_keys: set[str] = set()
    for hint in _merge_hints(hints).values():
        restored = registry.restore_device_from_key(
            hint.key,
            state_hints=hint.state_hints,
            channel_hints=hint.channel_hints,
        )
        if restored is not None:
            restored_keys.add(restored[0].key)
    return len(restored_keys)


def _hints_from_entity_entries(entries: Iterable[Any]) -> list[RegistryDeviceHint]:
    hints: list[RegistryDeviceHint] = []
    for entry in entries:
        hint = _hint_from_unique_id(getattr(entry, "unique_id", None))
        if hint is not None:
            hints.append(hint)
    return hints


def _hints_from_device_entries(entries: Iterable[Any]) -> list[RegistryDeviceHint]:
    hints: list[RegistryDeviceHint] = []
    for entry in entries:
        for domain, identifier in getattr(entry, "identifiers", set()):
            if domain != DOMAIN or not isinstance(identifier, str):
                continue
            hint = _hint_from_device_identifier(identifier)
            if hint is not None:
                hints.append(hint)
    return hints


def _hint_from_unique_id(unique_id: str | None) -> RegistryDeviceHint | None:
    if not isinstance(unique_id, str) or not unique_id.startswith(_PREFIX):
        return None

    body = unique_id[len(_PREFIX) :]
    for matcher in (
        _light_hint,
        _outlet_hint,
        _meter_hint,
        _generic_sensor_hint,
        _gas_hint,
        _entrance_hint,
        _common_entrance_hint,
        _climate_hint,
    ):
        hint = matcher(body)
        if hint is not None:
            return hint
    return None


def _hint_from_device_identifier(identifier: str) -> RegistryDeviceHint | None:
    match = _DEVICE_IDENTIFIER_RE.match(identifier)
    if match is None:
        return None

    value = match.group(1).upper()
    climate_channel = re.match(r"^(36[0-9A-F]{2}_CLIMATE)_CH(\d+)$", value)
    if climate_channel is not None:
        return RegistryDeviceHint(
            key=climate_channel.group(1).lower(),
            channel_hints={int(climate_channel.group(2))},
        )
    return RegistryDeviceHint(key=value.lower())


def _light_hint(body: str) -> RegistryDeviceHint | None:
    match = _LIGHT_RE.match(body)
    if match is None:
        return None
    return RegistryDeviceHint(key=match.group(1).upper())


def _outlet_hint(body: str) -> RegistryDeviceHint | None:
    match = _OUTLET_RE.match(body)
    if match is None:
        return None

    state_hints: set[str] = set()
    suffix = match.group(2)
    if suffix == "power":
        state_hints.add("power_w")
    elif suffix == "threshold":
        state_hints.add("threshold_w")
    return RegistryDeviceHint(key=match.group(1).upper(), state_hints=state_hints)


def _meter_hint(body: str) -> RegistryDeviceHint | None:
    match = _METER_RE.match(body)
    if match is None:
        return None
    return RegistryDeviceHint(
        key=match.group(1).upper(),
        state_hints={match.group(2).lower()},
    )


def _generic_sensor_hint(body: str) -> RegistryDeviceHint | None:
    match = _GENERIC_SENSOR_RE.match(body)
    if match is None:
        return None
    return RegistryDeviceHint(key=match.group(1).upper())


def _gas_hint(body: str) -> RegistryDeviceHint | None:
    match = _GAS_RE.match(body)
    if match is None:
        return None
    return RegistryDeviceHint(key=match.group(1).upper())


def _entrance_hint(body: str) -> RegistryDeviceHint | None:
    match = _ENTRANCE_RE.match(body)
    if match is None:
        return None
    return RegistryDeviceHint(key=match.group(1).upper())


def _common_entrance_hint(body: str) -> RegistryDeviceHint | None:
    match = _COMMON_ENTRANCE_RE.match(body)
    if match is None:
        return None
    return RegistryDeviceHint(key=match.group(1).upper())


def _climate_hint(body: str) -> RegistryDeviceHint | None:
    match = _CLIMATE_RE.match(body)
    if match is None:
        return None

    channel = match.group(2)
    channels = {int(channel)} if channel is not None else set()
    return RegistryDeviceHint(
        key=match.group(1).upper(),
        channel_hints=channels,
    )


def _merge_hints(
    hints: Iterable[RegistryDeviceHint],
) -> dict[str, RegistryDeviceHint]:
    merged: dict[str, RegistryDeviceHint] = {}
    for hint in hints:
        key = hint.key.upper()
        existing = merged.get(key)
        if existing is None:
            merged[key] = RegistryDeviceHint(
                key=key,
                state_hints=set(hint.state_hints),
                channel_hints=set(hint.channel_hints),
            )
            continue
        existing.state_hints.update(hint.state_hints)
        existing.channel_hints.update(hint.channel_hints)
    return merged
