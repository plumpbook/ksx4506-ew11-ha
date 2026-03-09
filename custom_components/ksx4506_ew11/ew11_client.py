from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine

from .protocol import Ksx4506Codec, KsFrame

_LOGGER = logging.getLogger(__name__)


class Ew11Client:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        retry: int,
        codec: Ksx4506Codec,
        on_frame: Callable[[KsFrame], Coroutine[None, None, None]],
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._retry = retry
        self._codec = codec
        self._on_frame = on_frame

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._worker_task: asyncio.Task | None = None
        self._running = False

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

    async def send_with_retry(self, payload: bytes) -> bool:
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        await self._cmd_queue.put((payload, fut))
        try:
            return await asyncio.wait_for(fut, timeout=max(self._timeout * (self._retry + 2), 1.0))
        except TimeoutError:
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
                _LOGGER.info("EW11 connected")

                while self._running:
                    try:
                        data = await asyncio.wait_for(self._reader.read(1024), timeout=self._timeout)
                    except TimeoutError:
                        # EW11/RS485 can stay idle for a while; this is not a connection failure.
                        continue

                    if not data:
                        raise ConnectionError("EW11 connection closed")

                    for frame in self._codec.feed(data):
                        await self._on_frame(frame)

            except Exception as exc:
                _LOGGER.warning("EW11 loop error (%s:%s): %r", self._host, self._port, exc)
                await self._close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)

    async def _close(self) -> None:
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
            for _ in range(self._retry + 1):
                if not self._writer:
                    await asyncio.sleep(0.2)
                    continue
                try:
                    self._writer.write(payload)
                    await self._writer.drain()
                    ok = True
                    break
                except Exception:
                    await asyncio.sleep(0.2)
            if not fut.done():
                fut.set_result(ok)
