from __future__ import annotations

from typing import Any


def ew11_health_report_from_coordinator(coordinator: Any) -> dict[str, Any]:
    if coordinator is None:
        return _missing_health_report()

    coordinator_report = getattr(coordinator, "ew11_health_report", None)
    if callable(coordinator_report):
        return coordinator_report()

    client = getattr(coordinator, "_client", None)
    client_report = getattr(client, "health_report", None)
    if callable(client_report):
        return client_report()

    return _missing_health_report()


def _missing_health_report() -> dict[str, Any]:
    return {
        "state": "unknown",
        "connected": False,
        "running": False,
        "last_connect_at": None,
        "connect_attempts": 0,
        "connect_successes": 0,
        "disconnect_count": 0,
        "last_disconnect_at": None,
        "last_disconnect_reason": None,
        "last_connected_duration_seconds": None,
        "current_uptime_seconds": None,
        "last_rx_at": None,
        "seconds_since_last_rx": None,
        "seconds_without_rx": None,
        "rx_stale_after": None,
        "last_error": "EW11 client health is unavailable",
    }
