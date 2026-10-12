"""Explicit, bounded status checks; no output commands or discovery admission."""
from __future__ import annotations

import asyncio  # noqa: ANYIO_OK - HA owns service and unload tasks
from collections.abc import Callable
from datetime import datetime, timezone
import re
import time
from typing import Any, TYPE_CHECKING

from .const import DOMAIN
from .ew11_health import state_query_connection_changed
from .response_validation import valid_response_payload

if TYPE_CHECKING:
    from .coordinator import Ksx4506Coordinator

CHECK_TIMEOUT = 2.0
ENDPOINT_COOLDOWN = 30.0
ENTRY_COOLDOWN = 5.0
_ENDPOINT = re.compile(r'^(?:0x)?([0-9a-f]{2})/(?:0x)?([0-9a-f]{2})$', re.IGNORECASE)
_SUMMARIES = {
    'idle': '등록된 주소를 선택해 상태를 다시 확인하세요',
    'checking': '해당 주소의 상태 응답 확인 중',
    'confirmed': '유효 상태 응답 확인 · 실제 출력 보증 아님',
    'no_response': '상태 요청 송신 후 유효 응답 미확인 · 고장 확정 아님',
    'not_sent': '상태 요청을 송신하지 못함 · 장치 무응답 판정 아님',
    'transport_unconfirmed': '전송 완료를 확인하지 못함 · 장치 무응답 판정 아님',
    'busy': '제어 또는 다른 확인 처리 중 · 잠시 후 다시 확인하세요',
    'cooldown': '재조회 간격 제한 · 잠시 후 다시 확인하세요',
    'unregistered': '이 통합의 활성 등록 주소가 아닙니다',
    'unsupported': '이 주소의 상태 조회를 지원하지 않습니다',
    'stopped': '통합이 중지되어 상태를 확인하지 않았습니다',
    'disconnected': 'TCP 연결이 없어 상태 요청을 보내지 않았습니다',
    'cancelled': '상태 확인 취소 · 장치 무응답 판정 아님',
    'connection_changed': '확인 중 TCP 연결 종료 또는 변경 · 장치 무응답 판정 아님',
    'error': '상태 확인 처리 오류 · 장치 무응답 판정 아님',
}


def parse_endpoint(value: str) -> tuple[int, int]:
    match = _ENDPOINT.fullmatch(value)
    if match is None:
        raise ValueError('주소는 device ID/sub ID 형식입니다 (예: 0E/11). 채널 번호가 아닙니다.')
    return int(match[1], 16), int(match[2], 16)


def eligible_targets(coordinator: Ksx4506Coordinator) -> set[tuple[int, int]]:
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    entry = coordinator.config_entry
    if entry is None:
        return set()
    entities = er.async_entries_for_config_entry(er.async_get(coordinator.hass), entry.entry_id)
    devices = dr.async_get(coordinator.hass)
    active = [entity for entity in entities if entity.disabled_by is None
              and entity.device_id is not None
              and (device := devices.async_get(entity.device_id)) is not None
              and device.disabled_by is None]
    return {
        (device.addr, int(device.state.get('status_sub_id', device.sub_id)))
        for device in coordinator.registry.devices.values()
        if any(entity.unique_id == f'ksx4506_{device.key}'
               or entity.unique_id.startswith(f'ksx4506_{device.key}_') for entity in active)
    }


