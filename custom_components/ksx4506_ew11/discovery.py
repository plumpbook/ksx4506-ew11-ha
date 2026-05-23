from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .devices.gas import GAS_DEVICE_ID, decode_gas_state
from .devices.lighting import LIGHT_DEVICE_ID, decode_light_state_byte
from .devices.meter import METER_DEVICE_ID, decode_meter_state
from .devices.outlet import OUTLET_DEVICE_ID, decode_outlet_state, decode_switch_state
from .devices.thermostat import THERMOSTAT_DEVICE_ID, decode_thermostat_state

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
    LIGHT_DEVICE_ID: ("light", {"on_off"}),
    GAS_DEVICE_ID: ("gas_valve", {"on_off"}),
    METER_DEVICE_ID: ("sensor", {"state"}),
    0x33: ("switch", {"on_off"}),  # breaker
    THERMOSTAT_DEVICE_ID: ("climate", {"target_temp", "current_temp"}),
    OUTLET_DEVICE_ID: ("switch", {"on_off"}),  # outlet
    0x60: ("sensor", {"state"}),
}


@dataclass
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
        if kind == "light" and addr == LIGHT_DEVICE_ID:
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
                    dev.state.update(decode_light_state_byte(state_byte))
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
                dev.state.update(decode_light_state_byte(payload[1]))
            elif payload:
                dev.state.update(decode_light_state_byte(payload[0]))

        elif dev.kind == "gas_valve":
            dev.state.update(decode_gas_state(payload))

        elif dev.kind == "switch":
            if dev.addr == OUTLET_DEVICE_ID:
                dev.state.update(
                    decode_outlet_state(
                        payload,
                        unit=dev.sub_id & 0x0F,
                        channel=dev.channel,
                    )
                )
            else:
                dev.state.update(decode_switch_state(payload))

        elif dev.kind == "fan" and payload:
            v = payload[-1]
            dev.state["on"] = v > 0
            dev.state["speed"] = v

        elif dev.kind == "climate":
            dev.state.update(decode_thermostat_state(payload, sub_id=dev.sub_id))

        elif dev.kind == "sensor" and dev.addr == METER_DEVICE_ID:
            dev.state.update(
                decode_meter_state(
                    payload,
                    sub_id=dev.sub_id,
                    command_type=cmd,
                )
            )

        if dev.kind in {"sensor", "unknown"} or not dev.state:
            dev.state["value_hex"] = payload.hex()
