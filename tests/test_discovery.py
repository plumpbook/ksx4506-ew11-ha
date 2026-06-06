from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402

_module = load_integration_module("discovery")
DeviceRegistry = _module.DeviceRegistry


def test_group_light_payload_expands_channels_with_standard_control_subids():
    reg = DeviceRegistry()
    changes = reg.upsert_from_frame(0x0E, 0x1F, 0x81, bytes([0x00, 0x01, 0x00, 0x01]), "f7...")

    assert len(changes) == 3
    keys = sorted(k for k in reg.devices.keys())
    assert keys == ["0E1F_light_1", "0E1F_light_2", "0E1F_light_3"]
    assert reg.devices["0E1F_light_1"].state["on"] is True
    assert reg.devices["0E1F_light_1"].state["dimmable"] is False
    assert reg.devices["0E1F_light_1"].state["status_sub_id"] == 0x1F
    assert reg.devices["0E1F_light_1"].state["control_sub_id"] == 0x11
    assert "control_channel" not in reg.devices["0E1F_light_1"].state
    assert reg.devices["0E1F_light_2"].state["on"] is False
    assert reg.devices["0E1F_light_2"].state["control_sub_id"] == 0x12
    assert "control_channel" not in reg.devices["0E1F_light_2"].state
    assert reg.devices["0E1F_light_3"].state["on"] is True


def test_light_status_byte_dimming_decode():
    reg = DeviceRegistry()
    # [err=0x00, state=0xA3] => dim step 10, dimmable, ON
    reg.upsert_from_frame(0x0E, 0x01, 0x81, bytes([0x00, 0xA3]), "f7...")
    d = reg.devices["0E01_light"]
    assert d.state["on"] is True
    assert d.state["dimmable"] is True
    assert d.state["brightness_step"] == 0x0A


def test_suroup_light_module_subids_expand_own_channels():
    reg = DeviceRegistry()

    reg.upsert_from_frame(
        0x0E,
        0x11,
        0x81,
        bytes.fromhex("00 00 00 00"),
        "f70e118104000000006d08",
    )
    reg.upsert_from_frame(0x0E, 0x12, 0x81, bytes.fromhex("00 01 01"), "f70e1281030001016906")

    assert reg.devices["0E11_light_1"].state["on"] is False
    assert reg.devices["0E11_light_1"].state["control_sub_id"] == 0x11
    assert reg.devices["0E11_light_1"].state["control_channel"] == 1
    assert reg.devices["0E11_light_2"].state["on"] is False
    assert reg.devices["0E11_light_3"].state["on"] is False
    assert reg.devices["0E12_light_1"].state["on"] is True
    assert reg.devices["0E12_light_2"].state["on"] is True
    assert "0E1F_light_1" not in reg.devices


def test_light_control_response_does_not_create_channels():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x0E, 0x11, 0x81, bytes.fromhex("00 00 00 00"), "f70e118104000000006d08")
    changes = reg.upsert_from_frame(
        0x0E,
        0x11,
        0xC1,
        bytes.fromhex("00 01 F0 79 10"),
        "f70e11c1050001f07910b40a",
    )

    assert changes == []
    assert sorted(reg.devices.keys()) == [
        "0E11_light_1",
        "0E11_light_2",
        "0E11_light_3",
    ]
    assert reg.unsupported_packet_report()["total_seen"] == 0


def test_gas_standard_status_decodes_closed_as_off():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x12, 0x01, 0x81, bytes.fromhex("00 02"), "f7...")

    d = reg.devices["1201_gas_valve"]
    assert d.state["on"] is False
    assert d.state["closed"] is True
    assert d.state["open"] is False


def test_outlet_standard_status_decodes_supply_and_power():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x39, 0x01, 0x81, bytes.fromhex("00 91 36 78"), "f7...")

    d = reg.devices["3901_switch"]
    assert d.state["on"] is True
    assert d.state["power_w"] == 1367.8
    assert d.state["auto_cut"] is True


def test_group_outlet_status_expands_to_individual_control_subids():
    reg = DeviceRegistry()

    changes = reg.upsert_from_frame(
        0x39,
        0x1F,
        0x81,
        bytes.fromhex("00 10 00 79 00 00 26"),
        "f7...",
    )

    assert len(changes) == 2
    assert sorted(reg.devices.keys()) == ["3911_switch", "3912_switch"]
    first = reg.devices["3911_switch"]
    second = reg.devices["3912_switch"]
    assert first.sub_id == 0x11
    assert first.state["status_sub_id"] == 0x1F
    assert first.state["status_channel"] == 1
    assert first.state["control_sub_id"] == 0x11
    assert first.state["on"] is True
    assert first.state["power_w"] == 7.9
    assert second.sub_id == 0x12
    assert second.state["status_sub_id"] == 0x1F
    assert second.state["status_channel"] == 2
    assert second.state["control_sub_id"] == 0x12
    assert second.state["on"] is False
    assert second.state["power_w"] == 2.6


