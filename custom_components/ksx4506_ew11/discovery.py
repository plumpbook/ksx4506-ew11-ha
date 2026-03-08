from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# cmd value는 프로젝트 진행 중 실측 캡처로 보정 필요
CMD_TYPE_MAP = {
    # Generic guesses
    0x10: ("light", {"on_off"}),
    0x20: ("switch", {"on_off"}),
    0x30: ("climate", {"target_temp", "hvac_mode"}),
    0x40: ("fan", {"on_off", "speed"}),
    0x50: ("sensor", {"state"}),
    0x60: ("gas_valve", {"on_off"}),

    # Observed on EW11 captures (KS X 4506 deployments)
    0x11: ("light", {"on_off"}),
    0x12: ("switch", {"on_off"}),
    0x13: ("switch", {"on_off"}),
    0x14: ("switch", {"on_off"}),
    0x15: ("switch", {"on_off"}),
    0x1F: ("sensor", {"state"}),
    0x33: ("switch", {"on_off"}),
    0x39: ("climate", {"target_temp", "current_temp"}),
}

# Some deployments encode device family in address byte (legacy F7 stream)
ADDR_TYPE_MAP = {
    0x30: ("light", {"on_off"}),
    0x39: ("climate", {"target_temp", "current_temp"}),
    0x60: ("gas_valve", {"on_off"}),
}


@dataclass(slots=True)
class DeviceState:
    key: str
    addr: int
    kind: str
    capabilities: set[str] = field(default_factory=set)
    state: dict[str, Any] = field(default_factory=dict)
    last_raw_hex: str = ""


class DeviceRegistry:
    def __init__(self) -> None:
        self.devices: dict[str, DeviceState] = {}

    def upsert_from_frame(self, addr: int, cmd: int, payload: bytes, raw_hex: str) -> tuple[DeviceState, bool]:
        kind, caps = CMD_TYPE_MAP.get(cmd, ("unknown", {"diagnostic"}))
        if kind == "unknown":
            kind, caps = ADDR_TYPE_MAP.get(addr, (kind, caps))
        key = f"{addr:02X}_{kind}"
        is_new = key not in self.devices

        if is_new:
            self.devices[key] = DeviceState(key=key, addr=addr, kind=kind, capabilities=set(caps))

        dev = self.devices[key]
        dev.last_raw_hex = raw_hex
        self._apply_state(dev, cmd, payload)
        return dev, is_new

    def _apply_state(self, dev: DeviceState, cmd: int, payload: bytes) -> None:
        if dev.kind in {"light", "switch", "gas_valve"} and payload:
            dev.state["on"] = payload[0] == 0x01
        elif dev.kind == "fan" and payload:
            dev.state["on"] = payload[0] > 0
            dev.state["speed"] = payload[0]
        elif dev.kind == "climate" and payload:
            dev.state["target_temp"] = payload[0]
            if len(payload) > 1:
                dev.state["current_temp"] = payload[1]
        elif dev.kind in {"sensor", "unknown"}:
            dev.state["value_hex"] = payload.hex()
