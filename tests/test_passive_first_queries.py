import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ._integration_loader import load_integration_module
from .ha_stubs import install_homeassistant_stubs


def test_starting_coordinator_does_not_schedule_startup_or_periodic_queries(monkeypatch):
    async def scenario():
        install_homeassistant_stubs()
        module = load_integration_module("coordinator")
        coordinator = module.Ksx4506Coordinator(SimpleNamespace(), {
            "host": "ew11.example.invalid", "port": 8899, "timeout": 0.1, "retry": 0,
        })
        coordinator._publish_registry_state = lambda: None
        coordinator._client.start = AsyncMock()
        coordinator._client.stop = AsyncMock()

        async def parked_recovery():
            await asyncio.Event().wait()

        monkeypatch.setattr(module, "HubRecovery", lambda _coordinator: SimpleNamespace(
            run=parked_recovery,
        ))
        before = asyncio.all_tasks()
        try:
            await coordinator.async_start()
            scheduled = asyncio.all_tasks() - before
            assert scheduled == {coordinator._recovery_task}
        finally:
            await coordinator.async_stop()

    asyncio.run(scenario())
