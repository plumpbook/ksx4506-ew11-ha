from collections import deque
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


def test_packet_capture_records_filtered_frames_with_limit():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    fake = types.SimpleNamespace(
        packet_capture_enabled=True,
        packet_capture_filter_text="33",
        packet_capture_filter={0x33},
        packet_capture_limit=1,
        packet_capture=deque(maxlen=1),
    )

    first = protocol_module.KsFrame(
        addr=0x33,
        sub_id=0x01,
        cmd=0x81,
        payload=bytes.fromhex("00 24 00"),
        checksum=0,
        raw=bytes.fromhex("F7 33 01 81 03 00 24 00 63 36"),
    )
    ignored = protocol_module.KsFrame(
        addr=0x40,
        sub_id=0x02,
        cmd=0x82,
        payload=bytes.fromhex("00 00"),
        checksum=0,
        raw=bytes.fromhex("F7 40 02 82 02 00 00 00 00"),
    )
    latest = protocol_module.KsFrame(
        addr=0x33,
        sub_id=0x01,
        cmd=0x43,
        payload=bytes.fromhex("80"),
        checksum=0,
        raw=bytes.fromhex("F7 33 01 43 01 80 07 F6"),
    )

    coordinator_module.Ksx4506Coordinator._capture_packet(fake, first)
    coordinator_module.Ksx4506Coordinator._capture_packet(fake, ignored)
    coordinator_module.Ksx4506Coordinator._capture_packet(fake, latest)
    report = coordinator_module.Ksx4506Coordinator.packet_capture_report(
        fake,
        include_packet_samples=True,
    )

    assert report["enabled"] is True
    assert report["filter"] == "33"
    assert report["limit"] == 1
    assert report["count"] == 1
    assert report["packets"][0]["device_id"] == "0x33"
    assert report["packets"][0]["command_type"] == "0x43"
    assert report["packets"][0]["payload_hex"] == "80"
    assert report["packets"][0]["raw_hex"] == "F7330143018007F6"


def test_packet_capture_report_splits_candidate_and_unsupported_packets():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    fake = types.SimpleNamespace(
        packet_capture_enabled=True,
        packet_capture_filter_text="",
        packet_capture_filter=None,
        packet_capture_limit=10,
        packet_capture=deque(maxlen=10),
    )

    supported = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0x11,
        cmd=0x81,
        payload=bytes.fromhex("00 01"),
        checksum=0,
        raw=bytes.fromhex("F7 0E 11 81 02 00 01 6D A0"),
    )
    unsupported = protocol_module.KsFrame(
        addr=0x39,
        sub_id=0x9F,
        cmd=0x52,
        payload=b"",
        checksum=0,
        raw=bytes.fromhex("F7 39 9F 52 00 C3 9A"),
    )
    candidate = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0xF1,
        cmd=0x81,
        payload=bytes.fromhex("00 01"),
        checksum=0,
        raw=bytes.fromhex("F7 0E F1 81 02 00 01 8D 80"),
    )

    coordinator_module.Ksx4506Coordinator._capture_packet(
        fake,
        supported,
        classification={"classification": "supported", "reason": None},
    )
    coordinator_module.Ksx4506Coordinator._capture_packet(
        fake,
        unsupported,
        classification={"classification": "unsupported", "reason": "unsupported_command"},
    )
    coordinator_module.Ksx4506Coordinator._capture_packet(
        fake,
        candidate,
        classification={"classification": "candidate", "reason": "unregistered_sub_id"},
    )

    report = coordinator_module.Ksx4506Coordinator.packet_capture_report(fake)

    assert report["classification_counts"] == {
        "candidate": 1,
        "ignored_request": 0,
        "supported": 1,
        "unsupported": 1,
    }
    assert [packet["command_type"] for packet in report["unsupported_packets"]] == ["0x52"]
    assert report["unsupported_packets"][0]["reason"] == "unsupported_command"
    assert [packet["sub_id"] for packet in report["candidate_packets"]] == ["0xF1"]
    assert report["candidate_packets"][0]["reason"] == "unregistered_sub_id"
    assert report["packets"][0]["classification"] == "candidate"
    assert report["packets"][1]["classification"] == "unsupported"
    assert report["packets"][2]["classification"] == "supported"
    assert report["packet_samples_redacted"] is True
    assert "raw_hex" not in repr(report)
    assert "payload_hex" not in repr(report)


