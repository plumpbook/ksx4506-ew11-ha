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
    sub_id: int
    kind: str
    channel: int | None = None
    capabilities: set[str] = field(default_factory=set)
    state: dict[str, Any] = field(default_factory=dict)
    last_raw_hex: str = ""


class DeviceRegistry:
    def __init__(self) -> None:
        self.devices: dict[str, DeviceState] = {}

    def upsert_from_frame(self, addr: int, sub_id: int, cmd: int, payload: bytes, raw_hex: str) -> list[tuple[DeviceState, bool]]:
        kind, caps = CMD_TYPE_MAP.get(cmd, ("unknown", {"diagnostic"}))
        if kind == "unknown":
            kind, caps = DEVICE_ID_MAP.get(addr, (kind, caps))

        changes: list[tuple[DeviceState, bool]] = []

        # KS X 4506-2(light): expose channel entities only (no group aggregate entity).
        if kind == "light" and addr == 0x0E:
            if len(payload) > 1:
                low = sub_id & 0x0F
                high = (sub_id >> 4) & 0x0F
                is_group_reply = low == 0x0F

                items: list[tuple[int, int]] = []
                if is_group_reply or len(payload) > 2:
                    # Group status reply: [err][ch1..chN]
                    items = [(ch, b) for ch, b in enumerate(payload[1:], start=1)]
                else:
                    # Single status reply: [err][state]
                    if high == 0 and low > 0:
                        # vendor single-group form: 0x03 -> group3 ch1
                        ch = 1
                    else:
                        ch = low if low > 0 else 1

                    # Field variant observed: 0x13/0x14/0x15 may represent group3/4/5 ch1.
                    if high == 0x01 and low >= 0x03:
                        high = low
                        ch = 1

                    items = [(ch, payload[1])]

                # Canonical group key for dedup across mixed reply forms.
                if is_group_reply:
                    group = high if high > 0 else 1
                elif len(payload) > 2:
                    group = low if high == 0 else high
                else:
                    group = high if high > 0 else low
                    if group == 0:
                        group = 1

                canonical_sub_id = ((group & 0x0F) << 4) | 0x0F

                existing_channels = {
                    d.channel
                    for d in self.devices.values()
                    if d.kind == "light"
                    and d.addr == addr
                    and d.sub_id == canonical_sub_id
                    and d.channel is not None
                }

                for ch, state_byte in items:
                    if existing_channels and ch not in existing_channels and 1 in existing_channels:
                        ch = 1
                    key = f"{addr:02X}{canonical_sub_id:02X}_{kind}_{ch}"
                    is_new = key not in self.devices
                    if is_new:
                        self.devices[key] = DeviceState(
                            key=key,
                            addr=addr,
                            sub_id=canonical_sub_id,
                            channel=ch,
                            kind=kind,
                            capabilities=set(caps),
                        )
                    dev = self.devices[key]
                    dev.last_raw_hex = raw_hex
                    dev.state["on"] = bool(state_byte & 0x01)
                    dev.state["dimmable"] = bool(state_byte & 0x02)
                    dev.state["brightness_step"] = (state_byte >> 4) & 0x0F if dev.state["dimmable"] else 0
                    changes.append((dev, is_new))

            return changes

        # Default one-device mapping (addr+sub+kind)
        key = f"{addr:02X}{sub_id:02X}_{kind}"
        is_new = key not in self.devices

        if is_new:
            self.devices[key] = DeviceState(
                key=key,
                addr=addr,
                sub_id=sub_id,
                kind=kind,
                capabilities=set(caps),
            )

        dev = self.devices[key]
        dev.last_raw_hex = raw_hex
        self._apply_state(dev, cmd, payload)
        changes.append((dev, is_new))
        return changes

    def _apply_state(self, dev: DeviceState, cmd: int, payload: bytes) -> None:
        # ACK state packets in KS X 4506 deployments are often 0x81.
        if dev.kind == "light":
            # For non-group light response payload usually [error, state].
            # state bit0: on/off, bit1: dimming-capable, bit7~4: dimming level(1~15)
            if len(payload) >= 2:
                v = payload[1]
                dev.state["on"] = bool(v & 0x01)
                dev.state["dimmable"] = bool(v & 0x02)
                dev.state["brightness_step"] = (v >> 4) & 0x0F if dev.state["dimmable"] else 0
            elif payload:
                v = payload[0]
                dev.state["on"] = bool(v & 0x01)

        elif dev.kind in {"switch", "gas_valve"}:
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
