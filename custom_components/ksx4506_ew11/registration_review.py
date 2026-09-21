"""Legacy identity review is deliberately separate from deletion eligibility."""
from typing import TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN


class RegisteredReview(TypedDict):
    device_id: str
    device_keys: list[str]
    name: str
    reason: str
    action: str


def registered_review(hass: HomeAssistant, entry_id: str,
                      verified_keys: set[str]) -> list[RegisteredReview]:
    """List unlabeled identities; lack of labels never authorizes removal."""
    devices, entities = dr.async_get(hass), er.async_get(hass)
    result: list[RegisteredReview] = []
    for device in dr.async_entries_for_config_entry(devices, entry_id):
        keys = sorted(key for domain, key in device.identifiers
                      if domain == DOMAIN and key != entry_id)
        if not keys or set(keys).issubset(verified_keys):
            continue
        members = er.async_entries_for_device(entities, device.id)
        user_labeled = (device.name_by_user or device.area_id
                        or any(e.name or e.area_id for e in members))
        if user_labeled:
            continue
        result.append(RegisteredReview(
            device_id=device.id, device_keys=keys, name=device.name or keys[0],
            reason="identity_not_user_confirmed", action="preserve_and_review",
        ))
    return result
