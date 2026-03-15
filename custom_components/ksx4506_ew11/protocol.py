from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable


@dataclass(slots=True)
class KsFrame:
    addr: int
    cmd: int
    payload: bytes
    checksum: int
    raw: bytes
    sub_id: int = 0


_LOGGER = logging.getLogger(__name__)


class Ksx4506Codec:
    """KS X 4506 codec.

    Supports two framing styles seen in the field:
    1) STX/ETX + addr/cmd/len/payload/checksum
    2) legacy F7-stream (frame starts with 0xF7, next 0xF7 starts next frame)
    """

    def __init__(self, stx: int = 0x02, etx: int = 0x03, checksum_mode: str = "sum8") -> None:
        self._stx = stx
        self._etx = etx
        self._checksum_mode = checksum_mode
        self._buf = bytearray()

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

    def _parse_stx_frame(self) -> KsFrame | None:
        if len(self._buf) < 7:
            return None

        length = self._buf[3]
        total = 1 + 1 + 1 + 1 + length + 1 + 1
        if total < 7 or total > 512:
            _LOGGER.debug("drop STX: invalid length=%d", total)
            del self._buf[:1]
            return None

        if len(self._buf) < total:
            n = self._next_header_pos(1)
            if n > 0:
                del self._buf[:n]
                return None
            return None

        frame_raw = bytes(self._buf[:total])

        if frame_raw[-1] != self._etx:
            _LOGGER.debug("drop STX: missing ETX raw=%s", frame_raw.hex())
            del self._buf[:1]
            return None

        addr = frame_raw[1]
        cmd = frame_raw[2]
        payload = frame_raw[4 : 4 + length]
        recv_checksum = frame_raw[4 + length]
        calc_checksum = self.calc_checksum([addr, cmd, length, *payload])
        if recv_checksum != calc_checksum:
            _LOGGER.debug(
                "drop STX: checksum mismatch recv=0x%02X calc=0x%02X raw=%s",
                recv_checksum,
                calc_checksum,
                frame_raw.hex(),
            )
            del self._buf[:1]
            return None

        del self._buf[:total]
        _LOGGER.debug("parsed STX frame addr=0x%02X cmd=0x%02X len=%d", addr, cmd, len(payload))
        return KsFrame(addr=addr, cmd=cmd, payload=payload, checksum=recv_checksum, raw=frame_raw)

    def _parse_f7_frame(self) -> KsFrame | None:
        # header+dev+sub+cmd+len+xor+add => minimum 7 bytes
        if len(self._buf) < 7:
            return None

        dev_id = self._buf[1]
        sub_id = self._buf[2]
        cmd = self._buf[3]
        length = self._buf[4]
        total = 1 + 1 + 1 + 1 + 1 + length + 1 + 1

        if total < 7 or total > 512:
            _LOGGER.debug("drop F7: invalid length=%d", total)
            del self._buf[:1]
            return None

        if len(self._buf) < total:
            n = self._next_header_pos(1)
            if n > 0:
                del self._buf[:n]
                return None
            return None

        frame_raw = bytes(self._buf[:total])
        payload = frame_raw[5 : 5 + length]
        recv_xor = frame_raw[5 + length]
        recv_add = frame_raw[6 + length]

        src = [frame_raw[0], dev_id, sub_id, cmd, length, *payload]
        calc_xor = 0
        for v in src:
            calc_xor ^= v & 0xFF
        calc_xor &= 0xFF

        calc_add = 0
        for v in [*src, calc_xor]:
            calc_add = (calc_add + (v & 0xFF)) & 0xFF

        if recv_xor != calc_xor or recv_add != calc_add:
            _LOGGER.debug(
                "drop F7: checksum mismatch xor recv=0x%02X calc=0x%02X add recv=0x%02X calc=0x%02X raw=%s",
                recv_xor,
                calc_xor,
                recv_add,
                calc_add,
                frame_raw.hex(),
            )
            del self._buf[:1]
            return None

        del self._buf[:total]
        _LOGGER.debug(
            "parsed F7 frame dev=0x%02X sub=0x%02X cmd=0x%02X len=%d",
            dev_id,
            sub_id,
            cmd,
            len(payload),
        )
        return KsFrame(addr=dev_id, sub_id=sub_id, cmd=cmd, payload=payload, checksum=recv_add, raw=frame_raw)

    def build(self, addr: int, cmd: int, payload: bytes) -> bytes:
        length = len(payload)
        checksum = self.calc_checksum([addr, cmd, length, *payload])
        return bytes([self._stx, addr & 0xFF, cmd & 0xFF, length & 0xFF, *payload, checksum, self._etx])

    def build_f7(self, dev_id: int, sub_id: int, cmd: int, payload: bytes) -> bytes:
        length = len(payload)
        src = [0xF7, dev_id & 0xFF, sub_id & 0xFF, cmd & 0xFF, length & 0xFF, *payload]

        xor = 0
        for v in src:
            xor ^= v & 0xFF
        xor &= 0xFF

        add = 0
        for v in [*src, xor]:
            add = (add + (v & 0xFF)) & 0xFF

        return bytes([*src, xor, add])

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
