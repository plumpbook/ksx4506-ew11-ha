from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Final, Literal, NotRequired, Protocol, TypedDict
import time

from .discovery import (
    EVENT_COMMANDS_BY_DEVICE,
    REQUEST_COMMANDS_BY_DEVICE,
    STATE_COMMANDS_BY_DEVICE,
)
from .response_validation import valid_response_payload

_DEFAULT_STALE_AFTER: Final = timedelta(minutes=5)
_COMMAND_ACKS_BY_DEVICE = {
    0x0E: {0xC1}, 0x12: {0xC1}, 0x39: {0xC1, 0xC3},
    0x36: STATE_COMMANDS_BY_DEVICE[0x36] - {0x81},
}


class VitalityFrame(Protocol):
    addr: int
    sub_id: int
    cmd: int
    payload: bytes


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
    last_failure_at: str | None
    last_failure_reason: str | None
    consecutive_failures: int
    state_response_count: NotRequired[int]
    last_state_response_at: NotRequired[str | None]
    seconds_since_state_response: NotRequired[float | None]
    command_ack_count: NotRequired[int]
    last_command_ack_at: NotRequired[str | None]
    invalid_response_count: NotRequired[int]
    last_invalid_response_at: NotRequired[str | None]
    probe_failure_count: NotRequired[int]
    consecutive_probe_failures: NotRequired[int]
    observation_state: NotRequired[str]
    status_summary: NotRequired[str]
    query_supported: NotRequired[bool]
    last_state_connection_epoch: NotRequired[int | None]
    state_current_connection: NotRequired[bool | None]
    last_query_result: NotRequired[dict[str, Any]]


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
    observed_since: NotRequired[str]
    connection_epoch: NotRequired[int | None]


@dataclass(slots=True)  # noqa: MUTABLE_OK - protocol counters accumulate over time
class _EndpointVitality:
    request_count: int = 0
    response_count: int = 0
    event_count: int = 0
    last_response_at: datetime | None = None
    last_event_at: datetime | None = None
    last_probe_at: datetime | None = None
    last_probe_success: bool | None = None
    last_failure_at: datetime | None = None
    last_failure_reason: str | None = None
    consecutive_failures: int = 0
    state_response_count: int = 0
    command_ack_count: int = 0
    invalid_response_count: int = 0
    probe_failure_count: int = 0
    consecutive_probe_failures: int = 0
    last_state_response_at: datetime | None = None
    last_state_response_clock: float | None = None
    last_response_clock: float | None = None
    last_command_ack_at: datetime | None = None
    last_invalid_response_at: datetime | None = None
    last_probe_clock: float | None = None
    last_state_connection_epoch: int | None = None


