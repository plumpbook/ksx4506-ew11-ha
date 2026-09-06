from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402

_module = load_integration_module("discovery")
DeviceRegistry = _module.DeviceRegistry


def confirm_new_devices(registry, addr, sub_id, payload):
    assert registry.upsert_from_frame(addr, sub_id, 0x81, payload, "f7...") == []
    return registry.upsert_from_frame(addr, sub_id, 0x81, payload, "f7...")


def test_group_light_creates_channels_only_no_group_entity():
    reg = DeviceRegistry()
    confirm_new_devices(reg, 0x0E, 0x1F, bytes([0x00, 0x01, 0x00, 0x01]))

    assert "0E1F_light" not in reg.devices
    assert "0E1F_light_1" in reg.devices
    assert "0E1F_light_2" in reg.devices
    assert "0E1F_light_3" in reg.devices
    assert reg.devices["0E1F_light_1"].state["control_sub_id"] == 0x11
    assert reg.devices["0E1F_light_2"].state["control_sub_id"] == 0x12


def test_group_channel_individual_reply_keeps_standard_channel():
    reg = DeviceRegistry()
    # group4 has one channel from grouped state
    confirm_new_devices(reg, 0x0E, 0x4F, bytes([0x00, 0x01]))

    # standard grouped channel sub_id 0x44 -> group4 ch4
    confirm_new_devices(reg, 0x0E, 0x44, bytes([0x00, 0x01]))

    assert "0E4F_light_1" in reg.devices
    assert "0E4F_light_4" in reg.devices
    assert reg.devices["0E4F_light_4"].state["control_sub_id"] == 0x44


def test_ungrouped_light_subid_stays_individual_light():
    reg = DeviceRegistry()
    # no-group lighting: 0x03/0x04/0x05 are individual light IDs
    confirm_new_devices(reg, 0x0E, 0x03, bytes([0x00, 0x01]))
    confirm_new_devices(reg, 0x0E, 0x04, bytes([0x00, 0x00]))
    confirm_new_devices(reg, 0x0E, 0x05, bytes([0x00, 0x01]))

    assert "0E03_light" in reg.devices
    assert "0E04_light" in reg.devices
    assert "0E05_light" in reg.devices
