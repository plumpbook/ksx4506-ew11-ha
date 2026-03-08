from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SIGNAL_DEVICE_ADDED, SIGNAL_DEVICE_UPDATE
from .discovery import DeviceRegistry
from .ew11_client import Ew11Client
from .protocol import Ksx4506Codec, KsFrame

_LOGGER = logging.getLogger(__name__)


class Ksx4506Coordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.registry = DeviceRegistry()
        self.codec = Ksx4506Codec(
            stx=int(config["stx"], 16),
            etx=int(config["etx"], 16),
            checksum_mode=config["checksum"],
        )
        self._client = Ew11Client(
            host=config["host"],
            port=config["port"],
            timeout=config["timeout"],
            retry=config["retry"],
            codec=self.codec,
            on_frame=self._on_frame,
        )
        self._gas_unlock = config.get("gas_unlock", False)

    async def _async_update_data(self):
        return {k: v.state for k, v in self.registry.devices.items()}

    async def async_start(self) -> None:
        await self._client.start()

    async def async_stop(self) -> None:
        await self._client.stop()

    async def _on_frame(self, frame: KsFrame) -> None:
        _LOGGER.debug(
            "RX frame addr=0x%02X cmd=0x%02X len=%d raw=%s",
            frame.addr,
            frame.cmd,
            len(frame.payload),
            frame.raw.hex(),
        )
        dev, is_new = self.registry.upsert_from_frame(
            frame.addr,
            frame.cmd,
            frame.payload,
            frame.raw.hex(),
        )
        if is_new:
            async_dispatcher_send(self.hass, SIGNAL_DEVICE_ADDED, dev.key)
        async_dispatcher_send(self.hass, SIGNAL_DEVICE_UPDATE, dev.key)
        self.async_set_updated_data({k: v.state for k, v in self.registry.devices.items()})

    async def async_send_command(self, addr: int, cmd: int, payload: bytes, *, guard: bool = False) -> bool:
        if guard and not self._gas_unlock:
            _LOGGER.warning("Blocked guarded command addr=%s cmd=%s", addr, cmd)
            return False
        packet = self.codec.build(addr, cmd, payload)
        return await self._client.send_with_retry(packet)
