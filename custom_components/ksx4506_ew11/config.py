from __future__ import annotations

from homeassistant.config_entries import ConfigEntry


def effective_config(entry: ConfigEntry) -> dict:
    """Return config entry data overlaid with user-editable options."""

    return {
        **dict(getattr(entry, "data", {}) or {}),
        **dict(getattr(entry, "options", {}) or {}),
    }
