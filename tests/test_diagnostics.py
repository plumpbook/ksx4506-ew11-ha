from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402

install_homeassistant_stubs()
const = load_integration_module("const")
discovery = load_integration_module("discovery")
diagnostics = load_integration_module("diagnostics")


class _FakeCoordinator:
    def __init__(self):
        self.registry = discovery.DeviceRegistry()


def test_config_entry_diagnostics_include_unsupported_packets_and_redact_host():
    coordinator = _FakeCoordinator()
    coordinator.registry.upsert_from_frame(
        0x99,
        0x01,
        0x81,
        bytes.fromhex("AA BB"),
        "f799018102aabb1234",
    )

    entry = types.SimpleNamespace(
        entry_id="entry-1",
        title="EW11 ew11.example.invalid",
        data={
            "host": "ew11.example.invalid",
            "port": 8899,
        },
    )
    hass = types.SimpleNamespace(data={const.DOMAIN: {entry.entry_id: coordinator}})

    data = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
    assert data["config_entry"]["title"] == "EW11 **REDACTED**"
    assert data["config_entry"]["data"]["host"] == "**REDACTED**"
    assert data["config_entry"]["data"]["port"] == 8899
    assert data["unsupported_packets"]["total_seen"] == 1
    assert data["unsupported_packets"]["packets"][0]["device_id"] == "0x99"
    assert "unsupported_packet.yml" in data["report_url"]
