from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .devices.common_entrance import (
    CALL_EVENT as COMMON_ENTRANCE_CALL_EVENT,
    COMMON_ENTRANCE_DEVICE_ID,
    OPEN_REQUEST as COMMON_ENTRANCE_OPEN_REQUEST,
    STATUS_REQUEST as COMMON_ENTRANCE_STATUS_REQUEST,
    STATUS_RESPONSE as COMMON_ENTRANCE_STATUS_RESPONSE,
    decode_common_entrance_state,
)
from .devices.entrance import ENTRANCE_PANEL_DEVICE_ID, decode_entrance_panel_state
from .devices.gas import (
    CONTROL_REQUEST as GAS_CONTROL_REQUEST,
    CONTROL_RESPONSE as GAS_CONTROL_RESPONSE,
    GAS_DEVICE_ID,
    STATUS_REQUEST as GAS_STATUS_REQUEST,
    STATUS_RESPONSE as GAS_STATUS_RESPONSE,
    decode_gas_state,
)
from .devices.lighting import (
    CONTROL_REQUEST as LIGHT_CONTROL_REQUEST,
    CONTROL_RESPONSE as LIGHT_CONTROL_RESPONSE,
    LIGHT_DEVICE_ID,
    STATUS_REQUEST as LIGHT_STATUS_REQUEST,
    STATUS_RESPONSE as LIGHT_STATUS_RESPONSE,
    decode_light_state_byte,
)
from .devices.meter import (
    CHARACTERISTIC_REQUEST as METER_CHARACTERISTIC_REQUEST,
    CHARACTERISTIC_RESPONSE as METER_CHARACTERISTIC_RESPONSE,
    METER_DEVICE_ID,
    STATUS_REQUEST as METER_STATUS_REQUEST,
    STATUS_RESPONSE as METER_STATUS_RESPONSE,
    VALID_METER_SUB_IDS,
    decode_meter_state,
    iter_meter_states,
)
from .devices.outlet import (
    CONTROL_REQUEST as OUTLET_CONTROL_REQUEST,
    CONTROL_RESPONSE as OUTLET_CONTROL_RESPONSE,
    CUTOFF_THRESHOLD_CONTROL_RESPONSE as OUTLET_THRESHOLD_CONTROL_RESPONSE,
    CUTOFF_THRESHOLD_RESPONSE as OUTLET_THRESHOLD_RESPONSE,
    OUTLET_DEVICE_ID,
    STATUS_REQUEST as OUTLET_STATUS_REQUEST,
    STATUS_RESPONSE as OUTLET_STATUS_RESPONSE,
    decode_outlet_state,
    decode_switch_state,
)
from .devices.thermostat import (
    AWAY_CONTROL_REQUEST as THERMOSTAT_AWAY_CONTROL_REQUEST,
    HEAT_CONTROL_REQUEST as THERMOSTAT_HEAT_CONTROL_REQUEST,
    HOT_WATER_CONTROL_REQUEST as THERMOSTAT_HOT_WATER_CONTROL_REQUEST,
    SCHEDULE_CONTROL_REQUEST as THERMOSTAT_SCHEDULE_CONTROL_REQUEST,
    STATE_RESPONSE_COMMANDS as THERMOSTAT_STATE_RESPONSE_COMMANDS,
    STATUS_REQUEST as THERMOSTAT_STATUS_REQUEST,
    TEMPERATURE_CONTROL_REQUEST as THERMOSTAT_TEMPERATURE_CONTROL_REQUEST,
    THERMOSTAT_DEVICE_ID,
    decode_thermostat_state,
)

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

ENTRANCE_PANEL_STATUS_RESPONSE = 0x81
ENTRANCE_PANEL_EVENT_RESPONSE = 0x33
GENERIC_SENSOR_DEVICE_ID = 0x60
GENERIC_STATUS_REQUEST = 0x01

