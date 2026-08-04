from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Final

PACKET_QUALITY_RECENT_WINDOW_SECONDS: Final = 600
_MAX_RECENT_EVENTS: Final = 512
_EVENT_F7_CHECKSUM_ERROR: Final = "f7_checksum_error"
_EVENT_F7_FRAME_ERROR: Final = "f7_frame_error"
_EVENT_F7_RESYNC: Final = "f7_resync"
_EVENT_STX_CHECKSUM_ERROR: Final = "stx_checksum_error"
_EVENT_STX_FRAME_ERROR: Final = "stx_frame_error"
_EVENT_STX_RESYNC: Final = "stx_resync"
_EVENT_TX_CONTROL_GIVEUP: Final = "tx_control_giveup"
_EVENT_TX_STATE_REQUEST_GIVEUP: Final = "tx_state_request_giveup"
_PACKET_SAMPLE_KEYS: Final = frozenset({"raw_hex", "payload_hex"})


class PacketQualityMonitor:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _utc_now
        self.valid_f7_frames = 0
        self.valid_stx_frames = 0
        self.f7_checksum_errors = 0
        self.f7_frame_errors = 0
        self.f7_resync_events = 0
        self.stx_checksum_errors = 0
        self.stx_frame_errors = 0
        self.stx_resync_events = 0
        self.tx_giveups = 0
        self.tx_control_giveups = 0
        self.tx_state_request_giveups = 0
        self._last_valid_f7: dict[str, Any] | None = None
        self._last_rx_error: dict[str, Any] | None = None
        self._last_rx_resync: dict[str, Any] | None = None
        self._last_tx_giveup: dict[str, Any] | None = None
        self._recent_events: deque[tuple[datetime, str]] = deque(
            maxlen=_MAX_RECENT_EVENTS
        )

    def record_f7_frame_ok(
        self,
        *,
        dev_id: int,
        sub_id: int,
        cmd: int,
        length: int,
        frame_raw: bytes,
    ) -> None:
        now = self._now()
        self.valid_f7_frames += 1
        self._last_valid_f7 = {
            "time": _format_time(now),
            "device_id": _hex_byte(dev_id),
            "sub_id": _hex_byte(sub_id),
            "command_type": _hex_byte(cmd),
            "payload_len": length,
            "raw_hex": frame_raw.hex().upper(),
        }

    def record_stx_frame_ok(self) -> None:
        self.valid_stx_frames += 1

    def record_f7_checksum_error(
        self,
        *,
        dev_id: int,
        sub_id: int,
        cmd: int,
        length: int,
        recv_xor: int,
        recv_add: int,
        calc_xor: int,
        calc_add: int,
        frame_raw: bytes,
    ) -> None:
        now = self._now()
        self.f7_checksum_errors += 1
        self._record_recent_event(now, _EVENT_F7_CHECKSUM_ERROR)
        self._last_rx_error = {
            "time": _format_time(now),
            "kind": "f7_checksum",
            "device_id": _hex_byte(dev_id),
            "sub_id": _hex_byte(sub_id),
            "command_type": _hex_byte(cmd),
            "payload_len": length,
            "received_checksum": f"{_hex_byte(recv_xor)}/{_hex_byte(recv_add)}",
            "expected_checksum": f"{_hex_byte(calc_xor)}/{_hex_byte(calc_add)}",
            "raw_hex": frame_raw.hex().upper(),
        }

    def record_f7_frame_error(
        self,
        *,
        reason: str,
        frame_raw: bytes,
        dev_id: int | None = None,
        sub_id: int | None = None,
        cmd: int | None = None,
        length: int | None = None,
    ) -> None:
        now = self._now()
        self.f7_frame_errors += 1
        self._record_recent_event(now, _EVENT_F7_FRAME_ERROR)
        self._last_rx_error = _frame_error_payload(
            "f7_frame",
            reason,
            frame_raw,
            now=now,
            dev_id=dev_id,
            sub_id=sub_id,
            cmd=cmd,
            length=length,
        )

    def record_f7_resync(
        self,
        *,
        reason: str,
        frame_raw: bytes,
        dev_id: int | None = None,
        sub_id: int | None = None,
        cmd: int | None = None,
        length: int | None = None,
    ) -> None:
        now = self._now()
        self.f7_resync_events += 1
        self._record_recent_event(now, _EVENT_F7_RESYNC)
        self._last_rx_resync = _frame_error_payload(
            "f7_resync",
            reason,
            frame_raw,
            now=now,
            dev_id=dev_id,
            sub_id=sub_id,
            cmd=cmd,
            length=length,
        )

    def record_stx_checksum_error(
        self,
        *,
        addr: int,
        cmd: int,
        length: int,
        recv_checksum: int,
        calc_checksum: int,
        frame_raw: bytes,
    ) -> None:
        now = self._now()
        self.stx_checksum_errors += 1
        self._record_recent_event(now, _EVENT_STX_CHECKSUM_ERROR)
        self._last_rx_error = {
            "time": _format_time(now),
            "kind": "stx_checksum",
            "device_id": _hex_byte(addr),
            "command_type": _hex_byte(cmd),
            "payload_len": length,
            "received_checksum": _hex_byte(recv_checksum),
            "expected_checksum": _hex_byte(calc_checksum),
            "raw_hex": frame_raw.hex().upper(),
        }

    def record_stx_frame_error(
        self,
        *,
        reason: str,
        frame_raw: bytes,
        addr: int | None = None,
        cmd: int | None = None,
        length: int | None = None,
    ) -> None:
        now = self._now()
        self.stx_frame_errors += 1
        self._record_recent_event(now, _EVENT_STX_FRAME_ERROR)
        self._last_rx_error = _frame_error_payload(
            "stx_frame",
            reason,
            frame_raw,
            now=now,
            dev_id=addr,
            cmd=cmd,
            length=length,
        )

    def record_stx_resync(
        self,
        *,
        reason: str,
        frame_raw: bytes,
        addr: int | None = None,
        cmd: int | None = None,
        length: int | None = None,
    ) -> None:
        now = self._now()
        self.stx_resync_events += 1
        self._record_recent_event(now, _EVENT_STX_RESYNC)
        self._last_rx_resync = _frame_error_payload(
            "stx_resync",
            reason,
            frame_raw,
            now=now,
            dev_id=addr,
            cmd=cmd,
            length=length,
        )

    def record_tx_giveup(
        self,
        *,
        dev_id: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        attempts: int,
        is_state_request: bool,
        health: dict[str, Any],
    ) -> None:
        now = self._now()
        self.tx_giveups += 1
        if is_state_request:
            self.tx_state_request_giveups += 1
            self._record_recent_event(now, _EVENT_TX_STATE_REQUEST_GIVEUP)
        else:
            self.tx_control_giveups += 1
            self._record_recent_event(now, _EVENT_TX_CONTROL_GIVEUP)
        self._last_tx_giveup = {
            "time": _format_time(now),
            "device_id": _hex_byte(dev_id),
            "sub_id": _hex_byte(sub_id),
            "command_type": _hex_byte(cmd),
            "payload_len": len(payload),
            "payload_hex": payload.hex().upper(),
            "attempts": attempts,
            "kind": "state_request" if is_state_request else "control",
            "ew11_state": health.get("state"),
            "seconds_since_last_rx": health.get("seconds_since_last_rx"),
            "last_error": health.get("last_error"),
        }

    def report(self, *, include_packet_samples: bool = False) -> dict[str, Any]:
        now = self._now()
        recent = self._recent_counts(now)
        rx_error_count = (
            self.f7_checksum_errors
            + self.f7_frame_errors
            + self.stx_checksum_errors
            + self.stx_frame_errors
        )
        recent_rx_error_count = (
            recent["rx_checksum_errors"] + recent["rx_frame_errors"]
        )
        state = _quality_state(
            rx_error_count=recent_rx_error_count,
            tx_control_giveups=recent["tx_control_giveups"],
        )
        lifetime_state = _quality_state(
            rx_error_count=rx_error_count,
            tx_control_giveups=self.tx_control_giveups,
        )

        report = {
            "state": state,
            "lifetime_state": lifetime_state,
            "packet_samples_redacted": not include_packet_samples,
            "recent_window_seconds": PACKET_QUALITY_RECENT_WINDOW_SECONDS,
            "summary": (
                f"recent_state={state}, "
                f"recent_rx_checksum_errors={recent['rx_checksum_errors']}, "
                f"recent_rx_frame_errors={recent['rx_frame_errors']}, "
                f"recent_rx_resync_events={recent['rx_resync_events']}, "
                f"recent_tx_control_giveups={recent['tx_control_giveups']}, "
                f"lifetime_rx_checksum_errors={self.f7_checksum_errors + self.stx_checksum_errors}, "
                f"lifetime_tx_control_giveups={self.tx_control_giveups}, "
                f"lifetime_tx_state_request_giveups={self.tx_state_request_giveups}"
            ),
            "recent": recent,
            "rx": {
                "valid_f7_frames": self.valid_f7_frames,
                "valid_stx_frames": self.valid_stx_frames,
                "f7_checksum_errors": self.f7_checksum_errors,
                "f7_frame_errors": self.f7_frame_errors,
                "f7_resync_events": self.f7_resync_events,
                "stx_checksum_errors": self.stx_checksum_errors,
                "stx_frame_errors": self.stx_frame_errors,
                "stx_resync_events": self.stx_resync_events,
                "last_valid_f7": self._last_valid_f7,
                "last_error": self._last_rx_error,
                "last_resync": self._last_rx_resync,
            },
            "tx": {
                "giveups": self.tx_giveups,
                "control_giveups": self.tx_control_giveups,
                "state_request_giveups": self.tx_state_request_giveups,
                "last_giveup": self._last_tx_giveup,
            },
        }
        if include_packet_samples:
            return report
        return _without_packet_samples(report)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _record_recent_event(self, now: datetime, event: str) -> None:
        self._recent_events.append((now, event))

    def _recent_counts(self, now: datetime) -> dict[str, int]:
        cutoff = now - timedelta(seconds=PACKET_QUALITY_RECENT_WINDOW_SECONDS)
        while self._recent_events and self._recent_events[0][0] < cutoff:
            self._recent_events.popleft()

        counts = {
            _EVENT_F7_CHECKSUM_ERROR: 0,
            _EVENT_F7_FRAME_ERROR: 0,
            _EVENT_F7_RESYNC: 0,
            _EVENT_STX_CHECKSUM_ERROR: 0,
            _EVENT_STX_FRAME_ERROR: 0,
            _EVENT_STX_RESYNC: 0,
            _EVENT_TX_CONTROL_GIVEUP: 0,
            _EVENT_TX_STATE_REQUEST_GIVEUP: 0,
        }
        for _, event in self._recent_events:
            counts[event] += 1

        return {
            "rx_checksum_errors": (
                counts[_EVENT_F7_CHECKSUM_ERROR]
                + counts[_EVENT_STX_CHECKSUM_ERROR]
            ),
            "rx_frame_errors": (
                counts[_EVENT_F7_FRAME_ERROR] + counts[_EVENT_STX_FRAME_ERROR]
            ),
            "rx_resync_events": (
                counts[_EVENT_F7_RESYNC] + counts[_EVENT_STX_RESYNC]
            ),
            "tx_giveups": (
                counts[_EVENT_TX_CONTROL_GIVEUP]
                + counts[_EVENT_TX_STATE_REQUEST_GIVEUP]
            ),
            "tx_control_giveups": counts[_EVENT_TX_CONTROL_GIVEUP],
            "tx_state_request_giveups": counts[_EVENT_TX_STATE_REQUEST_GIVEUP],
        }


