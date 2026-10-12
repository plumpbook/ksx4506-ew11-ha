from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def state_query_connection_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return after.get('connected') is False or any(
        before.get(field) != after.get(field)
        for field in ('connected', 'connection_epoch', 'connect_successes', 'disconnect_count')
    )


class LinkInspectionPolicy:
    """Explain sustained shared-link evidence; never request a hardware action."""

    def __init__(self, *, started: float) -> None:
        self.started = started
        self.multiple_since: float | None = None
        self.attempts_at_multiple = 0

    def evaluate(
        self, health: dict[str, Any], *, now: float, failed_endpoints: int,
        known_endpoints: int = 0, responsive_endpoints: int = 0,
    ) -> dict[str, Any]:
        running = bool(health.get("running"))
        age = health.get("seconds_since_valid_rx")
        recent_rx = isinstance(age, (int, float)) and 0 <= age < 180
        attempts = int(health.get("connect_attempts", 0))
        shared_response_outage = (
            known_endpoints >= 3 and failed_endpoints == known_endpoints
            and responsive_endpoints == 0
        )
        if running and (not recent_rx or shared_response_outage) and failed_endpoints >= 2:
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
                "TCP 복구 안 됨 · EW11·네트워크 점검 필요"
                if needed and reason == "repeated_transport_failure"
                else "여러 주소 응답 없음 · EW11 직렬측·월패드·RS485 경로 점검 필요" if needed
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
                if needed and reason == "repeated_transport_failure"
                else "EW11 직렬측·월패드·RS485 배선과 해당 기기를 확인하세요. "
                     "TCP 재연결만으로 원인을 확정하거나 복구를 보장할 수 없습니다."
                if needed else None
            ),
        }


def inspection_monitoring_report(state: str) -> dict[str, Any]:
    """Lifecycle status is independent of the saved unresolved incident journal."""
    fault_category = "monitoring_stopped" if state == "stopped" else "starting"
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
        "fault_category": fault_category,
        "fault_categories": [fault_category],
        "fault_summary": "감시 중지 · 복구 판정 아님" if state == "stopped" else "시작 후 통신 확인 중",
        "fault_peer_confirmed": False,
        "failed_endpoint_count": 0,
        "known_endpoint_count": 0,
        "control_failure_count": 0,
    }


def classify_faults(
    health: dict[str, Any], *, known_endpoints: Iterable[tuple[str, float]],
    failed_endpoints: set[str], control_failures: int, now: float,
    inspection_state: str,
    recent_state_endpoints: set[str] | None = None,
) -> dict[str, Any]:
    known = dict(known_endpoints)
    failed = failed_endpoints & known.keys()
    failed_addresses = {key.split("/")[0] for key in failed}
    peer_confirmed = bool(failed) and any(
        key not in failed and key.split("/")[0] not in failed_addresses
        and (key in recent_state_endpoints if recent_state_endpoints is not None
             else 0 <= now - last < 180)
        for key, last in known.items()
    )
    categories: list[str] = []
    if not health.get("running"):
        categories.append("monitoring_stopped")
    elif inspection_state == "starting":
        categories.append("starting")
    elif health.get("connected") is False:
        categories.append("tcp_disconnected")
    elif (len(known) >= 3 and len({key.split("/")[0] for key in known}) >= 2
          and failed == known.keys()):
        categories.append("shared_response_outage")
    elif failed:
        categories.append("endpoint_no_response")
    if control_failures and categories != ["monitoring_stopped"]:
        if categories == ["starting"]:
            categories.clear()
        categories.append("control_unconfirmed")
    if not categories:
        categories.append("none")
    primary = categories[0]
    summaries = {
        "monitoring_stopped": "감시 중지 · 복구 판정 아님",
        "starting": "시작 후 통신 확인 중",
        "tcp_disconnected": "EW11 TCP 연결 끊김 · EW11·네트워크 경로 확인 필요",
        "shared_response_outage": "여러 주소의 상태 응답 공통 중단 · EW11 직렬측·월패드·RS485 원인 미확정",
        "endpoint_no_response": (
            "일부 주소 상태 응답 없음 · 다른 주소 응답 확인" if peer_confirmed
            else "주소별 상태 응답 없음 · 공통 장애 여부 미확정"
        ),
        "control_unconfirmed": "요청한 제어 결과 미확인 · 상태 응답과 실제 동작은 별도 확인 필요",
        "none": "감지된 통신·제어 장애 없음 · 실제 동작 보증 아님",
    }
    guidance = {
        'endpoint_no_response': '먼저 해당 device ID/sub ID의 상태를 다시 확인하고 월패드·기기 반응을 확인하세요. '
            '같은 주소의 유효 상태 응답 누락이 계속되면 월패드 재시작을 검토할 수 있습니다. '
            '필요성·원인은 확정되지 않았으며 연결된 기기 제어가 중단될 수 있습니다.',
        'control_unconfirmed': '주소 응답과 요청한 채널 목표 상태를 따로 확인하세요. '
            '상태 다시 확인은 출력을 바꾸지 않으며 실제 동작 성공을 보증하지 않습니다.',
        'shared_response_outage': '여러 주소의 실제 상태 응답과 EW11 직렬측·월패드·RS485 경로를 확인하세요. '
            '공통 응답 중단만으로 전원 재시작 필요성을 확정할 수 없습니다.',
        'tcp_disconnected': 'EW11 전원·네트워크와 TCP 연결을 확인하세요. '
            'TCP 복구 후에도 해당 주소의 유효 상태 응답을 별도로 확인해야 합니다.',
    }.get(primary)
    return {
        "fault_category": primary,
        "fault_categories": categories,
        "fault_summary": summaries[primary],
        "fault_peer_confirmed": peer_confirmed,
        "failed_endpoint_count": len(failed),
        "known_endpoint_count": len(known),
        "control_failure_count": control_failures,
        'recovery_guidance': guidance,
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
