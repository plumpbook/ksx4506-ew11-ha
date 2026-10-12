import asyncio
from types import SimpleNamespace

import pytest

from ._integration_loader import load_integration_module
from .ha_stubs import install_homeassistant_stubs


@pytest.mark.parametrize('sent', [False, True])
def test_periodic_failures_require_confirmed_transmission(sent):
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
        for _ in range(3):
            await co.async_probe_known_device_states(delay=0, interval=0, max_attempts=1)
        report = co.device_vitality_report()['devices'][0]
        assert len(calls) == 3
        assert report['status'] == ('unresponsive' if sent else 'healthy')
        assert report.get('probe_failure_count') == (3 if sent else 0)
        assert co.state_query_results[(14, 17)]['result'] == ('no_response' if sent else 'not_sent')
        assert co._client.health_report()['response_failures_since_rx'] == (3 if sent else 0)
    asyncio.run(scenario())
