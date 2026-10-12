from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone


class AutoReconnectPolicy:
    def __init__(
        self, *, incident_started_at: float | None = None,
        attempted_at: float | None = None, verified_at: float | None = None,
    ) -> None:
        self.incident_started_at = incident_started_at
        self.attempted_at = attempted_at
        self.verified_at = verified_at

    def evaluate(
        self, endpoints: Iterable[tuple[str, float]], failed: set[str], *,
        now: float, connected: bool, busy: bool,
    ) -> bool:
        known = dict(endpoints)
        if self.attempted_at is not None:
            recovered = {key.split("/")[0] for key, last in known.items()
                         if last > self.attempted_at}
            if len(recovered) >= 2:
                self.verified_at = now
                self.incident_started_at = None
                self.attempted_at = None
            return False

        recent_baselines = {key for key, last in known.items()
                            if 0 <= now - last <= 86400}
        shared_outage = (
            len(known) >= 3
            and len({key.split("/")[0] for key in known}) >= 2
            and len(recent_baselines) >= 3
            and failed == known.keys()
        )
        if not shared_outage:
            self.incident_started_at = None
            return False
        if self.incident_started_at is None:
            self.incident_started_at = now
        if now - self.incident_started_at < 180 or not connected or busy:
            return False
        self.attempted_at = now
        return True

    def attributes(self) -> Mapping[str, str | None]:
        def timestamp(value: float | None) -> str | None:
            if value is None:
                return None
            return datetime.fromtimestamp(value, timezone.utc).isoformat()

        return {
            "auto_reconnect_state": (
                "awaiting_confirmed_responses" if self.attempted_at is not None
                else "suspected_shared_outage" if self.incident_started_at is not None
                else "last_attempt_verified" if self.verified_at is not None else "idle"
            ),
            "auto_reconnect_incident_started_at": timestamp(self.incident_started_at),
            "auto_reconnect_attempted_at": timestamp(self.attempted_at),
            "auto_reconnect_verified_at": timestamp(self.verified_at),
        }
