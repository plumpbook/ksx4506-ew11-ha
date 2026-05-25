from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .devices.common_entrance import (
    COMMON_ENTRANCE_DEVICE_ID,
    STATUS_REQUEST as COMMON_ENTRANCE_STATUS_REQUEST,
    decode_common_entrance_state,
)
from .devices.entrance import ENTRANCE_PANEL_DEVICE_ID, decode_entrance_panel_state
from .devices.gas import GAS_DEVICE_ID, decode_gas_state
from .devices.lighting import LIGHT_DEVICE_ID, decode_light_state_byte
from .devices.meter import METER_DEVICE_ID, decode_meter_state, iter_meter_states
from .devices.outlet import (
    CONTROL_RESPONSE as OUTLET_CONTROL_RESPONSE,
    CUTOFF_THRESHOLD_CONTROL_RESPONSE as OUTLET_THRESHOLD_CONTROL_RESPONSE,
    CUTOFF_THRESHOLD_RESPONSE as OUTLET_THRESHOLD_RESPONSE,
    OUTLET_DEVICE_ID,
    STATUS_RESPONSE as OUTLET_STATUS_RESPONSE,
    decode_outlet_state,
    decode_switch_state,
)
from .devices.thermostat import (
    STATE_RESPONSE_COMMANDS as THERMOSTAT_STATE_RESPONSE_COMMANDS,
    THERMOSTAT_DEVICE_ID,
    decode_thermostat_state,
)

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
    0x33: ("entrance_panel", {"state"}),
    0x39: ("climate", {"target_temp", "current_temp"}),
}

