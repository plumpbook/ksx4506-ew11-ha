from __future__ import annotations

import time
from datetime import datetime, timezone


class Ew11ConnectionStats:
    def __init__(self) -> None:
        self._connect_attempts = 0
        self._connect_successes = 0
        self._disconnect_count = 0
        self._last_disconnect_at: datetime | None = None
        self._last_disconnect_reason: str | None = None
        self._last_connected_duration_seconds: float | None = None

    def record_attempt(self) -> None:
        self._connect_attempts += 1

    def record_connected(self) -> None:
        self._connect_successes += 1

    def record_disconnect(
        self,
        reason: str | None,
        connected_monotonic: float | None,
    ) -> None:
        self._disconnect_count += 1
        self._last_disconnect_at = datetime.now(timezone.utc)
        self._last_disconnect_reason = reason
        if connected_monotonic is not None:
            self._last_connected_duration_seconds = round(
                time.monotonic() - connected_monotonic,
                1,
            )

    def report(
        self,
        connected: bool,
        connected_monotonic: float | None,
    ) -> dict[str, int | str | float | None]:
        return {
            "connect_attempts": self._connect_attempts,
            "connect_successes": self._connect_successes,
            "disconnect_count": self._disconnect_count,
            "last_disconnect_at": _isoformat_or_none(self._last_disconnect_at),
            "last_disconnect_reason": self._last_disconnect_reason,
            "last_connected_duration_seconds": self._last_connected_duration_seconds,
            "current_uptime_seconds": _current_uptime_seconds(
                connected,
                connected_monotonic,
            ),
        }

    def signature(self) -> tuple[int, int, int]:
        return (
            self._connect_attempts,
            self._connect_successes,
            self._disconnect_count,
        )


def _current_uptime_seconds(
    connected: bool,
    connected_monotonic: float | None,
) -> float | None:
    if not connected or connected_monotonic is None:
        return None
    return round(time.monotonic() - connected_monotonic, 1)


def _isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