class StateCheck:
    def __init__(self, coordinator: Ksx4506Coordinator, *,
                 targets: Callable[[], set[tuple[int, int]]] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.coordinator = coordinator
        self._targets = targets or (lambda: eligible_targets(coordinator))
        self._clock = clock
        self._accepting = False
        self._task: asyncio.Task[dict[str, Any]] | None = None
        self._accepted_at: dict[tuple[int, int], float] = {}
        self._entry_accepted_at: float | None = None
        self._last: dict[str, Any] = {'result': 'idle', 'summary': _SUMMARIES['idle']}

    def resume(self) -> None:
        self._accepting = True
        if self._last.get('result') == 'stopped':
            self._last = {'result': 'idle', 'summary': _SUMMARIES['idle']}

    def report(self) -> dict[str, Any]:
        return {**self._last, 'active': self._task is not None, 'accepting': self._accepting,
                'timeout_seconds': CHECK_TIMEOUT, 'max_transmissions': 1,
                'endpoint_cooldown_seconds': ENDPOINT_COOLDOWN,
                'entry_cooldown_seconds': ENTRY_COOLDOWN}

    def _result(self, result: str, endpoint: tuple[int, int], **extra: Any) -> dict[str, Any]:
        return {'result': result, 'summary': _SUMMARIES[result],
                'endpoint': f'{endpoint[0]:02X}/{endpoint[1]:02X}',
                'updated_at': datetime.now(timezone.utc).isoformat(), **extra}

    def _publish(self, result: dict[str, Any]) -> dict[str, Any]:
        self._last = result
        self.coordinator._publish_registry_state()
        return result

    def _completed(self, endpoint: tuple[int, int], result: dict[str, Any]) -> dict[str, Any]:
        outcomes = getattr(self.coordinator, 'state_query_results', None)
        if outcomes is not None:
            outcomes[endpoint] = {**result, 'source': 'manual'}
        return self._publish(result)

    async def check(self, endpoint: tuple[int, int]) -> dict[str, Any]:
        if not self._accepting:
            return self._publish(self._result('stopped', endpoint))
        if endpoint not in self._targets():
            return self._publish(self._result('unregistered', endpoint))
        if endpoint not in self.coordinator._known_state_request_targets():
            return self._publish(self._result('unsupported', endpoint))
        if self._task is not None:
            return self._result('busy', endpoint)
        if self.coordinator._transaction_lock.locked():
            return self._publish(self._result('busy', endpoint))
        health = self.coordinator._client.health_report()
        if not health.get('running'):
            return self._publish(self._result('stopped', endpoint))
        if not health.get('connected'):
            return self._publish(self._result('disconnected', endpoint))
        now = self._clock()
        remaining = max(
            ENDPOINT_COOLDOWN - (now - self._accepted_at.get(endpoint, float('-inf'))),
            ENTRY_COOLDOWN - (now - self._entry_accepted_at)
            if self._entry_accepted_at is not None else 0,
        )
        if remaining > 0:
            return self._publish(self._result('cooldown', endpoint,
                                             retry_after_seconds=round(remaining, 1)))
        self._accepted_at[endpoint] = self._entry_accepted_at = now
        deadline = asyncio.get_running_loop().time() + CHECK_TIMEOUT
        task = asyncio.create_task(self._run(endpoint, now, deadline))
        self._task = task
        self._publish(self._result('checking', endpoint))
        try:
            return await task
        finally:
            if self._task is task:
                self._task = None
                self.coordinator._publish_registry_state()

    async def _run(self, endpoint: tuple[int, int], started: float, deadline: float) -> dict[str, Any]:
        from .coordinator import _status_request_command, _status_response_command

        addr, sub_id = endpoint
        before = self.coordinator._client.health_report()
        try:
            async with asyncio.timeout_at(deadline):
                # Recheck after task scheduling; never wait behind user control.
                if not self._accepting:
                    return self._publish(self._result('stopped', endpoint))
                if self.coordinator._transaction_lock.locked():
                    return self._publish(self._result('busy', endpoint))
                if endpoint not in self._targets():
                    return self._publish(self._result('unregistered', endpoint))
                if asyncio.get_running_loop().time() >= deadline:
                    return self._completed(endpoint, self._result('not_sent', endpoint,
                        transmission_attempts=0, reason='deadline_expired'))
                async with self.coordinator._transaction_lock:
                    matched = await self.coordinator._async_send_f7_command_until_unlocked(
                        addr, sub_id, _status_request_command(addr), b'',
                        lambda frame: frame.addr == addr and frame.sub_id == sub_id
                        and frame.cmd == _status_response_command(addr)
                        and valid_response_payload(frame.addr, frame.cmd, frame.payload),
                        max_attempts=1, interval=0.5, single_send=True, deadline=deadline,
                    )
        except TimeoutError:
            matched = None
        except OSError:
            matched = None
        except asyncio.CancelledError:
            self._completed(endpoint, self._result('cancelled' if self._accepting else 'stopped', endpoint))
            raise
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK - retain neutral operation outcome
            return self._completed(endpoint, self._result('error', endpoint, error_type=type(exc).__name__))
        after = self.coordinator._client.health_report()
        transmissions = max(0, int(after.get('tx_write_attempts', 0))
                            - int(before.get('tx_write_attempts', 0)))
        sent = (after.get('last_tx_at') != before.get('last_tx_at')
                and after.get('last_tx_status') == 'sent')
        connection_changed = state_query_connection_changed(before, after)
        result = ('connection_changed' if connection_changed and (sent or matched is not None)
                  else 'confirmed' if matched is not None
                  else 'no_response' if sent else 'transport_unconfirmed' if transmissions else 'not_sent')
        if result in {'confirmed', 'no_response'}:
            self.coordinator.device_vitality.record_probe(addr, sub_id, success=matched is not None)
        return self._completed(endpoint, self._result(result, endpoint,
            elapsed_seconds=round(self._clock() - started, 3),
            connection_epoch=after.get('connection_epoch', after.get('connect_successes')),
            connected=after.get('connected'),
            disconnect_count=after.get('disconnect_count'),
            transmission_attempts=transmissions,
            transport_status=after.get('last_tx_status') if sent or not matched else None))

    async def stop(self) -> None:
        self._accepting = False
        task = self._task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def register_state_check_service(hass) -> None:
    import voluptuous as vol
    from homeassistant.core import ServiceCall, SupportsResponse
    from homeassistant.exceptions import ServiceValidationError

    if hass.services.has_service(DOMAIN, 'check_state'):
        return

    async def check(call: ServiceCall) -> dict[str, Any]:
        coordinator = hass.data.get(DOMAIN, {}).get(call.data['entry_id'])
        if coordinator is None:
            raise ServiceValidationError('실행 중인 EW11 통합을 선택하세요.')
        try:
            endpoint = parse_endpoint(call.data['endpoint'])
        except ValueError as exc:
            raise ServiceValidationError(str(exc)) from exc
        result = await coordinator.state_check.check(endpoint)
        if result['result'] != 'confirmed':
            detail = (f" · {result['retry_after_seconds']:.0f}초 후 다시 확인하세요"
                      if result['result'] == 'cooldown' else '')
            raise ServiceValidationError(result['summary'] + detail)
        return result

    hass.services.async_register(DOMAIN, 'check_state', check,
        schema=vol.Schema({vol.Required('entry_id'): str, vol.Required('endpoint'): str}),
        supports_response=SupportsResponse.OPTIONAL)
