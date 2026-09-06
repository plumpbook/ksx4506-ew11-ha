from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402

_module = load_integration_module("discovery")
DeviceRegistry = _module.DeviceRegistry


@pytest.mark.parametrize(
    ("addr", "sub_id", "cmd", "payload", "expected_keys"),
    [
        (0x0E, 0x2F, 0x81, bytes.fromhex("00 01 00"), {"0E2F_light_1", "0E2F_light_2"}),
        (0x12, 0x01, 0x81, bytes.fromhex("00 02"), {"1201_gas_valve"}),
        (0x30, 0x01, 0x81, bytes.fromhex("00 00 12 34 12 34 56"), {"3001_sensor"}),
        (0x33, 0x01, 0x81, bytes.fromhex("00 24 00"), {"3301_entrance_panel"}),
        (0x36, 0x2F, 0x81, bytes.fromhex("00 01 00 00 00 17 17"), {"362F_climate"}),
        (0x39, 0x2F, 0x81, bytes.fromhex("00 10 00 79"), {"3921_switch"}),
        (0x40, 0x02, 0x82, bytes.fromhex("00 00"), {"4002_common_entrance"}),
        (0x60, 0x01, 0x81, bytes.fromhex("00"), {"6001_sensor"}),
    ],
)
def test_new_devices_require_two_valid_observations(
    addr, sub_id, cmd, payload, expected_keys
):
    # Given
    registry = DeviceRegistry()

    # When
    first_changes = registry.upsert_from_frame(addr, sub_id, cmd, payload, "f7...")

    # Then
    assert first_changes == []
    assert registry.devices == {}

    # When
    second_changes = registry.upsert_from_frame(addr, sub_id, cmd, payload, "f7...")

    # Then
    assert {device.key for device, is_new in second_changes if is_new} == expected_keys
    assert set(registry.devices) == expected_keys


def test_restored_device_updates_on_first_observation():
    # Given
    registry = DeviceRegistry()
    registry.restore_device_from_key("1201_gas_valve")

    # When
    changes = registry.upsert_from_frame(
        0x12,
        0x01,
        0x81,
        bytes.fromhex("00 02"),
        "f7...",
    )

    # Then
    assert changes == [(registry.devices["1201_gas_valve"], False)]
    assert registry.devices["1201_gas_valve"].state["closed"] is True
