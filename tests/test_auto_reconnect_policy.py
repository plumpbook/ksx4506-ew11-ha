from ._integration_loader import load_integration_module


def _endpoint(key, response=1000):
    return (key, response)


def test_complete_response_outage_reconnects_once_and_requires_two_confirmed_recoveries():
    policy = load_integration_module("auto_reconnect").AutoReconnectPolicy()
    endpoints = (_endpoint("0x0E/0x11"), _endpoint("0x39/0x11"),
                 _endpoint("0x60/0x01"))
    failed = {key for key, _ in endpoints}
    assert not policy.evaluate(endpoints, failed, now=1200, connected=True, busy=False)
    assert not policy.evaluate(endpoints, failed, now=1379, connected=True, busy=False)
    assert not policy.evaluate(endpoints, failed, now=1380, connected=True, busy=True)
    assert policy.evaluate(endpoints, failed, now=1381, connected=True, busy=False)
    assert not policy.evaluate(endpoints, failed, now=2000, connected=True, busy=False)
    policy.evaluate((_endpoint("0x0E/0x11", 2001), *endpoints[1:]),
                    failed - {"0x0E/0x11"}, now=2001, connected=True, busy=False)
    assert policy.attempted_at == 1381
    policy.evaluate((_endpoint("0x0E/0x11", 2001), _endpoint("0x39/0x11", 2002),
                     endpoints[2]), failed - {"0x0E/0x11", "0x39/0x11"},
                    now=2002, connected=True, busy=False)
    assert policy.attempted_at is None
    assert policy.verified_at == 2002


def test_partial_failure_and_old_baselines_never_reconnect():
    policy = load_integration_module("auto_reconnect").AutoReconnectPolicy()
    endpoints = (_endpoint("0x0E/0x11"), _endpoint("0x39/0x11"),
                 _endpoint("0x60/0x01"))
    for now in (1200, 1500, 2000):
        assert not policy.evaluate(endpoints, {endpoints[0][0], endpoints[1][0]},
                                   now=now, connected=True, busy=False)
    old = tuple(_endpoint(key, 100) for key, _ in endpoints)
    assert not policy.evaluate(old, {key for key, _ in old},
                               now=100000, connected=True, busy=False)


def test_reload_does_not_repeat_reconnect_during_same_outage():
    cls = load_integration_module("auto_reconnect").AutoReconnectPolicy
    endpoints = (_endpoint("0x0E/0x11"), _endpoint("0x39/0x11"),
                 _endpoint("0x60/0x01"))
    failed = {key for key, _ in endpoints}
    policy = cls()
    policy.evaluate(endpoints, failed, now=1200, connected=True, busy=False)
    assert policy.evaluate(endpoints, failed, now=1380, connected=True, busy=False)
    restored = cls(incident_started_at=policy.incident_started_at,
                   attempted_at=policy.attempted_at)
    assert not restored.evaluate(endpoints, failed, now=100000,
                                 connected=True, busy=False)