# Device ID mapping from suroup/ezville reference.
DEVICE_ID_MAP = {
    LIGHT_DEVICE_ID: ("light", {"on_off"}),
    GAS_DEVICE_ID: ("gas_valve", {"on_off"}),
    METER_DEVICE_ID: ("sensor", {"state"}),
    ENTRANCE_PANEL_DEVICE_ID: ("entrance_panel", {"state"}),
    THERMOSTAT_DEVICE_ID: ("climate", {"target_temp", "current_temp"}),
    OUTLET_DEVICE_ID: ("switch", {"on_off"}),  # outlet
    COMMON_ENTRANCE_DEVICE_ID: ("common_entrance", {"state"}),
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


GENERIC_SENSOR_DEVICE_ID = 0x60
GENERIC_STATUS_REQUEST = 0x01


class DeviceRegistry:
    def __init__(self) -> None:
        self.devices: dict[str, DeviceState] = {}

    def upsert_from_frame(self, addr: int, sub_id: int, cmd: int, payload: bytes, raw_hex: str) -> list[tuple[DeviceState, bool]]:
        if _is_polling_request(addr, cmd):
            return []

        # Device 0x40 uses command 0x10 for common entrance events. Without
        # this override the generic command map would misclassify it as light.
        if addr == COMMON_ENTRANCE_DEVICE_ID:
            kind, caps = DEVICE_ID_MAP[addr]
        else:
            kind, caps = CMD_TYPE_MAP.get(cmd, ("unknown", {"diagnostic"}))
        if kind == "unknown":
            kind, caps = DEVICE_ID_MAP.get(addr, (kind, caps))

        changes: list[tuple[DeviceState, bool]] = []

        # KS X 4506 deployments observed through Suroup expose each lighting
        # module as sub_id 0x11, 0x12, ... and carry channel states in payload.
        # Standard all-channel replies such as 0x1F are still expanded.
        if kind == "light" and addr == LIGHT_DEVICE_ID:
            if len(payload) > 1:
                low = sub_id & 0x0F
                high = (sub_id >> 4) & 0x0F
                is_group_reply = high > 0 and low == 0x0F

                def upsert_light(
                    *,
                    entity_sub_id: int,
                    channel: int | None,
                    state_byte: int,
                    control_sub_id: int,
                    status_sub_id: int,
                    control_channel: int | None,
                ) -> None:
                    key = f"{addr:02X}{entity_sub_id:02X}_{kind}"
                    if channel is not None:
                        key = f"{key}_{channel}"

                    is_new = key not in self.devices
                    if is_new:
                        self.devices[key] = DeviceState(
                            key=key,
                            addr=addr,
                            sub_id=entity_sub_id,
                            channel=channel,
                            kind=kind,
                            capabilities=set(caps),
                        )

                    dev = self.devices[key]
                    dev.last_raw_hex = raw_hex
                    dev.state.update(decode_light_state_byte(state_byte))
                    dev.state["status_sub_id"] = status_sub_id
                    dev.state["control_sub_id"] = control_sub_id
                    if control_channel is None:
                        dev.state.pop("control_channel", None)
                    else:
                        dev.state["control_channel"] = control_channel
                    changes.append((dev, is_new))

                if is_group_reply:
                    group = high
                    for ch, state_byte in enumerate(payload[1:], start=1):
                        upsert_light(
                            entity_sub_id=sub_id,
                            channel=ch,
                            state_byte=state_byte,
                            control_sub_id=((group & 0x0F) << 4) | (ch & 0x0F),
                            status_sub_id=sub_id,
                            control_channel=None,
                        )
                elif high > 0 and 0x01 <= low <= 0x0E:
                    is_suroup_module_reply = 0x11 <= sub_id <= 0x15 or len(payload) > 2
                    standard_group_key = f"{addr:02X}{((high << 4) | 0x0F):02X}_{kind}_{low}"
                    if not is_suroup_module_reply or standard_group_key in self.devices:
                        upsert_light(
                            entity_sub_id=(high << 4) | 0x0F,
                            channel=low,
                            state_byte=payload[1],
                            control_sub_id=sub_id,
                            status_sub_id=sub_id,
                            control_channel=None,
                        )
                    else:
                        for ch, state_byte in enumerate(payload[1:], start=1):
                            upsert_light(
                                entity_sub_id=sub_id,
                                channel=ch,
                                state_byte=state_byte,
                                control_sub_id=sub_id,
                                status_sub_id=sub_id,
                                control_channel=ch,
                            )
                elif 0x01 <= low <= 0x0E:
                    upsert_light(
                        entity_sub_id=sub_id,
                        channel=None,
                        state_byte=payload[1],
                        control_sub_id=sub_id,
                        status_sub_id=sub_id,
                        control_channel=None,
                    )

            return changes

        # Suroup-compatible outlet model: grouped status packets such as 0x1F
        # carry multiple physical outlets, but each outlet is controlled through
        # its own sub-id (0x11, 0x12, ...).
        if kind == "switch" and addr == OUTLET_DEVICE_ID:
            outlet_changes = self._upsert_outlet_from_frame(
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
                caps,
            )
            if outlet_changes:
                return outlet_changes
            if _is_outlet_group_sub_id(sub_id):
                return []

        if kind == "sensor" and addr == METER_DEVICE_ID:
            meter_changes = self._upsert_meter_from_frame(
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
                caps,
            )
            if meter_changes:
                return meter_changes

        if kind == "climate" and addr == THERMOSTAT_DEVICE_ID:
            thermostat_changes = self._upsert_thermostat_from_frame(
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
            )
            if thermostat_changes:
                return thermostat_changes
            if (
                cmd in THERMOSTAT_STATE_RESPONSE_COMMANDS
                and _is_individual_thermostat_sub_id(sub_id)
            ):
                return []

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
                        command_type=cmd,
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

        elif dev.kind == "entrance_panel":
            dev.state.update(decode_entrance_panel_state(payload))

        elif dev.kind == "common_entrance":
            dev.state.update(
                decode_common_entrance_state(
                    payload,
                    command_type=cmd,
                )
            )

        if dev.kind in {"sensor", "unknown"} or not dev.state:
            dev.state["value_hex"] = payload.hex()

    def _upsert_thermostat_from_frame(
        self,
        addr: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        raw_hex: str,
    ) -> list[tuple[DeviceState, bool]]:
        if cmd not in THERMOSTAT_STATE_RESPONSE_COMMANDS:
            return []
        if not _is_individual_thermostat_sub_id(sub_id):
            return []

        group_sub_id = (sub_id & 0xF0) | 0x0F
        group_key = f"{addr:02X}{group_sub_id:02X}_climate"
        group = self.devices.get(group_key)
        if group is None:
            return []

        zone = _decode_individual_thermostat_zone(payload, channel=sub_id & 0x0F)
        if zone is None:
            return []

        zones = [
            dict(existing)
            for existing in group.state.get("zones", [])
            if existing.get("channel") != zone["channel"]
        ]
        zones.append(zone)
        zones.sort(key=lambda item: item.get("channel", 0))

        decoded = decode_thermostat_state(payload, sub_id=sub_id)
        group.state["zones"] = zones
        for key in ("error", "hot_water"):
            if key in decoded:
                group.state[key] = decoded[key]
        group.last_raw_hex = raw_hex
        return [(group, False)]

    def _upsert_outlet_from_frame(
        self,
        addr: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        raw_hex: str,
        caps: set[str],
    ) -> list[tuple[DeviceState, bool]]:
        if cmd not in {
            OUTLET_STATUS_RESPONSE,
            OUTLET_CONTROL_RESPONSE,
            OUTLET_THRESHOLD_RESPONSE,
            OUTLET_THRESHOLD_CONTROL_RESPONSE,
        }:
            return []

        low = sub_id & 0x0F
        high = (sub_id >> 4) & 0x0F
        count = _outlet_payload_channel_count(cmd, payload)
        if count <= 0:
            return []

        changes: list[tuple[DeviceState, bool]] = []
        if high > 0 and low == 0x0F:
            for channel in range(1, count + 1):
                entity_sub_id = ((high & 0x0F) << 4) | (channel & 0x0F)
                changes.append(
                    self._upsert_single_outlet(
                        addr=addr,
                        entity_sub_id=entity_sub_id,
                        status_sub_id=sub_id,
                        status_channel=channel,
                        cmd=cmd,
                        payload=payload,
                        raw_hex=raw_hex,
                        caps=caps,
                    )
                )
            return changes

        changes.append(
            self._upsert_single_outlet(
                addr=addr,
                entity_sub_id=sub_id,
                status_sub_id=sub_id,
                status_channel=1,
                cmd=cmd,
                payload=payload,
                raw_hex=raw_hex,
                caps=caps,
            )
        )
        return changes

    def _upsert_single_outlet(
        self,
        *,
        addr: int,
        entity_sub_id: int,
        status_sub_id: int,
        status_channel: int,
        cmd: int,
        payload: bytes,
        raw_hex: str,
        caps: set[str],
    ) -> tuple[DeviceState, bool]:
        key = f"{addr:02X}{entity_sub_id:02X}_switch"
        is_new = key not in self.devices
        if is_new:
            self.devices[key] = DeviceState(
                key=key,
                addr=addr,
                sub_id=entity_sub_id,
                kind="switch",
                capabilities=set(caps),
            )

        dev = self.devices[key]
        dev.last_raw_hex = raw_hex
        state = decode_outlet_state(
            payload,
            unit=entity_sub_id & 0x0F,
            channel=status_channel,
            command_type=cmd,
        )
        dev.state.update(state)
        dev.state["status_sub_id"] = status_sub_id
        dev.state["status_channel"] = status_channel
        dev.state["control_sub_id"] = entity_sub_id
        return dev, is_new

    def _upsert_meter_from_frame(
        self,
        addr: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        raw_hex: str,
        caps: set[str],
    ) -> list[tuple[DeviceState, bool]]:
        states = iter_meter_states(
            payload,
            sub_id=sub_id,
            command_type=cmd,
        )
        if not states:
            return []

        changes: list[tuple[DeviceState, bool]] = []
        for meter_sub_id, state in states:
            key = f"{addr:02X}{meter_sub_id:02X}_sensor"
            is_new = key not in self.devices
            if is_new:
                self.devices[key] = DeviceState(
                    key=key,
                    addr=addr,
                    sub_id=meter_sub_id,
                    kind="sensor",
                    capabilities=set(caps),
                )

            dev = self.devices[key]
            dev.last_raw_hex = raw_hex
            dev.state.update(state)
            dev.state["source_sub_id"] = sub_id
            changes.append((dev, is_new))
        return changes


def _is_polling_request(addr: int, cmd: int) -> bool:
    if addr == COMMON_ENTRANCE_DEVICE_ID:
        return cmd in {GENERIC_STATUS_REQUEST, COMMON_ENTRANCE_STATUS_REQUEST}
    if addr in {
        GENERIC_SENSOR_DEVICE_ID,
        METER_DEVICE_ID,
        THERMOSTAT_DEVICE_ID,
        OUTLET_DEVICE_ID,
    }:
        return cmd == GENERIC_STATUS_REQUEST
    return False


def _outlet_payload_channel_count(cmd: int, payload: bytes) -> int:
    if not payload:
        return 0
    if cmd in {OUTLET_STATUS_RESPONSE} and len(payload) >= 4 and (len(payload) - 1) % 3 == 0:
        return (len(payload) - 1) // 3
    if (
        cmd in {OUTLET_THRESHOLD_RESPONSE, OUTLET_THRESHOLD_CONTROL_RESPONSE}
        and len(payload) >= 3
        and (len(payload) - 1) % 2 == 0
    ):
        return (len(payload) - 1) // 2
    if cmd == OUTLET_CONTROL_RESPONSE and len(payload) >= 2:
        return len(payload) - 1
    return 0


def _is_outlet_group_sub_id(sub_id: int) -> bool:
    return ((sub_id >> 4) & 0x0F) > 0 and (sub_id & 0x0F) == 0x0F


def _is_individual_thermostat_sub_id(sub_id: int) -> bool:
    return ((sub_id >> 4) & 0x0F) > 0 and 0x01 <= (sub_id & 0x0F) <= 0x0E


def _decode_individual_thermostat_zone(
    payload: bytes,
    *,
    channel: int,
) -> dict[str, Any] | None:
    decoded = decode_thermostat_state(payload, sub_id=channel)
    zones = decoded.get("zones", [])
    if len(zones) != 1:
        return None

    zone = dict(zones[0])
    zone["channel"] = channel
    return zone
