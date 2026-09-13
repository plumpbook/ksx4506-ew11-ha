"""Opt-in power recovery for an independently connected, dedicated switch."""
from __future__ import annotations

import asyncio  # noqa: ANYIO_OK - HA service calls and cancellation share this loop
from collections.abc import Awaitable, Callable
from typing import Protocol, TypedDict
import time

CONF_RECOVERY_POWER_SWITCH = "recovery_power_switch"


class PowerJournal(TypedDict):
    last_attempt: float
    restore_pending: bool


class JournalStore(Protocol):
    async def async_save(self, data: PowerJournal) -> None: ...


class PowerRecovery:
    """Persist the attempt before switching off; always attempt to restore power."""

    def __init__(
        self, store: JournalStore, journal: PowerJournal,
        set_power: Callable[[bool], Awaitable[None]], ready: Callable[[], bool],
        *, off_seconds: float = 5, now: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.journal = journal
        self.set_power = set_power
        self.ready = ready
        self.off_seconds = off_seconds
        self.now = now
        self._lock = asyncio.Lock()

    async def restore(self) -> None:
        if not self.journal["restore_pending"]:
            return
        await self.set_power(True)
        self.journal["restore_pending"] = False
        await self.store.async_save(self.journal.copy())

    async def cycle(self) -> bool:
        async with self._lock:
            await self.restore()
            now = self.now()
            if not self.ready() or now - self.journal["last_attempt"] < 86400:
                return False
            self.journal.update(last_attempt=now, restore_pending=True)
            await self.store.async_save(self.journal.copy())
            try:
                await self.set_power(False)
                await asyncio.sleep(self.off_seconds)
            finally:
                # The caller cancelling a restart must not leave the wallpad off.
                restore = asyncio.create_task(self.restore())
                try:
                    await asyncio.shield(restore)
                except asyncio.CancelledError:
                    await restore
                    raise
            return True


async def async_configure_power_recovery(hass, entry, coordinator) -> None:
    """Only import HA storage for an explicitly configured power target."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.storage import Store

    from .config import effective_config
    from .const import DOMAIN

    entity_id = effective_config(entry)[CONF_RECOVERY_POWER_SWITCH]
    registry = er.async_get(hass)

    def ready() -> bool:
        entity = registry.async_get(entity_id)
        state = hass.states.get(entity_id)
        return (entity is not None and entity.platform != DOMAIN
                and entity_id.startswith("switch.")
                and state is not None and state.state == "on")

    async def set_power(on: bool) -> None:
        async with asyncio.timeout(15):
            await hass.services.async_call(
                "switch", "turn_on" if on else "turn_off",
                {"entity_id": entity_id}, blocking=True,
            )
            # Service completion is not physical-state confirmation.
            for _ in range(20):
                state = hass.states.get(entity_id)
                if state is not None and state.state == ("on" if on else "off"):
                    return
                await asyncio.sleep(0.5)
            raise TimeoutError("Recovery power switch state was not confirmed")

    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.power_recovery")
    saved = await store.async_load() or {}
    # Do not restore a different target after the user changes the option.
    same_target = saved.get("entity_id") == entity_id
    journal: PowerJournal = {
        "last_attempt": float(saved.get("last_attempt", 0)),
        "restore_pending": same_target and bool(saved.get("restore_pending", False)),
    }

    class TargetStore:
        async def async_save(self, data: PowerJournal) -> None:
            await store.async_save({**data, "entity_id": entity_id})

    power = PowerRecovery(TargetStore(), journal, set_power, ready)
    coordinator._power_cycle = power.cycle
    # Restore an interrupted cycle before starting the serial client.
    await power.restore()
