from __future__ import annotations

import asyncio  # noqa: ANYIO_OK
from contextlib import suppress
from dataclasses import dataclass
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any, Final

from .ew11_connection_stats import Ew11ConnectionStats
from .protocol import Ksx4506Codec, KsFrame

_LOGGER = logging.getLogger(__name__)
DEFAULT_RX_STALE_AFTER: Final = 20.0
DEFAULT_RX_RECONNECT_AFTER: Final = 120.0
MAX_COMMAND_QUEUE_SIZE: Final = 64


@dataclass(slots=True)
class _QueuedCommand:
    payload: bytes
    future: asyncio.Future[bool]
    deadline: float


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
        self._rx_reconnect_after = max(
            float(DEFAULT_RX_RECONNECT_AFTER),
            self._rx_stale_after,
            timeout,
        )

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._connected_event = asyncio.Event()
        self._running = False
        self._connected = False
        self._connected_at: datetime | None = None
        self._connected_monotonic: float | None = None
        self._last_rx_at: datetime | None = None
        self._last_rx_monotonic: float | None = None
        self._connection_stats = Ew11ConnectionStats()
        self._last_error: str | None = None
        self._health_listener: Callable[[], None] | None = None
        self._last_health_signature: (
            tuple[str, bool, bool, str | None, tuple[int, int, int]] | None
        ) = None

        self._cmd_queue: asyncio.Queue[_QueuedCommand] = asyncio.Queue(
            maxsize=MAX_COMMAND_QUEUE_SIZE
        )
        self._active_command: _QueuedCommand | None = None

    def set_health_listener(self, listener: Callable[[], None] | None) -> None:
        self._health_listener = listener

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._publish_health_change()
        self._task = asyncio.create_task(self._run_loop())
        self._worker_task = asyncio.create_task(self._command_worker())

    async def stop(self) -> None:
        self._running = False

        tasks = [task for task in (self._task, self._worker_task) if task is not None]

        active = self._active_command
        if active is not None and not active.future.done():
            active.future.set_result(False)

        # Unblock any pending send_with_retry waiters.
        while not self._cmd_queue.empty():
            command = self._cmd_queue.get_nowait()
            if not command.future.done():
                command.future.set_result(False)
            self._cmd_queue.task_done()

        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

        self._task = None
        self._worker_task = None
        self._active_command = None

        await self._close()

    def health_report(self) -> dict[str, Any]:
        rx_silence = self._rx_silence_seconds()
        seconds_since_last_rx = self._seconds_since_last_rx()
        stale = rx_silence is not None and rx_silence >= self._rx_stale_after
        state = self._health_state(stale)
        report = {
            "state": state,
            "connected": self._connected,
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "timeout": self._timeout,
            "retry": self._retry,
            "rx_stale_after": self._rx_stale_after,
            "rx_reconnect_after": self._rx_reconnect_after,
            "last_connect_at": _isoformat_or_none(self._connected_at),
            "last_rx_at": _isoformat_or_none(self._last_rx_at),
            "seconds_since_last_rx": seconds_since_last_rx,
            "seconds_without_rx": rx_silence,
            "last_error": self._last_error,
        }
        report.update(
            self._connection_stats.report(
                self._connected,
                self._connected_monotonic,
            )
        )
        return report

    async def send_with_retry(self, payload: bytes) -> bool:
        if not self._running:
            _LOGGER.warning("TX rejected because EW11 client is not running len=%d", len(payload))
            return False

        _LOGGER.debug("queue TX len=%d", len(payload))
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        command = _QueuedCommand(
            payload=payload,
            future=fut,
            deadline=loop.time() + self._command_timeout(),
        )
        try:
            self._cmd_queue.put_nowait(command)
        except asyncio.QueueFull:
            _LOGGER.warning("TX queue is full; rejecting command len=%d", len(payload))
            return False

        try:
            async with asyncio.timeout_at(command.deadline):
                return await asyncio.shield(fut)
        except TimeoutError:
            if not fut.done():
                fut.cancel()
            _LOGGER.warning("TX queue timed out len=%d", len(payload))
            return False
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            raise

    async def _run_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                _LOGGER.info("Connecting EW11 %s:%s", self._host, self._port)
                self._connection_stats.record_attempt()
                self._publish_health_change()
                try:
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self._host, self._port),
                        timeout=self._timeout,
                    )
                except (asyncio.TimeoutError, TimeoutError) as exc:
                    raise TimeoutError(
                        f"EW11 connect timed out after {self._timeout:.1f}s"
                    ) from exc
                backoff = 1
                self._mark_connected()
                _LOGGER.info("EW11 connected")

                reader = self._reader
                while self._running and reader is not None:
                    try:
                        data = await asyncio.wait_for(
                            reader.read(1024), timeout=self._timeout
                        )
                    except (asyncio.TimeoutError, TimeoutError):
                        self._publish_health_change()
                        if self._should_reconnect_for_rx_silence():
                            silence = self._rx_silence_seconds()
                            raise ConnectionError(f"EW11 RX stale for {silence:.1f}s")
                        continue

                    if not data:
                        raise ConnectionError("EW11 connection closed")

                    _LOGGER.debug("EW11 RX chunk len=%d", len(data))
                    frames = self._codec.feed(data)
                    if frames:
                        self._mark_rx()
                    for frame in frames:
                        await self._on_frame(frame)

            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                reason = repr(exc)
                self._last_error = reason
                _LOGGER.warning("EW11 loop error (%s:%s): %r", self._host, self._port, exc)
                await self._close(reason=reason, count_disconnect=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)

    async def _close(
        self,
        reason: str | None = None,
        count_disconnect: bool = False,
    ) -> None:
        was_connected = self._connected
        connected_monotonic = self._connected_monotonic
        self._connected = False
        self._connected_monotonic = None
        self._connected_event.clear()
        if was_connected and count_disconnect:
            self._connection_stats.record_disconnect(reason, connected_monotonic)
        self._publish_health_change()
        writer = self._writer
        self._reader, self._writer = None, None
        if writer:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=self._timeout)
            except (OSError, TimeoutError) as exc:
                _LOGGER.debug("EW11 writer close wait failed: %r", exc)

    async def _command_worker(self) -> None:
        while True:
            command = await self._cmd_queue.get()
            self._active_command = command
            try:
                ok = await self._send_queued_command(command)
                if not command.future.done():
                    command.future.set_result(ok)
            finally:
                self._active_command = None
                self._cmd_queue.task_done()

    async def _send_queued_command(self, command: _QueuedCommand) -> bool:
        loop = asyncio.get_running_loop()
        attempts = self._retry + 1
        attempt = 0
        while attempt < attempts:
            if (
                not self._running
                or command.future.done()
                or loop.time() >= command.deadline
            ):
                return False

            writer = self._writer
            if writer is None or (
                callable(is_closing := getattr(writer, "is_closing", None))
                and is_closing()
            ):
                remaining = command.deadline - loop.time()
                if remaining <= 0:
                    return False
                try:
                    await asyncio.wait_for(
                        self._connected_event.wait(),
                        timeout=min(0.2, remaining),
                    )
                except TimeoutError:
                    pass
                continue

            attempt += 1
            try:
                writer.write(command.payload)
                remaining = command.deadline - loop.time()
                if remaining <= 0:
                    self._abort_writer(writer)
                    return False
                await asyncio.wait_for(
                    writer.drain(),
                    timeout=min(self._timeout, remaining),
                )
                _LOGGER.debug(
                    "TX sent (attempt=%d/%d) len=%d",
                    attempt,
                    attempts,
                    len(command.payload),
                )
                return True
            except (OSError, TimeoutError) as exc:
                _LOGGER.debug(
                    "TX failed (attempt=%d/%d): %r",
                    attempt,
                    attempts,
                    exc,
                )
                self._abort_writer(writer)
                await self._close(reason=repr(exc), count_disconnect=True)
                if attempt < attempts:
                    await asyncio.sleep(
                        min(0.2, max(command.deadline - loop.time(), 0))
                    )

        _LOGGER.warning(
            "TX failed after %d attempts len=%d",
            attempts,
            len(command.payload),
        )
        return False

    def _command_timeout(self) -> float:
        return max((self._retry + 1) * (self._timeout + 0.2) + 1.0, 1.0)

    @staticmethod
    def _abort_writer(writer: asyncio.StreamWriter) -> None:
        transport = getattr(writer, "transport", None)
        abort = getattr(transport, "abort", None)
        if callable(abort):
            abort()
            return
        writer.close()

    def _mark_connected(self) -> None:
        self._connected = True
        self._connected_event.set()
        self._connection_stats.record_connected()
        self._connected_at = datetime.now(timezone.utc)
        self._connected_monotonic = time.monotonic()
        self._last_rx_monotonic = None
        self._last_error = None
        self._publish_health_change()

    def _mark_rx(self) -> None:
        self._last_rx_at = datetime.now(timezone.utc)
        self._last_rx_monotonic = time.monotonic()
        self._publish_health_change()

    def _is_rx_stale(self) -> bool:
        silence = self._rx_silence_seconds()
        return silence is not None and silence >= self._rx_stale_after

    def _should_reconnect_for_rx_silence(self) -> bool:
        silence = self._rx_silence_seconds()
        return silence is not None and silence >= self._rx_reconnect_after

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

    def _health_signature(self) -> tuple[str, bool, bool, str | None, tuple[int, int, int]]:
        return (
            self._health_state(self._is_rx_stale()),
            self._connected,
            self._running,
            self._last_error,
            self._connection_stats.signature(),
        )

    def _publish_health_change(self) -> None:
        signature = self._health_signature()
        if signature == self._last_health_signature:
            return
        self._last_health_signature = signature
        if self._health_listener is not None:
            self._health_listener()


def _isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
