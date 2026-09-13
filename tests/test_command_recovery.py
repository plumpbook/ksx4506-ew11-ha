import asyncio  # noqa: ANYIO_OK - exercises the HA event loop

from ._integration_loader import load_integration_module

recovery = load_integration_module("recovery")
KsFrame = load_integration_module("protocol_types").KsFrame


def frame(payload=b"\x00\x00\x01"):
    return KsFrame(0x0E, 0x81, payload, 0, b"", 0x11)


def test_failed_channel_is_not_cleared_by_sibling_or_ack():
    async def scenario():
        monitor = recovery.CommandRecovery(lambda: None, delays=())

        async def fail():
            return None

        matcher = lambda f: f.cmd == 0x81 and len(f.payload) == 3 and f.payload[2] == 0
        await monitor.execute("light_3", (14, 17), matcher, fail)
        assert not monitor.observe(frame())
        assert monitor.attributes("light_3")["control_status"] == "failed"
        assert monitor.observe(frame(b"\x00\x00\x00"))
        assert monitor.attributes("light_3")["control_status"] == "healthy"

    asyncio.run(scenario())


def test_probe_confirms_delayed_command_without_replay():
    async def scenario():
        monitor = recovery.CommandRecovery(lambda: None, delays=(0, 0))
        calls = []
        expected = frame()

        async def send():
            calls.append("send")
            return None

        async def probe():
            calls.append("probe")
            return expected

        result = await monitor.execute("light_3", (14, 17), lambda f: f is expected, send, probe)
        assert result is expected
        assert calls == ["send", "probe"]

    asyncio.run(scenario())


def test_latest_command_cancels_prior_and_keeps_latest_status():
    async def scenario():
        monitor = recovery.CommandRecovery(lambda: None)
        entered = asyncio.Event()
        stopped = asyncio.Event()
        expected = frame()

        async def old():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def new():
            await stopped.wait()
            return expected

        first = asyncio.create_task(monitor.execute("same", (14, 17), lambda f: False, old))
        await entered.wait()
        assert await monitor.execute("same", (14, 17), lambda f: f is expected, new) is expected
        assert await first is None
        assert monitor.attributes("same")["control_status"] == "healthy"
        assert not monitor._tasks

    asyncio.run(scenario())


def test_deadline_cancels_blocked_command_and_retains_failure():
    async def scenario():
        monitor = recovery.CommandRecovery(lambda: None, deadline=0.01)
        cancelled = asyncio.Event()

        async def blocked():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        assert await monitor.execute("light", (14, 17), lambda f: False, blocked) is None
        assert cancelled.is_set()
        assert monitor.attributes("light")["control_error"] == "command_expired"
        assert monitor.failed_endpoints() == {(14, 17)}

    asyncio.run(scenario())


def test_pause_rejects_commands_without_sending_and_resume_allows_new():
    async def scenario():
        monitor = recovery.CommandRecovery(lambda: None)
        sent = []
        expected = frame()

        async def send():
            sent.append(True)
            return expected

        await monitor.stop()
        assert await monitor.execute("light", (14, 17), lambda f: True, send) is None
        assert sent == []
        monitor.resume()
        assert await monitor.execute("light", (14, 17), lambda f: True, send) is expected

    asyncio.run(scenario())


def test_guarded_operation_has_no_additional_retries():
    async def scenario():
        monitor = recovery.CommandRecovery(lambda: None, delays=(0, 0))
        sent = []

        async def send():
            sent.append(True)
            return None

        await monitor.execute("gas", (18, 17), lambda f: False, send, retry=False)
        assert sent == [True]

    asyncio.run(scenario())


def test_hub_needs_independent_endpoints_and_rate_limits_power():
    policy = recovery.HubRecoveryPolicy()

    def step(now, count=2, responders=0):
        return policy.action(now=now, link_failed=False, failed_endpoints=count,
                             responders=responders, power_enabled=True)

    assert step(0, count=1) is None
    assert step(1) is None
    assert step(31) == "reconnect"
    assert step(150) is None
    assert step(151, responders=1) is None
    assert step(152) == "power_cycle"
    assert step(400) is None
    assert policy.state == "failed"
