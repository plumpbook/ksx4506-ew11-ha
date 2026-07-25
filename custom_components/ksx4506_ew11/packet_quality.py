from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class PacketQualityMonitor:
    def __init__(self) -> None:
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

    def record_f7_frame_ok(
        self,
        *,
        dev_id: int,
        sub_id: int,
        cmd: int,
        length: int,
        frame_raw: bytes,
    ) -> None:
        self.valid_f7_frames += 1
        self._last_valid_f7 = {
            "time": _now(),
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
        self.f7_checksum_errors += 1
        self._last_rx_error = {
            "time": _now(),
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
        self.f7_frame_errors += 1
        self._last_rx_error = _frame_error_payload(
            "f7_frame",
            reason,
            frame_raw,
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
        self.f7_resync_events += 1
        self._last_rx_resync = _frame_error_payload(
            "f7_resync",
            reason,
            frame_raw,
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
        self.stx_checksum_errors += 1
        self._last_rx_error = {
            "time": _now(),
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
        self.stx_frame_errors += 1
        self._last_rx_error = _frame_error_payload(
            "stx_frame",
            reason,
            frame_raw,
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
        self.stx_resync_events += 1
        self._last_rx_resync = _frame_error_payload(
            "stx_resync",
            reason,
            frame_raw,
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
        self.tx_giveups += 1
        if is_state_request:
            self.tx_state_request_giveups += 1
        else:
            self.tx_control_giveups += 1
        self._last_tx_giveup = {
            "time": _now(),
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

    def report(self) -> dict[str, Any]:
        rx_error_count = (
            self.f7_checksum_errors
            + self.f7_frame_errors
            + self.stx_checksum_errors
            + self.stx_frame_errors
        )
        state = "ok"
        if rx_error_count and self.tx_giveups:
            state = "rx_and_tx_errors"
        elif self.tx_giveups:
            state = "tx_giveups"
        elif rx_error_count:
            state = "rx_errors"

        return {
            "state": state,
            "summary": (
                f"rx_checksum_errors={self.f7_checksum_errors + self.stx_checksum_errors}, "
                f"rx_frame_errors={self.f7_frame_errors + self.stx_frame_errors}, "
                f"rx_resync_events={self.f7_resync_events + self.stx_resync_events}, "
                f"tx_giveups={self.tx_giveups}"
            ),
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


def empty_packet_quality_report() -> dict[str, Any]:
    return PacketQualityMonitor().report()


def _frame_error_payload(
    kind: str,
    reason: str,
    frame_raw: bytes,
    *,
    dev_id: int | None = None,
    sub_id: int | None = None,
    cmd: int | None = None,
    length: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time": _now(),
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
