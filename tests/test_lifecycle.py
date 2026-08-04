from pathlib import Path
import asyncio
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


class _FakeConfigEntries:
    def __init__(self, *, unload_result=True, fail_forward=False):
        self.unload_result = unload_result
        self.fail_forward = fail_forward

    async def async_unload_platforms(self, _entry, _platforms):
        return self.unload_result

    async def async_forward_entry_setups(self, _entry, _platforms):
        if self.fail_forward:
            raise RuntimeError("forward failed")


class _FakeEntry:
    entry_id = "entry"
    data = {}
    options = {}

    def add_update_listener(self, _listener):
        return object()

    def async_on_unload(self, _callback):
        return None


def test_unload_failure_preserves_running_coordinator():
    install_homeassistant_stubs()
    init_module = load_integration_module("__init__")
    coordinator = types.SimpleNamespace(stopped=False)

    async def stop():
        coordinator.stopped = True

    coordinator.async_stop = stop
    hass = types.SimpleNamespace(
        data={init_module.DOMAIN: {"entry": coordinator}},
        config_entries=_FakeConfigEntries(unload_result=False),
    )

    result = asyncio.run(init_module.async_unload_entry(hass, _FakeEntry()))

    assert result is False
    assert coordinator.stopped is False
    assert hass.data[init_module.DOMAIN]["entry"] is coordinator


def test_setup_failure_stops_and_removes_coordinator(monkeypatch):
    install_homeassistant_stubs()
    init_module = load_integration_module("__init__")

    class FakeCoordinator:
        instances = []

        def __init__(self, _hass, _config):
            self.registry = object()
            self.started = False
            self.stopped = False
            self.instances.append(self)

        async def async_start(self):
            self.started = True

        async def async_stop(self):
            self.stopped = True

    async def no_op(*_args):
        return None

    monkeypatch.setattr(init_module, "Ksx4506Coordinator", FakeCoordinator)
    monkeypatch.setattr(init_module, "_async_prune_legacy_registry_entries", no_op)
    monkeypatch.setattr(init_module, "async_restore_registry_devices_from_ha", no_op)
    hass = types.SimpleNamespace(
        data={},
        config_entries=_FakeConfigEntries(fail_forward=True),
    )

    with pytest.raises(RuntimeError, match="forward failed"):
        asyncio.run(init_module.async_setup_entry(hass, _FakeEntry()))

    coordinator = FakeCoordinator.instances[-1]
    assert coordinator.started is True
    assert coordinator.stopped is True
    assert "entry" not in hass.data.get(init_module.DOMAIN, {})
