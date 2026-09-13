"""Monitor device health without restarting the shared bridge or wallpad."""
from __future__ import annotations

import asyncio  # noqa: ANYIO_OK - HA lifecycle owns and awaits this task
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import Ksx4506Coordinator
    from .device_alerts import DeviceAlerts

_LOGGER = logging.getLogger(__name__)


class HubRecovery:
    def __init__(self, coordinator: Ksx4506Coordinator) -> None:
        self.coordinator = coordinator
        self.alerts: DeviceAlerts | None = None

    async def run(self) -> None:
        from .device_alerts import DeviceAlerts

        entry = self.coordinator.config_entry
        if entry is None:
            return
        self.alerts = DeviceAlerts(self.coordinator, entry.entry_id)
        loaded = False
        try:
            while not loaded:
                try:
                    await self.alerts.async_load()
                    loaded = True
                except Exception:  # noqa: BROAD_EXCEPT_OK - retain saved evidence and retry
                    _LOGGER.exception("EW11 saved alert state could not be loaded; retrying")
                    await asyncio.sleep(30)
            while True:
                await asyncio.sleep(15)
                await self.tick()
        finally:
            if loaded:
                await self.alerts.async_save()

    async def tick(self) -> None:
        try:
            if self.alerts is not None:
                await self.alerts.async_tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BROAD_EXCEPT_OK - keep the HA monitor alive
            _LOGGER.exception("EW11 device health notification update failed")
        finally:
            self.coordinator._publish_registry_state()
