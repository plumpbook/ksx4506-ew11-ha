"""Native HA service/registry/diagnostic flow against a local fake bus only."""
import asyncio
from pathlib import Path
import socket
import tempfile
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er, service
from homeassistant import loader

from custom_components.ksx4506_ew11.const import DOMAIN
from custom_components.ksx4506_ew11.coordinator import Ksx4506Coordinator
from custom_components.ksx4506_ew11.diagnostic_sensors import KsxDeviceVitalitySensor
from custom_components.ksx4506_ew11.discovery import DeviceState
from custom_components.ksx4506_ew11.discovery_setup import async_prepare_discovery, async_stop_discovery
from custom_components.ksx4506_ew11.registry_bootstrap import async_restore_registry_devices_from_ha
from custom_components.ksx4506_ew11.protocol import Ksx4506Codec
from custom_components.ksx4506_ew11.guarded_registry import GuardedRegistry


async def main():
    mode = ['ack']
    packets = []
    async def bridge(reader, writer):
        codec = Ksx4506Codec()
        try:
            while data := await reader.read(1024):
                for frame in codec.feed(data):
                    packets.append((frame.addr, frame.sub_id, frame.cmd, frame.payload))
                    assert frame.cmd == 0x01 and frame.payload == b''
                    if mode[0] != 'silent':
                        cmd = 0xC1 if mode[0] == 'ack' else 0x81
                        writer.write(codec.build_f7(14, 17, cmd, b'\0\1\0\1'))
                        await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(bridge, 'localhost', 0, family=socket.AF_INET)
    host, port = server.sockets[0].getsockname()[:2]
    with tempfile.TemporaryDirectory(prefix='ew11-state-check-') as directory:
        custom = Path(directory) / 'custom_components'
        custom.mkdir()
        (custom / DOMAIN).symlink_to(Path(__file__).resolve().parents[1] / 'custom_components' / DOMAIN)
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        hass.config_entries = ConfigEntries(hass, {})
        entry = ConfigEntry(domain=DOMAIN, title='Synthetic bridge', data={'host': host}, options={},
            source='user', version=1, minor_version=1, unique_id='state-check-runtime',
            discovery_keys=MappingProxyType({}), subentries_data=None)
        hass.config_entries._entries[entry.entry_id] = entry
        await dr.async_load(hass)
        await er.async_load(hass)
        devices, entities = dr.async_get(hass), er.async_get(hass)
        members = []
        for channel in (1, 2, 3):
            key = f'0E11_light_{channel}'
            device = devices.async_get_or_create(config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, key)}, name=f'Synthetic channel {channel}')
            entity = entities.async_get_or_create('light', DOMAIN, f'ksx4506_{key}',
                config_entry=entry, device_id=device.id)
            members.append(entity.entity_id)
        co = Ksx4506Coordinator(hass, {'host': host, 'port': port, 'timeout': 0.1,
                                     'retry': 2, 'max_attempts': 10}, entry=entry)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = co
        await async_prepare_discovery(hass, entry, co)
        await async_restore_registry_devices_from_ha(hass, entry, co.registry)
        clock = [1000.0]
        co.state_check._clock = lambda: clock[0]
        co.state_check.resume()
        sensor = KsxDeviceVitalitySensor(co, entry)
        initial_registry = set(entities.entities), set(devices.devices)
        try:
            # The native HA action form consumes these exact service descriptors.
            descriptions = await service.async_get_all_descriptions(hass)
            action = descriptions[DOMAIN]['check_state']
            assert action['name'] == '상태 다시 확인'
            assert action['fields']['entry_id']['selector']['config_entry']['integration'] == DOMAIN
            assert '채널 번호가 아닙니다' in action['fields']['endpoint']['description']
            assert hass.services.has_service(DOMAIN, 'review_discovery')
            await co._client.start()
            await asyncio.wait_for(co._client._connected_event.wait(), 2)
            async def call(endpoint='0E/11', entry_id=None):
                return await hass.services.async_call(DOMAIN, 'check_state',
                    {'entry_id': entry_id or entry.entry_id, 'endpoint': endpoint},
                    blocking=True, return_response=True)
            for _ in range(3):
                try:
                    await call()
                    raise AssertionError('ACK must not confirm a status query')
                except ServiceValidationError:
                    pass
                clock[0] += 30
            report = co.device_vitality_report()['devices'][0]
            assert report.get('state_response_count') == 0 and report.get('command_ack_count') == 3
            assert report['status'] == 'unknown'
            assert len(packets) == 3
            mode[0] = 'state'
            response = await call('0x0E/0x11')
            assert response is not None
            assert response['result'] == 'confirmed' and response['transmission_attempts'] == 1
            assert len(packets) == 4
            assert sensor.extra_state_attributes['state_check']['result'] == 'confirmed'
            assert sensor.extra_state_attributes['endpoint_summary'][0]['last_state_response_at']
            try:
                await call()
                raise AssertionError('Cooldown must reject the second tap')
            except ServiceValidationError:
                pass
            assert len(packets) == 4
            clock[0] += 30
            for target in ('0E/12', '11-3'):
                try:
                    await call(target)
                    raise AssertionError('Unregistered or invalid target must be blocked')
                except ServiceValidationError:
                    pass
            for entity_id in members:
                entities.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
            try:
                await call()
                raise AssertionError('Disabled endpoint must be blocked')
            except ServiceValidationError:
                pass
            assert len(packets) == 4
            for entity_id in members:
                entities.async_update_entity(entity_id, disabled_by=None)
            # A registered meter is visible, but this polling route is unsupported.
            meter = devices.async_get_or_create(config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, '3001_sensor')}, name='Synthetic passive meter')
            entities.async_get_or_create('sensor', DOMAIN, 'ksx4506_3001_sensor',
                config_entry=entry, device_id=meter.id)
            co.registry.devices['3001_sensor'] = DeviceState(
                key='3001_sensor', addr=0x30, sub_id=1, kind='sensor', state={})
            try:
                await call('30/01')
                raise AssertionError('Unsupported status query must be blocked')
            except ServiceValidationError:
                pass
            assert len(packets) == 4
            assert initial_registry[0] <= set(entities.entities)
            assert initial_registry[1] <= set(devices.devices)
            assert isinstance(co.registry, GuardedRegistry)
            assert not co.registry.guard.pending
            assert not any(event.action.startswith('admitted') for event in co.registry.guard.evidence.events)
            # Cancellation while waiting must remove waiters and stop all owned work.
            mode[0] = 'silent'
            task = asyncio.create_task(call())
            while len(packets) < 5:
                await asyncio.sleep(0)
            await co.async_stop()
            try:
                await task
                raise AssertionError('Unloading must cancel the check')
            except asyncio.CancelledError:
                pass
            assert co.state_check.report()['result'] == 'stopped'
            assert not co._frame_waiters and co._client._cmd_queue.empty()
            assert co._client._worker_task is None and not co._transaction_lock.locked()
            print('native HA state-check flow: action descriptors, ACK/status distinction, one transmission, '
                  'cooldown, invalid/unregistered/disabled/unsupported guards, approval preservation, '
                  'cancel/unload cleanup, zero output commands: passed')
        finally:
            await co.async_stop()
            await async_stop_discovery(hass, entry)
            await hass.async_stop()
    server.close()
    await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
