from __future__ import annotations

from typing import Final

DISCOVERY_CONFIRMATION_OBSERVATIONS: Final = 2
MAX_PENDING_DISCOVERIES: Final = 100


class DiscoveryConfirmationTracker:
    """Require repeated observations before exposing newly discovered devices."""

    def __init__(self) -> None:
        self._observations: dict[frozenset[str], int] = {}

    def confirm(self, device_keys: set[str]) -> bool:
        signature = frozenset(device_keys)
        observations = self._observations.get(signature, 0) + 1
        if observations < DISCOVERY_CONFIRMATION_OBSERVATIONS:
            self._observations[signature] = observations
            if len(self._observations) > MAX_PENDING_DISCOVERIES:
                self._observations.pop(next(iter(self._observations)))
            return False

        self._observations.pop(signature, None)
        return True
