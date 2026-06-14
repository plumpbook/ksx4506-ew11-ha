from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any, Final

from .protocol import Ksx4506Codec, KsFrame

_LOGGER = logging.getLogger(__name__)
DEFAULT_RX_STALE_AFTER: Final = 120.0


class Ew11Client:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        retry: int,
        codec: Ksx4506Codec,
        on_frame: Callable[[KsFrame], Coroutine[None, None, None]],
        rx_stale_after: float = DEFAULT_RX_STALE_AFTER,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._retry = retry
        self._codec = codec
        self._on_frame = on_frame
        self._rx_stale_after = max(float(rx_stale_after), timeout)

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._connected = False
        self._connected_at: datetime | None = None
        self._connected_monotonic: float | None = None
        self._last_rx_at: datetime | None = None
        self._last_rx_monotonic: float | None = None
        self._last_error: str | None = None

        self._cmd_queue: asyncio.Queue[tuple[bytes, asyncio.Future[bool]]] = asyncio.Queue()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        self._worker_task = asyncio.create_task(self._command_worker())

    async def stop(self) -> None:
        self._running = False

        if self._task:
            self._task.cancel()
        if self._worker_task:
            self._worker_task.cancel()

        # Unblock any pending send_with_retry waiters.
        while not self._cmd_queue.empty():
            _, fut = self._cmd_queue.get_nowait()
            if not fut.done():
                fut.set_result(False)

        await self._close()

    def health_report(self) -> dict[str, Any]:
        rx_silence = self._rx_silence_seconds()
        seconds_since_last_rx = self._seconds_since_last_rx()
        stale = rx_silence is not None and rx_silence >= self._rx_stale_after
        state = self._health_state(stale)
        return {
            "state": state,
            "connected": self._connected,
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "timeout": self._timeout,
            "retry": self._retry,
            "rx_stale_after": self._rx_stale_after,
            "last_connect_at": _isoformat_or_none(self._connected_at),
            "last_rx_at": _isoformat_or_none(self._last_rx_at),
            "seconds_since_last_rx": seconds_since_last_rx,
            "seconds_without_rx": rx_silence,
            "last_error": self._last_error,
        }

    async def send_with_retry(self, payload: bytes) -> bool:
        _LOGGER.debug("queue TX len=%d hex=%s", len(payload), payload.hex())
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        await self._cmd_queue.put((payload, fut))
        try:
            return await asyncio.wait_for(fut, timeout=max(self._timeout * (self._retry + 2), 1.0))
        except TimeoutError:
            _LOGGER.warning("TX queue timed out len=%d hex=%s", len(payload), payload.hex())
            return False

    async def _run_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                _LOGGER.info("Connecting EW11 %s:%s", self._host, self._port)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), timeout=self._timeout
                )
                backoff = 1
                self._mark_connected()
                _LOGGER.info("EW11 connected")

                while self._running:
                    try:
                        data = await asyncio.wait_for(self._reader.read(1024), timeout=self._timeout)
                    except TimeoutError:
                        if self._is_rx_stale():
                            silence = self._rx_silence_seconds()
                            raise ConnectionError(f"EW11 RX stale for {silence:.1f}s")
                        continue

                    if not data:
                        raise ConnectionError("EW11 connection closed")

                    self._mark_rx()
                    _LOGGER.debug("EW11 RX chunk len=%d hex=%s", len(data), data.hex())
                    for frame in self._codec.feed(data):
                        await self._on_frame(frame)

            except Exception as exc:
                self._last_error = repr(exc)
                _LOGGER.warning("EW11 loop error (%s:%s): %r", self._host, self._port, exc)
                await self._close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)

    async def _close(self) -> None:
        self._connected = False
        self._connected_monotonic = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader, self._writer = None, None

    async def _command_worker(self) -> None:
        while self._running:
            payload, fut = await self._cmd_queue.get()
            ok = False
            for attempt in range(self._retry + 1):
                if not self._writer:
                    _LOGGER.debug("TX waiting for writer (attempt=%d/%d)", attempt + 1, self._retry + 1)
                    await asyncio.sleep(0.2)
                    continue
                try:
                    self._writer.write(payload)
                    await self._writer.drain()
                    _LOGGER.debug("TX sent (attempt=%d/%d) hex=%s", attempt + 1, self._retry + 1, payload.hex())
                    ok = True
                    break
                except Exception as exc:
                    _LOGGER.debug("TX failed (attempt=%d/%d): %r", attempt + 1, self._retry + 1, exc)
                    await asyncio.sleep(0.2)
            if not ok:
                _LOGGER.warning("TX failed after %d attempts hex=%s", self._retry + 1, payload.hex())
            if not fut.done():
                fut.set_result(ok)

    def _mark_connected(self) -> None:
        self._connected = True
        self._connected_at = datetime.now(timezone.utc)
        self._connected_monotonic = time.monotonic()
        self._last_rx_monotonic = None
        self._last_error = None

    def _mark_rx(self) -> None:
        self._last_rx_at = datetime.now(timezone.utc)
        self._last_rx_monotonic = time.monotonic()

    def _is_rx_stale(self) -> bool:
        silence = self._rx_silence_seconds()
        return silence is not None and silence >= self._rx_stale_after

    def _rx_silence_seconds(self) -> float | None:
        if self._last_rx_monotonic is not None:
            return round(time.monotonic() - self._last_rx_monotonic, 1)
        if self._connected_monotonic is not None:
            return round(time.monotonic() - self._connected_monotonic, 1)
        return None

    def _seconds_since_last_rx(self) -> float | None:
        if self._last_rx_at is None:
            return None
        return round((datetime.now(timezone.utc) - self._last_rx_at).total_seconds(), 1)

    def _health_state(self, stale: bool) -> str:
        if not self._connected:
            return "disconnected"
        if stale:
            return "stale"
        if self._last_rx_monotonic is None:
            return "connected_no_rx"
        return "receiving"


def _isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