REQUEST_COMMANDS_BY_DEVICE = {
    LIGHT_DEVICE_ID: {LIGHT_STATUS_REQUEST, LIGHT_CONTROL_REQUEST},
    GAS_DEVICE_ID: {GAS_STATUS_REQUEST, GAS_CONTROL_REQUEST},
    METER_DEVICE_ID: {METER_STATUS_REQUEST, METER_CHARACTERISTIC_REQUEST},
    ENTRANCE_PANEL_DEVICE_ID: set(),
    THERMOSTAT_DEVICE_ID: {
        THERMOSTAT_STATUS_REQUEST,
        THERMOSTAT_HEAT_CONTROL_REQUEST,
        THERMOSTAT_TEMPERATURE_CONTROL_REQUEST,
        THERMOSTAT_AWAY_CONTROL_REQUEST,
        THERMOSTAT_SCHEDULE_CONTROL_REQUEST,
        THERMOSTAT_HOT_WATER_CONTROL_REQUEST,
    },
    OUTLET_DEVICE_ID: {OUTLET_STATUS_REQUEST, OUTLET_CONTROL_REQUEST},
    COMMON_ENTRANCE_DEVICE_ID: {
        COMMON_ENTRANCE_STATUS_REQUEST,
        COMMON_ENTRANCE_OPEN_REQUEST,
    },
    GENERIC_SENSOR_DEVICE_ID: {GENERIC_STATUS_REQUEST},
}

STATE_COMMANDS_BY_DEVICE = {
    LIGHT_DEVICE_ID: {LIGHT_STATUS_RESPONSE, LIGHT_CONTROL_RESPONSE},
    GAS_DEVICE_ID: {GAS_STATUS_RESPONSE, GAS_CONTROL_RESPONSE},
    METER_DEVICE_ID: {METER_STATUS_RESPONSE, METER_CHARACTERISTIC_RESPONSE},
    ENTRANCE_PANEL_DEVICE_ID: {
        ENTRANCE_PANEL_STATUS_RESPONSE,
        ENTRANCE_PANEL_EVENT_RESPONSE,
    },
    THERMOSTAT_DEVICE_ID: THERMOSTAT_STATE_RESPONSE_COMMANDS,
    OUTLET_DEVICE_ID: {
        OUTLET_STATUS_RESPONSE,
        OUTLET_CONTROL_RESPONSE,
        OUTLET_THRESHOLD_RESPONSE,
        OUTLET_THRESHOLD_CONTROL_RESPONSE,
    },
    COMMON_ENTRANCE_DEVICE_ID: {COMMON_ENTRANCE_STATUS_RESPONSE},
    GENERIC_SENSOR_DEVICE_ID: {LIGHT_STATUS_RESPONSE},
}

