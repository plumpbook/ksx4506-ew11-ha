from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry


def effective_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return config entry data overlaid with user-editable options."""

    return {
        **dict(getattr(entry, "data", {}) or {}),
        **dict(getattr(entry, "options", {}) or {}),
    }
