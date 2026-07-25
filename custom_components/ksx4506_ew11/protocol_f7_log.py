from __future__ import annotations

from dataclasses import dataclass
import json
import logging


_LOGGER = logging.getLogger("custom_components.ksx4506_ew11.protocol")


@dataclass(frozen=True)
class F7PacketLog:
    dev_id: int
    sub_id: int
    cmd: int
    length: int
    payload: bytes
    recv_xor: int
    recv_add: int
    calc_xor: int
    calc_add: int
    frame_raw: bytes


@dataclass
class F7PacketLogger:
    last_ok_hex: str | None = None
    last_bad_hex: str | None = None

    def emit(self, packet: F7PacketLog, *, parity: bool) -> None:
        hex_string = packet.frame_raw.hex()
        info: dict[str, str | int | bool | dict[str, str]] = {
            "header": "f7",
            "devId": f"{packet.dev_id:02x}",
            "subId": f"{packet.sub_id:02x}",
            "command": f"{packet.cmd:02x}",
            "len": packet.length,
            "data": packet.payload.hex(),
            "xor": f"{packet.recv_xor:02x}",
            "add": f"{packet.recv_add:02x}",
            "size": len(hex_string),
            "hexString": hex_string,
            "checksum": {
                "xor": f"{packet.calc_xor:02x}",
                "add": f"{packet.calc_add:02x}",
            },
            "parity": parity,
        }

        if not parity:
            _LOGGER.warning(
                "drop F7: checksum mismatch dev=0x%02X sub=0x%02X cmd=0x%02X "
                + "len=%d recv=0x%02X/0x%02X calc=0x%02X/0x%02X",
                packet.dev_id,
                packet.sub_id,
                packet.cmd,
                packet.length,
                packet.recv_xor,
                packet.recv_add,
                packet.calc_xor,
                packet.calc_add,
            )
            if self.last_bad_hex != hex_string:
                self.last_bad_hex = hex_string
                _LOGGER.debug(
                    "drop F7 packet :: %s",
                    json.dumps(info, ensure_ascii=False, indent=2),
                )
            return

        if self.last_ok_hex == hex_string:
            return
        self.last_ok_hex = hex_string
        _LOGGER.debug("packet :: %s", json.dumps(info, ensure_ascii=False, indent=2))