def test_packet_capture_report_includes_readable_summary_fields():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    fake = types.SimpleNamespace(
        packet_capture_enabled=True,
        packet_capture_filter_text="",
        packet_capture_filter=None,
        packet_capture_limit=10,
        packet_capture=deque(maxlen=10),
    )

    unsupported = protocol_module.KsFrame(
        addr=0x99,
        sub_id=0x01,
        cmd=0x81,
        payload=bytes.fromhex("AA BB"),
        checksum=0,
        raw=bytes.fromhex("F7 99 01 81 02 AA BB 12 34"),
    )
    candidate = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0xF1,
        cmd=0x81,
        payload=bytes.fromhex("00 01"),
        checksum=0,
        raw=bytes.fromhex("F7 0E F1 81 02 00 01 8D 80"),
    )

    coordinator_module.Ksx4506Coordinator._capture_packet(
        fake,
        unsupported,
        classification={"classification": "unsupported", "reason": "unsupported_device_id"},
    )
    coordinator_module.Ksx4506Coordinator._capture_packet(
        fake,
        candidate,
        classification={"classification": "candidate", "reason": "unregistered_sub_id"},
    )

    report = coordinator_module.Ksx4506Coordinator.packet_capture_report(
        fake,
        include_packet_samples=True,
    )

    assert report["summary"] == (
        "supported=0, ignored_request=0, candidate=1, unsupported=1"
    )
    assert report["latest_packet_signature"] == (
        "candidate unregistered_sub_id 0x0E/0xF1/0x81 len=2"
    )
    assert report["latest_unsupported_signature"] == (
        "unsupported unsupported_device_id 0x99/0x01/0x81 len=2"
    )
    assert report["latest_candidate_signature"] == (
        "candidate unregistered_sub_id 0x0E/0xF1/0x81 len=2"
    )
    assert report["latest_unsupported"]["raw_hex"] == "F799018102AABB1234"
    assert report["latest_candidate"]["payload_hex"] == "0001"


def test_packet_capture_sensor_reports_coordinator_capture():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")

    include_samples = []

    def packet_capture_report(*, include_packet_samples=False):
        include_samples.append(include_packet_samples)
        return {
            "enabled": True,
            "filter": "33,40",
            "limit": 20,
            "count": 1,
            "packets": [{"device_id": "0x33"}],
        }

    coordinator = types.SimpleNamespace(
        packet_capture_report=packet_capture_report,
    )
    entry = types.SimpleNamespace(
        entry_id="entry-1",
        title="EW11 example",
        data={},
        options={},
    )

    entity = sensor_module.KsxPacketCaptureSensor(coordinator, entry)

    assert entity.native_value == 1
    assert entity.extra_state_attributes["packets"] == [{"device_id": "0x33"}]
    assert entity._attr_unique_id == "ksx4506_entry-1_packet_capture"
    assert include_samples == [False, False]


def test_packet_capture_sensor_honors_explicit_sample_exposure_option():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")
    include_samples = []

    def packet_capture_report(*, include_packet_samples=False):
        include_samples.append(include_packet_samples)
        return {"count": 1, "packets": [{"raw_hex": "F733"}]}

    coordinator = types.SimpleNamespace(packet_capture_report=packet_capture_report)
    entry = types.SimpleNamespace(
        entry_id="entry-1",
        title="EW11 example",
        data={},
        options={"expose_packet_samples": True},
    )

    entity = sensor_module.KsxPacketCaptureSensor(coordinator, entry)

    assert entity.extra_state_attributes["packets"] == [{"raw_hex": "F733"}]
    assert include_samples == [True]


def test_packet_quality_sensor_reports_coordinator_quality():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")

    report = {
        "state": "tx_giveups",
        "summary": "rx_checksum_errors=0, rx_frame_errors=0, tx_giveups=1",
        "rx": {"f7_checksum_errors": 0},
        "tx": {"giveups": 1},
    }
    include_samples = []

    def packet_quality_report(*, include_packet_samples=False):
        include_samples.append(include_packet_samples)
        return report

    coordinator = types.SimpleNamespace(packet_quality_report=packet_quality_report)
    entry = types.SimpleNamespace(
        entry_id="entry-1",
        title="EW11 example",
        data={},
        options={},
    )

    entity = sensor_module.KsxPacketQualitySensor(coordinator, entry)

    assert entity.native_value == "tx_giveups"
    assert entity.extra_state_attributes["tx"]["giveups"] == 1
    assert entity._attr_unique_id == "ksx4506_entry-1_packet_quality"
    assert entity._attr_entity_registry_enabled_default is False
    assert include_samples == [False, False]


