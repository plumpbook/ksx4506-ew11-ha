"""Admission is evidence based; silence never deletes registered devices."""
from collections.abc import Callable
from dataclasses import dataclass, replace
import time
from typing import Final, TypedDict

from .discovery_evidence import DiscoveryEvidence, EvidenceEvent, EvidenceSnapshot, MAX_RAW_HEX

MIN_OBSERVATIONS: Final = 3
MIN_SPACING: Final = 60.0
MIN_SPAN: Final = 600.0
CANDIDATE_TTL: Final = 86400.0
MAX_CANDIDATES: Final = 100
BLOCK_TTL: Final = 86400.0


@dataclass(frozen=True, slots=True)
class Observation:
    endpoint: str
    keys: tuple[str, ...]
    raw_hex: str
    automatic: bool


@dataclass(frozen=True, slots=True)
class Candidate:
    observation: Observation
    first: float
    last: float
    counted: float
    count: int = 1
    probes: int = 0
    last_probe: float | None = None
    approved: bool = False


class CandidateRow(TypedDict):
    endpoint: str
    keys: list[str]
    observations: int
    successful_probes: int
    first_seen: float
    last_seen: float
    action: str


class DiscoveryGuard:
    """Accumulates candidate evidence without trusting saved validation progress."""

    def __init__(self, now: Callable[[], float] = time.time) -> None:
        self.now = now
        self.evidence = DiscoveryEvidence(now)
        self.pending: dict[str, Candidate] = {}
        self.blocked_until: dict[str, float] = {}
        self.verification_enabled = True
        self.link_healthy: Callable[[], bool] = lambda: True

    def record(self, observation: Observation, action: str) -> None:
        self.evidence.record(EvidenceEvent(
            time=self.now(), endpoint=observation.endpoint, action=action,
            keys=observation.keys, raw_hex=observation.raw_hex[:MAX_RAW_HEX].upper(),
        ))

    def observe(self, observation: Observation) -> bool:
        self.expire()
        now = self.now()
        endpoint = observation.endpoint
        if endpoint in self.blocked_until:
            return False
        previous = self.pending.get(endpoint)
        if not observation.keys:
            if previous:
                self.record(previous.observation, "topology_disappeared")
                self.pending.pop(endpoint)
            return True
        if previous is None or previous.observation.keys != observation.keys:
            if previous:
                self.record(previous.observation, "topology_changed")
            if len(self.pending) >= MAX_CANDIDATES and previous is None:
                return False
            self.pending[endpoint] = Candidate(observation, now, now, now)
            self.record(observation, "candidate_observed")
            return False
        spaced = now - previous.counted >= MIN_SPACING
        candidate = replace(previous, observation=observation, last=now,
                            counted=now if spaced else previous.counted,
                            count=previous.count + int(spaced))
        self.pending[endpoint] = candidate
        if spaced:
            self.record(observation, "candidate_observed")
        stable = candidate.count >= MIN_OBSERVATIONS and now - candidate.first >= MIN_SPAN
        verified = candidate.approved or (observation.automatic and candidate.probes >= 2)
        fresh_probe = candidate.last_probe is not None and now - candidate.last_probe <= MIN_SPAN
        if (stable and verified and self.verification_enabled and self.link_healthy()
                and (candidate.approved or fresh_probe)):
            self.record(observation, "admitted_by_user" if candidate.approved else "admitted_by_probe")
            self.pending.pop(endpoint)
            return True
        return False

    def record_probe(self, observation: Observation, success: bool) -> None:
        candidate = self.pending.get(observation.endpoint)
        if candidate is None or candidate.observation.keys != observation.keys:
            return
        now = self.now()
        if candidate.last_probe is not None and now - candidate.last_probe < MIN_SPACING:
            return
        self.pending[observation.endpoint] = replace(
            candidate, last_probe=now, probes=candidate.probes + 1 if success else 0,
        )
        self.record(observation, "probe_matched" if success else "probe_unconfirmed")

    def review(self, endpoint: str, approve: bool) -> bool:
        self.expire()
        candidate = self.pending.get(endpoint)
        if candidate is None:
            if approve and endpoint in self.blocked_until:
                self.blocked_until.pop(endpoint)
                self.record(Observation(endpoint, (), "", False), "user_unblocked")
                return True
            return False
        if approve:
            self.pending[endpoint] = replace(candidate, approved=True)
            self.record(candidate.observation, "user_approved")
        else:
            self._discard(endpoint, "user_rejected")
        return True

    def _discard(self, endpoint: str, reason: str) -> None:
        candidate = self.pending.pop(endpoint)
        self.record(candidate.observation, reason)
        if len(self.blocked_until) >= MAX_CANDIDATES:
            oldest = min(self.blocked_until, key=lambda key: self.blocked_until[key])
            self.blocked_until.pop(oldest)
        self.blocked_until[endpoint] = self.now() + BLOCK_TTL

    def expire(self) -> None:
        now = self.now()
        for endpoint, until in list(self.blocked_until.items()):
            if until <= now:
                self.blocked_until.pop(endpoint)
                self.evidence.revision += 1
        for endpoint, candidate in list(self.pending.items()):
            if now < candidate.first or now - candidate.first >= CANDIDATE_TTL:
                self._discard(endpoint, "candidate_expired")
        self.evidence.prune()

    def probe_candidates(self) -> list[Observation]:
        self.expire()
        return [c.observation for c in sorted(self.pending.values(), key=lambda c: c.last_probe or 0)
                if c.observation.automatic and not c.approved
                and self.now() - c.last <= MIN_SPAN
                and (c.last_probe is None or self.now() - c.last_probe >= MIN_SPAN)][:2]

    def snapshot(self) -> EvidenceSnapshot:
        self.expire()
        return EvidenceSnapshot(events=tuple(self.evidence.events), blocked_until=self.blocked_until.copy())

    def restore(self, snapshot: EvidenceSnapshot) -> None:
        self.evidence.restore(snapshot)
        self.blocked_until = {k: v for k, v in snapshot.blocked_until.items()
                              if self.now() < v <= self.now() + BLOCK_TTL}

    def report(self) -> list[CandidateRow]:
        return [CandidateRow(endpoint=key, keys=list(c.observation.keys),
                             observations=c.count, successful_probes=c.probes,
                             first_seen=c.first, last_seen=c.last,
                             action="verification_pending" if c.observation.automatic else "review_required")
                for key, c in sorted(self.pending.items())]
