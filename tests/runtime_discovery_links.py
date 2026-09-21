"""Exercise notification shortcuts against real HA registries, without a bridge."""
import asyncio  # noqa: ANYIO_OK - Home Assistant owns the test runtime
import re
import tempfile
from types import MappingProxyType

from homeassistant.components import persistent_notification as pn
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from custom_components.ksx4506_ew11.const import DOMAIN
from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11.discovery_runtime import DiscoveryRuntime
from custom_components.ksx4506_ew11.review_links import device_review_links


async def main() -> None:
    # Given real HA registries, more than 20 review items, and another EW11 entry.
    with tempfile.TemporaryDirectory(prefix="ew11-links-") as directory:
        hass = HomeAssistant(directory)
        hass.config_entries = ConfigEntries(hass, {})
        entries = [ConfigEntry(
            domain=DOMAIN, title=title, data={}, options={}, source="user",
            version=1, minor_version=1, unique_id=title,
            discovery_keys=MappingProxyType({}), subentries_data=None,
        ) for title in ("Primary", "Other")]
        for entry in entries:
            hass.config_entries._entries[entry.entry_id] = entry
        await dr.async_load(hass)
        await er.async_load(hass)
        await ar.async_load(hass)
        devices = dr.async_get(hass)
        area = ar.async_get(hass).async_create("거실")
        owner = entries[0].entry_id
        key = "0E11_light_2"
        real = devices.async_get_or_create(
            config_entry_id=owner, identifiers={(DOMAIN, key)}, name="Factory name",
        )
        devices.async_update_device(real.id, name_by_user="거실 조명2", area_id=area.id)
        legacy = [devices.async_get_or_create(
            config_entry_id=owner, identifiers={(DOMAIN, f"0E{i:02X}_light_1")},
            name=f"Unnamed {i}",
        ) for i in range(32, 57)]
        foreign = devices.async_get_or_create(
            config_entry_id=entries[1].entry_id, identifiers={(DOMAIN, "0E99_light_1")},
            name="Other bridge",
        )
        coordinator = Ksx4506Coordinator(hass, {
            "host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0,
        }, entry=entries[0])
        runtime = DiscoveryRuntime(coordinator, owner)
        coordinator.registry._cleanup_candidates.record(key, reason="reported_channel_count_shrank")
        coordinator.registry._cleanup_candidates.record("missing_key", reason="reported_channel_count_shrank")
        coordinator.registry._cleanup_candidates.record("0E99_light_1", reason="reported_channel_count_shrank")
        before = set(devices.devices)
        try:
            # When the existing notification is produced.
            runtime._notify()
            message = pn._async_get_or_create_notifications(hass)[runtime.notification_id]["message"]
            # Then every registered review item has its own actual device route.
            routes = re.findall(r"\]\((/config/devices/device/[^)]+)\)", message)
            expected = {f"/config/devices/device/{d.id}" for d in [real, *legacy]}
            assert set(routes) == expected, (routes, expected)
            assert f"/config/devices/device/{foreign.id}" not in message
            assert "/config/devices/device/missing_key" not in message
            assert "거실 조명2" in message and "거실" in message
            assert before == set(devices.devices)

            # When a user renames or moves a still-pending device.
            devices.async_update_device(real.id, name_by_user="새 이름 [test](https://invalid.example)")
            runtime._notify()
            renamed = pn._async_get_or_create_notifications(hass)[runtime.notification_id]["message"]
            # Then the notification refreshes without allowing a label to inject a link.
            assert renamed != message
            assert set(re.findall(r"\]\(([^)]+)\)", renamed)) == expected | {
                f"/config/integrations/integration/{DOMAIN}",
            }

            # When only the device's area changes, the shortcut stays on that device.
            other_area = ar.async_get(hass).async_create("드레스룸")
            devices.async_update_device(real.id, area_id=other_area.id)
            runtime._notify()
            moved = pn._async_get_or_create_notifications(hass)[runtime.notification_id]["message"]
            assert moved != renamed and "드레스룸" in moved
            assert set(re.findall(r"\]\((/config/devices/device/[^)]+)\)", moved)) == expected

            # Given a merged device also associated with another EW11 entry.
            er.async_get(hass).async_get_or_create(
                "light", DOMAIN, f"ksx4506_{key}", config_entry=entries[0], device_id=real.id,
            )
            devices.async_get_or_create(
                config_entry_id=entries[1].entry_id,
                identifiers={(DOMAIN, key), (DOMAIN, "0EFF_light_1")},
            )
            # When resolving shortcuts, only entity-backed keys belong to this entry.
            shared = device_review_links(hass, owner)
            assert key in shared
            assert "0EFF_light_1" not in shared

            # When the registry item disappears while a review key remains.
            devices.async_remove_device(real.id)
            runtime._notify()
            removed = pn._async_get_or_create_notifications(hass)[runtime.notification_id]["message"]
            # Then no stale direct route is kept in the refreshed notification.
            assert f"/config/devices/device/{real.id}" not in removed
        finally:
            await hass.async_stop()
        print("Real HA review shortcuts, full list, isolation, rename and stale-link checks passed")


if __name__ == "__main__":
    asyncio.run(main())