def test_outlet_threshold_response_decodes_cutoff_threshold():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x39, 0x01, 0xB1, bytes.fromhex("00 01 31"), "f7...")

    d = reg.devices["3901_switch"]
    assert d.state["threshold_w"] == 13.1
    assert d.state["thresholds"] == [{"channel": 1, "threshold_w": 13.1}]


def test_unsupported_outlet_command_does_not_create_legacy_entity():
    reg = DeviceRegistry()

    changes = reg.upsert_from_frame(0x39, 0x5F, 0x99, bytes.fromhex("00 10"), "f7...")

    assert changes == []
    assert reg.devices == {}
    report = reg.unsupported_packet_report()
    assert report["total_seen"] == 1
    assert report["packets"][0]["category"] == "unsupported"
    assert report["packets"][0]["reason"] == "unsupported_command"
    assert report["packets"][0]["device_id"] == "0x39"
    assert report["packets"][0]["sub_id"] == "0x5F"
    assert report["packets"][0]["command_type"] == "0x99"


def test_known_outlet_auxiliary_commands_are_ignored():
    reg = DeviceRegistry()

    for sub_id, cmd, payload in [
        (0x1F, 0x52, b""),
        (0x1F, 0xD2, bytes.fromhex("00 10 00")),
        (0xFF, 0x51, bytes.fromhex("00 00 00 00 00 00 00 00")),
    ]:
        assert reg.upsert_from_frame(0x39, sub_id, cmd, payload, "f7...") == []
        assert reg.last_packet_classification == {
            "classification": "ignored_request",
            "reason": "auxiliary_command",
        }

    assert reg.devices == {}
    assert reg.unsupported_packet_report()["total_seen"] == 0


def test_polling_requests_for_stateful_devices_are_ignored():
    reg = DeviceRegistry()

    assert reg.upsert_from_frame(0x30, 0x03, 0x01, b"", "f730030100c5f0") == []
    assert reg.upsert_from_frame(0x36, 0x1F, 0x01, b"", "f7361f0100df2c") == []
    assert reg.upsert_from_frame(0x39, 0x1F, 0x01, b"", "f7391f0100d020") == []
    assert reg.unsupported_packet_report()["total_seen"] == 0


def test_entrance_panel_status_decodes_without_switch_entity():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x33, 0x01, 0x81, bytes.fromhex("00 24 00"), "f7...")

    d = reg.devices["3301_entrance_panel"]
    assert d.kind == "entrance_panel"
    assert d.state["elevator_call_active"] is True
    assert d.state["all_lights_off_active"] is False


def test_common_entrance_call_packet_is_not_misclassified_as_light():
    reg = DeviceRegistry()

    reg.upsert_from_frame(
        0x40,
        0x02,
        0x10,
        bytes.fromhex("62 02 00 00 00 00"),
        "f740021006620200000000c376",
    )

    d = reg.devices["4002_common_entrance"]
    assert d.kind == "common_entrance"
    assert d.state["event"] == "call_detected"
    assert d.state["call_detected"] is True


def test_common_entrance_status_response_decodes_as_sensor_family():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x40, 0x02, 0x82, bytes.fromhex("00 00"), "f7...")

    d = reg.devices["4002_common_entrance"]
    assert d.kind == "common_entrance"
    assert d.state["event"] == "status_response"
    assert d.state["status_byte"] == 0x00


def test_common_entrance_polling_requests_do_not_change_sensor_state():
    reg = DeviceRegistry()

    assert reg.upsert_from_frame(0x40, 0x02, 0x02, b"", "f740020200b7f2") == []
    assert reg.upsert_from_frame(0x40, 0x03, 0x01, b"", "f740030100b5f0") == []
    assert reg.devices == {}
    assert reg.unsupported_packet_report()["total_seen"] == 0

    reg.upsert_from_frame(0x40, 0x02, 0x82, bytes.fromhex("00 00"), "f7...")

    d = reg.devices["4002_common_entrance"]
    assert d.state["event"] == "status_response"


