from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402


def test_packet_quality_monitor_reports_rx_checksum_error():
    install_homeassistant_stubs()
    packet_quality = load_integration_module("packet_quality")

    monitor = packet_quality.PacketQualityMonitor()
    monitor.record_f7_checksum_error(
        dev_id=0x0E,
        sub_id=0x11,
        cmd=0x81,
        length=2,
        recv_xor=0x00,
        recv_add=0x00,
        calc_xor=0x6D,
        calc_add=0xA0,
        frame_raw=bytes.fromhex("F7 0E 11 81 02 00 01 00 00"),
    )

    report = monitor.report()

    assert report["state"] == "rx_errors"
    assert report["rx"]["f7_checksum_errors"] == 1
    assert report["rx"]["last_error"]["kind"] == "f7_checksum"
    assert report["rx"]["last_error"]["device_id"] == "0x0E"
    assert report["rx"]["last_error"]["sub_id"] == "0x11"
    assert report["rx"]["last_error"]["command_type"] == "0x81"
    assert report["rx"]["last_error"]["received_checksum"] == "0x00/0x00"
    assert report["rx"]["last_error"]["expected_checksum"] == "0x6D/0xA0"
    assert report["rx"]["last_error"]["raw_hex"] == "F70E11810200010000"


def test_codec_records_f7_checksum_errors_and_valid_f7_frames():
    install_homeassistant_stubs()
    packet_quality = load_integration_module("packet_quality")
    protocol = load_integration_module("protocol")

    monitor = packet_quality.PacketQualityMonitor()
    codec = protocol.Ksx4506Codec(packet_quality=monitor)
    valid = codec.build_f7(0x0E, 0x11, 0x81, b"\x00\x01")
    invalid = valid[:-1] + bytes([valid[-1] ^ 0x01])

    assert codec.feed(invalid) == []
    codec = protocol.Ksx4506Codec(packet_quality=monitor)
    assert codec.feed(valid)[0].addr == 0x0E

    report = monitor.report()
    assert report["state"] == "rx_errors"
    assert report["rx"]["f7_checksum_errors"] == 1
    assert report["rx"]["valid_f7_frames"] == 1
    assert report["rx"]["last_valid_f7"]["device_id"] == "0x0E"
    assert report["rx"]["last_error"]["device_id"] == "0x0E"


def test_packet_quality_records_tx_give_up_from_coordinator():
    install_homeassistant_stubs()
    packet_quality = load_integration_module("packet_quality")
    coordinator_module = load_integration_module("coordinator")
    protocol = load_integration_module("protocol")

    class FakeClient:
        def health_report(self):
            return {
                "state": "stale",
                "seconds_since_last_rx": 42.0,
                "last_error": "EW11 RX stale for 42.0s",
            }

    class FakeCoordinator:
        def __init__(self):
            self.max_attempts = 1
            self._frame_waiters = []
            self.sent = []
            self.codec = protocol.Ksx4506Codec()
            self.packet_quality = packet_quality.PacketQualityMonitor()
            self._client = FakeClient()
            self.published = 0

        async def async_send_f7_command(
            self,
            dev_id,
            sub_id,
            cmd,
            payload,
            *,
            guard=False,
        ):
            self.sent.append((dev_id, sub_id, cmd, payload, guard))
            return True

        def _publish_registry_state(self):
            self.published += 1

    fake = FakeCoordinator()
    fake.async_send_f7_command_until = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
        fake,
    )

    result = asyncio.run(
        fake.async_send_f7_command_until(
            0x0E,
            0x11,
            0x41,
            b"\x01\x01\x00",
            lambda frame: False,
        )
    )

    assert result is None
    assert fake.published == 1
    report = fake.packet_quality.report()
    assert report["state"] == "tx_giveups"
    assert report["tx"]["giveups"] == 1
    assert report["tx"]["control_giveups"] == 1
    assert report["tx"]["state_request_giveups"] == 0
    assert report["tx"]["last_giveup"]["device_id"] == "0x0E"
    assert report["tx"]["last_giveup"]["sub_id"] == "0x11"
    assert report["tx"]["last_giveup"]["command_type"] == "0x41"
    assert report["tx"]["last_giveup"]["payload_hex"] == "010100"
    assert report["tx"]["last_giveup"]["ew11_state"] == "stale"
