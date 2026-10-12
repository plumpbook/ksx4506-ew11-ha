from ._integration_loader import load_integration_module


def _classify(*, connected=True, known=(), failed=(), controls=0, now=1200,
              inspection_state="watching"):
    return load_integration_module("ew11_health").classify_faults(
        {"running": True, "connected": connected},
        known_endpoints=known, failed_endpoints=set(failed),
        control_failures=controls, now=now, inspection_state=inspection_state,
    )


def test_tcp_disconnect_is_not_called_an_rs485_fault():
    report = _classify(connected=False, known=(("0x0E/0x11", 1000),),
                       failed=("0x0E/0x11",))
    assert report["fault_category"] == "tcp_disconnected"
    assert "TCP" in report["fault_summary"]
    assert "RS485 고장" not in report["fault_summary"]


def test_complete_confirmed_response_outage_is_not_called_an_ew11_failure():
    known = (("0x0E/0x11", 1000), ("0x39/0x11", 1000),
             ("0x60/0x01", 1000))
    report = _classify(known=known, failed=(key for key, _ in known))
    assert report["fault_category"] == "shared_response_outage"
    assert "공통" in report["fault_summary"]
    assert "원인 미확정" in report["fault_summary"]
    assert report["failed_endpoint_count"] == 3


def test_one_address_failure_with_recent_peer_is_a_partial_fault():
    known = (("0x0E/0x11", 1000), ("0x39/0x11", 1199))
    report = _classify(known=known, failed=("0x0E/0x11",))
    assert report["fault_category"] == "endpoint_no_response"
    assert report["fault_peer_confirmed"] is True
    assert "다른 주소 응답 확인" in report["fault_summary"]


def test_old_or_same_address_peer_does_not_prove_isolated_failure():
    for known in ((("0x0E/0x11", 1000), ("0x39/0x11", 1001)),
                  (("0x0E/0x11", 1000), ("0x0E/0x12", 1199))):
        report = _classify(known=known, failed=("0x0E/0x11",))
        assert report["fault_category"] == "endpoint_no_response"
        assert report["fault_peer_confirmed"] is False
        assert "공통 장애 여부 미확정" in report["fault_summary"]


def test_failed_control_is_separate_from_response_loss():
    known = (("0x0E/0x11", 1199), ("0x39/0x11", 1199))
    control_only = _classify(known=known, controls=1)
    assert control_only["fault_category"] == "control_unconfirmed"
    assert "제어 결과" in control_only["fault_summary"]
    partial = _classify(known=known, failed=("0x0E/0x11",), controls=1)
    assert partial["fault_categories"] == ["endpoint_no_response", "control_unconfirmed"]


def test_startup_and_stopped_monitoring_do_not_claim_a_live_fault():
    assert _classify(connected=False, inspection_state="starting")["fault_category"] == "starting"
    module = load_integration_module("ew11_health")
    stopped = module.classify_faults(
        {"running": False, "connected": False}, known_endpoints=(),
        failed_endpoints=set(), control_failures=0, now=1200,
        inspection_state="stopped",
    )
    assert stopped["fault_category"] == "monitoring_stopped"
