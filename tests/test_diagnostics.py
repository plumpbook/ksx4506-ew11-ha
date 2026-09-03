from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402

install_homeassistant_stubs()
const = load_integration_module("const")
discovery = load_integration_module("discovery")
diagnostics = load_integration_module("diagnostics")


class _FakeCoordinator:
    def __init__(self):
        self.registry = discovery.DeviceRegistry()
        self.packet_quality_include_samples = None

    def ew11_health_report(self):
        return {
            "state": "stale",
            "connected": True,
            "last_rx_at": "2026-06-14T10:00:00+00:00",
            "seconds_since_last_rx": 180.0,
            "rx_stale_after": 120.0,
            "last_error": "Connect call failed for ew11.example.invalid",
            "host": "ew11.example.invalid",
        }

    def packet_quality_report(self, *, include_packet_samples=False):
        self.packet_quality_include_samples = include_packet_samples
        report = {
            "state": "rx_errors",
            "summary": "rx_checksum_errors=1, rx_frame_errors=0, tx_giveups=0",
            "rx": {
                "f7_checksum_errors": 1,
                "f7_frame_errors": 0,
                "stx_checksum_errors": 0,
                "stx_frame_errors": 0,
                "last_error": {"raw_hex": "F70E11810200010000"},
            },
            "tx": {
                "giveups": 0,
                "control_giveups": 0,
                "state_request_giveups": 0,
                "last_giveup": {"payload_hex": "010100"},
            },
        }
        if not include_packet_samples:
            report["rx"]["last_error"] = {}
            report["tx"]["last_giveup"] = {}
        return report

    def device_vitality_report(self):
        return {
            "state": "healthy",
            "total": 1,
            "healthy": 1,
            "unresponsive": 0,
            "stale": 0,
            "event_only": 0,
            "unknown": 0,
            "devices": [{"endpoint": "0x39/0x11", "status": "healthy"}],
        }


def test_config_entry_diagnostics_include_unsupported_packets_and_redact_host():
    coordinator = _FakeCoordinator()
    coordinator.registry.upsert_from_frame(
        0x99,
        0x01,
        0x81,
        bytes.fromhex("AA BB"),
        "f799018102aabb1234",
    )
    coordinator.registry.upsert_from_frame(
        0x0E,
        0xF1,
        0x81,
        bytes.fromhex("00 01"),
        "f70ef1810200011234",
    )

    entry = types.SimpleNamespace(
        entry_id="entry-1",
        title="EW11 ew11.example.invalid",
        data={
            "host": "ew11.example.invalid",
            "port": 8899,
            const.CONF_EXPOSE_PACKET_SAMPLES: False,
        },
    )
    hass = types.SimpleNamespace(data={const.DOMAIN: {entry.entry_id: coordinator}})

    data = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
    assert data["config_entry"]["title"] == "EW11 **REDACTED**"
    assert data["config_entry"]["data"]["host"] == "**REDACTED**"
    assert data["config_entry"]["data"]["port"] == 8899
    assert data["unsupported_packets"]["total_seen"] == 2
    assert data["unsupported_packets"]["unsupported_seen"] == 1
    assert data["unsupported_packets"]["candidate_seen"] == 1
    assert data["unsupported_packets"]["packet_samples_redacted"] is True
    assert data["unsupported_packets"]["latest_packet"]["device_id"] == "0x0E"
    assert "last_raw_hex" not in data["unsupported_packets"]["latest_packet"]
    assert "last_payload_hex" not in data["unsupported_packets"]["latest_packet"]
    assert data["unsupported_packets"]["unsupported_packets"][0]["device_id"] == "0x99"
    assert data["unsupported_packets"]["candidate_packets"][0]["device_id"] == "0x0E"
    assert data["unsupported_packets"]["candidate_packets"][0]["sub_id"] == "0xF1"
    assert data["ew11_connection"]["state"] == "stale"
    assert data["ew11_connection"]["seconds_since_last_rx"] == 180.0
    assert data["device_vitality"]["state"] == "healthy"
    assert data["device_vitality"]["devices"][0]["endpoint"] == "0x39/0x11"
    assert data["packet_quality"]["state"] == "rx_errors"
    assert data["packet_quality"]["rx"]["f7_checksum_errors"] == 1
    assert data["ew11_connection"]["host"] == "**REDACTED**"
    assert data["ew11_connection"]["last_error"] == (
        "Connect call failed for **REDACTED**"
    )
    assert "raw_hex" not in repr(data["packet_quality"])
    assert "payload_hex" not in repr(data["packet_quality"])
    assert coordinator.packet_quality_include_samples is False
    assert "ew11.example.invalid" not in repr(data)
    assert "unsupported_packet.yml" in data["report_url"]


def test_config_entry_diagnostics_can_include_packet_samples_when_enabled():
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
            const.CONF_EXPOSE_PACKET_SAMPLES: False,
        },
        options={const.CONF_EXPOSE_PACKET_SAMPLES: True},
    )
    hass = types.SimpleNamespace(data={const.DOMAIN: {entry.entry_id: coordinator}})

    data = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert data["unsupported_packets"]["packet_samples_redacted"] is False
    assert data["config_entry"]["data"][const.CONF_EXPOSE_PACKET_SAMPLES] is True
    assert data["unsupported_packets"]["latest_packet"]["last_payload_hex"] == "AABB"
    assert data["unsupported_packets"]["latest_packet"]["last_raw_hex"] == "F799018102AABB1234"
    assert data["packet_quality"]["rx"]["last_error"]["raw_hex"] == "F70E11810200010000"
    assert data["packet_quality"]["tx"]["last_giveup"]["payload_hex"] == "010100"
    assert coordinator.packet_quality_include_samples is True
