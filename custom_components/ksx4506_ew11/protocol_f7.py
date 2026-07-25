from __future__ import annotations

import logging
from typing import Protocol

from .frame import ChecksumError, Frame, FrameError
from .packet_quality import PacketQualityMonitor
from .protocol_f7_log import F7PacketLog, F7PacketLogger
from .protocol_types import KsFrame


_LOGGER = logging.getLogger("custom_components.ksx4506_ew11.protocol")


class F7CodecHost(Protocol):
    _buf: bytearray
    _packet_quality: PacketQualityMonitor | None
    _f7_logger: F7PacketLogger

    def _next_header_pos(self, start: int = 1) -> int: ...

    def _parse_buffer_head(self) -> KsFrame | None: ...

    def _valid_embedded_f7_pos(self, limit: int) -> int: ...


def valid_embedded_f7_pos(buffer: bytearray, limit: int) -> int:
    pos = 5
    while pos < limit:
        try:
            pos = buffer.index(0xF7, pos, limit)
        except ValueError:
            return -1

        if len(buffer) < pos + 5:
            return pos

        length = buffer[pos + 4]
        total = 1 + 1 + 1 + 1 + 1 + length + 1 + 1
        if total < 7 or total > 512:
            pos += 1
            continue

        if len(buffer) < pos + total:
            return pos

        try:
            _ = Frame.from_bytes(bytes(buffer[pos : pos + total]))
        except FrameError:
            pos += 1
            continue
        return pos

    return -1


def parse_f7_frame(codec: F7CodecHost) -> KsFrame | None:
    if len(codec._buf) < 7:
        return None

    dev_id = codec._buf[1]
    sub_id = codec._buf[2]
    cmd = codec._buf[3]
    length = codec._buf[4]
    total = 1 + 1 + 1 + 1 + 1 + length + 1 + 1

    if total < 7 or total > 512:
        _LOGGER.debug("drop F7: invalid length=%d", total)
        if codec._packet_quality is not None:
            codec._packet_quality.record_f7_frame_error(
                reason="invalid_length",
                frame_raw=bytes(codec._buf[: min(len(codec._buf), 16)]),
                dev_id=dev_id,
                sub_id=sub_id,
                cmd=cmd,
                length=length,
            )
        del codec._buf[:1]
        return None

    if len(codec._buf) < total:
        n = codec._next_header_pos(1)
        if n > 0:
            if codec._packet_quality is not None:
                codec._packet_quality.record_f7_resync(
                    reason="incomplete_before_next_header",
                    frame_raw=bytes(codec._buf[:n]),
                    dev_id=dev_id,
                    sub_id=sub_id,
                    cmd=cmd,
                    length=length,
                )
            del codec._buf[:n]
            return codec._parse_buffer_head()
        return None

    frame_raw = bytes(codec._buf[:total])
    recv_xor = frame_raw[5 + length]
    recv_add = frame_raw[6 + length]

    try:
        parsed = Frame.from_bytes(frame_raw)
        calc_xor, calc_add = parsed.checksums()
    except ChecksumError:
        payload = frame_raw[5 : 5 + length]
        calc_xor, calc_add = Frame(
            device_id=dev_id,
            sub_id=sub_id,
            command_type=cmd,
            data=payload,
        ).checksums()
        resync_pos = codec._valid_embedded_f7_pos(total)
        if resync_pos > 0:
            if codec._packet_quality is not None:
                codec._packet_quality.record_f7_resync(
                    reason="checksum_mismatch_with_embedded_header",
                    frame_raw=frame_raw,
                    dev_id=dev_id,
                    sub_id=sub_id,
                    cmd=cmd,
                    length=length,
                )
            del codec._buf[:resync_pos]
            return codec._parse_buffer_head()

        codec._f7_logger.emit(
            F7PacketLog(
                dev_id=dev_id,
                sub_id=sub_id,
                cmd=cmd,
                length=length,
                payload=payload,
                recv_xor=recv_xor,
                recv_add=recv_add,
                calc_xor=calc_xor,
                calc_add=calc_add,
                frame_raw=frame_raw,
            ),
            parity=False,
        )
        if codec._packet_quality is not None:
            codec._packet_quality.record_f7_checksum_error(
                dev_id=dev_id,
                sub_id=sub_id,
                cmd=cmd,
                length=length,
                recv_xor=recv_xor,
                recv_add=recv_add,
                calc_xor=calc_xor,
                calc_add=calc_add,
                frame_raw=frame_raw,
            )
        del codec._buf[:1]
        return None
    except FrameError as exc:
        _LOGGER.debug("drop F7: invalid frame raw=%s error=%s", frame_raw.hex(), exc)
        if codec._packet_quality is not None:
            codec._packet_quality.record_f7_frame_error(
                reason=str(exc),
                frame_raw=frame_raw,
                dev_id=dev_id,
                sub_id=sub_id,
                cmd=cmd,
                length=length,
            )
        del codec._buf[:1]
        return None

    codec._f7_logger.emit(
        F7PacketLog(
            dev_id=parsed.device_id,
            sub_id=parsed.sub_id,
            cmd=parsed.command_type,
            length=parsed.length,
            payload=parsed.data,
            recv_xor=recv_xor,
            recv_add=recv_add,
            calc_xor=calc_xor,
            calc_add=calc_add,
            frame_raw=frame_raw,
        ),
        parity=True,
    )

    del codec._buf[:total]
    if codec._packet_quality is not None:
        codec._packet_quality.record_f7_frame_ok(
            dev_id=parsed.device_id,
            sub_id=parsed.sub_id,
            cmd=parsed.command_type,
            length=parsed.length,
            frame_raw=frame_raw,
        )
    return KsFrame(
        addr=parsed.device_id,
        sub_id=parsed.sub_id,
        cmd=parsed.command_type,
        payload=parsed.data,
        checksum=recv_add,
        raw=frame_raw,
    )
