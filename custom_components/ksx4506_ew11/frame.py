"""KS X 4506 frame encoding and stream decoding.

EW11 is expected to carry a raw serial byte stream over TCP. TCP can split or
merge serial frames, so the stream decoder keeps its own byte buffer and emits
complete validated frames as they become available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

HEADER = 0xF7
FRAME_OVERHEAD = 7
XOR_CHECKSUM_INDEX = -2
ADD_CHECKSUM_INDEX = -1


class FrameError(ValueError):
    """Base error for invalid KS X frames."""


class IncompleteFrameError(FrameError):
    """Raised when bytes do not yet contain a full frame."""


class ChecksumError(FrameError):
    """Raised when XOR/ADD checksums do not match."""


def _require_byte(name: str, value: int) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0 or value > 0xFF:
        raise ValueError(f"{name} must fit in one byte")
    return value


def calculate_checksums(frame_without_checksums: bytes) -> Tuple[int, int]:
    """Return ``(xor_sum, add_sum)`` for HEADER through DATA bytes."""

    if not frame_without_checksums:
        raise FrameError("cannot calculate checksum for empty frame")

    xor_sum = 0
    for byte in frame_without_checksums:
        xor_sum ^= byte

    add_sum = (sum(frame_without_checksums) + xor_sum) & 0xFF
    return xor_sum, add_sum


def bytes_from_hex(value: str) -> bytes:
    """Parse a human-friendly hex string into bytes.

    Accepts compact strings (``F712010100E5F0``) and separated strings such as
    ``F7 12 01 01 00 E5 F0`` or ``F7:12:01:01:00:E5:F0``.
    """

    cleaned = (
        value.replace("0x", "")
        .replace("0X", "")
        .replace(",", " ")
        .replace(":", " ")
        .replace("-", " ")
    )
    compact = "".join(cleaned.split())

    if len(compact) % 2:
        raise ValueError("hex string must contain an even number of digits")

    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise ValueError(f"invalid hex string: {value!r}") from exc


def hex_from_bytes(value: bytes) -> str:
    """Format bytes as uppercase space-separated hex."""

    return " ".join(f"{byte:02X}" for byte in value)


@dataclass(frozen=True)
class Frame:
    """A validated KS X 4506 application frame without transport concerns."""

    device_id: int
    sub_id: int
    command_type: int
    data: bytes = b""

    def __post_init__(self) -> None:
        _require_byte("device_id", self.device_id)
        _require_byte("sub_id", self.sub_id)
        _require_byte("command_type", self.command_type)

        if not isinstance(self.data, (bytes, bytearray)):
            raise TypeError("data must be bytes")
        if len(self.data) > 0xFF:
            raise ValueError("data length must fit in one byte")

        object.__setattr__(self, "data", bytes(self.data))

    @property
    def length(self) -> int:
        return len(self.data)

    @property
    def is_response(self) -> bool:
        return bool(self.command_type & 0x80)

    @property
    def is_request(self) -> bool:
        return not self.is_response

    @property
    def group(self) -> int:
        return self.sub_id >> 4

    @property
    def unit(self) -> int:
        return self.sub_id & 0x0F

    def without_checksums(self) -> bytes:
        return bytes(
            [
                HEADER,
                self.device_id,
                self.sub_id,
                self.command_type,
                self.length,
            ]
        ) + self.data

    def checksums(self) -> Tuple[int, int]:
        return calculate_checksums(self.without_checksums())

    def to_bytes(self) -> bytes:
        xor_sum, add_sum = self.checksums()
        return self.without_checksums() + bytes([xor_sum, add_sum])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Frame":
        raw = bytes(raw)

        if len(raw) < FRAME_OVERHEAD:
            raise IncompleteFrameError(
                f"frame requires at least {FRAME_OVERHEAD} bytes"
            )
        if raw[0] != HEADER:
            raise FrameError(f"expected header 0x{HEADER:02X}, got 0x{raw[0]:02X}")

        data_length = raw[4]
        expected_length = data_length + FRAME_OVERHEAD
        if len(raw) < expected_length:
            raise IncompleteFrameError(
                f"frame needs {expected_length} bytes, got {len(raw)}"
            )
        if len(raw) > expected_length:
            raise FrameError(f"frame has trailing bytes: expected {expected_length}")

        expected_xor, expected_add = calculate_checksums(raw[:-2])
        actual_xor = raw[XOR_CHECKSUM_INDEX]
        actual_add = raw[ADD_CHECKSUM_INDEX]
        if (actual_xor, actual_add) != (expected_xor, expected_add):
            raise ChecksumError(
                "checksum mismatch: "
                f"expected {expected_xor:02X} {expected_add:02X}, "
                f"got {actual_xor:02X} {actual_add:02X}"
            )

        return cls(
            device_id=raw[1],
            sub_id=raw[2],
            command_type=raw[3],
            data=raw[5:-2],
        )


class FrameStreamDecoder:
    """Incrementally decode validated frames from a raw byte stream."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.discarded_bytes = 0
        self.checksum_errors = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()

    def feed(self, chunk: bytes) -> List[Frame]:
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("chunk must be bytes")

        self._buffer.extend(chunk)
        frames: List[Frame] = []

        while True:
            header_index = self._buffer.find(bytes([HEADER]))
            if header_index < 0:
                self.discarded_bytes += len(self._buffer)
                self._buffer.clear()
                break

            if header_index:
                self.discarded_bytes += header_index
                del self._buffer[:header_index]

            if len(self._buffer) < 5:
                break

            data_length = self._buffer[4]
            frame_length = data_length + FRAME_OVERHEAD
            if len(self._buffer) < frame_length:
                break

            candidate = bytes(self._buffer[:frame_length])
            try:
                frame = Frame.from_bytes(candidate)
            except ChecksumError:
                self.checksum_errors += 1
                self.discarded_bytes += 1
                del self._buffer[0]
                continue

            del self._buffer[:frame_length]
            frames.append(frame)

        return frames

