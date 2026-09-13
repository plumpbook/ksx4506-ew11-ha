"""Conservative endpoint alert selection, independent of HA and wallpad power."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SILENCE_SECONDS: Final = 180
PASSIVE_STALE_SECONDS: Final = 900


@dataclass(frozen=True, slots=True)
class Endpoint:
    key: str
    device_keys: tuple[str, ...]
    responses: int
    last_response: float | None
    queryable: bool


@dataclass(frozen=True, slots=True)
class DeviceAlert:
    endpoint: str
    device_keys: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class AlertScan:
    probes: tuple[str, ...]
    alerts: tuple[DeviceAlert, ...]


class AlertPolicy:
    """Accumulate evidence; old registry records alone never qualify for alerts."""

    def __init__(self, *, started: float, known: dict[str, float] | None = None) -> None:
        self.started = started
        self.known = dict(known or {})
        self.failures: dict[str, int] = {}
        self.probed_at: dict[str, float] = {}
        self.last_observed: dict[str, float] = {}

    def scan(self, endpoints: tuple[Endpoint, ...], *, now: float) -> AlertScan:
        present = {endpoint.key for endpoint in endpoints}
        for mapping in (self.known, self.failures, self.probed_at, self.last_observed):
            for key in mapping.keys() - present:
                del mapping[key]
        due: list[str] = []
        alerts: list[DeviceAlert] = []
        for endpoint in endpoints:
            key, observed = endpoint.key, endpoint.last_response
            if observed is not None and observed > self.last_observed.get(key, -1):
                self.last_observed[key] = observed
                self.failures.pop(key, None)
            if endpoint.responses >= 3 and observed is not None:
                self.known[key] = max(observed, self.known.get(key, observed))
            baseline = self.known.get(key)
            if baseline is None or now - self.started < SILENCE_SECONDS:
                continue
            last_seen = max(baseline, observed if observed is not None else baseline)
            threshold = SILENCE_SECONDS if endpoint.queryable else PASSIVE_STALE_SECONDS
            if now - last_seen < threshold:
                continue
            if endpoint.queryable:
                if now - self.probed_at.get(key, float("-inf")) >= 30:
                    due.append(key)
                if self.failures.get(key, 0) < 3:
                    continue
            alerts.append(DeviceAlert(key, endpoint.device_keys,
                                      "no_response" if endpoint.queryable else "stale"))
        due.sort(key=lambda key: (self.probed_at.get(key, float("-inf")), key))
        return AlertScan(tuple(due[:4]), tuple(alerts))

    def record_probe(self, key: str, *, success: bool, now: float) -> None:
        self.probed_at[key] = now
        if success:
            self.known[key] = now
            self.failures.pop(key, None)
        else:
            self.failures[key] = self.failures.get(key, 0) + 1
