from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ._integration_loader import load_integration_module


def fixture():
    wall = [datetime(2026, 10, 12, tzinfo=timezone.utc)]
    clock = [100.0]
    module = load_integration_module('device_vitality')
    monitor = module.DeviceVitalityMonitor(now=lambda: wall[0], clock=lambda: clock[0])
    device = SimpleNamespace(key='0E11_light_3', addr=0x0E, sub_id=0x11,
                             kind='light', channel=3, state={})
    def report():
        return monitor.report([device])['devices'][0]
    def frame(cmd, payload=b'\x00\x00\x00\x01'):
        return SimpleNamespace(addr=0x0E, sub_id=0x11, cmd=cmd, payload=payload)
    return monitor, report, frame, wall, clock


def test_request_ack_and_valid_state_are_distinct_evidence():
    monitor, report, frame, _, _ = fixture()
    monitor.observe(frame(0x01, b''))
    assert report()['status'] == 'unknown'
    monitor.observe(frame(0xC1))
    assert report()['command_ack_count'] == 1
    assert report()['state_response_count'] == 0
    assert report()['status'] == 'unknown'
    assert report()['observation_state'] == 'ack_only'
    monitor.observe(frame(0x81))
    assert report()['state_response_count'] == 1
    assert report()['status'] == 'healthy'


def test_invalid_state_does_not_refresh_valid_state_evidence():
    monitor, report, frame, _, clock = fixture()
    monitor.observe(frame(0x81))
    clock[0] += 301
    monitor.observe(frame(0x81, b''))
    assert report()['state_response_count'] == 1
    assert report()['invalid_response_count'] == 1
    assert report()['status'] == 'stale'


def test_unobserved_restored_target_does_not_become_fault_after_failed_queries():
    monitor, report, _, _, clock = fixture()
    for _ in range(4):
        monitor.record_probe(0x0E, 0x11, success=False)
        clock[0] += 30
    assert report()['status'] == 'unknown'
    assert report()['observation_state'] == 'unobserved'
    assert report()['probe_failure_count'] == 4


def test_old_success_and_wall_clock_corrections_do_not_keep_status_healthy():
    monitor, report, frame, wall, clock = fixture()
    monitor.observe(frame(0x81))
    monitor.record_probe(0x0E, 0x11, success=True)
    clock[0] += 360
    wall[0] -= timedelta(hours=1)
    assert report()['status'] == 'stale'
    assert report()['seconds_since_state_response'] == 360
    clock[0] += 1
    monitor.observe(frame(0x81))
    assert report()['status'] == 'healthy'


def test_recent_state_and_failed_channel_can_coexist():
    monitor, report, frame, _, _ = fixture()
    monitor.observe(frame(0x81))
    monitor.record_command_failure(0x0E, 0x11, reason='control_not_confirmed')
    assert report()['status'] == 'healthy'
    assert report()['last_failure_reason'] == 'control_not_confirmed'


def test_failed_probe_requires_repeated_evidence_and_new_state_clears_it():
    monitor, report, frame, _, clock = fixture()
    monitor.observe(frame(0x81))
    for _ in range(2):
        clock[0] += 30
        monitor.record_probe(0x0E, 0x11, success=False)
        assert report()['status'] != 'unresponsive'
    monitor.record_probe(0x0E, 0x11, success=False)
    assert report()['status'] == 'unresponsive'
    clock[0] += 1
    monitor.observe(frame(0x81))
    assert report()['status'] == 'healthy'


def test_previous_tcp_epoch_is_not_current_endpoint_health():
    from .ha_stubs import install_homeassistant_stubs
    install_homeassistant_stubs()
    module = load_integration_module('coordinator')
    discovery = load_integration_module('discovery')
    co = module.Ksx4506Coordinator(SimpleNamespace(), {
        'host': 'ew11.example.invalid', 'port': 8899, 'timeout': 0.1, 'retry': 0,
    })
    device = discovery.DeviceState(key='0E11_light_1', addr=14, sub_id=17,
        kind='light', channel=1, state={'status_sub_id': 17})
    co.registry.devices[device.key] = device
    frame = SimpleNamespace(addr=14, sub_id=17, cmd=0x81, payload=b'\0\1')
    co._client._mark_connected()
    co.device_vitality.observe(frame, connection_epoch=1)
    assert co.device_vitality_report()['healthy'] == 1
    co._client._mark_connected()
    report = co.device_vitality_report()
    assert report['healthy'] == 0 and report['unknown'] == 1
    assert report['devices'][0].get('state_current_connection') is False
    assert report['devices'][0].get('last_state_connection_epoch') == 1
    co.device_vitality.observe(frame, connection_epoch=2)
    assert co.device_vitality_report()['healthy'] == 1


def test_quiet_event_only_endpoint_never_becomes_unresponsive():
    module = load_integration_module('device_vitality')
    clock = [0.0]
    monitor = module.DeviceVitalityMonitor(clock=lambda: clock[0])
    device = SimpleNamespace(key='4002_common_entrance', addr=0x40, sub_id=2,
                             kind='common_entrance', channel=None, state={})
    monitor.observe(SimpleNamespace(addr=0x40, sub_id=2, cmd=0x10, payload=b'\0'))
    clock[0] += 86400
    report = monitor.report([device])['devices'][0]
    assert report['status'] == 'event_only' and report.get('state_response_count') == 0
