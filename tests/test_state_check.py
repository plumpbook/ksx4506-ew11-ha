import asyncio
from types import SimpleNamespace

import pytest

from ._integration_loader import load_integration_module


def fixture():
    mod = load_integration_module('state_check')
    clock = [100.0]
    health = {'running': True, 'connected': True, 'connect_successes': 1,
              'connection_epoch': 1, 'disconnect_count': 0,
              'last_tx_at': None, 'last_tx_status': None}
    sent = []
    vitality = load_integration_module('device_vitality').DeviceVitalityMonitor()
    response = SimpleNamespace(addr=0x0E, sub_id=0x11, cmd=0x81, payload=b'\0\0\0\1')
    async def query(addr, sub, cmd, payload, matcher, **kwargs):
        assert kwargs['max_attempts'] == 1 and kwargs['interval'] == 0.5 and kwargs['single_send'] is True
        assert kwargs['deadline'] >= asyncio.get_running_loop().time()
        assert cmd == 0x01 and payload == b''
        sent.append((addr, sub))
        health.update(last_tx_at=str(len(sent)), last_tx_status='sent')
        assert not matcher(SimpleNamespace(addr=addr, sub_id=sub + 1, cmd=0x81, payload=response.payload))
        assert not matcher(SimpleNamespace(addr=addr, sub_id=sub, cmd=0xC1, payload=response.payload))
        assert not matcher(SimpleNamespace(addr=addr, sub_id=sub, cmd=0x81, payload=b''))
        vitality.observe(response)
        return response if matcher(response) else None
    coordinator = SimpleNamespace(_client=SimpleNamespace(health_report=lambda: health.copy()),
        _transaction_lock=asyncio.Lock(), _known_state_request_targets=lambda: [(14, 17)],
        _async_send_f7_command_until_unlocked=query, _publish_registry_state=lambda: None,
        device_vitality=vitality)
    checker = mod.StateCheck(coordinator, targets=lambda: {(14, 17), (48, 1)}, clock=lambda: clock[0])
    checker.resume()
    return checker, coordinator, clock, health, sent


def test_format_does_not_confuse_device_sub_id_with_channel():
    mod = load_integration_module('state_check')
    assert mod.parse_endpoint('0E/11') == (14, 17)
    assert mod.parse_endpoint('0x0e/0x11') == (14, 17)
    for value in ('11-3', '0E/11/3', '0E/111', '*', ' 0E/11', '0E/00/1'):
        with pytest.raises(ValueError):
            mod.parse_endpoint(value)


def test_registered_single_status_query_and_monotonic_cooldown():
    async def scenario():
        checker, _, clock, _, sent = fixture()
        assert (await checker.check((14, 17)))['result'] == 'confirmed'
        assert (await checker.check((14, 17)))['result'] == 'cooldown'
        assert sent == [(14, 17)]
        clock[0] += 30
        assert (await checker.check((14, 17)))['result'] == 'confirmed'
        assert len(sent) == 2
        assert checker.report()['active'] is False
    asyncio.run(scenario())


def test_unregistered_unsupported_busy_disconnected_and_stopped_never_send():
    async def scenario():
        checker, co, _, health, sent = fixture()
        assert (await checker.check((14, 18)))['result'] == 'unregistered'
        assert (await checker.check((48, 1)))['result'] == 'unsupported'
        await co._transaction_lock.acquire()
        assert (await checker.check((14, 17)))['result'] == 'busy'
        co._transaction_lock.release()
        health['connected'] = False
        assert (await checker.check((14, 17)))['result'] == 'disconnected'
        await checker.stop()
        assert (await checker.check((14, 17)))['result'] == 'stopped'
        assert sent == []
    asyncio.run(scenario())


def test_repeated_taps_cancel_and_unload_have_no_late_or_duplicate_query():
    async def scenario():
        checker, co, _, _, sent = fixture()
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def blocked(*args, **kwargs):
            sent.append((14, 17))
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        co._async_send_f7_command_until_unlocked = blocked
        task = asyncio.create_task(checker.check((14, 17)))
        await entered.wait()
        assert checker.report()['result'] == 'checking'
        for _ in range(10):
            assert (await checker.check((14, 17)))['result'] == 'busy'
        await checker.stop()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set() and sent == [(14, 17)]
        assert checker.report()['result'] == 'stopped'
        assert not co._transaction_lock.locked()
    asyncio.run(scenario())


@pytest.mark.parametrize('sent', [False, True])
def test_timeout_separates_not_sent_from_endpoint_no_response(monkeypatch, sent):
    async def scenario():
        mod = load_integration_module('state_check')
        monkeypatch.setattr(mod, 'CHECK_TIMEOUT', 0.01)
        # The fixture reloads this module; patch the actual checker module too.
        checker, co, _, health, transmissions = fixture()
        monkeypatch.setattr(__import__('sys').modules[type(checker).__module__], 'CHECK_TIMEOUT', 0.01)
        async def blocked(*args, **kwargs):
            if sent:
                transmissions.append((14, 17))
                health.update(last_tx_at='new', last_tx_status='sent')
            await asyncio.Event().wait()
        co._async_send_f7_command_until_unlocked = blocked
        result = await checker.check((14, 17))
        assert result['result'] == ('no_response' if sent else 'not_sent')
        assert not co._transaction_lock.locked()
        assert checker.report()['active'] is False
        if not sent:
            assert co.device_vitality._endpoints.get((14, 17)) is None
        else:
            assert co.device_vitality._endpoints[(14, 17)].probe_failure_count == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('field', ['connect_successes', 'connection_epoch', 'disconnect_count'])
def test_connection_epoch_change_is_not_endpoint_failure(field):
    async def scenario():
        checker, co, _, health, sent = fixture()
        async def changed(*args, **kwargs):
            health.update(last_tx_at='new', last_tx_status='sent')
            health[field] += 1
            sent.append((14, 17))
            return None
        co._async_send_f7_command_until_unlocked = changed
        assert (await checker.check((14, 17)))['result'] == 'connection_changed'
        assert co.device_vitality._endpoints == {}
    asyncio.run(scenario())


def test_different_endpoint_still_respects_entry_cooldown():
    async def scenario():
        checker, co, clock, _, sent = fixture()
        checker._targets = lambda: {(14, 17), (14, 18)}
        co._known_state_request_targets = lambda: [(14, 17), (14, 18)]
        assert (await checker.check((14, 17)))['result'] == 'confirmed'
        result = await checker.check((14, 18))
        assert result['result'] == 'cooldown' and result['retry_after_seconds'] == 5
        assert sent == [(14, 17)]
        clock[0] += 5
        assert (await checker.check((14, 18)))['result'] == 'no_response'
        assert sent == [(14, 17), (14, 18)]
    asyncio.run(scenario())


def test_expired_scheduled_check_never_enqueues_a_request():
    async def scenario():
        checker, _, clock, _, sent = fixture()
        result = await checker._run((14, 17), clock[0], asyncio.get_running_loop().time() - 1)
        assert result['result'] == 'not_sent' and result['reason'] == 'deadline_expired'
        assert result['transmission_attempts'] == 0 and sent == []
    asyncio.run(scenario())
