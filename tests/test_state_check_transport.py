import asyncio
from types import SimpleNamespace

import pytest

from ._integration_loader import load_integration_module
from .ha_stubs import install_homeassistant_stubs


def fixture():
    install_homeassistant_stubs()
    module = load_integration_module('coordinator')
    discovery = load_integration_module('discovery')
    co = module.Ksx4506Coordinator(SimpleNamespace(), {
        'host': 'ew11.example.invalid', 'port': 8899, 'timeout': 3,
        'retry': 10, 'max_attempts': 20,
    })
    dev = discovery.DeviceState(key='0E11_light_3', addr=14, sub_id=17, kind='light',
        channel=3, state={'status_sub_id': 17, 'control_sub_id': 17, 'control_channel': 3})
    co.registry.devices[dev.key] = dev
    co.state_check._targets = lambda: {(14, 17)}
    co.state_check.resume()
    co._client._running = True
    co._client._mark_connected()
    return co


def test_one_actual_write_even_with_ten_transport_retries_configured():
    async def scenario():
        co = fixture()
        writes = []
        class Writer:
            def write(self, packet):
                frame = co.codec.feed(packet)[0]
                assert (frame.addr, frame.sub_id, frame.cmd, frame.payload) == (14, 17, 1, b'')
                writes.append(packet)
            async def drain(self):
                raise OSError('synthetic write completion failure')
            def close(self):
                pass
            async def wait_closed(self):
                pass
        co._client._writer = Writer()
        co._client._worker_task = asyncio.create_task(co._client._command_worker())
        try:
            result = await co.state_check.check((14, 17))
            assert result['result'] == 'transport_unconfirmed'
            assert result['transmission_attempts'] == 1 and len(writes) == 1
            assert co._client.health_report()['response_failures_since_rx'] == 0
            assert co.device_vitality._endpoints == {}
        finally:
            await co.state_check.stop()
            await co._client.stop()
    asyncio.run(scenario())


def test_timeout_before_worker_start_cannot_send_after_completion(monkeypatch):
    async def scenario():
        co = fixture()
        state_module = __import__('sys').modules[type(co.state_check).__module__]
        monkeypatch.setattr(state_module, 'CHECK_TIMEOUT', 0.01)
        writes = []
        class Writer:
            def write(self, packet):
                writes.append(packet)
            async def drain(self):
                pass
            def close(self):
                pass
            async def wait_closed(self):
                pass
        co._client._writer = Writer()
        try:
            result = await co.state_check.check((14, 17))
            assert result['result'] == 'not_sent' and result['transmission_attempts'] == 0
            command = co._client._cmd_queue._queue[0]
            assert command.deadline <= asyncio.get_running_loop().time()
            assert not co._frame_waiters and not co._transaction_lock.locked()
            co._client._worker_task = asyncio.create_task(co._client._command_worker())
            await asyncio.wait_for(co._client._cmd_queue.join(), 1)
            assert not writes and co.device_vitality._endpoints == {}
        finally:
            await co.state_check.stop()
            await co._client.stop()
    asyncio.run(scenario())


def test_cancel_during_write_completion_never_retries_or_leaves_waiters(monkeypatch):
    async def scenario():
        co = fixture()
        state_module = __import__('sys').modules[type(co.state_check).__module__]
        monkeypatch.setattr(state_module, 'CHECK_TIMEOUT', 0.01)
        writes, entered, release = [], asyncio.Event(), asyncio.Event()
        class Writer:
            def write(self, packet):
                writes.append(packet)
            async def drain(self):
                entered.set()
                await release.wait()
            def close(self):
                pass
            async def wait_closed(self):
                pass
        co._client._writer = Writer()
        co._client._worker_task = asyncio.create_task(co._client._command_worker())
        try:
            task = asyncio.create_task(co.state_check.check((14, 17)))
            await entered.wait()
            result = await task
            assert result['result'] == 'transport_unconfirmed'
            assert result['transmission_attempts'] == 1
            release.set()
            await asyncio.wait_for(co._client._cmd_queue.join(), 1)
            assert len(writes) == 1
            assert not co._frame_waiters and not co._transaction_lock.locked()
            assert co.state_check.report()['result'] == 'transport_unconfirmed'
        finally:
            await co.state_check.stop()
            await co._client.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize('path', ['periodic', 'manual'])
@pytest.mark.parametrize('closure', ['counted', 'uncounted', 'restored', 'reconnected'])
def test_tcp_close_after_completed_send_is_not_endpoint_no_response(path, closure):
    async def scenario():
        co = fixture()
        co.device_vitality.observe(SimpleNamespace(addr=14, sub_id=17, cmd=0x81,
            payload=b'\0\1'), connection_epoch=1)
        writes = []

        class Writer:
            def write(self, packet):
                frame = co.codec.feed(packet)[0]
                assert (frame.addr, frame.sub_id, frame.cmd, frame.payload) == (14, 17, 1, b'')
                writes.append(packet)

            async def drain(self):
                pass

            def close(self):
                pass

            async def wait_closed(self):
                pass

        co._client._worker_task = asyncio.create_task(co._client._command_worker())
        try:
            for attempt in range(3 if path == 'periodic' else 1):
                co._client._writer = Writer()
                if not co._client.health_report()['connected']:
                    co._client._mark_connected()
                before = co._client.health_report()
                task = asyncio.create_task(
                    co.async_probe_known_device_states(delay=0, interval=0.05, max_attempts=1)
                    if path == 'periodic' else co.state_check.check((14, 17)))
                # Queue completion proves drain and the send result finished before TCP closes.
                while len(writes) == attempt:
                    await asyncio.sleep(0)
                await co._client._cmd_queue.join()
                assert co._client.health_report()['last_tx_status'] == 'sent'
                assert not task.done()
                await co._client._close(reason='synthetic EOF', count_disconnect=closure != 'uncounted')
                if closure == 'restored':
                    co._client._connected = True
                    co._client._connected_event.set()
                elif closure == 'reconnected':
                    co._client._mark_connected()
                after = co._client.health_report()
                if closure != 'reconnected':
                    assert after['connect_successes'] == before['connect_successes']
                    assert after['connection_epoch'] == before['connection_epoch']
                result = await task
                outcome = (co.state_query_results[(14, 17)] if path == 'periodic' else result)
                assert outcome['result'] == 'connection_changed'
                assert co.device_vitality._endpoints[(14, 17)].probe_failure_count == 0
                assert co.device_vitality_report()['devices'][0]['status'] != 'unresponsive'
                assert co._client.health_report()['response_failures_since_rx'] == 0
            assert len(writes) == (3 if path == 'periodic' else 1)
            assert not co._frame_waiters and not co._transaction_lock.locked()
        finally:
            await co.state_check.stop()
            await co._client.stop()

    asyncio.run(scenario())
