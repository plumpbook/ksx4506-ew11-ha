"""Bounded command recovery; a shared status packet never clears another channel."""
from __future__ import annotations

import asyncio  # noqa: ANYIO_OK - Home Assistant owns the asyncio event loop
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any

from .protocol_types import KsFrame

type Operation = Callable[[], Awaitable[KsFrame | None]]


@dataclass(slots=True)  # noqa: MUTABLE_OK - command lifecycle state
class CommandStatus:
    endpoint: tuple[int, int]
    matcher: Callable[[KsFrame], bool]
    state: str = "pending"
    attempts: int = 0
    reason: str | None = None
    failed_at: float | None = None
    channel: int | None = None
    target_state: dict[str, Any] | None = None
    ack_matcher: Callable[[KsFrame], bool] | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_clock: float = field(default_factory=time.monotonic)
    last_ack_at: str | None = None
    confirmed_at: str | None = None
    finished_at: str | None = None


class CommandRecovery:
    def __init__(
        self, publish: Callable[[], None], *, deadline: float = 30,
        delays: tuple[float, ...] = (1.0, 3.0),
    ) -> None:
        self._publish = publish
        self.deadline = deadline
        self.delays = delays
        self.status: dict[str, CommandStatus] = {}
        self._tasks: dict[str, asyncio.Task[KsFrame | None]] = {}
        self._accepting = True

    async def execute(
        self, key: str, endpoint: tuple[int, int],
        matcher: Callable[[KsFrame], bool], operation: Operation,
        probe: Operation | None = None, *, retry: bool = True,
        channel: int | None = None, target_state: dict[str, Any] | None = None,
        ack_matcher: Callable[[KsFrame], bool] | None = None,
    ) -> KsFrame | None:
        previous = self._tasks.get(key)
        if previous is not None:
            previous.cancel()
        status = CommandStatus(endpoint, matcher)
        status.channel = channel
        status.target_state = target_state.copy() if target_state is not None else None
        status.ack_matcher = ack_matcher
        self.status[key] = status
        if not self._accepting:
            status.state = "failed"
            status.reason = "recovery_in_progress"
            self._publish()
            return None

        async def run() -> KsFrame | None:
            try:
                async with asyncio.timeout(self.deadline):
                    for index, delay in enumerate((0.0, *(self.delays if retry else ()))):
                        if index:
                            status.state = "recovering"
                            self._publish()
                            await asyncio.sleep(delay)
                            if probe is not None:
                                matched = await probe()
                                if matched is not None and matcher(matched):
                                    status.state = "healthy"
                                    status.confirmed_at = datetime.now(timezone.utc).isoformat()
                                    return matched
                        status.attempts += 1
                        matched = await operation()
                        if matched is not None and matcher(matched):
                            status.state = "healthy"
                            status.confirmed_at = datetime.now(timezone.utc).isoformat()
                            return matched
                    status.reason = "state_not_confirmed"
            except TimeoutError:
                status.reason = "command_expired"
            except asyncio.CancelledError:
                status.state = "failed"
                status.reason = "superseded_or_stopped"
                status.failed_at = time.monotonic()
                raise
            except Exception:  # noqa: BROAD_EXCEPT_OK - record then propagate to HA
                status.state = "failed"
                status.reason = "command_exception"
                status.failed_at = time.monotonic()
                raise
            finally:
                status.finished_at = datetime.now(timezone.utc).isoformat()
                self._publish()
            status.state = "failed"
            status.failed_at = time.monotonic()
            self._publish()
            return None

        task = asyncio.create_task(run())
        self._tasks[key] = task
        self._publish()
        try:
            return await task
        except asyncio.CancelledError:
            # Superseding a command must not cancel the newer HA service call.
            if self._tasks.get(key) is not task:
                return None
            raise
        finally:
            if self._tasks.get(key) is task:
                del self._tasks[key]

    def observe(self, frame: KsFrame) -> bool:
        changed = False
        for status in self.status.values():
            if (status.state in {'pending', 'recovering'} and status.ack_matcher is not None
                    and status.ack_matcher(frame)):
                status.last_ack_at = datetime.now(timezone.utc).isoformat()
                changed = True
            if status.state == "failed" and status.matcher(frame):
                status.state = "healthy"
                status.reason = None
                status.failed_at = None
                status.confirmed_at = datetime.now(timezone.utc).isoformat()
                changed = True
        return changed

    def attributes(self, key: str) -> dict[str, Any]:
        status = self.status.get(key)
        return {
            "control_status": status.state if status else "unknown",
            "recovery_attempts": status.attempts if status else 0,
            "control_error": status.reason if status else None,
            "control_channel": status.channel if status else None,
            "control_target_state": status.target_state if status else None,
            "control_started_at": status.started_at if status else None,
            "control_finished_at": status.finished_at if status else None,
            "control_last_ack_at": status.last_ack_at if status else None,
            "target_state_confirmed_at": status.confirmed_at if status else None,
        }

    def report(self) -> dict[str, dict[str, Any]]:
        return {key: self.attributes(key) for key in self.status
                if self.status[key].state != "healthy"}

    def failed_endpoints(self, *, window: float = 120) -> set[tuple[int, int]]:
        now = time.monotonic()
        return {s.endpoint for s in self.status.values()
                if s.state == "failed" and s.failed_at is not None
                and now - s.failed_at < window}

    async def stop(self) -> None:
        self._accepting = False
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def resume(self) -> None:
        self._accepting = True


class HubRecoveryPolicy:
    """Two independent failed endpoints before reconnect; zero responders before power."""

    def __init__(self) -> None:
        self.bad_since: float | None = None
        self.reconnected_at: float | None = None
        self.last_reconnect: float | None = None
        self.power_attempted = False
        self.state = "idle"

    def action(
        self, *, now: float, link_failed: bool, failed_endpoints: int,
        responders: int, power_enabled: bool,
    ) -> str | None:
        bad = link_failed or failed_endpoints >= 2
        if not bad:
            self.bad_since = None
            self.reconnected_at = None
            self.power_attempted = False
            self.state = "idle"
            return None
        if self.bad_since is None:
            self.bad_since = now
        if now - self.bad_since < 30:
            return None
        if self.reconnected_at is None:
            if self.last_reconnect is not None and now - self.last_reconnect < 300:
                return None
            self.last_reconnect = self.reconnected_at = now
            self.state = "reconnecting"
            return "reconnect"
        if now - self.reconnected_at < 120:
            return None
        self.state = "failed"
        if responders == 0 and power_enabled and not self.power_attempted:
            self.power_attempted = True
            self.state = "power_cycle"
            return "power_cycle"
        return None
