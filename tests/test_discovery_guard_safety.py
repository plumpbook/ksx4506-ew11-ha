"""Safety gates must fail closed without touching registered devices."""
import json

import pytest

from .test_discovery_guard import make_registry, policy
from ._integration_loader import load_integration_module

evidence = load_integration_module("discovery_evidence")


@pytest.mark.parametrize("raw", ["null", "[]", "{}", "broken", '{"policy_version":2}'])
def test_invalid_saved_evidence_fails_closed(raw):
    # Given/When/Then
    with pytest.raises(evidence.InvalidEvidence):
        evidence.EvidenceSnapshot.from_json(raw)


def test_corrupt_event_cannot_be_loaded():
    # Given
    saved = {"policy_version": 1, "blocked_until": {}, "events": [{
        "time": float("nan"), "endpoint": "0E/11", "action": "admitted_by_probe",
        "keys": [], "raw_hex": "AA", "context": [],
    }]}
    # When/Then
    with pytest.raises(evidence.InvalidEvidence):
        evidence.EvidenceSnapshot.from_json(json.dumps(saved))


@pytest.mark.parametrize("field", ["keys", "context"])
def test_string_instead_of_saved_array_is_rejected(field):
    event = {"time": 1, "endpoint": "0E/11", "action": "candidate_observed",
             "keys": [], "context": []}
    event[field] = "not-an-array"
    saved = {"policy_version": 1, "blocked_until": {}, "events": [event]}
    with pytest.raises(evidence.InvalidEvidence):
        evidence.EvidenceSnapshot.from_json(json.dumps(saved))


def test_unhealthy_bus_blocks_even_user_approved_admission():
    # Given
    clock, guard, registry = make_registry()
    registry.upsert_from_frame(14, 79, 129, b"\x00\x01", "F70E4F")
    guard.review("0E/4F", True)
    guard.link_healthy = lambda: False
    # When
    for _ in range(5):
        clock.value += 300
        registry.upsert_from_frame(14, 79, 129, b"\x00\x01", "F70E4F")
    # Then
    assert registry.devices == {}


def test_user_approval_admits_only_stable_matching_topology():
    # Given
    clock, guard, registry = make_registry()
    registry.upsert_from_frame(14, 79, 129, b"\x00\x01", "F70E4F")
    guard.review("0E/4F", True)
    # When
    for _ in range(2):
        clock.value += 300
        registry.upsert_from_frame(14, 79, 129, b"\x00\x01", "F70E4F")
    # Then
    assert set(registry.devices) == {"0E4F_light_1"}
    assert guard.evidence.events[-1].action == "admitted_by_user"


def test_wrong_key_probe_and_bursty_probe_cannot_validate_candidate():
    # Given
    _, guard, registry = make_registry()
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E11")
    wrong = policy.Observation("0E/11", ("0E11_light_2",), "F70E11", True)
    # When
    guard.record_probe(wrong, True)
    actual = guard.pending["0E/11"].observation
    for _ in range(100):
        guard.record_probe(actual, True)
    # Then
    assert guard.pending["0E/11"].probes == 1
    assert not registry.devices


def test_rejection_can_be_reversed_without_restoring_approval_or_proof():
    # Given
    _, guard, registry = make_registry()
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E11")
    guard.review("0E/11", False)
    # When
    assert guard.review("0E/11", True)
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01", "F70E11")
    # Then
    assert not guard.blocked_until
    assert guard.pending["0E/11"].probes == 0
    assert not guard.pending["0E/11"].approved


def test_existing_device_receives_updates_while_new_channel_is_blocked():
    # Given
    _, guard, registry = make_registry()
    registry.restore_device_from_key("0E11_light_1")
    registry.upsert_from_frame(14, 17, 129, b"\x00\x00\x01", "F70E11")
    guard.review("0E/11", False)
    # When
    registry.upsert_from_frame(14, 17, 129, b"\x00\x01\x01", "F70E11")
    # Then
    assert set(registry.devices) == {"0E11_light_1"}
    assert registry.devices["0E11_light_1"].state["on"] is True
