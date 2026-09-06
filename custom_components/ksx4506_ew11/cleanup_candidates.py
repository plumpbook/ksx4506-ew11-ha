from __future__ import annotations

from typing import Literal, TypedDict


class CleanupCandidate(TypedDict):
    device_key: str
    reason: str
    action: Literal["review_required"]


class CleanupCandidateReport(TypedDict):
    count: int
    candidates: list[CleanupCandidate]


class CleanupCandidateTracker:
    """Keep possible stale devices visible until a user reviews them."""

    def __init__(self) -> None:
        self._reasons: dict[str, str] = {}

    def record(self, device_key: str, *, reason: str) -> None:
        self._reasons[device_key] = reason

    def clear(self, device_key: str) -> None:
        self._reasons.pop(device_key, None)

    def report(self) -> CleanupCandidateReport:
        candidates: list[CleanupCandidate] = [
            {
                "device_key": device_key,
                "reason": reason,
                "action": "review_required",
            }
            for device_key, reason in sorted(self._reasons.items())
        ]
        return {"count": len(candidates), "candidates": candidates}
