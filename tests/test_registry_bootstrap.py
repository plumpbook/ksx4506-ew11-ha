from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


def test_bootstrap_restores_known_entities_from_ha_registries():
    install_homeassistant_stubs()
    discovery = load_integration_module("discovery")
    bootstrap = load_integration_module("registry_bootstrap")

    registry = discovery.DeviceRegistry()
    entry = types.SimpleNamespace(entry_id="entry-a")
    hass = types.SimpleNamespace(
        entity_registry=types.SimpleNamespace(
            entries=[
                types.SimpleNamespace(
                    entity_id="light.living_1",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_0E11_light_1",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.living_outlet_power",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_3911_switch_power",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.ksx_60_01_sensor",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_6001_sensor",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.ew11_link",
                    config_entry_id="entry-a",
                    unique_id="ksx4506_entry-a_ew11_link",
                ),
            ]
        ),
        device_registry=types.SimpleNamespace(
            entries=[
                types.SimpleNamespace(
                    id="thermostat-zone-1",
                    config_entries={"entry-a"},
                    identifiers={("ksx4506_ew11", "361F_climate_ch1")},
                )
            ]
        ),
    )

    restored_count = asyncio.run(
        bootstrap.async_restore_registry_devices_from_ha(hass, entry, registry)
    )

    assert restored_count == 4
    assert sorted(registry.devices) == [
        "0E11_light_1",
        "361F_climate",
        "3911_switch",
        "6001_sensor",
    ]
    assert registry.devices["3911_switch"].state["power_w"] is None
    assert registry.devices["3911_switch"].state["status_sub_id"] == 0x1F
    assert registry.devices["361F_climate"].state["zones"] == [{"channel": 1}]


def test_startup_probe_targets_use_restored_status_subids():
    discovery = load_integration_module("discovery")
    coordinator_module = load_integration_module("coordinator")

    registry = discovery.DeviceRegistry()
    registry.restore_device_from_key("0E11_light_1")
    registry.restore_device_from_key("3911_switch")
    fake = types.SimpleNamespace(registry=registry)

    targets = coordinator_module.Ksx4506Coordinator._known_state_request_targets(fake)

    assert targets == [(0x0E, 0x11), (0x39, 0x1F)]
