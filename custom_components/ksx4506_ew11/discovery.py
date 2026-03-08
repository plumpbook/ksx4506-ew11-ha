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

# Device ID mapping from suroup/ezville reference.
DEVICE_ID_MAP = {
    0x0E: ("light", {"on_off"}),
    0x12: ("gas_valve", {"on_off"}),
    0x30: ("switch", {"on_off"}),
    0x33: ("switch", {"on_off"}),  # breaker
    0x36: ("climate", {"target_temp", "current_temp"}),
    0x39: ("switch", {"on_off"}),  # outlet
    0x60: ("sensor", {"state"}),
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

    def upsert_from_frame(self, addr: int, sub_id: int, cmd: int, payload: bytes, raw_hex: str) -> tuple[DeviceState, bool]:
        kind, caps = CMD_TYPE_MAP.get(cmd, ("unknown", {"diagnostic"}))
        if kind == "unknown":
            kind, caps = DEVICE_ID_MAP.get(addr, (kind, caps))

        # Keep per-device-group separation with sub_id.
        key = f"{addr:02X}{sub_id:02X}_{kind}"
        is_new = key not in self.devices

        if is_new:
            self.devices[key] = DeviceState(key=key, addr=addr, kind=kind, capabilities=set(caps))

        dev = self.devices[key]
        dev.last_raw_hex = raw_hex
        self._apply_state(dev, cmd, payload)
        return dev, is_new

    def _apply_state(self, dev: DeviceState, cmd: int, payload: bytes) -> None:
        # ACK state packets in KS X 4506 deployments are often 0x81.
        if dev.kind in {"light", "switch", "gas_valve"}:
            if payload:
                # ignore first error/status byte when present
                state_bytes = payload[1:] if len(payload) > 1 else payload
                dev.state["on"] = any((b & 0x0F) > 0 for b in state_bytes)

        elif dev.kind == "fan" and payload:
            v = payload[-1]
            dev.state["on"] = v > 0
            dev.state["speed"] = v

        elif dev.kind == "climate":
            # Suroup reference: per-zone [setTemp, curTemp] pairs in payload tail.
            if len(payload) >= 2:
                dev.state["target_temp"] = payload[-2]
                dev.state["current_temp"] = payload[-1]

        if dev.kind in {"sensor", "unknown"} or not dev.state:
            dev.state["value_hex"] = payload.hex()