def empty_packet_quality_report(
    *, include_packet_samples: bool = False
) -> dict[str, Any]:
    return PacketQualityMonitor().report(
        include_packet_samples=include_packet_samples
    )


def _without_packet_samples(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_packet_samples(item)
            for key, item in value.items()
            if key not in _PACKET_SAMPLE_KEYS
        }
    if isinstance(value, list):
        return [_without_packet_samples(item) for item in value]
    return value


def _quality_state(*, rx_error_count: int, tx_control_giveups: int) -> str:
    if rx_error_count and tx_control_giveups:
        return "rx_and_tx_errors"
    if tx_control_giveups:
        return "tx_giveups"
    if rx_error_count:
        return "rx_errors"
    return "ok"


def _frame_error_payload(
    kind: str,
    reason: str,
    frame_raw: bytes,
    *,
    now: datetime,
    dev_id: int | None = None,
    sub_id: int | None = None,
    cmd: int | None = None,
    length: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time": _format_time(now),
        "kind": kind,
        "reason": reason,
        "raw_hex": frame_raw.hex().upper(),
    }
    if dev_id is not None:
        payload["device_id"] = _hex_byte(dev_id)
    if sub_id is not None:
        payload["sub_id"] = _hex_byte(sub_id)
    if cmd is not None:
        payload["command_type"] = _hex_byte(cmd)
    if length is not None:
        payload["payload_len"] = length
    return payload


def _hex_byte(value: int) -> str:
    return f"0x{value & 0xFF:02X}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.isoformat()
