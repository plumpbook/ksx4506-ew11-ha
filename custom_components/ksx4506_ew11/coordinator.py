from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_MAX_ATTEMPTS,
    CONF_PACKET_CAPTURE_ENABLED,
    CONF_PACKET_CAPTURE_FILTER,
    CONF_PACKET_CAPTURE_LIMIT,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_PACKET_CAPTURE_ENABLED,
    DEFAULT_PACKET_CAPTURE_FILTER,
    DEFAULT_PACKET_CAPTURE_LIMIT,
    DOMAIN,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_REMOVED,
    SIGNAL_DEVICE_UPDATE,
)
from .devices.common_entrance import (
    CALL_EVENT,
    COMMON_ENTRANCE_DEVICE_ID,
    STATUS_REQUEST as COMMON_ENTRANCE_STATUS_REQUEST,
    STATUS_RESPONSE as COMMON_ENTRANCE_STATUS_RESPONSE,
    decode_common_entrance_state,
    format_common_entrance_packet_log,
)
from .devices.entrance import ENTRANCE_PANEL_DEVICE_ID
from .devices.gas import GAS_DEVICE_ID
from .devices.lighting import LIGHT_DEVICE_ID
from .devices.meter import METER_DEVICE_ID, METER_WHOLE_ORDER
from .devices.outlet import OUTLET_DEVICE_ID
from .devices.thermostat import THERMOSTAT_DEVICE_ID
from .discovery import DeviceRegistry
from .ew11_client import Ew11Client
from .packet_quality import PacketQualityMonitor, empty_packet_quality_report
from .protocol import Ksx4506Codec, KsFrame

_LOGGER = logging.getLogger(__name__)
_METER_STARTUP_PROBE_SUB_IDS = (0x0F, *METER_WHOLE_ORDER)
_F7_STATUS_REQUEST = 0x01
_F7_STATUS_RESPONSE = 0x81
GENERIC_SENSOR_DEVICE_ID = 0x60
REQUESTABLE_F7_DEVICE_IDS = {
    LIGHT_DEVICE_ID,
    GAS_DEVICE_ID,
    ENTRANCE_PANEL_DEVICE_ID,
    THERMOSTAT_DEVICE_ID,
    OUTLET_DEVICE_ID,
    COMMON_ENTRANCE_DEVICE_ID,
    GENERIC_SENSOR_DEVICE_ID,
}
STATUS_REQUEST_COMMAND_BY_DEVICE_ID = {
    COMMON_ENTRANCE_DEVICE_ID: COMMON_ENTRANCE_STATUS_REQUEST,
}
STATUS_RESPONSE_COMMAND_BY_DEVICE_ID = {
    COMMON_ENTRANCE_DEVICE_ID: COMMON_ENTRANCE_STATUS_RESPONSE,
}


