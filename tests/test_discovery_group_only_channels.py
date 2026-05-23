from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402

_module = load_integration_module("discovery")
DeviceRegistry = _module.DeviceRegistry


def test_group_light_creates_channels_only_no_group_entity():
    reg = DeviceRegistry()
    reg.upsert_from_frame(0x0E, 0x1F, 0x81, bytes([0x00, 0x01, 0x00, 0x01]), "f7...")

    assert "0E1F_light" not in reg.devices
    assert "0E1F_light_1" in reg.devices
    assert "0E1F_light_2" in reg.devices
    assert "0E1F_light_3" in reg.devices


def test_single_reply_channel_out_of_known_range_falls_back_to_ch1():
    reg = DeviceRegistry()
    # group4 has one channel from grouped state
    reg.upsert_from_frame(0x0E, 0x4F, 0x81, bytes([0x00, 0x01]), "f7...")

    # single reply comes as sub_id 0x44 (field variant) -> should map to group4 ch1
    reg.upsert_from_frame(0x0E, 0x44, 0x81, bytes([0x00, 0x01]), "f7...")

    assert "0E4F_light_1" in reg.devices
    assert "0E4F_light_4" not in reg.devices


def test_single_group_subid_maps_to_group_ch1():
    reg = DeviceRegistry()
    # vendor single-group replies: 0x03/0x04/0x05 => group3/4/5 channel1
    reg.upsert_from_frame(0x0E, 0x03, 0x81, bytes([0x00, 0x01]), "f7...")
    reg.upsert_from_frame(0x0E, 0x04, 0x81, bytes([0x00, 0x00]), "f7...")
    reg.upsert_from_frame(0x0E, 0x05, 0x81, bytes([0x00, 0x01]), "f7...")

    assert "0E3F_light_1" in reg.devices
    assert "0E4F_light_1" in reg.devices
    assert "0E5F_light_1" in reg.devices
