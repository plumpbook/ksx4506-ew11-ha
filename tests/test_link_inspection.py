import asyncio  # noqa: ANYIO_OK - isolated fake transport
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ._integration_loader import load_integration_module


def _health(**changes):
    return {"running": True, "connected": True, "connect_attempts": 1,
            "seconds_since_valid_rx": None, "transport_failures_since_rx": 0,
            "seconds_since_transport_fault": None,
            "connect_attempts_since_transport_fault": 0, **changes}


def _policy():
    return load_integration_module("ew11_health").LinkInspectionPolicy(started=0)


@pytest.mark.parametrize("age", [None, 20, 180, 86400])
def test_quiet_or_low_traffic_does_not_need_inspection(age):
    report = _policy().evaluate(_health(seconds_since_valid_rx=age), now=86400, failed_endpoints=0)
    assert not report["inspection_needed"]
    assert report["manual_restart_consideration"] is None


@pytest.mark.parametrize("failed_endpoints", [0, 1])
def test_noise_or_one_endpoint_never_becomes_shared_link_failure(failed_endpoints):
    policy = _policy()
    health = _health(rx_fault_evidence="unvalidated_bytes", response_failures_since_rx=100,
                     consecutive_connection_failures=100, connect_attempts=100)
    for now in (180, 360, 10000):
        assert not policy.evaluate(health, now=now, failed_endpoints=failed_endpoints)["inspection_needed"]


@pytest.mark.parametrize("changes,now", [
    ({}, 179),
    ({"transport_failures_since_rx": 2}, 180),
    ({"connect_attempts_since_transport_fault": 1}, 180),
    ({"seconds_since_transport_fault": 179}, 180),
    ({"running": False}, 180),
    ({"seconds_since_valid_rx": 0}, 180),
])
def test_transport_alert_needs_grace_duration_retries_and_no_recent_valid_rx(changes, now):
    health = _health(connected=False, transport_failures_since_rx=3,
                     seconds_since_transport_fault=180, connect_attempts_since_transport_fault=2)
    health.update(changes)
    assert not _policy().evaluate(health, now=now, failed_endpoints=0)["inspection_needed"]


def test_sustained_transport_failure_is_inspection_not_a_reboot_verdict():
    health = _health(connected=False, transport_failures_since_rx=3,
                     seconds_since_transport_fault=180, connect_attempts_since_transport_fault=2)
    report = _policy().evaluate(health, now=180, failed_endpoints=0)
    assert report["inspection_needed"]
    assert report["inspection_reason"] == "repeated_transport_failure"
    assert "EW11·네트워크 점검 필요" in report["inspection_summary"]
    assert "원인은 확정되지 않았습니다" in report["manual_restart_consideration"]


def test_two_confirmed_endpoints_need_sustained_failure_after_reconnect():
    policy = _policy()
    health = _health(connect_attempts=1)
    assert not policy.evaluate(health, now=180, failed_endpoints=2)["inspection_needed"]
    # Repeated probes alone are not a failed recovery attempt.
    assert not policy.evaluate(health, now=360, failed_endpoints=2)["inspection_needed"]
    health["connect_attempts"] = 2
    assert policy.evaluate(health, now=360, failed_endpoints=2)["inspection_needed"]
    # One remaining downstream failure stays an individual problem.
    assert not policy.evaluate(health, now=361, failed_endpoints=1)["inspection_needed"]
    assert not policy.evaluate(health, now=362, failed_endpoints=2)["inspection_needed"]
    health["seconds_since_valid_rx"] = 0
    assert not policy.evaluate(health, now=1000, failed_endpoints=2)["inspection_needed"]


def test_old_or_changed_failure_condition_must_accumulate_a_new_duration():
    policy = _policy()
    health = _health()
    policy.evaluate(health, now=180, failed_endpoints=2)
    policy.evaluate(health, now=300, failed_endpoints=0)
    health["connect_attempts"] = 5
    assert not policy.evaluate(health, now=400, failed_endpoints=2)["inspection_needed"]
    health["connect_attempts"] = 6
    assert not policy.evaluate(health, now=579, failed_endpoints=2)["inspection_needed"]
    assert policy.evaluate(health, now=580, failed_endpoints=2)["inspection_needed"]


