from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402


def _install_homeassistant_stubs():
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        pass

    config_entries.ConfigEntry = ConfigEntry

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    core.HomeAssistant = HomeAssistant

    helpers = types.ModuleType("homeassistant.helpers")

    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_send = lambda *args, **kwargs: None

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __init__(self, *args, **kwargs):
            pass

        def __class_getitem__(cls, item):
            return cls

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator

    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda hass: hass.entity_registry
    entity_registry.async_entries_for_config_entry = (
        lambda registry, entry_id: [
            entry
            for entry in registry.entries
            if entry.config_entry_id == entry_id
        ]
    )

    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry.async_get = lambda hass: hass.device_registry
    device_registry.async_entries_for_config_entry = (
        lambda registry, entry_id: [
            entry
            for entry in registry.entries
            if entry_id in entry.config_entries
        ]
    )

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry
    sys.modules["homeassistant.helpers.device_registry"] = device_registry


class _FakeEntityRegistry:
    def __init__(self, entries):
        self.entries = entries
        self.removed = []

    def async_remove(self, entity_id):
        self.removed.append(entity_id)


class _FakeDeviceRegistry:
    def __init__(self, entries):
        self.entries = entries
        self.updated = []

    def async_update_device(self, device_id, **kwargs):
        self.updated.append((device_id, kwargs))


def test_remove_entry_cleans_entities_and_devices_for_config_entry():
    _install_homeassistant_stubs()
    integration = load_integration_module("__init__")
    entry = types.SimpleNamespace(entry_id="entry-a")
    hass = types.SimpleNamespace(
        entity_registry=_FakeEntityRegistry(
            [
                types.SimpleNamespace(
                    entity_id="switch.ksx_old",
                    config_entry_id="entry-a",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.other_entry",
                    config_entry_id="entry-b",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.ksx_old_power",
                    config_entry_id="entry-a",
                ),
            ]
        ),
        device_registry=_FakeDeviceRegistry(
            [
                types.SimpleNamespace(
                    id="device-a",
                    config_entries={"entry-a"},
                ),
                types.SimpleNamespace(
                    id="device-shared",
                    config_entries={"entry-a", "entry-b"},
                ),
                types.SimpleNamespace(
                    id="device-other",
                    config_entries={"entry-b"},
                ),
            ]
        ),
    )

    asyncio.run(integration.async_remove_entry(hass, entry))

    assert hass.entity_registry.removed == [
        "switch.ksx_old",
        "sensor.ksx_old_power",
    ]
    assert hass.device_registry.updated == [
        ("device-a", {"remove_config_entry_id": "entry-a"}),
        ("device-shared", {"remove_config_entry_id": "entry-a"}),
    ]
