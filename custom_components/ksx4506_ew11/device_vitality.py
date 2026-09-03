from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, Literal, Protocol, TypedDict

from .discovery import (
    EVENT_COMMANDS_BY_DEVICE,
    REQUEST_COMMANDS_BY_DEVICE,
    STATE_COMMANDS_BY_DEVICE,
)

_DEFAULT_STALE_AFTER: Final = timedelta(minutes=5)


class VitalityFrame(Protocol):
    addr: int
    sub_id: int
    cmd: int


class VitalityDevice(Protocol):
    key: str
    addr: int
    sub_id: int
    kind: str
    channel: int | None
    @property
    def state(self) -> Mapping[str, int]: ...


type VitalityStatus = Literal[
    "healthy",
    "unresponsive",
    "stale",
    "event_only",
    "unknown",
]


class DeviceVitalityEntry(TypedDict):
    endpoint: str
    device_id: str
    sub_id: str
    kind: str
    device_keys: list[str]
    status: VitalityStatus
    request_count: int
    response_count: int
    event_count: int
    last_response_at: str | None
    seconds_since_response: float | None
    last_probe_at: str | None
    last_probe_success: bool | None


class VitalityCounts(TypedDict):
    healthy: int
    unresponsive: int
    stale: int
    event_only: int
    unknown: int


class DeviceVitalityReport(VitalityCounts):
    state: VitalityStatus
    total: int
    stale_after_seconds: float
    devices: list[DeviceVitalityEntry]


@dataclass(slots=True)  # noqa: MUTABLE_OK - protocol counters accumulate over time
class _EndpointVitality:
    request_count: int = 0
    response_count: int = 0
    event_count: int = 0
    last_response_at: datetime | None = None
    last_event_at: datetime | None = None
    last_probe_at: datetime | None = None
    last_probe_success: bool | None = None


class DeviceVitalityMonitor:
    """Track protocol endpoint health from passive traffic and active probes."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        stale_after: timedelta = _DEFAULT_STALE_AFTER,
    ) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._stale_after = stale_after
        self._endpoints: dict[tuple[int, int], _EndpointVitality] = {}

    def observe(self, frame: VitalityFrame) -> None:
        commands = REQUEST_COMMANDS_BY_DEVICE.get(frame.addr, set())
        response_commands = STATE_COMMANDS_BY_DEVICE.get(frame.addr, set())
        event_commands = EVENT_COMMANDS_BY_DEVICE.get(frame.addr, set())
        if frame.cmd not in commands | response_commands | event_commands:
            return

        endpoint = self._endpoint(frame.addr, frame.sub_id)
        if frame.cmd in response_commands:
            endpoint.response_count += 1
            endpoint.last_response_at = self._now()
        elif frame.cmd in event_commands:
            endpoint.event_count += 1
            endpoint.last_event_at = self._now()
        else:
            endpoint.request_count += 1

    def record_probe(self, addr: int, sub_id: int, *, success: bool) -> None:
        endpoint = self._endpoint(addr, sub_id)
        endpoint.last_probe_at = self._now()
        endpoint.last_probe_success = success

    def report(self, devices: Iterable[VitalityDevice]) -> DeviceVitalityReport:
        now = self._now()
        grouped: dict[tuple[int, int], list[VitalityDevice]] = {}
        for device in devices:
            status_sub_id = device.state.get("status_sub_id", device.sub_id)
            grouped.setdefault((device.addr, status_sub_id), []).append(device)

        entries = [
            self._device_report(endpoint, members, now)
            for endpoint, members in sorted(grouped.items())
        ]
        counts: VitalityCounts = {
            "healthy": sum(entry["status"] == "healthy" for entry in entries),
            "unresponsive": sum(
                entry["status"] == "unresponsive" for entry in entries
            ),
            "stale": sum(entry["status"] == "stale" for entry in entries),
            "event_only": sum(
                entry["status"] == "event_only" for entry in entries
            ),
            "unknown": sum(entry["status"] == "unknown" for entry in entries),
        }
        return {
            "state": self._overall_state(counts, bool(entries)),
            "total": len(entries),
            **counts,
            "stale_after_seconds": self._stale_after.total_seconds(),
            "devices": entries,
        }

    def _endpoint(self, addr: int, sub_id: int) -> _EndpointVitality:
        return self._endpoints.setdefault((addr, sub_id), _EndpointVitality())

    def _device_report(
        self,
        endpoint_key: tuple[int, int],
        devices: list[VitalityDevice],
        now: datetime,
    ) -> DeviceVitalityEntry:
        addr, sub_id = endpoint_key
        endpoint = self._endpoints.get(endpoint_key, _EndpointVitality())
        seconds_since_response = _seconds_since(now, endpoint.last_response_at)
        response_after_probe = (
            endpoint.last_response_at is not None
            and endpoint.last_probe_at is not None
            and endpoint.last_response_at > endpoint.last_probe_at
        )
        failed_latest_probe = (
            endpoint.last_probe_success is False and not response_after_probe
        )

        if failed_latest_probe:
            status: VitalityStatus = "unresponsive"
        elif endpoint.last_probe_success is True:
            status = "healthy"
        elif seconds_since_response is not None:
            status = (
                "healthy"
                if seconds_since_response <= self._stale_after.total_seconds()
                else "stale"
            )
        elif endpoint.event_count:
            status = "event_only"
        else:
            status = "unknown"

        return {
            "endpoint": f"0x{addr:02X}/0x{sub_id:02X}",
            "device_id": f"0x{addr:02X}",
            "sub_id": f"0x{sub_id:02X}",
            "kind": devices[0].kind,
            "device_keys": sorted(device.key for device in devices),
            "status": status,
            "request_count": endpoint.request_count,
            "response_count": endpoint.response_count,
            "event_count": endpoint.event_count,
            "last_response_at": _isoformat(endpoint.last_response_at),
            "seconds_since_response": seconds_since_response,
            "last_probe_at": _isoformat(endpoint.last_probe_at),
            "last_probe_success": endpoint.last_probe_success,
        }

    @staticmethod
    def _overall_state(
        counts: VitalityCounts,
        has_devices: bool,
    ) -> VitalityStatus:
        if counts["unresponsive"]:
            return "unresponsive"
        if counts["stale"]:
            return "stale"
        if counts["unknown"] or counts["event_only"]:
            return "unknown"
        return "healthy" if has_devices else "unknown"


def _seconds_since(now: datetime, then: datetime | None) -> float | None:
    if then is None:
        return None
    return max(0.0, (now - then).total_seconds())


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
