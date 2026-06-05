from collections import deque
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402


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
    report = coordinator_module.Ksx4506Coordinator.packet_capture_report(fake)

    assert report["enabled"] is True
    assert report["filter"] == "33"
    assert report["limit"] == 1
    assert report["count"] == 1
    assert report["packets"][0]["device_id"] == "0x33"
    assert report["packets"][0]["command_type"] == "0x43"
    assert report["packets"][0]["payload_hex"] == "80"
    assert report["packets"][0]["raw_hex"] == "F7330143018007F6"


def test_packet_capture_sensor_reports_coordinator_capture():
    install_homeassistant_stubs()
    sensor_module = load_integration_module("sensor")

    coordinator = types.SimpleNamespace(
        packet_capture_report=lambda: {
            "enabled": True,
            "filter": "33,40",
            "limit": 20,
            "count": 1,
            "packets": [{"device_id": "0x33"}],
        }
    )
    entry = types.SimpleNamespace(entry_id="entry-1", title="EW11 example")

    entity = sensor_module.KsxPacketCaptureSensor(coordinator, entry)

    assert entity.native_value == 1
    assert entity.extra_state_attributes["packets"] == [{"device_id": "0x33"}]
    assert entity._attr_unique_id == "ksx4506_entry-1_packet_capture"
