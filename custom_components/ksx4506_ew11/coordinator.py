from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_MAX_ATTEMPTS,
    DEFAULT_MAX_ATTEMPTS,
    DOMAIN,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATE,
)
from .devices.common_entrance import (
    CALL_EVENT,
    COMMON_ENTRANCE_DEVICE_ID,
    decode_common_entrance_state,
    format_common_entrance_packet_log,
)
from .devices.meter import METER_DEVICE_ID, METER_WHOLE_ORDER
from .discovery import DeviceRegistry
from .ew11_client import Ew11Client
from .protocol import Ksx4506Codec, KsFrame

_LOGGER = logging.getLogger(__name__)
_METER_STARTUP_PROBE_SUB_IDS = (0x0F, *METER_WHOLE_ORDER)


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
        self.max_attempts = max(
            1,
            min(20, int(config.get(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS))),
        )
        self._frame_waiters: list[tuple[Callable[[KsFrame], bool], asyncio.Future[KsFrame]]] = []
        self._meter_probe_task: asyncio.Task | None = None

    async def _async_update_data(self):
        return {k: v.state for k, v in self.registry.devices.items()}

    async def async_start(self) -> None:
        await self._client.start()
        if self._meter_probe_task is None or self._meter_probe_task.done():
            self._meter_probe_task = asyncio.create_task(self.async_probe_meter_states())

    async def async_stop(self) -> None:
        if self._meter_probe_task:
            self._meter_probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._meter_probe_task
            self._meter_probe_task = None
        await self._client.stop()

    async def _on_frame(self, frame: KsFrame) -> None:
        _LOGGER.debug(
            "RX frame dev=0x%02X sub=0x%02X cmd=0x%02X len=%d raw=%s",
            frame.addr,
            frame.sub_id,
            frame.cmd,
            len(frame.payload),
            frame.raw.hex(),
        )
        if frame.addr == COMMON_ENTRANCE_DEVICE_ID:
            log_message = format_common_entrance_packet_log(
                frame.sub_id,
                frame.cmd,
                frame.payload,
                frame.raw,
                direction="RX",
            )
            if frame.cmd == CALL_EVENT:
                state = decode_common_entrance_state(
                    frame.payload,
                    command_type=frame.cmd,
                )
                _LOGGER.info(
                    "Common entrance call event sub=0x%02X detected=%s",
                    frame.sub_id,
                    state.get("call_detected", False),
                )
                _LOGGER.debug(log_message)
            else:
                _LOGGER.debug(log_message)
        changes = self.registry.upsert_from_frame(
            frame.addr,
            frame.sub_id,
            frame.cmd,
            frame.payload,
            frame.raw.hex(),
        )
        for dev, is_new in changes:
            if is_new:
                async_dispatcher_send(self.hass, SIGNAL_DEVICE_ADDED, dev.key)
            async_dispatcher_send(self.hass, SIGNAL_DEVICE_UPDATE, dev.key)
        self.async_set_updated_data({k: v.state for k, v in self.registry.devices.items()})
        self._notify_frame_waiters(frame)

    def _notify_frame_waiters(self, frame: KsFrame) -> None:
        for matcher, fut in tuple(self._frame_waiters):
            if fut.done():
                continue
            try:
                matched = matcher(frame)
            except Exception:
                _LOGGER.exception("Frame waiter matcher failed")
                matched = False
            if matched and not fut.done():
                fut.set_result(frame)

    async def async_send_command(self, addr: int, cmd: int, payload: bytes, *, guard: bool = False) -> bool:
        if guard and not self._gas_unlock:
            _LOGGER.warning("Blocked guarded command addr=%s cmd=%s", addr, cmd)
            return False
        packet = self.codec.build(addr, cmd, payload)
        _LOGGER.debug(
            "TX STX addr=0x%02X cmd=0x%02X payload=%s packet=%s",
            addr,
            cmd,
            payload.hex(),
            packet.hex(),
        )
        return await self._client.send_with_retry(packet)

    async def async_send_f7_command(
        self,
        dev_id: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        *,
        guard: bool = False,
    ) -> bool:
        if guard and not self._gas_unlock:
            _LOGGER.warning(
                "Blocked guarded F7 command dev=%s sub=%s cmd=%s",
                dev_id,
                sub_id,
                cmd,
            )
            return False
        packet = self.codec.build_f7(dev_id, sub_id, cmd, payload)
        _LOGGER.debug(
            "TX F7 dev=0x%02X sub=0x%02X cmd=0x%02X payload=%s packet=%s",
            dev_id,
            sub_id,
            cmd,
            payload.hex(),
            packet.hex(),
        )
        return await self._client.send_with_retry(packet)

    async def async_send_f7_command_until(
        self,
        dev_id: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        matcher: Callable[[KsFrame], bool],
        *,
        max_attempts: int | None = None,
        interval: float = 0.1,
        guard: bool = False,
    ) -> KsFrame | None:
        attempts = max(1, min(20, int(max_attempts or self.max_attempts)))
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[KsFrame] = loop.create_future()
        waiter = (matcher, fut)
        self._frame_waiters.append(waiter)

        try:
            for attempt in range(1, attempts + 1):
                if fut.done():
                    matched = fut.result()
                    _LOGGER.debug(
                        "TX F7 control matched before send dev=0x%02X sub=0x%02X cmd=0x%02X "
                        "attempt=%d/%d matched_sub=0x%02X matched_cmd=0x%02X",
                        dev_id,
                        sub_id,
                        cmd,
                        attempt,
                        attempts,
                        matched.sub_id,
                        matched.cmd,
                    )
                    return matched

                _LOGGER.debug(
                    "TX F7 control attempt dev=0x%02X sub=0x%02X cmd=0x%02X "
                    "attempt=%d/%d interval=%.3fs payload=%s",
                    dev_id,
                    sub_id,
                    cmd,
                    attempt,
                    attempts,
                    interval,
                    payload.hex(),
                )

                await self.async_send_f7_command(
                    dev_id,
                    sub_id,
                    cmd,
                    payload,
                    guard=guard,
                )

                try:
                    matched = await asyncio.wait_for(asyncio.shield(fut), timeout=interval)
                    _LOGGER.debug(
                        "TX F7 control matched dev=0x%02X sub=0x%02X cmd=0x%02X "
                        "attempt=%d/%d matched_sub=0x%02X matched_cmd=0x%02X",
                        dev_id,
                        sub_id,
                        cmd,
                        attempt,
                        attempts,
                        matched.sub_id,
                        matched.cmd,
                    )
                    return matched
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "TX F7 control wait timeout dev=0x%02X sub=0x%02X cmd=0x%02X "
                        "attempt=%d/%d",
                        dev_id,
                        sub_id,
                        cmd,
                        attempt,
                        attempts,
                    )
                    continue

            if fut.done():
                matched = fut.result()
                _LOGGER.debug(
                    "TX F7 control matched after final send dev=0x%02X sub=0x%02X cmd=0x%02X "
                    "attempts=%d matched_sub=0x%02X matched_cmd=0x%02X",
                    dev_id,
                    sub_id,
                    cmd,
                    attempts,
                    matched.sub_id,
                    matched.cmd,
                )
                return matched
            _LOGGER.debug(
                "TX F7 control gave up dev=0x%02X sub=0x%02X cmd=0x%02X attempts=%d",
                dev_id,
                sub_id,
                cmd,
                attempts,
            )
            return None
        finally:
            with suppress(ValueError):
                self._frame_waiters.remove(waiter)

    async def async_request_f7_state(self, dev_id: int, sub_id: int) -> bool:
        # Generic state request command for KS X 4506 family
        return await self.async_send_f7_command(dev_id, sub_id, 0x01, b"")

    async def async_probe_meter_states(
        self,
        *,
        delay: float = 1.0,
        interval: float = 0.2,
    ) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            for sub_id in _METER_STARTUP_PROBE_SUB_IDS:
                ok = await self.async_request_f7_state(METER_DEVICE_ID, sub_id)
                _LOGGER.debug(
                    "Meter startup probe sub=0x%02X ok=%s",
                    sub_id,
                    ok,
                )
                if interval > 0:
                    await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Meter startup probe failed")
