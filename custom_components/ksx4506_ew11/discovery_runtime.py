"""HA-owned evidence storage and rate-limited read-only candidate verification."""
import asyncio  # noqa: ANYIO_OK - Home Assistant owns this task and transaction lock
from contextlib import suppress
from dataclasses import replace
import logging
import json
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.core import CoreState
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .discovery_evidence import EvidenceEvent, EvidenceSnapshot
from .discovery_guard import DiscoveryGuard
from .guarded_registry import GuardedRegistry
from .registration_review import registered_review
from .review_links import device_review_links

if TYPE_CHECKING:
    from .coordinator import Ksx4506Coordinator

_LOGGER = logging.getLogger(__name__)


def _saved_data_matches(path: str, expected: str) -> bool:
    stored = json.loads(Path(path).read_text(encoding="utf-8"))
    return isinstance(stored, dict) and stored.get("data") == expected


class DiscoveryRuntime:
    def __init__(self, coordinator: "Ksx4506Coordinator", entry_id: str) -> None:
        self.coordinator = coordinator
        self.guard = DiscoveryGuard()
        self.guard.verification_enabled = False
        self.guard.link_healthy = self._link_healthy
        self.store = Store[str](coordinator.hass, 1, f"{DOMAIN}.{entry_id}.discovery_evidence",
                                private=True, atomic_writes=True)
        self.task: asyncio.Task[None] | None = None
        self.saved_revision = -1
        self.notification_id = f"ew11_discovery_{entry_id}"
        self.entry_id = entry_id
        self.previous_summary: tuple[str, ...] = ()
        self.last_error_signature = ""
        self.save_lock = asyncio.Lock()
        self.operation_lock = asyncio.Lock()

    async def async_load(self) -> None:
        saved = await self.store.async_load()
        if saved is not None:
            self.guard.restore(EvidenceSnapshot.from_json(saved))
        self.coordinator.registry = GuardedRegistry(self.guard)
        self.saved_revision = self.guard.evidence.revision

    def start(self) -> None:
        self.task = self.coordinator.hass.async_create_background_task(
            self._run(), "EW11 discovery evidence", eager_start=False,
        )

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        await self.async_save()

    async def async_save(self) -> None:
        async with self.save_lock:
            snapshot = self.guard.snapshot()
            revision = self.guard.evidence.revision
            if revision != self.saved_revision:
                serialized = snapshot.to_json()
                await self.store.async_save(serialized)
                if self.coordinator.hass.state is CoreState.stopping:
                    # HA owns the final-write listener; no admission during shutdown.
                    self.guard.verification_enabled = False
                    return
                if not await self.coordinator.hass.async_add_executor_job(
                    _saved_data_matches, self.store.path, serialized,
                ):
                    raise OSError("Discovery evidence write could not be verified")
                self.saved_revision = revision

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self.async_tick()
            except Exception:
                # HA background-task boundary: a failed tick must fail closed and retry.
                self.guard.verification_enabled = False
                _LOGGER.exception("EW11 discovery evidence update failed; admission paused")

    def _link_healthy(self) -> bool:
        return (
            self.coordinator.hass.state is not CoreState.stopping
            and self.coordinator._client.health_report()["state"] == "receiving"
            and self.coordinator.packet_quality_report()["state"] == "ok"
        )

    async def async_tick(self) -> None:
        async with self.operation_lock:
            await self._async_tick()

    async def async_review(self, endpoint: str, approve: bool) -> bool:
        async with self.operation_lock:
            # A periodic tick must not resume admission during a failed review save.
            self.guard.verification_enabled = False
            if not self.guard.review(endpoint, approve):
                return False
            await self.async_save()
            self._notify()
            return True

    async def _async_tick(self) -> None:
        self.guard.expire()
        self.guard.verification_enabled = False
        self._record_rx_error()
        if self._link_healthy():
            for observation in self.guard.probe_candidates():
                if self.coordinator._transaction_lock.locked():
                    break
                addr, sub_id = (int(part, 16) for part in observation.endpoint.split("/"))
                from .coordinator import _status_request_command
                request = self.coordinator.codec.build_f7(addr, sub_id, _status_request_command(addr), b"")
                self.guard.record(replace(observation, raw_hex=request.hex()), "probe_requested")
                result = replace(observation, raw_hex="")
                try:
                    async with asyncio.timeout(2):
                        matched = await self.coordinator.async_request_f7_state_until(
                            addr, sub_id, max_attempts=1, interval=0.5,
                        )
                    current = self.guard.pending.get(observation.endpoint)
                    success = (matched is not None and current is not None
                               and current.observation.keys == observation.keys
                               and current.observation.raw_hex.upper() == matched.raw.hex().upper())
                    if matched is not None:
                        result = replace(observation, raw_hex=matched.raw.hex())
                except (TimeoutError, OSError):
                    success = False
                self.guard.record_probe(result, success)
        await self.async_save()
        self.guard.verification_enabled = self._link_healthy()
        self._notify()

    def _record_rx_error(self) -> None:
        error = self.coordinator.packet_quality_report(include_packet_samples=True)["rx"]["last_error"]
        if not error:
            return
        signature = str(error.get("time")) + str(error.get("raw_hex"))
        if signature == self.last_error_signature:
            return
        self.guard.evidence.record(EvidenceEvent(
            time=self.guard.now(), endpoint="RX", action="rx_validation_failed",
            raw_hex=str(error.get("raw_hex", ""))[:1024],
            detail=f"{error.get('kind', '')}; received={error.get('received_checksum', '')}; "
                   f"expected={error.get('expected_checksum', '')}",
        ))
        self.last_error_signature = signature

    def _notify(self) -> None:
        rows = self.guard.report()
        existing = self.coordinator.registry.cleanup_candidate_report()["candidates"]
        verified = {key for event in self.guard.evidence.events
                    if event.action in {"admitted_by_user", "admitted_by_probe"} for key in event.keys}
        legacy = registered_review(self.coordinator.hass, self.entry_id, verified)
        if not rows and not existing and not legacy and not self.previous_summary:
            return
        links = device_review_links(self.coordinator.hass, self.entry_id)
        lines = [f"등록 검증 대기 {len(rows)}개 통신 지점 · 기존 기기 검토 {len(existing)}개", ""]
        lines += [f"- {r['endpoint']}: {', '.join(r['keys'])} — "
                  + ("수동 확인 필요" if r["action"] == "review_required" else "상태 조회 검증 중")
                  for r in rows[:20]]
        lines += [f"- {links.get(c['device_key'], c['device_key'] + ' · 기기 등록 정보 없음')}"
                  "\n  채널 구성 재확인 필요 · 삭제하지 않고 보존" for c in existing]
        if legacy:
            lines += ["", f"별도 실체 확인이 필요한 이름·영역 미지정 기기: {len(legacy)}개",
                      "이름·영역 미지정만으로 가짜 기기라고 판단하지 않습니다.", ""]
            for candidate in legacy:
                shortcut = next((links[key] for key in candidate['device_keys'] if key in links),
                                candidate['device_keys'][0] + ' · 연결 기기 확인 필요')
                lines.append(f"- {shortcut}")
        lines += ["", "무응답은 삭제 근거가 아닙니다. 기존 기기는 자동 삭제하지 않습니다.",
                  "진단 다운로드의 discovery_guard에서 근거를 확인할 수 있습니다.",
                  "실제 새 기기가 확인되면 review_discovery 동작으로 승인하거나 거부할 수 있습니다.",
                  f"[EW11 확인](/config/integrations/integration/{DOMAIN})"]
        summary = tuple(lines)
        if summary == self.previous_summary:
            return
        persistent_notification.async_create(
            self.coordinator.hass, "\n".join(lines), title="EW11 등록 검토",
            notification_id=self.notification_id,
        )
        self.previous_summary = summary