class DeviceVitalityMonitor:
    """Track protocol endpoint health from passive traffic and active probes."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        stale_after: timedelta = _DEFAULT_STALE_AFTER,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._clock = clock or (time.monotonic if now is None else lambda: self._now().timestamp())
        self._started_at = self._now()
        self._stale_after = stale_after
        self._endpoints: dict[tuple[int, int], _EndpointVitality] = {}

    def observe(self, frame: VitalityFrame, *, connection_epoch: int | None = None) -> None:
        commands = REQUEST_COMMANDS_BY_DEVICE.get(frame.addr, set())
        response_commands = STATE_COMMANDS_BY_DEVICE.get(frame.addr, set())
        event_commands = EVENT_COMMANDS_BY_DEVICE.get(frame.addr, set())
        if frame.cmd not in commands | response_commands | event_commands:
            return
        endpoint = self._endpoint(frame.addr, frame.sub_id)
        if frame.cmd in response_commands and not valid_response_payload(
            frame.addr, frame.cmd, frame.payload,
        ):
            endpoint.invalid_response_count += 1
            endpoint.last_invalid_response_at = self._now()
            return

        if frame.cmd in response_commands:
            endpoint.response_count += 1
            endpoint.last_response_at = self._now()
            endpoint.last_response_clock = self._clock()
            if frame.addr == 0x33 and frame.cmd == 0x83:
                endpoint.event_count += 1
                endpoint.last_event_at = self._now()
            if frame.cmd == (0x82 if frame.addr == 0x40 else 0x81):
                endpoint.state_response_count += 1
                endpoint.last_state_response_at = self._now()
                endpoint.last_state_response_clock = self._clock()
                endpoint.last_state_connection_epoch = connection_epoch
                endpoint.consecutive_failures = 0
                endpoint.consecutive_probe_failures = 0
            elif frame.cmd in _COMMAND_ACKS_BY_DEVICE.get(frame.addr, set()):
                endpoint.command_ack_count += 1
                endpoint.last_command_ack_at = self._now()
        elif frame.cmd in event_commands:
            endpoint.event_count += 1
            endpoint.last_event_at = self._now()
        else:
            endpoint.request_count += 1

    def record_probe(self, addr: int, sub_id: int, *, success: bool) -> None:
        endpoint = self._endpoint(addr, sub_id)
        endpoint.last_probe_at = self._now()
        endpoint.last_probe_clock = self._clock()
        endpoint.last_probe_success = success
        if success:
            endpoint.consecutive_failures = 0
            endpoint.consecutive_probe_failures = 0
            return
        endpoint.probe_failure_count += 1
        endpoint.consecutive_probe_failures += 1
        self._record_failure(endpoint, reason="state_probe_not_confirmed")

    def record_command_failure(
        self,
        addr: int,
        sub_id: int,
        *,
        reason: str,
    ) -> None:
        """Mark an endpoint unhealthy immediately after a control failure."""
        self._record_failure(self._endpoint(addr, sub_id), reason=reason)

    def _record_failure(
        self,
        endpoint: _EndpointVitality,
        *,
        reason: str,
    ) -> None:
        endpoint.last_failure_at = self._now()
        endpoint.last_failure_reason = reason
        endpoint.consecutive_failures += 1

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
            "observed_since": self._started_at.isoformat(),
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
        clock = self._clock()
        seconds_since_response = _elapsed(clock, endpoint.last_response_clock)
        state_age = _elapsed(clock, endpoint.last_state_response_clock)
        probe_age = _elapsed(clock, endpoint.last_probe_clock)
        response_after_probe = (
            endpoint.last_state_response_clock is not None
            and endpoint.last_probe_clock is not None
            and endpoint.last_state_response_clock > endpoint.last_probe_clock
        )
        failed_latest_probe = (
            endpoint.last_probe_success is False and not response_after_probe
        )
        if (endpoint.state_response_count > 0 and failed_latest_probe
                and endpoint.consecutive_probe_failures >= 3):
            status: VitalityStatus = "unresponsive"
        elif (endpoint.last_probe_success is True and probe_age is not None
              and probe_age <= self._stale_after.total_seconds()):
            status = "healthy"
        elif state_age is not None:
            status = (
                "healthy"
                if state_age <= self._stale_after.total_seconds()
                else "stale"
            )
        elif endpoint.event_count:
            status = "event_only"
        else:
            status = "unknown"
        observation = ("state_observed" if state_age is not None
                       else "event_only" if endpoint.event_count
                       else "ack_only" if endpoint.command_ack_count
                       else "other_response" if endpoint.response_count else "unobserved")
        summary = {
            "healthy": "최근 유효 상태 확인 · 실제 출력 보증 아님",
            "unresponsive": "응답 이력 있음 · 상태 확인 3회 이상 실패 · 원인 미확정",
            "stale": "상태 응답이 오래됨 · 조용함만으로 고장 확정 불가",
            "event_only": "이벤트만 관측 · 조용함만으로 고장 판단 안 함",
            "unknown": "유효 상태 미관측 · 고장 판단 근거 부족",
        }[status]

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
            "last_failure_at": _isoformat(endpoint.last_failure_at),
            "last_failure_reason": endpoint.last_failure_reason,
            "consecutive_failures": endpoint.consecutive_failures,
            "state_response_count": endpoint.state_response_count,
            "last_state_response_at": _isoformat(endpoint.last_state_response_at),
            "seconds_since_state_response": state_age,
            "command_ack_count": endpoint.command_ack_count,
            "last_command_ack_at": _isoformat(endpoint.last_command_ack_at),
            "invalid_response_count": endpoint.invalid_response_count,
            "last_invalid_response_at": _isoformat(endpoint.last_invalid_response_at),
            "probe_failure_count": endpoint.probe_failure_count,
            "consecutive_probe_failures": endpoint.consecutive_probe_failures,
            "observation_state": observation,
            "status_summary": summary,
            'last_state_connection_epoch': endpoint.last_state_connection_epoch,
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


def _elapsed(now: float, then: float | None) -> float | None:
    return max(0.0, now - then) if then is not None else None
