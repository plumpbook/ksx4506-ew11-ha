from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


def _bind_method(instance, name: str, method):
    bound_method = types.MethodType(method, instance)
    setattr(instance, name, bound_method)
    return bound_method


def test_coordinator_skips_device_update_for_repeated_identical_frame(monkeypatch):
    install_homeassistant_stubs()
    const_module = load_integration_module("const")
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")
    dispatched = []

    monkeypatch.setattr(
        coordinator_module,
        "async_dispatcher_send",
        lambda hass, signal, dev_key: dispatched.append((signal, dev_key)),
    )

    class FakeCoordinator:
        def __init__(self):
            self.registry = coordinator_module.DeviceRegistry()
            self.hass = object()
            self.packet_capture_enabled = False
            self._last_changed_device_keys = None
            self._last_published_device_states = {}
            self.published_scopes = []

        def async_set_updated_data(self, data):
            self.data = data
            self.published_scopes.append(self._last_changed_device_keys)

        def _notify_frame_waiters(self, frame):
            _ = frame

    fake = FakeCoordinator()
    on_frame = _bind_method(
        fake,
        "_on_frame",
        coordinator_module.Ksx4506Coordinator._on_frame,
    )
    _bind_method(
        fake,
        "_publish_registry_state",
        coordinator_module.Ksx4506Coordinator._publish_registry_state,
    )
    _bind_method(
        fake,
        "_semantic_state_changes",
        coordinator_module.Ksx4506Coordinator._semantic_state_changes,
    )
    frame = protocol_module.KsFrame(
        addr=0x39,
        sub_id=0x1F,
        cmd=0x81,
        payload=bytes.fromhex("00 10 00 79 00 00 26"),
        checksum=0,
        raw=bytes.fromhex("F7 39 1F 81 07 00 10 00 79 00 00 26 00 00"),
    )

    asyncio.run(on_frame(frame))
    asyncio.run(on_frame(frame))

    updates = [
        dev_key
        for signal, dev_key in dispatched
        if signal == const_module.SIGNAL_DEVICE_UPDATE
    ]
    assert updates == ["3911_switch", "3912_switch"]
    assert fake.published_scopes[-1] == frozenset()
