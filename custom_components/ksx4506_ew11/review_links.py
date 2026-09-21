"""Resolve review shortcuts from the current entry's Home Assistant devices."""
from collections.abc import Mapping
from html import escape
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .const import DOMAIN


def device_review_links(hass: HomeAssistant, entry_id: str) -> Mapping[str, str]:
    """Return safe display labels and device routes indexed by protocol identity."""
    devices, entities, areas = dr.async_get(hass), er.async_get(hass), ar.async_get(hass)
    links: dict[str, str] = {}
    for device in dr.async_entries_for_config_entry(devices, entry_id):
        keys = sorted(key for domain, key in device.identifiers
                      if domain == DOMAIN and key != entry_id)
        if not keys:
            continue
        members = [e for e in er.async_entries_for_device(entities, device.id)
                   if e.config_entry_id == entry_id]
        if len(device.config_entries) > 1:
            owned_ids = {e.unique_id for e in members if e.platform == DOMAIN}
            keys = [key for key in keys if f"ksx4506_{key}" in owned_ids]
            if not keys:
                continue
        primary = next((e for e in members if e.entity_category is None), None)
        name = device.name_by_user or (primary.name if primary else None) or device.name or keys[0]
        area_id = (primary.area_id if primary else None) or device.area_id
        area = areas.async_get_area(area_id) if area_id else None
        label = f"{area.name if area else '영역 미지정'} · {name}"
        label = re.sub(r"([\\`*_\[\]{}()#+.!|>~-])", r"\\\1", escape(" ".join(label.split())))
        line = f"{label} — [기기 상세 열기](/config/devices/device/{device.id})"
        for key in keys:
            links[key] = line
    return links
