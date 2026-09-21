"""Admission tests use decoded frames; clocks never sleep."""
from ._integration_loader import load_integration_module

policy = load_integration_module("discovery_guard")
registry_module = load_integration_module("guarded_registry")


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def make_registry():
    clock = Clock()
    guard = policy.DiscoveryGuard(clock)
    return clock, guard, registry_module.GuardedRegistry(guard)


def test_short_burst_must_not_register_devices():
    # Given: the production registry with no previously registered devices.
    _, guard, registry = make_registry()
    # When: a brief repeated group response appears.
    for _ in range(10):
        registry.upsert_from_frame(0x0E, 0x4F, 0x81, b"\x00\x01\x00", "F70E4F8103000100")
    # Then: unverified group channels must not become HA devices.
    assert registry.devices == {}
    assert guard.report()[0]["observations"] == 1
    assert guard.report()[0]["action"] == "review_required"


def test_direct_device_needs_time_and_two_matching_probes():
    # Given
    clock, guard, registry = make_registry()
    def observe():
        return registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
    observe()
    guard.record_probe(guard.pending["0E/11"].observation, True)
    clock.value += 300
    observe()
    guard.record_probe(guard.pending["0E/11"].observation, True)
    assert registry.devices == {}
    # When
    clock.value += 300
    changes = observe()
    # Then
    assert [(d.key, new) for d, new in changes] == [("0E11_light_1", True)]
    assert not guard.pending
    assert guard.evidence.events[-1].action == "admitted_by_probe"


def test_time_and_passive_repetition_alone_cannot_admit():
    # Given
    clock, guard, registry = make_registry()
    # When
    for _ in range(20):
        registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
        clock.value += 300
    # Then
    assert registry.devices == {}
    assert guard.report()[0]["successful_probes"] == 0


def test_existing_light_channels_survive_shrink_and_resume_immediately():
    # Given
    _, guard, registry = make_registry()
    for channel in (1, 2, 3):
        registry.restore_device_from_key(f"0E11_light_{channel}")
    # When
    for _ in range(20):
        registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
    # Then
    assert set(registry.devices) == {"0E11_light_1", "0E11_light_2", "0E11_light_3"}
    assert registry.devices["0E11_light_1"].state["on"] is True
    assert registry.retired_device_keys == set()
    assert not guard.pending
    assert {c["device_key"] for c in registry.cleanup_candidate_report()["candidates"]} == {
        "0E11_light_2", "0E11_light_3",
    }


def test_expired_candidate_is_discarded_and_temporarily_blocked():
    # Given
    clock, guard, registry = make_registry()
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
    # When
    clock.value += policy.CANDIDATE_TTL
    guard.expire()
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
    # Then
    assert not guard.pending and not registry.devices
    assert "0E/11" in guard.blocked_until
    assert guard.evidence.events[-1].action == "candidate_expired"


def test_topology_change_resets_proof_and_user_approval():
    # Given
    _, guard, registry = make_registry()
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
    guard.review("0E/11", True)
    guard.record_probe(guard.pending["0E/11"].observation, True)
    # When
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01\x00", "F70E118103000100")
    # Then
    candidate = guard.pending["0E/11"]
    assert candidate.probes == 0 and not candidate.approved
    assert candidate.count == 1
    assert not registry.devices


def test_group_probe_does_not_admit_individual_channels():
    # Given
    clock, guard, registry = make_registry()
    # When
    for _ in range(5):
        registry.upsert_from_frame(14, 79, 129, b"\x00\x01", "F70E4F81020001")
        guard.record_probe(guard.pending["0E/4F"].observation, True)
        clock.value += 300
    # Then
    assert not registry.devices
    assert guard.probe_candidates() == []


def test_new_thermostat_zone_in_existing_device_is_quarantined():
    # Given
    _, guard, registry = make_registry()
    registry.restore_device_from_key("361F_climate", channel_hints={1})
    # When: a second zone briefly appears inside an already registered group.
    registry.upsert_from_frame(54, 31, 129, bytes.fromhex("00 03 00 00 00 17 17 18 18"), "F7361F")
    # Then
    assert [z["channel"] for z in registry.devices["361F_climate"].state["zones"]] == [1]
    assert guard.report()[0]["keys"] == ["361F_climate_ch2"]


def test_saved_evidence_is_redacted_and_does_not_restore_validation_progress():
    # Given
    clock, guard, registry = make_registry()
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E1181020001")
    # When
    saved = guard.snapshot().to_json()
    restored = policy.DiscoveryGuard(clock)
    restored.restore(policy.EvidenceSnapshot.from_json(saved))
    # Then
    assert not restored.pending
    assert restored.evidence.events[0].raw_hex == "F70E1181020001"
    assert "raw_hex" not in repr(restored.evidence.report())
    assert "context" not in repr(restored.evidence.report())
    assert "F70E1181020001" in repr(restored.evidence.report(True))


def test_storage_and_candidate_counts_are_bounded():
    # Given
    clock, guard, _ = make_registry()
    # When
    for number in range(2000):
        guard.observe(policy.Observation(f"0E/{number:04X}", (f"light_{number}",), "AA" * 2000, False))
    # Then
    assert len(guard.pending) == policy.MAX_CANDIDATES
    assert len(guard.evidence.events) <= 256
    assert all(len(event.raw_hex) <= 1024 for event in guard.evidence.events)
    clock.value += 31 * 86400
    guard.expire()
    assert all(event.time == clock.value for event in guard.evidence.events)