EVENT_COMMANDS_BY_DEVICE = {
    COMMON_ENTRANCE_DEVICE_ID: {COMMON_ENTRANCE_CALL_EVENT},
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


@dataclass
class UnsupportedPacketRecord:
    category: str
    reason: str
    addr: int
    sub_id: int
    cmd: int
    payload_len: int
    count: int
    first_seen_seq: int
    last_seen_seq: int
    last_payload_hex: str
    last_raw_hex: str
    sample_raw_hexes: list[str] = field(default_factory=list)

    def as_dict(self, *, include_packet_samples: bool = False) -> dict[str, Any]:
        data = {
            "category": self.category,
            "reason": self.reason,
            "device_id": f"0x{self.addr:02X}",
            "sub_id": f"0x{self.sub_id:02X}",
            "command_type": f"0x{self.cmd:02X}",
            "payload_len": self.payload_len,
            "count": self.count,
            "first_seen_seq": self.first_seen_seq,
            "last_seen_seq": self.last_seen_seq,
            "packet_samples_available": bool(self.sample_raw_hexes),
            "packet_sample_count": len(self.sample_raw_hexes),
        }
        if include_packet_samples:
            data.update(
                {
                    "last_payload_hex": self.last_payload_hex.upper(),
                    "last_raw_hex": self.last_raw_hex.upper(),
                    "sample_raw_hexes": [
                        sample.upper() for sample in self.sample_raw_hexes
                    ],
                }
            )
        return data


MAX_UNSUPPORTED_PACKET_RECORDS = 50
MAX_CANDIDATE_PACKET_RECORDS = 100
MAX_PACKET_RECORD_SAMPLES = 5


class DeviceRegistry:
    def __init__(self) -> None:
        self.devices: dict[str, DeviceState] = {}
        self.unsupported_packets: dict[str, UnsupportedPacketRecord] = {}
        self.candidate_packets: dict[str, UnsupportedPacketRecord] = {}
        self._unsupported_seen_seq = 0

    def upsert_from_frame(self, addr: int, sub_id: int, cmd: int, payload: bytes, raw_hex: str) -> list[tuple[DeviceState, bool]]:
        if addr not in DEVICE_ID_MAP:
            self.record_unsupported_packet(
                "unsupported_device_id",
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
            )
            return []

        kind, caps = DEVICE_ID_MAP[addr]

        if _is_ignored_request(addr, cmd):
            return []

        if not _is_supported_command(addr, cmd):
            self.record_unsupported_packet(
                "unsupported_command",
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
            )
            return []

        if not _is_valid_sub_id_for_device(addr, sub_id):
            self.record_candidate_packet(
                "unregistered_sub_id",
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
            )
            return []

        changes: list[tuple[DeviceState, bool]] = []

        if addr == LIGHT_DEVICE_ID and cmd != LIGHT_STATUS_RESPONSE:
            return []

        # KS X 4506 deployments observed through Suroup expose each lighting
        # module as sub_id 0x11, 0x12, ... and carry channel states in payload.
        # Standard all-channel replies such as 0x1F are still expanded.
        if kind == "light" and addr == LIGHT_DEVICE_ID and cmd == LIGHT_STATUS_RESPONSE:
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

            if not changes:
                self.record_candidate_packet(
                    "candidate_light_packet",
                    addr,
                    sub_id,
                    cmd,
                    payload,
                    raw_hex,
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
            self.record_candidate_packet(
                "candidate_outlet_packet",
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
            )
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
            if cmd == METER_STATUS_RESPONSE:
                self.record_candidate_packet(
                    "candidate_meter_packet",
                    addr,
                    sub_id,
                    cmd,
                    payload,
                    raw_hex,
                )
                return []

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
                self.record_candidate_packet(
                    "thermostat_individual_without_group_state",
                    addr,
                    sub_id,
                    cmd,
                    payload,
                    raw_hex,
                )
                return []

        if kind == "unknown":
            self.record_unsupported_packet(
                "unknown_packet",
                addr,
                sub_id,
                cmd,
                payload,
                raw_hex,
            )
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

    def record_unsupported_packet(
        self,
        reason: str,
        addr: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        raw_hex: str,
    ) -> None:
        self._unsupported_seen_seq += 1
        payload_hex = payload.hex()
        self._record_packet(
            self.unsupported_packets,
            category="unsupported",
            reason=reason,
            addr=addr,
            sub_id=sub_id,
            cmd=cmd,
            payload_hex=payload_hex,
            raw_hex=raw_hex,
            max_records=MAX_UNSUPPORTED_PACKET_RECORDS,
        )

    def record_candidate_packet(
        self,
        reason: str,
        addr: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        raw_hex: str,
    ) -> None:
        self._unsupported_seen_seq += 1
        self._record_packet(
            self.candidate_packets,
            category="candidate",
            reason=reason,
            addr=addr,
            sub_id=sub_id,
            cmd=cmd,
            payload_hex=payload.hex(),
            raw_hex=raw_hex,
            max_records=MAX_CANDIDATE_PACKET_RECORDS,
        )

    def _record_packet(
        self,
        records: dict[str, UnsupportedPacketRecord],
        *,
        category: str,
        reason: str,
        addr: int,
        sub_id: int,
        cmd: int,
        payload_hex: str,
        raw_hex: str,
        max_records: int,
    ) -> None:
        key = f"{category}:{reason}:{addr:02X}:{sub_id:02X}:{cmd:02X}:{len(payload_hex) // 2}"
        record = records.get(key)
        if record is None:
            record = UnsupportedPacketRecord(
                category=category,
                reason=reason,
                addr=addr,
                sub_id=sub_id,
                cmd=cmd,
                payload_len=len(payload_hex) // 2,
                count=0,
                first_seen_seq=self._unsupported_seen_seq,
                last_seen_seq=self._unsupported_seen_seq,
                last_payload_hex=payload_hex,
                last_raw_hex=raw_hex,
                sample_raw_hexes=[],
            )
            records[key] = record

        record.count += 1
        record.last_seen_seq = self._unsupported_seen_seq
        record.last_payload_hex = payload_hex
        record.last_raw_hex = raw_hex
        if raw_hex not in record.sample_raw_hexes:
            record.sample_raw_hexes.append(raw_hex)
            del record.sample_raw_hexes[:-MAX_PACKET_RECORD_SAMPLES]

        if len(records) > max_records:
            oldest_key = min(
                records,
                key=lambda item: records[item].last_seen_seq,
            )
            del records[oldest_key]

    def unsupported_packet_report(
        self,
        *,
        limit: int = MAX_UNSUPPORTED_PACKET_RECORDS,
        include_packet_samples: bool = False,
    ) -> dict[str, Any]:
        unsupported_packets = sorted(
            self.unsupported_packets.values(),
            key=lambda item: item.last_seen_seq,
            reverse=True,
        )
        candidate_packets = sorted(
            self.candidate_packets.values(),
            key=lambda item: item.last_seen_seq,
            reverse=True,
        )
        packets = sorted(
            [*unsupported_packets, *candidate_packets],
            key=lambda item: item.last_seen_seq,
            reverse=True,
        )
        limited = packets[: max(0, limit)]
        latest_packet = (
            packets[0].as_dict(include_packet_samples=include_packet_samples)
            if packets
            else None
        )
        return {
            "total_seen": sum(packet.count for packet in packets),
            "unsupported_seen": sum(packet.count for packet in unsupported_packets),
            "candidate_seen": sum(packet.count for packet in candidate_packets),
            "unique_signatures": len(packets),
            "latest_packet": latest_packet,
            "packet_samples_redacted": not include_packet_samples,
            "packets": [
                packet.as_dict(include_packet_samples=include_packet_samples)
                for packet in limited
            ],
            "unsupported_packets": [
                packet.as_dict(include_packet_samples=include_packet_samples)
                for packet in unsupported_packets[: max(0, limit)]
            ],
            "candidate_packets": [
                packet.as_dict(include_packet_samples=include_packet_samples)
                for packet in candidate_packets[: max(0, limit)]
            ],
        }

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

        elif dev.kind == "unknown":
            dev.state.update(
                {
                    "device_id": f"0x{dev.addr:02X}",
                    "sub_id": f"0x{dev.sub_id:02X}",
                    "command_type": f"0x{cmd:02X}",
                    "payload_len": len(payload),
                }
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


def _is_ignored_request(addr: int, cmd: int) -> bool:
    return cmd in REQUEST_COMMANDS_BY_DEVICE.get(addr, set())


def _is_supported_command(addr: int, cmd: int) -> bool:
    return cmd in (
        REQUEST_COMMANDS_BY_DEVICE.get(addr, set())
        | STATE_COMMANDS_BY_DEVICE.get(addr, set())
        | EVENT_COMMANDS_BY_DEVICE.get(addr, set())
    )


def _is_valid_sub_id_for_device(addr: int, sub_id: int) -> bool:
    if sub_id < 0x01 or sub_id > 0xFF:
        return False

    if addr == METER_DEVICE_ID:
        return sub_id in VALID_METER_SUB_IDS

    if addr in {
        GAS_DEVICE_ID,
        ENTRANCE_PANEL_DEVICE_ID,
        COMMON_ENTRANCE_DEVICE_ID,
        GENERIC_SENSOR_DEVICE_ID,
    }:
        return 0x01 <= sub_id <= 0x0E

    if addr in {LIGHT_DEVICE_ID, THERMOSTAT_DEVICE_ID, OUTLET_DEVICE_ID}:
        return 0x01 <= sub_id <= 0xEF and (sub_id & 0x0F) != 0

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
