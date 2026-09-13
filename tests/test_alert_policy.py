from dataclasses import replace

from ._integration_loader import load_integration_module


def test_ghosts_and_brief_silence_remain_quiet():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=0)
    ghost = module.Endpoint("ghost", ("old",), 0, None, True)
    live = module.Endpoint("light", ("light_1",), 3, 180, True)
    result = policy.scan((ghost, live), now=200)
    assert result.probes == ()
    assert result.alerts == ()


def test_multiple_kinds_require_three_probes_and_recover_independently():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=0)
    endpoints = tuple(module.Endpoint(key, (key,), 3, 0, True)
                      for key in ("light", "fan", "climate", "switch"))
    assert policy.scan(endpoints, now=179).probes == ()
    for now in (180, 210, 240):
        result = policy.scan(endpoints, now=now)
        assert len(result.probes) == 4
        for endpoint in result.probes:
            policy.record_probe(endpoint, success=False, now=now)
    result = policy.scan(endpoints, now=241)
    assert {alert.endpoint for alert in result.alerts} == {e.key for e in endpoints}
    assert all(alert.reason == "no_response" for alert in result.alerts)
    refreshed = (replace(endpoints[0], responses=4, last_response=242), *endpoints[1:])
    result = policy.scan(refreshed, now=242)
    assert {a.endpoint for a in result.alerts} == {"fan", "climate", "switch"}


def test_event_devices_and_unsupported_queries_are_not_control_failures():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=0)
    endpoints = (module.Endpoint("door", ("door",), 0, None, False),
                 module.Endpoint("meter", ("meter",), 3, 0, False))
    assert policy.scan(endpoints, now=300).alerts == ()
    result = policy.scan(endpoints, now=901)
    assert result.probes == ()
    assert [(a.endpoint, a.reason) for a in result.alerts] == [("meter", "stale")]


def test_reload_preserves_recent_baseline_but_honors_startup_grace():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=100, known={"light": 50})
    endpoint = module.Endpoint("light", ("light_3",), 0, None, True)
    assert policy.scan((endpoint,), now=279).probes == ()
    assert policy.scan((endpoint,), now=280).probes == ("light",)


def test_fair_probe_budget_and_removed_devices():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=0)
    endpoints = tuple(module.Endpoint(str(i), (str(i),), 3, 0, True) for i in range(10))
    first = policy.scan(endpoints, now=200).probes
    for key in first:
        policy.record_probe(key, success=False, now=200)
    second = policy.scan(endpoints, now=215).probes
    assert set(first).isdisjoint(second)
    policy.scan((), now=216)
    assert policy.known == {}


def test_successful_probe_does_not_move_back_to_an_older_passive_timestamp():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=0)
    endpoint = module.Endpoint("light", ("light",), 3, 0, True)
    policy.scan((endpoint,), now=200)
    policy.record_probe("light", success=True, now=200)
    assert policy.scan((endpoint,), now=250).probes == ()
    assert policy.known["light"] == 200


def test_long_outage_and_reloaded_baseline_do_not_expire_into_recovery():
    module = load_integration_module("alert_policy")
    policy = module.AlertPolicy(started=0, known={"meter": 0, "light": 0})
    endpoints = (module.Endpoint("meter", ("meter",), 0, None, False),
                 module.Endpoint("light", ("light",), 0, None, True))
    result = policy.scan(endpoints, now=10 * 86400)
    assert result.probes == ("light",)
    assert [(a.endpoint, a.reason) for a in result.alerts] == [("meter", "stale")]
