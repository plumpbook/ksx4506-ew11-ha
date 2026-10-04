from __future__ import annotations

from typing import Any


class LinkInspectionPolicy:
    """Explain sustained shared-link evidence; never request a hardware action."""

    def __init__(self, *, started: float) -> None:
        self.started = started
        self.multiple_since: float | None = None
        self.attempts_at_multiple = 0

    def evaluate(
        self, health: dict[str, Any], *, now: float, failed_endpoints: int,
    ) -> dict[str, Any]:
        running = bool(health.get("running"))
        age = health.get("seconds_since_valid_rx")
        recent_rx = isinstance(age, (int, float)) and 0 <= age < 180
        attempts = int(health.get("connect_attempts", 0))
        if running and not recent_rx and failed_endpoints >= 2:
            if self.multiple_since is None:
                self.multiple_since = now
                self.attempts_at_multiple = attempts
        else:
            self.multiple_since = None
        multiple_duration = (now - self.multiple_since
                             if self.multiple_since is not None else 0)
        multiple_retries = max(0, attempts - self.attempts_at_multiple)
        transport_duration = float(health.get("seconds_since_transport_fault") or 0)
        transport_failures = int(health.get("transport_failures_since_rx", 0))
        transport_retries = int(health.get("connect_attempts_since_transport_fault", 0))
        reason = None
        duration = 0.0
        retries = 0
        if not recent_rx and transport_failures >= 3 and transport_retries >= 2:
            reason, duration, retries = "repeated_transport_failure", transport_duration, transport_retries
        elif self.multiple_since is not None and multiple_retries >= 1:
            reason, duration, retries = "multiple_endpoints_no_response", multiple_duration, multiple_retries
        needed = running and now - self.started >= 180 and reason is not None and duration >= 180
        state = ("stopped" if not running else "starting" if now - self.started < 180
                 else "inspection_required" if needed else "suspected" if reason else "watching")
        return {
            "inspection_state": state,
            "inspection_needed": needed,
            "inspection_reason": reason,
            "inspection_summary": (
                "통신 복구 안 됨 · EW11·네트워크 점검 필요" if needed
                else "감시 중지" if not running
                else "시작 후 통신 확인 중" if state == "starting"
                else "공유 통신 장애 판정 조건에 해당하지 않음"
            ),
            "inspection_failure_duration_seconds": round(duration, 1),
            "inspection_recovery_attempts": retries,
            "inspection_failed_endpoints": failed_endpoints,
            "inspection_recent_valid_rx": recent_rx,
            "manual_restart_consideration": (
                "EW11 전원·케이블·네트워크와 RS-485 배선을 확인한 뒤에도 "
                "장애가 계속되면 EW11 재부팅을 검토하세요. 원인은 확정되지 않았습니다."
                if needed else None
            ),
        }


def inspection_monitoring_report(state: str) -> dict[str, Any]:
    """Lifecycle status is independent of the saved unresolved incident journal."""
    return {
        "inspection_state": state,
        "inspection_needed": False,
        "inspection_reason": None,
        "inspection_summary": "감시 중지 · 복구 판정 아님" if state == "stopped" else "시작 후 통신 확인 중",
        "inspection_failure_duration_seconds": 0.0,
        "inspection_recovery_attempts": 0,
        "inspection_failed_endpoints": 0,
        "inspection_recent_valid_rx": False,
        "manual_restart_consideration": None,
    }


def ew11_health_report_from_coordinator(coordinator: Any) -> dict[str, Any]:
    if coordinator is None:
        return _missing_health_report()

    coordinator_report = getattr(coordinator, "ew11_health_report", None)
    if callable(coordinator_report):
        report = coordinator_report()
        if isinstance(report, dict):
            return report

    client = getattr(coordinator, "_client", None)
    client_report = getattr(client, "health_report", None)
    if callable(client_report):
        report = client_report()
        if isinstance(report, dict):
            report = report.copy()
            report.update(getattr(coordinator, "link_inspection", {}))
            return report

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
        "seconds_since_valid_rx": None,
        "seconds_without_rx": None,
        "rx_stale_after": None,
        "last_error": "EW11 client health is unavailable",
    }