class Ksx4506Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.registry = DeviceRegistry()
        self.packet_quality = PacketQualityMonitor()
        self.codec = Ksx4506Codec(
            stx=int(config["stx"], 16),
            etx=int(config["etx"], 16),
            checksum_mode=config["checksum"],
            packet_quality=self.packet_quality,
        )
        self._client = Ew11Client(
            host=config["host"],
            port=config["port"],
            timeout=config["timeout"],
            retry=config["retry"],
            codec=self.codec,
            on_frame=self._on_frame,
        )
        self._client.set_health_listener(self._publish_registry_state)
        self._gas_unlock = config.get("gas_unlock", False)
        self.max_attempts = max(
            1,
            min(20, int(config.get(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS))),
        )
        self.packet_capture_enabled = bool(
            config.get(
                CONF_PACKET_CAPTURE_ENABLED,
                DEFAULT_PACKET_CAPTURE_ENABLED,
            )
        )
        self.packet_capture_filter_text = str(
            config.get(
                CONF_PACKET_CAPTURE_FILTER,
                DEFAULT_PACKET_CAPTURE_FILTER,
            )
        )
        self.packet_capture_filter = _parse_packet_capture_filter(
            self.packet_capture_filter_text
        )
        self.packet_capture_limit = max(
            1,
            min(
                100,
                int(
                    config.get(
                        CONF_PACKET_CAPTURE_LIMIT,
                        DEFAULT_PACKET_CAPTURE_LIMIT,
                    )
                ),
            ),
        )
        self.packet_capture: deque[dict[str, Any]] = deque(
            maxlen=self.packet_capture_limit
        )
        self._last_changed_device_keys: frozenset[str] | None = None
        self._frame_waiters: list[tuple[Callable[[KsFrame], bool], asyncio.Future[KsFrame]]] = []
        self._meter_probe_task: asyncio.Task[None] | None = None
        self._known_device_probe_task: asyncio.Task[None] | None = None

    async def _async_update_data(self):
        return {k: v.state for k, v in self.registry.devices.items()}

    def _publish_registry_state(
        self,
        changed_device_keys: set[str] | frozenset[str] | None = None,
    ) -> None:
        self._last_changed_device_keys = (
            None if changed_device_keys is None else frozenset(changed_device_keys)
        )
        self.async_set_updated_data(
            {key: device.state for key, device in self.registry.devices.items()}
        )

    async def async_start(self) -> None:
        await self._client.start()
        if self._meter_probe_task is None or self._meter_probe_task.done():
            self._meter_probe_task = asyncio.create_task(self.async_probe_meter_states())
        if (
            self._known_device_probe_task is None
            or self._known_device_probe_task.done()
        ):
            self._known_device_probe_task = asyncio.create_task(
                self.async_probe_known_device_states()
            )

    async def async_stop(self) -> None:
        if self._known_device_probe_task:
            self._known_device_probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._known_device_probe_task
            self._known_device_probe_task = None
        if self._meter_probe_task:
            self._meter_probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._meter_probe_task
            self._meter_probe_task = None
        await self._client.stop()

    async def _on_frame(self, frame: KsFrame) -> None:
        _LOGGER.debug(
            "RX frame dev=0x%02X sub=0x%02X cmd=0x%02X len=%d raw=%s",
            frame.addr,
            frame.sub_id,
            frame.cmd,
            len(frame.payload),
            frame.raw.hex(),
        )
        if frame.addr == COMMON_ENTRANCE_DEVICE_ID:
            log_message = format_common_entrance_packet_log(
                frame.sub_id,
                frame.cmd,
                frame.payload,
                frame.raw,
                direction="RX",
            )
            if frame.cmd == CALL_EVENT:
                state = decode_common_entrance_state(
                    frame.payload,
                    command_type=frame.cmd,
                )
                _LOGGER.info(
                    "Common entrance call event sub=0x%02X detected=%s",
                    frame.sub_id,
                    state.get("call_detected", False),
                )
                _LOGGER.debug(log_message)
            else:
                _LOGGER.debug(log_message)
        retired_before = self.registry.retired_device_keys.copy()
        changes = self.registry.upsert_from_frame(
            frame.addr,
            frame.sub_id,
            frame.cmd,
            frame.payload,
            frame.raw.hex(),
        )
        if getattr(self, "packet_capture_enabled", False):
            self._capture_packet(
                frame,
                classification=getattr(
                    self.registry,
                    "last_packet_classification",
                    None,
                ),
            )
        for dev, is_new in changes:
            if is_new:
                async_dispatcher_send(self.hass, SIGNAL_DEVICE_ADDED, dev.key)
            async_dispatcher_send(self.hass, SIGNAL_DEVICE_UPDATE, dev.key)
        for dev_key in self.registry.retired_device_keys - retired_before:
            async_dispatcher_send(self.hass, SIGNAL_DEVICE_REMOVED, dev_key)
        self._publish_registry_state(
            {dev.key for dev, _is_new in changes}
            | (self.registry.retired_device_keys - retired_before)
        )
        self._notify_frame_waiters(frame)

    def _capture_packet(
        self,
        frame: KsFrame,
        classification: dict[str, str | None] | None = None,
    ) -> None:
        if not self.packet_capture_enabled:
            return
        if (
            self.packet_capture_filter is not None
            and frame.addr not in self.packet_capture_filter
        ):
            return

        classification = classification or {
            "classification": "supported",
            "reason": None,
        }
        self.packet_capture.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "direction": "rx",
                "device_id": f"0x{frame.addr:02X}",
                "sub_id": f"0x{frame.sub_id:02X}",
                "command_type": f"0x{frame.cmd:02X}",
                "classification": classification.get("classification", "supported"),
                "reason": classification.get("reason"),
                "signature": _packet_capture_signature(frame, classification),
                "payload_len": len(frame.payload),
                "payload_hex": frame.payload.hex().upper(),
                "raw_hex": frame.raw.hex().upper(),
            }
        )

    def packet_capture_report(self) -> dict[str, Any]:
        packets = list(reversed(self.packet_capture))
        classification_counts = {
            "candidate": 0,
            "ignored_request": 0,
            "supported": 0,
            "unsupported": 0,
        }
        for packet in packets:
            classification = packet.get("classification", "supported")
            classification_counts[classification] = (
                classification_counts.get(classification, 0) + 1
            )
        latest_packet = packets[0] if packets else None
        latest_unsupported = next(
            (
                packet
                for packet in packets
                if packet.get("classification") == "unsupported"
            ),
            None,
        )
        latest_candidate = next(
            (
                packet
                for packet in packets
                if packet.get("classification") == "candidate"
            ),
            None,
        )
        return {
            "enabled": self.packet_capture_enabled,
            "filter": self.packet_capture_filter_text,
            "limit": self.packet_capture_limit,
            "count": len(packets),
            "summary": (
                f"supported={classification_counts.get('supported', 0)}, "
                f"ignored_request={classification_counts.get('ignored_request', 0)}, "
                f"candidate={classification_counts.get('candidate', 0)}, "
                f"unsupported={classification_counts.get('unsupported', 0)}"
            ),
            "classification_counts": classification_counts,
            "latest_packet": latest_packet,
            "latest_packet_signature": (
                latest_packet.get("signature") if latest_packet else None
            ),
            "latest_unsupported": latest_unsupported,
            "latest_unsupported_signature": (
                latest_unsupported.get("signature") if latest_unsupported else None
            ),
            "latest_candidate": latest_candidate,
            "latest_candidate_signature": (
                latest_candidate.get("signature") if latest_candidate else None
            ),
            "unsupported_packets": [
                packet
                for packet in packets
                if packet.get("classification") == "unsupported"
            ],
            "candidate_packets": [
                packet
                for packet in packets
                if packet.get("classification") == "candidate"
            ],
            "packets": packets,
        }

    def packet_quality_report(self) -> dict[str, Any]:
        quality = getattr(self, "packet_quality", None)
        if quality is None:
            return empty_packet_quality_report()
        return quality.report()

    def _notify_frame_waiters(self, frame: KsFrame) -> None:
        for matcher, fut in tuple(self._frame_waiters):
            if fut.done():
                continue
            try:
                matched = matcher(frame)
            except Exception:
                _LOGGER.exception("Frame waiter matcher failed")
                matched = False
            if matched and not fut.done():
                fut.set_result(frame)

    async def async_send_command(self, addr: int, cmd: int, payload: bytes, *, guard: bool = False) -> bool:
        if guard and not self._gas_unlock:
            _LOGGER.warning("Blocked guarded command addr=%s cmd=%s", addr, cmd)
            return False
        packet = self.codec.build(addr, cmd, payload)
        _LOGGER.debug(
            "TX STX addr=0x%02X cmd=0x%02X payload=%s packet=%s",
            addr,
            cmd,
            payload.hex(),
            packet.hex(),
        )
        return await self._client.send_with_retry(packet)

    async def async_send_f7_command(
        self,
        dev_id: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        *,
        guard: bool = False,
    ) -> bool:
        if guard and not self._gas_unlock:
            _LOGGER.warning(
                "Blocked guarded F7 command dev=%s sub=%s cmd=%s",
                dev_id,
                sub_id,
                cmd,
            )
            return False
        packet = self.codec.build_f7(dev_id, sub_id, cmd, payload)
        _LOGGER.debug(
            "TX F7 dev=0x%02X sub=0x%02X cmd=0x%02X payload=%s packet=%s",
            dev_id,
            sub_id,
            cmd,
            payload.hex(),
            packet.hex(),
        )
        return await self._client.send_with_retry(packet)

    async def async_send_f7_command_until(
        self,
        dev_id: int,
        sub_id: int,
        cmd: int,
        payload: bytes,
        matcher: Callable[[KsFrame], bool],
        *,
        max_attempts: int | None = None,
        interval: float = 0.1,
        guard: bool = False,
    ) -> KsFrame | None:
        attempts = max(1, min(20, int(max_attempts or self.max_attempts)))
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[KsFrame] = loop.create_future()
        waiter = (matcher, fut)
        self._frame_waiters.append(waiter)

        try:
            for attempt in range(1, attempts + 1):
                if fut.done():
                    matched = fut.result()
                    _LOGGER.debug(
                        "TX F7 control matched before send dev=0x%02X sub=0x%02X cmd=0x%02X "
                        "attempt=%d/%d matched_sub=0x%02X matched_cmd=0x%02X",
                        dev_id,
                        sub_id,
                        cmd,
                        attempt,
                        attempts,
                        matched.sub_id,
                        matched.cmd,
                    )
                    return matched

                _LOGGER.debug(
                    "TX F7 control attempt dev=0x%02X sub=0x%02X cmd=0x%02X "
                    "attempt=%d/%d interval=%.3fs payload=%s",
                    dev_id,
                    sub_id,
                    cmd,
                    attempt,
                    attempts,
                    interval,
                    payload.hex(),
                )

                await self.async_send_f7_command(
                    dev_id,
                    sub_id,
                    cmd,
                    payload,
                    guard=guard,
                )

                try:
                    matched = await asyncio.wait_for(asyncio.shield(fut), timeout=interval)
                    _LOGGER.debug(
                        "TX F7 control matched dev=0x%02X sub=0x%02X cmd=0x%02X "
                        "attempt=%d/%d matched_sub=0x%02X matched_cmd=0x%02X",
                        dev_id,
                        sub_id,
                        cmd,
                        attempt,
                        attempts,
                        matched.sub_id,
                        matched.cmd,
                    )
                    return matched
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "TX F7 control wait timeout dev=0x%02X sub=0x%02X cmd=0x%02X "
                        "attempt=%d/%d",
                        dev_id,
                        sub_id,
                        cmd,
                        attempt,
                        attempts,
                    )
                    continue

            if fut.done():
                matched = fut.result()
                _LOGGER.debug(
                    "TX F7 control matched after final send dev=0x%02X sub=0x%02X cmd=0x%02X "
                    "attempts=%d matched_sub=0x%02X matched_cmd=0x%02X",
                    dev_id,
                    sub_id,
                    cmd,
                    attempts,
                    matched.sub_id,
                    matched.cmd,
                )
                return matched
            health = self._client.health_report()
            is_state_request = (
                cmd == _status_request_command(dev_id) and payload == b""
            )
            packet_hex = self.codec.build_f7(dev_id, sub_id, cmd, payload).hex()
            if is_state_request:
                _LOGGER.debug(
                    "TX F7 state request gave up dev=0x%02X sub=0x%02X cmd=0x%02X "
                    "attempts=%d payload=%s packet=%s ew11_state=%s "
                    "seconds_since_last_rx=%s last_error=%s",
                    dev_id,
                    sub_id,
                    cmd,
                    attempts,
                    payload.hex(),
                    packet_hex,
                    health.get("state"),
                    health.get("seconds_since_last_rx"),
                    health.get("last_error"),
                )
            else:
                _LOGGER.warning(
                    "TX F7 control gave up dev=0x%02X sub=0x%02X cmd=0x%02X "
                    "attempts=%d payload=%s packet=%s ew11_state=%s "
                    "seconds_since_last_rx=%s last_error=%s",
                    dev_id,
                    sub_id,
                    cmd,
                    attempts,
                    payload.hex(),
                    packet_hex,
                    health.get("state"),
                    health.get("seconds_since_last_rx"),
                    health.get("last_error"),
                )
            quality = getattr(self, "packet_quality", None)
            if quality is not None:
                quality.record_tx_giveup(
                    dev_id=dev_id,
                    sub_id=sub_id,
                    cmd=cmd,
                    payload=payload,
                    attempts=attempts,
                    is_state_request=is_state_request,
                    health=health,
                )
                publish = getattr(self, "_publish_registry_state", None)
                if publish is not None:
                    publish()
            return None
        finally:
            with suppress(ValueError):
                self._frame_waiters.remove(waiter)

    async def async_request_f7_state(self, dev_id: int, sub_id: int) -> bool:
        cmd = _status_request_command(dev_id)
        return await self.async_send_f7_command(dev_id, sub_id, cmd, b"")

    async def async_request_f7_state_until(
        self,
        dev_id: int,
        sub_id: int,
        *,
        interval: float = 0.25,
    ) -> KsFrame | None:
        request_cmd = _status_request_command(dev_id)
        response_cmd = _status_response_command(dev_id)

        def matcher(frame: KsFrame) -> bool:
            return (
                frame.addr == dev_id
                and frame.sub_id == sub_id
                and frame.cmd == response_cmd
            )

        return await self.async_send_f7_command_until(
            dev_id,
            sub_id,
            request_cmd,
            b"",
            matcher,
            interval=interval,
        )

    async def async_probe_meter_states(
        self,
        *,
        delay: float = 1.0,
        interval: float = 0.2,
    ) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            for sub_id in _METER_STARTUP_PROBE_SUB_IDS:
                ok = await self.async_request_f7_state(METER_DEVICE_ID, sub_id)
                _LOGGER.debug(
                    "Meter startup probe sub=0x%02X ok=%s",
                    sub_id,
                    ok,
                )
                if interval > 0:
                    await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Meter startup probe failed")

    async def async_probe_known_device_states(
        self,
        *,
        delay: float = 1.5,
        interval: float = 0.15,
    ) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            for dev_id, sub_id in self._known_state_request_targets():
                matched = await self.async_request_f7_state_until(
                    dev_id,
                    sub_id,
                    interval=interval,
                )
                _LOGGER.debug(
                    "Known device startup probe dev=0x%02X sub=0x%02X matched=%s",
                    dev_id,
                    sub_id,
                    matched is not None,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Known device startup probe failed")

    def _known_state_request_targets(self) -> list[tuple[int, int]]:
        targets: set[tuple[int, int]] = set()
        for dev in self.registry.devices.values():
            if dev.addr == METER_DEVICE_ID:
                continue
            if dev.addr not in REQUESTABLE_F7_DEVICE_IDS:
                continue
            sub_id = int(dev.state.get("status_sub_id", dev.sub_id))
            if 0x01 <= sub_id <= 0xEF:
                targets.add((dev.addr, sub_id))
        return sorted(targets)


def _status_request_command(dev_id: int) -> int:
    return STATUS_REQUEST_COMMAND_BY_DEVICE_ID.get(dev_id, _F7_STATUS_REQUEST)


def _status_response_command(dev_id: int) -> int:
    return STATUS_RESPONSE_COMMAND_BY_DEVICE_ID.get(dev_id, _F7_STATUS_RESPONSE)


def _parse_packet_capture_filter(value: str) -> set[int] | None:
    cleaned = str(value or "").strip()
    if not cleaned or cleaned.lower() in {"*", "all"}:
        return None

    out: set[int] = set()
    for token in cleaned.replace(";", ",").replace(" ", ",").split(","):
        token = token.strip()
        if not token:
            continue
        token = token.removeprefix("0x").removeprefix("0X")
        try:
            device_id = int(token, 16)
        except ValueError:
            continue
        if 0 <= device_id <= 0xFF:
            out.add(device_id)
    return out


def _packet_capture_signature(
    frame: KsFrame,
    classification: dict[str, str | None],
) -> str:
    reason = classification.get("reason") or "-"
    return (
        f"{classification.get('classification', 'supported')} {reason} "
        f"0x{frame.addr:02X}/0x{frame.sub_id:02X}/0x{frame.cmd:02X} "
        f"len={len(frame.payload)}"
    )
