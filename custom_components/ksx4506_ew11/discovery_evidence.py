"""Bounded local evidence, independently retained from optional packet capture."""
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
import json
import math
import time
from typing import Final, TypedDict

MAX_EVENTS: Final = 256
RETENTION: Final = 30 * 86400
MAX_RAW_HEX: Final = 1024


class InvalidEvidence(ValueError):
    """Stored evidence is invalid; do not overwrite it or resume admission."""


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    time: float
    endpoint: str
    action: str
    keys: tuple[str, ...] = ()
    raw_hex: str = ""
    context: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        valid = (isinstance(self.time, (int, float)) and math.isfinite(self.time)
                 and self.time >= 0 and isinstance(self.endpoint, str)
                 and len(self.endpoint) <= 16 and isinstance(self.action, str)
                 and len(self.action) <= 64 and isinstance(self.raw_hex, str)
                 and len(self.raw_hex) <= MAX_RAW_HEX
                 and isinstance(self.detail, str) and len(self.detail) <= 512
                 and len(self.keys) <= 32 and len(self.context) <= 4
                 and all(isinstance(k, str) and len(k) <= 128 for k in self.keys)
                 and all(isinstance(k, str) and len(k) <= MAX_RAW_HEX for k in self.context))
        if not valid:
            raise InvalidEvidence()


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    events: tuple[EvidenceEvent, ...] = ()
    blocked_until: dict[str, float] = field(default_factory=dict)
    policy_version: int = 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), allow_nan=False)

    @classmethod
    def from_json(cls, raw: str) -> "EvidenceSnapshot":
        """Validate disk data once; validation progress is never persisted."""
        try:
            if len(raw) > 3 * 1024 * 1024:
                raise InvalidEvidence()
            data = json.loads(raw)
            if (not isinstance(data, dict)
                    or set(data) != {"events", "blocked_until", "policy_version"}
                    or data["policy_version"] != 1 or not isinstance(data["events"], list)
                    or len(data["events"]) > MAX_EVENTS
                    or not isinstance(data["blocked_until"], dict)
                    or len(data["blocked_until"]) > 100):
                raise InvalidEvidence()
            if any(not isinstance(event, dict) or not isinstance(event.get("keys"), list)
                   or not isinstance(event.get("context"), list) for event in data["events"]):
                raise InvalidEvidence()
            events = tuple(EvidenceEvent(**{**event, "keys": tuple(event["keys"]),
                                           "context": tuple(event["context"])})
                           for event in data["events"])
            blocked: dict[str, float] = {}
            for key, value in data["blocked_until"].items():
                if (not isinstance(key, str) or len(key) > 16
                        or not isinstance(value, (int, float)) or not math.isfinite(value)):
                    raise InvalidEvidence()
                blocked[key] = float(value)
            return cls(events=events, blocked_until=blocked)
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise InvalidEvidence() from exc


class EvidenceRow(TypedDict, total=False):
    time: float
    endpoint: str
    action: str
    keys: list[str]
    raw_hex: str
    context: list[str]
    detail: str


class DiscoveryEvidence:
    """Mutable bounded recorder; ordinary traffic is kept in RAM only."""

    def __init__(self, now: Callable[[], float] = time.time) -> None:
        self.now = now
        self.events: deque[EvidenceEvent] = deque(maxlen=MAX_EVENTS)
        self.context: deque[str] = deque(maxlen=4)
        self.revision = 0

    def observe(self, raw_hex: str) -> None:
        self.context.append(raw_hex[:MAX_RAW_HEX].upper())

    def record(self, event: EvidenceEvent) -> None:
        self.events.append(replace(event, context=tuple(self.context)))
        self.revision += 1
        self.prune()

    def prune(self) -> None:
        kept = [e for e in self.events if self.now() - RETENTION <= e.time <= self.now()]
        if len(kept) != len(self.events):
            self.events = deque(kept, maxlen=MAX_EVENTS)
            self.revision += 1

    def restore(self, snapshot: EvidenceSnapshot) -> None:
        self.events = deque(snapshot.events, maxlen=MAX_EVENTS)
        self.prune()

    def report(self, include_raw: bool = False) -> list[EvidenceRow]:
        self.prune()
        result: list[EvidenceRow] = []
        for event in self.events:
            row: EvidenceRow = {
                "time": event.time, "endpoint": event.endpoint,
                "action": event.action, "keys": list(event.keys),
                "detail": event.detail,
            }
            if include_raw:
                row.update(raw_hex=event.raw_hex, context=list(event.context))
            result.append(row)
        return result