def test_generic_sensor_polling_request_does_not_change_sensor_state():
    reg = DeviceRegistry()

    assert reg.upsert_from_frame(0x60, 0x01, 0x01, bytes.fromhex("00 06 66"), "f760010103000666f4bc") == []
    reg.upsert_from_frame(0x60, 0x01, 0x81, bytes.fromhex("00"), "f7600181010016f0")

    d = reg.devices["6001_sensor"]
    assert d.state["value_hex"] == "00"


def test_periodic_bus_requests_are_ignored_not_reported():
    reg = DeviceRegistry()

    assert reg.upsert_from_frame(
        0x33,
        0x01,
        0x01,
        bytes.fromhex("01"),
        "f73301010101c4f2",
    ) == []
    assert reg.upsert_from_frame(0x40, 0x03, 0x01, b"", "f740030100b5f0") == []
    assert reg.upsert_from_frame(0x12, 0x01, 0x0F, b"", "f712010f00eb04") == []

    assert reg.devices == {}
    assert reg.unsupported_packet_report()["total_seen"] == 0


def test_unknown_packet_is_reported_without_creating_device():
    reg = DeviceRegistry()

    changes = reg.upsert_from_frame(0x99, 0x01, 0x81, bytes.fromhex("AA BB"), "f799018102aabb1234")

    assert changes == []
    assert reg.devices == {}

    report = reg.unsupported_packet_report()
    assert report["total_seen"] == 1
    assert report["unique_signatures"] == 1
    assert report["latest_packet"]["category"] == "unsupported"
    assert report["latest_packet"]["reason"] == "unsupported_device_id"
    assert report["latest_packet"]["device_id"] == "0x99"
    assert report["latest_packet"]["sub_id"] == "0x01"
    assert report["latest_packet"]["command_type"] == "0x81"
    assert report["latest_packet"]["payload_len"] == 2
    assert report["latest_packet"]["packet_samples_available"] is True
    assert "last_payload_hex" not in report["latest_packet"]
    assert report["packets"][0] == report["latest_packet"]

    detailed = reg.unsupported_packet_report(include_packet_samples=True)
    assert detailed["latest_packet"]["last_payload_hex"] == "AABB"
    assert detailed["latest_packet"]["last_raw_hex"] == "F799018102AABB1234"


def test_known_device_invalid_sub_id_is_candidate_without_device():
    reg = DeviceRegistry()

    for addr, sub_id, cmd, payload in [
        (0x0E, 0xF1, 0x81, bytes.fromhex("00 01")),
        (0x12, 0x14, 0x81, bytes.fromhex("00 02")),
        (0x33, 0x14, 0x81, bytes.fromhex("00 04 00")),
        (0x40, 0x14, 0x82, bytes.fromhex("00 00")),
        (0x60, 0x14, 0x81, bytes.fromhex("00")),
    ]:
        assert reg.upsert_from_frame(addr, sub_id, cmd, payload, "f7...") == []

    assert reg.devices == {}
    report = reg.unsupported_packet_report()
    assert report["unsupported_seen"] == 0
    assert report["candidate_seen"] == 5
    assert report["total_seen"] == 5
    assert {packet["category"] for packet in report["packets"]} == {"candidate"}
    assert {packet["reason"] for packet in report["packets"]} == {"unregistered_sub_id"}


def test_supported_command_with_invalid_payload_is_candidate():
    reg = DeviceRegistry()

    changes = reg.upsert_from_frame(0x0E, 0x1F, 0x81, bytes.fromhex("00"), "f7...")

    assert changes == []
    assert reg.devices == {}
    report = reg.unsupported_packet_report()
    assert report["candidate_seen"] == 1
    assert report["latest_packet"]["category"] == "candidate"
    assert report["latest_packet"]["reason"] == "candidate_light_packet"


def test_registry_tracks_last_packet_classification():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x99, 0x01, 0x81, bytes.fromhex("AA BB"), "f7...")
    assert reg.last_packet_classification == {
        "classification": "unsupported",
        "reason": "unsupported_device_id",
    }

    reg.upsert_from_frame(0x0E, 0xF1, 0x81, bytes.fromhex("00 01"), "f7...")
    assert reg.last_packet_classification == {
        "classification": "candidate",
        "reason": "unregistered_sub_id",
    }

    reg.upsert_from_frame(0x39, 0x1F, 0x01, b"", "f7...")
    assert reg.last_packet_classification == {
        "classification": "ignored_request",
        "reason": "request_command",
    }

    reg.upsert_from_frame(0x0E, 0x11, 0x81, bytes.fromhex("00 01"), "f7...")
    assert reg.last_packet_classification == {
        "classification": "supported",
        "reason": None,
    }


