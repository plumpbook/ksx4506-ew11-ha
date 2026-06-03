from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeEntityRegistry:
    def __init__(self, entries):
        self.entries = entries
        self.removed = []
        self.updated = []

    def async_remove(self, entity_id):
        self.removed.append(entity_id)

    def async_update_entity(self, entity_id, **kwargs):
        self.updated.append((entity_id, kwargs))


class _FakeDeviceRegistry:
    def __init__(self, entries):
        self.entries = entries
        self.updated = []

    def async_update_device(self, device_id, **kwargs):
        self.updated.append((device_id, kwargs))


def test_remove_entry_cleans_entities_and_devices_for_config_entry():
    install_homeassistant_stubs()
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


def test_setup_prunes_legacy_outlet_group_channel_registry_entries():
    install_homeassistant_stubs()
    integration = load_integration_module("__init__")
    entry = types.SimpleNamespace(entry_id="entry-a")
    hass = types.SimpleNamespace(
        entity_registry=_FakeEntityRegistry(
            [
                types.SimpleNamespace(
                    entity_id="switch.legacy_group",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_395F_switch_ch1",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.legacy_group_power",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_395F_switch_ch1_power",
                ),
                types.SimpleNamespace(
                    entity_id="switch.current_outlet",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_3951_switch",
                ),
                types.SimpleNamespace(
                    entity_id="number.legacy_target_temperature",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_361F_climate_ch1_target_temperature",
                ),
                types.SimpleNamespace(
                    entity_id="climate.legacy_individual_thermostat",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_3611_climate_ch1",
                ),
                types.SimpleNamespace(
                    entity_id="switch.legacy_individual_heat",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_3611_climate_ch1_heat",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.legacy_unknown_packet",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_B314_unknown",
                ),
                types.SimpleNamespace(
                    entity_id="climate.current_thermostat",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_361F_climate_ch1",
                    original_name="Climate",
                ),
                types.SimpleNamespace(
                    entity_id="climate.legacy_named_thermostat",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_361F_climate_ch2",
                    original_name="Target Temperature",
                ),
                types.SimpleNamespace(
                    entity_id="number.other_entry_legacy_target_temperature",
                    config_entry_id="entry-b",
                    unique_id="ksx4506_361F_climate_ch1_target_temperature",
                ),
                types.SimpleNamespace(
                    entity_id="switch.other_entry_legacy_group",
                    config_entry_id="entry-b",
                    unique_id="ksx4506_395F_switch_ch1",
                ),
            ]
        ),
        device_registry=_FakeDeviceRegistry(
            [
                types.SimpleNamespace(
                    id="legacy-device",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "395F_switch_ch1")},
                ),
                types.SimpleNamespace(
                    id="legacy-thermostat-device",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "3611_climate_ch1")},
                ),
                types.SimpleNamespace(
                    id="legacy-unknown-device",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "B314_unknown")},
                ),
                types.SimpleNamespace(
                    id="current-device",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "3951_switch")},
                ),
                types.SimpleNamespace(
                    id="legacy-meter-device",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "3003_sensor")},
                    name="KSX 30-03",
                    name_by_user=None,
                ),
                types.SimpleNamespace(
                    id="user-named-meter-device",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "3004_sensor")},
                    name="KSX 30-04",
                    name_by_user="My Hot Water",
                ),
                types.SimpleNamespace(
                    id="other-entry-legacy-device",
                    config_entries={"entry-b"},
                    identifiers={("ksx4506_ew11", "395F_switch_ch1")},
                ),
            ]
        ),
    )

    integration._async_prune_legacy_outlet_group_registry_entries(hass, entry)

    assert hass.entity_registry.removed == [
        "switch.legacy_group",
        "sensor.legacy_group_power",
        "number.legacy_target_temperature",
        "climate.legacy_individual_thermostat",
        "switch.legacy_individual_heat",
        "sensor.legacy_unknown_packet",
    ]
    assert hass.entity_registry.updated == [
        ("climate.legacy_named_thermostat", {"original_name": "Climate"}),
    ]
    assert hass.device_registry.updated == [
        ("legacy-device", {"remove_config_entry_id": "entry-a"}),
        ("legacy-thermostat-device", {"remove_config_entry_id": "entry-a"}),
        ("legacy-unknown-device", {"remove_config_entry_id": "entry-a"}),
        ("legacy-meter-device", {"name": "Electric Meter 30-03"}),
    ]


def test_setup_prunes_legacy_entries_from_registry_fallback_scan():
    install_homeassistant_stubs()
    integration = load_integration_module("__init__")
    entry = types.SimpleNamespace(entry_id="entry-a")
    hass = types.SimpleNamespace(
        entity_registry=_FakeEntityRegistry([]),
        device_registry=_FakeDeviceRegistry([]),
    )
    hass.entity_registry.entities = {
        "climate.fallback_legacy": types.SimpleNamespace(
            entity_id="climate.fallback_legacy",
            config_entry_id="entry-a",
            platform="ksx4506_ew11",
            unique_id="ksx4506_3611_climate_ch1",
        )
    }
    hass.device_registry.devices = {
        "fallback-device": types.SimpleNamespace(
            id="fallback-device",
            config_entries={"entry-a"},
            identifiers={("ksx4506_ew11", "3611_climate_ch1")},
        )
    }

    integration._async_prune_legacy_registry_entries(hass, entry)

    assert hass.entity_registry.removed == ["climate.fallback_legacy"]
    assert hass.device_registry.updated == [
        ("fallback-device", {"remove_config_entry_id": "entry-a"}),
    ]