def test_receiving_link_with_residual_query_checksum_and_recovered_control_errors():
    # Anonymized operational pattern: two early control rounds later confirmed,
    # 14 checksum errors and 174 exhausted queries in ten minutes, including an
    # unresolved downstream thermostat. Other endpoints keep producing frames.
    health = _health(
        state="receiving", seconds_since_valid_rx=0.2,
        checksum_errors_recent=14, query_timeouts_recent=174,
        control_timeouts_lifetime=2, control_timeouts_recent=0,
    )
    policy = _policy()
    for now in (180, 360, 1800):
        report = policy.evaluate(health, now=now, failed_endpoints=2)
        assert not report["inspection_needed"]
        assert report["inspection_recent_valid_rx"]
        assert report["manual_restart_consideration"] is None


@pytest.mark.parametrize("fault", ["connect", "rx_recovery"])
def test_real_client_classifies_transport_evidence_without_network(monkeypatch, fault):
    async def scenario():
        module = load_integration_module("ew11_client")
        codec = load_integration_module("protocol").Ksx4506Codec()
        clock = [0.0]
        sleeps = []

        async def on_frame(_frame):
            return None

        client = module.Ew11Client("ew11.example.invalid", 8899, 0.1, 0, codec, on_frame)

        class Reader:
            async def read(self, _size):
                clock[0] += 121
                return b"\x99"

        class Writer:
            def close(self):
                pass

            async def wait_closed(self):
                pass

        async def connect(_host, _port):
            if fault == "connect":
                raise ConnectionRefusedError("synthetic connection refusal")
            return Reader(), Writer()

        async def pause(delay):
            sleeps.append(delay)
            clock[0] += delay
            if len(sleeps) == 8:
                client._running = False

        monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
        monkeypatch.setattr(module.asyncio, "open_connection", connect)
        monkeypatch.setattr(module.asyncio, "sleep", pause)
        client._running = True
        await client._run_loop()
        report = client.health_report()
        assert sleeps == [1, 2, 4, 8, 16, 32, 60, 60]
        if fault == "connect":
            assert report["transport_failures_since_rx"] == 8
            assert report["connect_attempts_since_transport_fault"] == 7
            assert report["seconds_since_transport_fault"] == 183
            # TCP accepting a connection is insufficient to declare recovery.
            client._mark_connected()
            assert client.health_report()["transport_failures_since_rx"] == 8
            client._mark_rx()
            assert client.health_report()["transport_failures_since_rx"] == 0
            assert client.health_report()["seconds_since_transport_fault"] is None
        else:
            assert report["transport_failures_since_rx"] == 0
            assert report["seconds_since_transport_fault"] is None

    asyncio.run(scenario())


@pytest.mark.parametrize("wall_adjustment", [-3600, -60, 60, 3600])
@pytest.mark.parametrize("received", [False, True])
def test_inspection_uses_monotonic_receive_age_across_clock_changes_and_reconnect(
    monkeypatch, wall_adjustment, received,
):
    module = load_integration_module("ew11_client")
    clock = [0.0]
    wall = [0.0]
    initial = datetime(2026, 10, 4, tzinfo=timezone.utc)

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return initial + timedelta(seconds=wall[0])

    monkeypatch.setattr(module, "datetime", ClockDateTime)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def on_frame(_frame):
        return None

    client = module.Ew11Client("ew11.example.invalid", 8899, 0.1, 0,
                               load_integration_module("protocol").Ksx4506Codec(), on_frame)
    client._running = True
    client._mark_connected()
    if received:
        client._mark_rx()
    for stamp in (10, 30, 60):
        clock[0] = wall[0] = stamp
        client._connection_stats.record_attempt()
        client._record_transport_failure()
    clock[0] = 200
    wall[0] = 200 + wall_adjustment
    client._connected = False
    report = client.health_report()
    assert report["seconds_since_valid_rx"] == (200 if received else None)
    if received:
        assert report["seconds_since_last_rx"] == 200 + wall_adjustment
    else:
        assert report["last_rx_at"] is None
    inspection = _policy().evaluate(report, now=clock[0], failed_endpoints=0)
    assert inspection["inspection_needed"]
    assert not inspection["inspection_recent_valid_rx"]
    # Current TCP uptime starts again; last valid receive does not.
    client._mark_connected()
    report = client.health_report()
    assert report["seconds_without_rx"] == 0
    assert report["seconds_since_valid_rx"] == (200 if received else None)
    assert _policy().evaluate(report, now=clock[0], failed_endpoints=0)["inspection_needed"]
    client._mark_rx()
    assert client.health_report()["seconds_since_valid_rx"] == 0
    assert not _policy().evaluate(client.health_report(), now=clock[0], failed_endpoints=0)["inspection_needed"]
    wall[0] += 7200
    clock[0] += 1
    assert client.health_report()["seconds_since_valid_rx"] == 1
    assert _policy().evaluate(client.health_report(), now=clock[0], failed_endpoints=0)["inspection_recent_valid_rx"]
