import asyncio  # noqa: ANYIO_OK - HA lifecycle integration

import pytest

from ._integration_loader import load_integration_module

PowerRecovery = load_integration_module("power_recovery").PowerRecovery


class Store:
    def __init__(self):
        self.saved = []

    async def async_save(self, data):
        self.saved.append(data.copy())


def test_power_attempt_is_durable_and_limited_across_restart():
    async def scenario():
        store = Store()
        switched = []

        async def switch(on):
            assert store.saved[0]["restore_pending"]
            switched.append(on)

        power = PowerRecovery(store, {"last_attempt": 0, "restore_pending": False},
                              switch, lambda: True, now=lambda: 100000, off_seconds=0)
        assert await power.cycle()
        restarted = PowerRecovery(store, store.saved[-1].copy(), switch, lambda: True,
                                  now=lambda: 100001, off_seconds=0)
        assert not await restarted.cycle()
        assert switched == [False, True]
        assert store.saved[-1]["restore_pending"] is False

    asyncio.run(scenario())


def test_cancel_during_power_off_restores_on_before_exit():
    async def scenario():
        store = Store()
        switched = []
        off = asyncio.Event()

        async def switch(on):
            switched.append(on)
            if not on:
                off.set()

        power = PowerRecovery(store, {"last_attempt": 0, "restore_pending": False},
                              switch, lambda: True, now=lambda: 100000)
        task = asyncio.create_task(power.cycle())
        await off.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert switched == [False, True]
        assert store.saved[-1]["restore_pending"] is False

    asyncio.run(scenario())


def test_unavailable_or_user_off_switch_is_not_power_cycled():
    async def scenario():
        store = Store()

        async def switch(on):
            pytest.fail("No power service call is allowed")

        power = PowerRecovery(store, {"last_attempt": 0, "restore_pending": False},
                              switch, lambda: False, now=lambda: 100000)
        assert not await power.cycle()
        assert store.saved == []

    asyncio.run(scenario())


def test_restore_failure_keeps_durable_pending_flag():
    async def scenario():
        store = Store()

        async def switch(on):
            if on:
                raise TimeoutError("not confirmed")

        power = PowerRecovery(store, {"last_attempt": 0, "restore_pending": False},
                              switch, lambda: True, now=lambda: 100000, off_seconds=0)
        with pytest.raises(TimeoutError):
            await power.cycle()
        assert store.saved[-1]["restore_pending"] is True

    asyncio.run(scenario())