def test_device_vitality_sensor_reports_protocol_endpoint_health():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")

    report = {
        "state": "unresponsive",
        "total": 2,
        "healthy": 1,
        "unresponsive": 1,
        "devices": [{"endpoint": "0x39/0x11", "status": "unresponsive"}],
    }
    coordinator = types.SimpleNamespace(device_vitality_report=lambda: report)
    entry = types.SimpleNamespace(entry_id="entry-1", title="EW11 example")

    entity = sensor_module.KsxDeviceVitalitySensor(coordinator, entry)

    assert entity.native_value == "unresponsive"
    assert entity.extra_state_attributes["unresponsive"] == 1
    assert entity.extra_state_attributes["devices"][0]["endpoint"] == "0x39/0x11"
    assert entity._attr_unique_id == "ksx4506_entry-1_device_vitality"
    assert entity._attr_entity_registry_enabled_default is True


def test_ew11_link_sensor_reports_connection_health():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")

    report = {
        "state": "stale",
        "connected": True,
        "last_rx_at": "2026-06-14T10:00:00+00:00",
        "seconds_since_last_rx": 180.0,
        "rx_stale_after": 120.0,
        "last_error": None,
    }
    coordinator = types.SimpleNamespace(ew11_health_report=lambda: report)
    entry = types.SimpleNamespace(entry_id="entry-1", title="EW11 example")

    entity = sensor_module.KsxEw11LinkSensor(coordinator, entry)

    assert entity.native_value == "stale"
    assert entity.extra_state_attributes["connected"] is True
    assert entity.extra_state_attributes["seconds_since_last_rx"] == 180.0
    assert entity._attr_unique_id == "ksx4506_entry-1_ew11_link"


def test_unsupported_packets_sensor_reports_unique_signatures_as_state():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")

    report = {
        "total_seen": 42,
        "unsupported_seen": 42,
        "candidate_seen": 0,
        "unique_signatures": 2,
        "latest_packet": None,
        "packet_samples_redacted": True,
        "packets": [],
        "unsupported_packets": [],
        "candidate_packets": [],
    }
    coordinator = types.SimpleNamespace(
        registry=types.SimpleNamespace(
            unsupported_packet_report=lambda **_: report,
        )
    )
    entry = types.SimpleNamespace(
        entry_id="entry-1",
        title="EW11 example",
        data={},
        options={},
    )

    entity = sensor_module.KsxUnsupportedPacketsSensor(coordinator, entry)

    assert entity.native_value == 2
    assert entity.extra_state_attributes["total_seen"] == 42


def test_diagnostic_sensor_coalesces_frame_updates_within_one_second(monkeypatch):
    install_homeassistant_stubs()
    diagnostic_module = load_integration_module("diagnostic_sensors")
    times = iter((100.0, 100.2, 101.1))
    monkeypatch.setattr(diagnostic_module, "monotonic", lambda: next(times))
    coordinator = types.SimpleNamespace(
        _last_changed_device_keys=frozenset({"3911_switch"}),
        ew11_health_report=lambda: {"state": "receiving"},
    )
    entry = types.SimpleNamespace(entry_id="entry-1", title="EW11 example")
    entity = diagnostic_module.KsxEw11LinkSensor(coordinator, entry)
    writes = []
    entity.async_write_ha_state = lambda: writes.append("write")

    entity._handle_coordinator_update()
    entity._handle_coordinator_update()
    entity._handle_coordinator_update()

    assert writes == ["write", "write"]


def test_diagnostic_sensor_publishes_global_health_update_immediately(monkeypatch):
    install_homeassistant_stubs()
    diagnostic_module = load_integration_module("diagnostic_sensors")
    times = iter((100.0, 100.2))
    monkeypatch.setattr(diagnostic_module, "monotonic", lambda: next(times))
    coordinator = types.SimpleNamespace(
        _last_changed_device_keys=frozenset({"3911_switch"}),
        ew11_health_report=lambda: {"state": "receiving"},
    )
    entry = types.SimpleNamespace(entry_id="entry-1", title="EW11 example")
    entity = diagnostic_module.KsxEw11LinkSensor(coordinator, entry)
    writes = []
    entity.async_write_ha_state = lambda: writes.append("write")

    entity._handle_coordinator_update()
    coordinator._last_changed_device_keys = None
    entity._handle_coordinator_update()

    assert writes == ["write", "write"]
