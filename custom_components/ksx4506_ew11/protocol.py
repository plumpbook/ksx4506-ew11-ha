from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class KsFrame:
    addr: int
    cmd: int
    payload: bytes
    checksum: int
    raw: bytes


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
        out: list[KsFrame] = []

        # Prefer explicit STX/ETX framing when available.
        if self._stx in self._buf:
            while True:
                try:
                    s = self._buf.index(self._stx)
                except ValueError:
                    self._buf.clear()
                    break

                if s > 0:
                    del self._buf[:s]

                if len(self._buf) < 7:
                    break

                length = self._buf[3]
                total = 1 + 1 + 1 + 1 + length + 1 + 1
                if len(self._buf) < total:
                    break

                frame_raw = bytes(self._buf[:total])
                del self._buf[:total]

                if frame_raw[-1] != self._etx:
                    continue

                addr = frame_raw[1]
                cmd = frame_raw[2]
                payload = frame_raw[4 : 4 + length]
                recv_checksum = frame_raw[4 + length]
                calc_checksum = self.calc_checksum([addr, cmd, length, *payload])

                if recv_checksum != calc_checksum:
                    continue

                out.append(KsFrame(addr=addr, cmd=cmd, payload=payload, checksum=recv_checksum, raw=frame_raw))

            return out

        # Fallback: legacy F7 stream framing.
        while True:
            try:
                s = self._buf.index(0xF7)
            except ValueError:
                self._buf.clear()
                break

            if s > 0:
                del self._buf[:s]

            if len(self._buf) < 4:
                break

            # Find next frame start as current frame boundary.
            try:
                n = self._buf.index(0xF7, 1)
            except ValueError:
                break

            frame_raw = bytes(self._buf[:n])
            del self._buf[:n]

            if len(frame_raw) < 4:
                continue

            addr = frame_raw[1]
            cmd = frame_raw[2]
            payload = frame_raw[3:]
            out.append(KsFrame(addr=addr, cmd=cmd, payload=payload, checksum=0, raw=frame_raw))

        return out

    def build(self, addr: int, cmd: int, payload: bytes) -> bytes:
        length = len(payload)
        checksum = self.calc_checksum([addr, cmd, length, *payload])
        return bytes([self._stx, addr & 0xFF, cmd & 0xFF, length & 0xFF, *payload, checksum, self._etx])

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
