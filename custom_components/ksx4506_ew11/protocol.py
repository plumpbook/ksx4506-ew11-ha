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
    sub_id: int = 0


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

        # Fallback: legacy F7 framing (f7 devId subId cmd len data xor add)
        while True:
            try:
                s = self._buf.index(0xF7)
            except ValueError:
                self._buf.clear()
                break

            if s > 0:
                del self._buf[:s]

            # header+dev+sub+cmd+len+xor+add => minimum 7 bytes
            if len(self._buf) < 7:
                break

            dev_id = self._buf[1]
            sub_id = self._buf[2]
            cmd = self._buf[3]
            length = self._buf[4]
            total = 1 + 1 + 1 + 1 + 1 + length + 1 + 1
            if len(self._buf) < total:
                break

            frame_raw = bytes(self._buf[:total])
            del self._buf[:total]

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

            # Keep frame even on checksum mismatch for diagnostics/learning.
            checksum_ok = recv_xor == calc_xor and recv_add == calc_add
            checksum = recv_add if checksum_ok else 0

            out.append(KsFrame(addr=dev_id, sub_id=sub_id, cmd=cmd, payload=payload, checksum=checksum, raw=frame_raw))

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
