import asyncio  # noqa: ANYIO_OK - HA task boundary
import sys
import types

import pytest

from ._integration_loader import load_integration_module
from .ha_stubs import install_homeassistant_stubs


@pytest.mark.parametrize("connected,probed_zero,responders,expected", [
    (True, True, 0, 0),
    (False, True, 0, 0),
    (True, False, 0, 0),
    (True, True, 1, 0),
])
def test_watchdog_never_cycles_power_even_with_confirmed_bus_wide_silence(
    monkeypatch, connected, probed_zero, responders, expected,
):
    async def scenario():
        install_homeassistant_stubs()
        module = load_integration_module("hub_recovery")
        recovery = load_integration_module("recovery")
        policy = recovery.HubRecoveryPolicy()
        policy.reconnected_at = asyncio.get_running_loop().time() - 121
        policy.bad_since = policy.reconnected_at - 30
        operations = []

        async def power():
            operations.append("power")
            return True

        async def stop():
            operations.append("stop")

        async def start():
            operations.append("start")

        async def no_wait(seconds):
            return None

        monkeypatch.setattr(module.asyncio, "sleep", no_wait)
        monkeypatch.setattr(sys.modules["homeassistant.components"], "persistent_notification",
                            types.SimpleNamespace(async_create=lambda *a, **kw: None), raising=False)
        commands = recovery.CommandRecovery(lambda: None)
        monkeypatch.setattr(commands, "failed_endpoints", lambda **kw: {(14, 17), (57, 17)})
        coordinator = types.SimpleNamespace(
            hub_recovery=policy, recovery=commands, _power_cycle=power,
            _client=types.SimpleNamespace(
                health_report=lambda: {"state": "receiving", "connected": connected},
                stop=stop, start=start,
            ),
            _transaction_lock=asyncio.Lock(),
            device_vitality_report=lambda: {"devices": [
                {"seconds_since_response": 0, "consecutive_failures": 0}
            ] * responders},
            _publish_registry_state=lambda: None, hass=None, recovery_notification_id="test",
        )
        watchdog = module.HubRecovery(coordinator)
        await watchdog.tick()
        await watchdog.tick()
        assert operations.count("power") == expected
        assert operations == (["stop", "power", "start"] if expected else [])
        assert commands._accepting

    asyncio.run(scenario())
