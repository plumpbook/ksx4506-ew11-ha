from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402

_module = load_integration_module("discovery")
DeviceRegistry = _module.DeviceRegistry


def test_group_light_creates_channels_only_no_group_entity():
    reg = DeviceRegistry()
    reg.upsert_from_frame(0x0E, 0x1F, 0x81, bytes([0x00, 0x01, 0x00, 0x01]), "f7...")

    assert "0E1F_light" not in reg.devices
    assert "0E1F_light_1" in reg.devices
    assert "0E1F_light_2" in reg.devices
    assert "0E1F_light_3" in reg.devices
    assert reg.devices["0E1F_light_1"].state["control_sub_id"] == 0x11
    assert reg.devices["0E1F_light_2"].state["control_sub_id"] == 0x12


def test_group_channel_individual_reply_keeps_standard_channel():
    reg = DeviceRegistry()
    # group4 has one channel from grouped state
    reg.upsert_from_frame(0x0E, 0x4F, 0x81, bytes([0x00, 0x01]), "f7...")

    # standard grouped channel sub_id 0x44 -> group4 ch4
    reg.upsert_from_frame(0x0E, 0x44, 0x81, bytes([0x00, 0x01]), "f7...")

    assert "0E4F_light_1" in reg.devices
    assert "0E4F_light_4" in reg.devices
    assert reg.devices["0E4F_light_4"].state["control_sub_id"] == 0x44


def test_ungrouped_light_subid_stays_individual_light():
    reg = DeviceRegistry()
    # no-group lighting: 0x03/0x04/0x05 are individual light IDs
    reg.upsert_from_frame(0x0E, 0x03, 0x81, bytes([0x00, 0x01]), "f7...")
    reg.upsert_from_frame(0x0E, 0x04, 0x81, bytes([0x00, 0x00]), "f7...")
    reg.upsert_from_frame(0x0E, 0x05, 0x81, bytes([0x00, 0x01]), "f7...")

    assert "0E03_light" in reg.devices
    assert "0E04_light" in reg.devices
    assert "0E05_light" in reg.devices
