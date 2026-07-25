from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Protocol

from .packet_quality import PacketQualityMonitor
from .protocol_types import KsFrame


_LOGGER = logging.getLogger("custom_components.ksx4506_ew11.protocol")


class StxCodecHost(Protocol):
    _buf: bytearray
    _stx: int
    _etx: int
    _packet_quality: PacketQualityMonitor | None

    def _next_header_pos(self, start: int = 1) -> int: ...

    def _parse_buffer_head(self) -> KsFrame | None: ...

    def calc_checksum(self, values: Iterable[int]) -> int: ...


def parse_stx_frame(codec: StxCodecHost) -> KsFrame | None:
    if len(codec._buf) < 7:
        return None

    length = codec._buf[3]
    total = 1 + 1 + 1 + 1 + length + 1 + 1
    if total < 7 or total > 512:
        n = codec._next_header_pos(1)
        if n > 0:
            if codec._packet_quality is not None:
                codec._packet_quality.record_stx_resync(
                    reason="invalid_length_before_next_header",
                    frame_raw=bytes(codec._buf[:n]),
                    length=length,
                )
            del codec._buf[:n]
            return codec._parse_buffer_head()

        _LOGGER.debug("drop STX: invalid length=%d", total)
        if codec._packet_quality is not None:
            codec._packet_quality.record_stx_frame_error(
                reason="invalid_length",
                frame_raw=bytes(codec._buf[: min(len(codec._buf), 16)]),
                length=length,
            )
        del codec._buf[:1]
        return None

    if len(codec._buf) < total:
        n = codec._next_header_pos(1)
        if n > 0:
            if codec._packet_quality is not None:
                codec._packet_quality.record_stx_resync(
                    reason="incomplete_before_next_header",
                    frame_raw=bytes(codec._buf[:n]),
                    addr=codec._buf[1] if len(codec._buf) > 1 else None,
                    cmd=codec._buf[2] if len(codec._buf) > 2 else None,
                    length=length,
                )
            del codec._buf[:n]
            return codec._parse_buffer_head()
        return None

    frame_raw = bytes(codec._buf[:total])

    if frame_raw[-1] != codec._etx:
        n = codec._next_header_pos(1)
        if n > 0 and n < total:
            if codec._packet_quality is not None:
                codec._packet_quality.record_stx_resync(
                    reason="missing_etx_before_next_header",
                    frame_raw=frame_raw,
                    addr=frame_raw[1],
                    cmd=frame_raw[2],
                    length=length,
                )
            del codec._buf[:n]
            return codec._parse_buffer_head()

        _LOGGER.debug("drop STX: missing ETX raw=%s", frame_raw.hex())
        if codec._packet_quality is not None:
            codec._packet_quality.record_stx_frame_error(
                reason="missing_etx",
                frame_raw=frame_raw,
                addr=frame_raw[1],
                cmd=frame_raw[2],
                length=length,
            )
        del codec._buf[:1]
        return None

    addr = frame_raw[1]
    cmd = frame_raw[2]
    payload = frame_raw[4 : 4 + length]
    recv_checksum = frame_raw[4 + length]
    calc_checksum = codec.calc_checksum([addr, cmd, length, *payload])
    if recv_checksum != calc_checksum:
        n = codec._next_header_pos(1)
        if n > 0 and n < total:
            if codec._packet_quality is not None:
                codec._packet_quality.record_stx_resync(
                    reason="checksum_mismatch_before_next_header",
                    frame_raw=frame_raw,
                    addr=addr,
                    cmd=cmd,
                    length=length,
                )
            del codec._buf[:n]
            return codec._parse_buffer_head()

        _LOGGER.debug(
            "drop STX: checksum mismatch recv=0x%02X calc=0x%02X raw=%s",
            recv_checksum,
            calc_checksum,
            frame_raw.hex(),
        )
        if codec._packet_quality is not None:
            codec._packet_quality.record_stx_checksum_error(
                addr=addr,
                cmd=cmd,
                length=length,
                recv_checksum=recv_checksum,
                calc_checksum=calc_checksum,
                frame_raw=frame_raw,
            )
        del codec._buf[:1]
        return None

    del codec._buf[:total]
    _LOGGER.debug("parsed STX frame addr=0x%02X cmd=0x%02X len=%d", addr, cmd, len(payload))
    if codec._packet_quality is not None:
        codec._packet_quality.record_stx_frame_ok()
    return KsFrame(addr=addr, cmd=cmd, payload=payload, checksum=recv_checksum, raw=frame_raw)
