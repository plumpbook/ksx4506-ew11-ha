import asyncio
from types import SimpleNamespace

import pytest

from ._integration_loader import load_integration_module
from .ha_stubs import install_homeassistant_stubs


@pytest.mark.parametrize('sent', [False, True])
def test_silent_device_checks_require_confirmed_transmission(sent):
    async def scenario():
        install_homeassistant_stubs()
        module = load_integration_module('coordinator')
        discovery = load_integration_module('discovery')
        co = module.Ksx4506Coordinator(SimpleNamespace(), {
            'host': 'ew11.example.invalid', 'port': 8899, 'timeout': 0.1, 'retry': 0,
        })
        device = discovery.DeviceState(key='0E11_light_1', addr=14, sub_id=17,
            kind='light', channel=1, state={'status_sub_id': 17})
        co.registry.devices[device.key] = device
        co._client._mark_connected()
        co.device_vitality.observe(SimpleNamespace(addr=14, sub_id=17, cmd=0x81,
            payload=b'\0\1'), connection_epoch=1)
        calls = []
        async def send(packet, **kwargs):
            calls.append(packet)
            co._client._record_tx_result(status='sent' if sent else 'queue_full',
                                        attempts=1 if sent else 0, error=None)
            return sent
        co._client.send_with_retry = send
        policy_module = load_integration_module('alert_policy')
        policy = policy_module.AlertPolicy(started=0, known={'0E/11': 0})
        endpoint = policy_module.Endpoint('0E/11', (device.key,), 3, 0, True)
        for now in (180, 210, 240):
            assert policy.scan((endpoint,), now=now).probes == ('0E/11',)
            matched = await co.async_request_f7_state_until(14, 17, interval=0, max_attempts=1)
            outcome = co.state_query_results[(14, 17)]['result']
            proved = matched is not None or outcome == 'no_response'
            if proved:
                co.device_vitality.record_probe(14, 17, success=matched is not None)
            policy.record_probe('0E/11', success=matched is not None if proved else None,
                                now=now)
        report = co.device_vitality_report()['devices'][0]
        assert len(calls) == 3
        assert report['status'] == ('unresponsive' if sent else 'healthy')
        assert report.get('probe_failure_count') == (3 if sent else 0)
        assert co.state_query_results[(14, 17)]['result'] == ('no_response' if sent else 'not_sent')
        assert co._client.health_report()['response_failures_since_rx'] == (3 if sent else 0)
        assert len(policy.scan((endpoint,), now=241).alerts) == (1 if sent else 0)
    asyncio.run(scenario())
