from __future__ import annotations

from collections.abc import Iterable
import logging

from .frame import Frame
from .packet_quality import PacketQualityMonitor
from .protocol_f7 import parse_f7_frame, valid_embedded_f7_pos
from .protocol_f7_log import F7PacketLogger
from .protocol_stx import parse_stx_frame
from .protocol_types import KsFrame


_LOGGER = logging.getLogger(__name__)


class Ksx4506Codec:
    """KS X 4506 codec.

    Supports two framing styles seen in the field:
    1) STX/ETX + addr/cmd/len/payload/checksum
    2) legacy F7-stream (frame starts with 0xF7, next 0xF7 starts next frame)
    """

    def __init__(
        self,
        stx: int = 0x02,
        etx: int = 0x03,
        checksum_mode: str = "sum8",
        packet_quality: PacketQualityMonitor | None = None,
    ) -> None:
        self._stx: int = stx
        self._etx: int = etx
        self._checksum_mode: str = checksum_mode
        self._packet_quality: PacketQualityMonitor | None = packet_quality
        self._buf: bytearray = bytearray()
        self._f7_logger = F7PacketLogger()

    def feed(self, data: bytes) -> list[KsFrame]:
        self._buf.extend(data)
        _LOGGER.debug("codec.feed bytes=%d data=%s", len(data), data.hex())
        out: list[KsFrame] = []

        while True:
            s_stx = self._find_header(self._stx)
            s_f7 = self._find_header(0xF7)

            if s_stx == -1 and s_f7 == -1:
                self._buf.clear()
                break

            starts = [x for x in (s_stx, s_f7) if x >= 0]
            s = min(starts)
            if s > 0:
                del self._buf[:s]

            if not self._buf:
                break

            head = self._buf[0]
            if head == self._stx:
                frame = self._parse_stx_frame()
            elif head == 0xF7:
                frame = self._parse_f7_frame()
            else:
                del self._buf[:1]
                continue

            if frame is None:
                if self._buf and self._buf[0] in (self._stx, 0xF7):
                    break
                continue

            out.append(frame)

        return out

    def _find_header(self, header: int) -> int:
        try:
            return self._buf.index(header)
        except ValueError:
            return -1

    def _next_header_pos(self, start: int = 1) -> int:
        positions: list[int] = []
        for h in (self._stx, 0xF7):
            try:
                positions.append(self._buf.index(h, start))
            except ValueError:
                pass
        return min(positions) if positions else -1

    def _parse_buffer_head(self) -> KsFrame | None:
        if not self._buf:
            return None
        if self._buf[0] == self._stx:
            return self._parse_stx_frame()
        if self._buf[0] == 0xF7:
            return self._parse_f7_frame()
        return None

    def _parse_stx_frame(self) -> KsFrame | None:
        return parse_stx_frame(self)

    def _parse_f7_frame(self) -> KsFrame | None:
        return parse_f7_frame(self)

    def _valid_embedded_f7_pos(self, limit: int) -> int:
        return valid_embedded_f7_pos(self._buf, limit)

    def build(self, addr: int, cmd: int, payload: bytes) -> bytes:
        length = len(payload)
        checksum = self.calc_checksum([addr, cmd, length, *payload])
        return bytes([self._stx, addr & 0xFF, cmd & 0xFF, length & 0xFF, *payload, checksum, self._etx])

    def build_f7(self, dev_id: int, sub_id: int, cmd: int, payload: bytes) -> bytes:
        return Frame(
            device_id=dev_id,
            sub_id=sub_id,
            command_type=cmd,
            data=payload,
        ).to_bytes()

    def calc_checksum(self, values: Iterable[int]) -> int:
        if self._checksum_mode == "xor8":
            x = 0
            for v in values:
                x ^= v & 0xFF
            return x & 0xFF

        s = 0
        for v in values:
            s = (s + (v & 0xFF)) & 0xFF
        return s


__all__ = ["KsFrame", "Ksx4506Codec"]
