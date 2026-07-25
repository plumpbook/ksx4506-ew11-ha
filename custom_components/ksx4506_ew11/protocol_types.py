from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KsFrame:
    addr: int
    cmd: int
    payload: bytes
    checksum: int
    raw: bytes
    sub_id: int = 0
