from datetime import datetime, timedelta, timezone
import asyncio
from types import SimpleNamespace

from ._integration_loader import load_integration_module


NOW = datetime(2026, 9, 3, 0, 0, tzinfo=timezone.utc)


def _frame(*, addr: int, sub_id: int, cmd: int):
    return SimpleNamespace(addr=addr, sub_id=sub_id, cmd=cmd)


def _device(*, key: str, addr: int, sub_id: int, status_sub_id: int | None = None):
    state = {} if status_sub_id is None else {"status_sub_id": status_sub_id}
    return SimpleNamespace(
        key=key,
        addr=addr,
        sub_id=sub_id,
        kind="switch",
        channel=None,
        state=state,
    )


def test_requests_do_not_count_as_device_vitality():
    module = load_integration_module("device_vitality")
    monitor = module.DeviceVitalityMonitor(now=lambda: NOW)
    device = _device(key="3911_switch", addr=0x39, sub_id=0x11)

    monitor.observe(_frame(addr=0x39, sub_id=0x11, cmd=0x01))
    report = monitor.report([device])

    assert report["state"] == "unknown"
    assert report["devices"][0]["request_count"] == 1
    assert report["devices"][0]["response_count"] == 0
    assert report["devices"][0]["last_response_at"] is None


def test_response_packets_mark_protocol_endpoint_alive():
    module = load_integration_module("device_vitality")
    current = NOW
    monitor = module.DeviceVitalityMonitor(now=lambda: current)
    devices = [
        _device(key="391F_switch_1", addr=0x39, sub_id=0x1F, status_sub_id=0x1F),
        _device(key="391F_switch_2", addr=0x39, sub_id=0x1F, status_sub_id=0x1F),
    ]

    monitor.observe(_frame(addr=0x39, sub_id=0x1F, cmd=0x81))
    report = monitor.report(devices)

    assert report["state"] == "healthy"
    assert report["healthy"] == 1
    assert report["devices"][0]["status"] == "healthy"
    assert report["devices"][0]["device_keys"] == [
        "391F_switch_1",
        "391F_switch_2",
    ]
    assert report["devices"][0]["response_count"] == 1


def test_failed_probe_overrides_older_passive_response():
    module = load_integration_module("device_vitality")
    current = NOW
    monitor = module.DeviceVitalityMonitor(now=lambda: current)
    device = _device(key="3911_switch", addr=0x39, sub_id=0x11)

    monitor.observe(_frame(addr=0x39, sub_id=0x11, cmd=0x81))
    current += timedelta(seconds=10)
    monitor.record_probe(0x39, 0x11, success=False)
    report = monitor.report([device])

    assert report["state"] == "unresponsive"
    assert report["unresponsive"] == 1
    assert report["devices"][0]["status"] == "unresponsive"
    assert report["devices"][0]["last_probe_success"] is False


def test_later_response_recovers_failed_probe():
    module = load_integration_module("device_vitality")
    current = NOW
    monitor = module.DeviceVitalityMonitor(now=lambda: current)
    device = _device(key="3911_switch", addr=0x39, sub_id=0x11)

    monitor.record_probe(0x39, 0x11, success=False)
    current += timedelta(seconds=1)
    monitor.observe(_frame(addr=0x39, sub_id=0x11, cmd=0x81))
    report = monitor.report([device])

    assert report["state"] == "healthy"
    assert report["devices"][0]["status"] == "healthy"


def test_old_response_becomes_stale_without_a_new_probe():
    module = load_integration_module("device_vitality")
    current = NOW
    monitor = module.DeviceVitalityMonitor(
        now=lambda: current,
        stale_after=timedelta(minutes=5),
    )
    device = _device(key="3911_switch", addr=0x39, sub_id=0x11)

    monitor.observe(_frame(addr=0x39, sub_id=0x11, cmd=0x81))
    current += timedelta(minutes=6)
    report = monitor.report([device])

    assert report["state"] == "stale"
    assert report["stale"] == 1
    assert report["devices"][0]["seconds_since_response"] == 360.0


def test_known_device_probe_records_each_traversal_result():
    coordinator_module = load_integration_module("coordinator")
    probe_results = []

    async def request(addr, sub_id, *, interval, max_attempts):
        assert interval == 0
        assert max_attempts == 1
        return object() if sub_id == 0x11 else None

    fake = SimpleNamespace(
        _known_state_request_targets=lambda: [(0x39, 0x11), (0x39, 0x12)],
        async_request_f7_state_until=request,
        device_vitality=SimpleNamespace(
            record_probe=lambda addr, sub_id, *, success: probe_results.append(
                (addr, sub_id, success)
            )
        ),
    )

    asyncio.run(
        coordinator_module.Ksx4506Coordinator.async_probe_known_device_states(
            fake,
            delay=0,
            interval=0,
            max_attempts=1,
        )
    )

    assert probe_results == [(0x39, 0x11, True), (0x39, 0x12, False)]