def test_repeated_unsupported_packets_are_counted_by_signature():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x99, 0x01, 0x81, bytes.fromhex("AA BB"), "f799018102aabb1234")
    reg.upsert_from_frame(0x99, 0x01, 0x81, bytes.fromhex("CC DD"), "f799018102ccdd5678")

    report = reg.unsupported_packet_report()
    assert report["total_seen"] == 2
    assert report["unique_signatures"] == 1
    assert report["latest_packet"]["count"] == 2
    assert "last_payload_hex" not in report["latest_packet"]
    assert report["packets"][0]["count"] == 2

    detailed = reg.unsupported_packet_report(include_packet_samples=True)
    assert detailed["latest_packet"]["last_payload_hex"] == "CCDD"
    assert detailed["packets"][0]["last_payload_hex"] == "CCDD"


def test_meter_status_is_sensor_with_parsed_value():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x30, 0x01, 0x81, bytes.fromhex("00 00 12 34 12 34 56"), "f7...")

    d = reg.devices["3001_sensor"]
    assert d.kind == "sensor"
    assert d.state["meter"] == "water"
    assert d.state["instant"] == 1.234
    assert d.state["value"] == 12345.6
    assert d.state["unit"] == "m3"


def test_meter_whole_status_expands_to_individual_meter_devices():
    reg = DeviceRegistry()

    changes = reg.upsert_from_frame(
        0x30,
        0x0F,
        0x81,
        bytes.fromhex(
            "00"
            " 00 12 34 12 34 56"
            " 00 00 45 00 01 23"
            " 00 06 55 03 48 16"
        ),
        "f7...",
    )

    assert len(changes) == 3
    assert sorted(reg.devices.keys()) == [
        "3001_sensor",
        "3002_sensor",
        "3003_sensor",
    ]
    assert reg.devices["3001_sensor"].state["meter"] == "water"
    assert reg.devices["3001_sensor"].state["total"] == 12345.6
    assert reg.devices["3001_sensor"].state["source_sub_id"] == 0x0F
    assert reg.devices["3002_sensor"].state["meter"] == "gas"
    assert reg.devices["3002_sensor"].state["total"] == 12.3
    assert reg.devices["3003_sensor"].state["meter"] == "electricity"
    assert reg.devices["3003_sensor"].state["instant"] == 655
    assert reg.devices["3003_sensor"].state["total"] == 3481.6


def test_thermostat_group_status_preserves_tail_zone_for_entity():
    reg = DeviceRegistry()

    reg.upsert_from_frame(0x36, 0x1F, 0x81, bytes.fromhex("00 03 00 00 00 17 17 18 18"), "f7...")

    d = reg.devices["361F_climate"]
    assert d.state["target_temp"] == 24
    assert d.state["current_temp"] == 24
    assert d.state["on"] is True


def test_thermostat_individual_ack_updates_existing_group_zone():
    reg = DeviceRegistry()

    reg.upsert_from_frame(
        0x36,
        0x1F,
        0x81,
        bytes.fromhex("00 03 00 00 00 17 17 18 18"),
        "f7...",
    )
    changes = reg.upsert_from_frame(
        0x36,
        0x11,
        0xC3,
        bytes.fromhex("00 00 01 00 00 17 17"),
        "f7...",
    )

    assert "3611_climate" not in reg.devices
    assert changes == [(reg.devices["361F_climate"], False)]
    zones = reg.devices["361F_climate"].state["zones"]
    assert zones[0]["channel"] == 1
    assert zones[0]["on"] is False
    assert zones[0]["away"] is True
    assert zones[1]["channel"] == 2
    assert zones[1]["on"] is True


def test_thermostat_individual_ack_without_group_does_not_create_device():
    reg = DeviceRegistry()

    changes = reg.upsert_from_frame(
        0x36,
        0x11,
        0xC3,
        bytes.fromhex("00 00 01 00 00 17 17"),
        "f7...",
    )

    assert changes == []
    assert "3611_climate" not in reg.devices
    assert reg.devices == {}
    report = reg.unsupported_packet_report()
    assert report["candidate_seen"] == 1
    assert report["latest_packet"]["category"] == "candidate"
    assert report["latest_packet"]["reason"] == "thermostat_individual_without_group_state"
