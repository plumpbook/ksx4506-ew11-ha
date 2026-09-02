from pathlib import Path
import asyncio
import logging
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402
from .ha_stubs import install_homeassistant_stubs  # noqa: E402


def _bind_method(instance, name: str, method):
    bound_method = types.MethodType(method, instance)
    setattr(instance, name, bound_method)
    return bound_method


class _FakeCoordinator:
    def __init__(self, matched_frame, *, match_after_attempts=2):
        self.max_attempts = 3
        self._frame_waiters = []
        self._transaction_lock = asyncio.Lock()
        self.sent = []
        self._matched_frame = matched_frame
        self._match_after_attempts = match_after_attempts

    async def async_send_f7_command(self, dev_id, sub_id, cmd, payload, *, guard=False):
        self.sent.append((dev_id, sub_id, cmd, payload, guard))
        if len(self.sent) < self._match_after_attempts:
            return True

        for matcher, fut in tuple(self._frame_waiters):
            if not fut.done() and matcher(self._matched_frame):
                fut.set_result(self._matched_frame)
        return True

    async def _async_send_f7_command_unlocked(
        self, dev_id, sub_id, cmd, payload, *, guard=False
    ):
        return await self.async_send_f7_command(
            dev_id, sub_id, cmd, payload, guard=guard
        )

    async def _async_send_f7_command_until_unlocked(self, *args, **kwargs):
        coordinator_module = load_integration_module("coordinator")
        method = types.MethodType(
            coordinator_module.Ksx4506Coordinator._async_send_f7_command_until_unlocked,
            self,
        )
        return await method(*args, **kwargs)


class _FakeClient:
    def health_report(self):
        return {
            "state": "stale",
            "seconds_since_last_rx": 42.0,
            "last_error": "EW11 RX stale for 42.0s",
        }


def test_send_f7_command_until_logs_control_attempts(caplog):
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    matched = protocol_module.KsFrame(
        addr=0x39,
        sub_id=0x11,
        cmd=0xC1,
        payload=b"\x00\x01",
        checksum=0,
        raw=bytes.fromhex("f73911c10200011d22"),
    )
    fake = _FakeCoordinator(matched)
    send_until = _bind_method(
        fake,
        "async_send_f7_command_until",
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
    )

    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11.coordinator")

    result = asyncio.run(
        send_until(
            0x39,
            0x11,
            0x41,
            bytes.fromhex("DE AD BE EF"),
            lambda frame: frame.addr == 0x39
            and frame.sub_id == 0x11
            and frame.cmd == 0xC1,
        )
    )

    assert result is matched
    assert len(fake.sent) == 2
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "TX F7 control attempt dev=0x39 sub=0x11 cmd=0x41 attempt=1/3" in messages
    assert "TX F7 control wait timeout dev=0x39 sub=0x11 cmd=0x41 attempt=1/3" in messages
    assert "TX F7 control matched dev=0x39 sub=0x11 cmd=0x41 attempt=2/3" in messages
    assert "deadbeef" not in messages.lower()


def test_send_f7_command_until_give_up_log_omits_packet_samples(caplog):
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    matched = protocol_module.KsFrame(
        addr=0x39,
        sub_id=0x11,
        cmd=0x81,
        payload=b"",
        checksum=0,
        raw=b"",
    )
    fake = _FakeCoordinator(matched, match_after_attempts=99)
    fake.max_attempts = 1
    setattr(fake, "codec", protocol_module.Ksx4506Codec())
    setattr(fake, "_client", _FakeClient())
    send_until = _bind_method(
        fake,
        "async_send_f7_command_until",
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
    )

    caplog.set_level(logging.WARNING, logger="custom_components.ksx4506_ew11.coordinator")

    result = asyncio.run(
        send_until(
            0x0E,
            0x11,
            0x41,
            b"\x01\x01\x00",
            lambda frame: False,
        )
    )

    assert result is None
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "TX F7 control gave up dev=0x0E sub=0x11 cmd=0x41 attempts=1" in messages
    assert "payload_len=3" in messages
    assert "010100" not in messages
    assert "f70e114103010100aa06" not in messages
    assert "ew11_state=stale" in messages
    assert "seconds_since_last_rx=42.0" in messages


def test_send_f7_state_request_give_up_logs_at_debug_not_warning(caplog):
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    packet_quality_module = load_integration_module("packet_quality")
    protocol_module = load_integration_module("protocol")

    matched = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0x3F,
        cmd=0x81,
        payload=b"",
        checksum=0,
        raw=b"",
    )
    fake = _FakeCoordinator(matched, match_after_attempts=99)
    fake.max_attempts = 1
    monitor = packet_quality_module.PacketQualityMonitor()
    setattr(fake, "codec", protocol_module.Ksx4506Codec())
    setattr(fake, "_client", _FakeClient())
    setattr(fake, "packet_quality", monitor)
    send_until = _bind_method(
        fake,
        "async_send_f7_command_until",
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
    )

    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11.coordinator")

    result = asyncio.run(
        send_until(
            0x0E,
            0x3F,
            0x01,
            b"",
            lambda frame: False,
            interval=0,
        )
    )

    assert result is None
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "TX F7 state request gave up dev=0x0E sub=0x3F cmd=0x01" in messages
    report = monitor.report()
    assert report["state"] == "ok"
    assert report["tx"]["state_request_giveups"] == 1


def test_generic_control_without_state_confirmation_records_giveup():
    asyncio.run(_assert_generic_control_without_state_confirmation_records_giveup())


async def _assert_generic_control_without_state_confirmation_records_giveup():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    packet_quality_module = load_integration_module("packet_quality")

    class FakeClient:
        async def send_with_retry(self, _payload):
            return True

        def health_report(self):
            return {
                "state": "receiving",
                "seconds_since_last_rx": 0.1,
                "last_error": None,
            }

    fake = types.SimpleNamespace(
        _transaction_lock=asyncio.Lock(),
        _frame_waiters=[],
        _client=FakeClient(),
        codec=types.SimpleNamespace(build=lambda _addr, _cmd, _payload: b"command"),
        packet_quality=packet_quality_module.PacketQualityMonitor(),
        _publish_registry_state=lambda: None,
    )
    fake._async_send_command_unlocked = types.MethodType(
        coordinator_module.Ksx4506Coordinator._async_send_command_unlocked,
        fake,
    )
    send_and_confirm = types.MethodType(
        coordinator_module.Ksx4506Coordinator.async_send_command_and_confirm,
        fake,
    )

    result = await send_and_confirm(
        0x10,
        0x41,
        b"\x01",
        lambda _frame: False,
        confirmation_timeout=0,
    )

    assert result is None
    report = fake.packet_quality.report()
    assert report["tx"]["control_giveups"] == 1
    assert report["tx"]["last_giveup"]["device_id"] == "0x10"
    assert report["tx"]["last_giveup"]["command_type"] == "0x41"


def test_control_transactions_remain_serialized_through_state_confirmation():
    asyncio.run(_assert_control_transactions_remain_serialized())


async def _assert_control_transactions_remain_serialized():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")

    first_ack = types.SimpleNamespace(kind="first_ack")
    first_state = types.SimpleNamespace(kind="first_state")
    second_state = types.SimpleNamespace(kind="second_state")

    class FakeCoordinator:
        def __init__(self):
            self._transaction_lock = asyncio.Lock()
            self.calls = []
            self.first_status_started = asyncio.Event()
            self.release_first_status = asyncio.Event()

        async def _async_send_f7_command_until_unlocked(
            self,
            dev_id,
            sub_id,
            cmd,
            payload,
            _matcher,
            **_kwargs,
        ):
            self.calls.append((dev_id, sub_id, cmd, payload))
            if payload == b"first":
                return first_ack
            if payload == b"second":
                return second_state
            self.first_status_started.set()
            await self.release_first_status.wait()
            return first_state

    fake = FakeCoordinator()
    send_and_confirm = _bind_method(
        fake,
        "async_send_f7_command_and_confirm",
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_and_confirm,
    )
    first = asyncio.create_task(
        send_and_confirm(
            0x0E,
            0x11,
            0x41,
            b"first",
            lambda frame: frame.kind == "first_ack",
            status_sub_id=0x11,
            confirmation_matcher=lambda frame: frame.kind == "first_state",
            max_attempts=1,
            interval=0,
            confirmation_interval=0,
        )
    )
    await asyncio.wait_for(fake.first_status_started.wait(), timeout=1)

    second = asyncio.create_task(
        send_and_confirm(
            0x0E,
            0x12,
            0x41,
            b"second",
            lambda frame: frame.kind == "second_state",
            status_sub_id=0x12,
            confirmation_matcher=lambda frame: frame.kind == "second_state",
            max_attempts=1,
            interval=0,
            confirmation_interval=0,
        )
    )
    await asyncio.sleep(0)

    assert all(call[3] != b"second" for call in fake.calls)

    fake.release_first_status.set()
    assert await asyncio.wait_for(first, timeout=1) is first_state
    assert await asyncio.wait_for(second, timeout=1) is second_state
    assert [call[3] for call in fake.calls] == [b"first", b"", b"second"]


def test_meter_startup_probe_requests_whole_and_individual_meter_states():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")

    class FakeCoordinator:
        def __init__(self):
            self.state_requests = []

        async def async_request_f7_state(self, dev_id, sub_id):
            self.state_requests.append((dev_id, sub_id))
            return True

    fake = FakeCoordinator()
    probe_meter_states = _bind_method(
        fake,
        "async_probe_meter_states",
        coordinator_module.Ksx4506Coordinator.async_probe_meter_states,
    )

    asyncio.run(probe_meter_states(delay=0, interval=0))

    assert fake.state_requests == [
        (0x30, 0x0F),
        (0x30, 0x01),
        (0x30, 0x02),
        (0x30, 0x03),
        (0x30, 0x04),
        (0x30, 0x05),
    ]


def test_known_device_startup_probe_retries_until_status_response():
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    discovery_module = load_integration_module("discovery")
    protocol_module = load_integration_module("protocol")

    matched = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0x11,
        cmd=0x81,
        payload=b"\x00\x01\x00\x00",
        checksum=0,
        raw=bytes.fromhex("f70e11810400010000a5f6"),
    )
    fake = _FakeCoordinator(matched)
    registry = discovery_module.DeviceRegistry()
    setattr(fake, "registry", registry)
    registry.restore_device_from_key("0E11_light_1")
    _bind_method(
        fake,
        "async_send_f7_command_until",
        coordinator_module.Ksx4506Coordinator.async_send_f7_command_until,
    )
    _bind_method(
        fake,
        "async_request_f7_state_until",
        coordinator_module.Ksx4506Coordinator.async_request_f7_state_until,
    )
    probe_known_device_states = _bind_method(
        fake,
        "async_probe_known_device_states",
        coordinator_module.Ksx4506Coordinator.async_probe_known_device_states,
    )
    _bind_method(
        fake,
        "_known_state_request_targets",
        coordinator_module.Ksx4506Coordinator._known_state_request_targets,
    )

    asyncio.run(probe_known_device_states(delay=0, interval=0))

    assert fake.sent == [
        (0x0E, 0x11, 0x01, b"", False),
        (0x0E, 0x11, 0x01, b"", False),
    ]


def test_coordinator_publishes_registry_state_on_ew11_health_change():
    asyncio.run(_assert_coordinator_publishes_registry_state_on_ew11_health_change())


def test_coordinator_dispatches_removed_light_after_confirmed_topology(monkeypatch):
    install_homeassistant_stubs()
    const_module = load_integration_module("const")
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")
    dispatched = []

    monkeypatch.setattr(
        coordinator_module,
        "async_dispatcher_send",
        lambda hass, signal, dev_key: dispatched.append((signal, dev_key)),
    )

    class FakeCoordinator:
        def __init__(self):
            self.registry = coordinator_module.DeviceRegistry()
            self.registry.restore_device_from_key("0E15_light_1")
            self.registry.restore_device_from_key("0E15_light_2")
            self.hass = object()
            self.data = None
            self._last_published_device_states = {}

        def async_set_updated_data(self, data):
            self.data = data

        def _notify_frame_waiters(self, frame):
            _ = frame
            return None

    fake = FakeCoordinator()
    on_frame = _bind_method(
        fake,
        "_on_frame",
        coordinator_module.Ksx4506Coordinator._on_frame,
    )
    _bind_method(
        fake,
        "_publish_registry_state",
        coordinator_module.Ksx4506Coordinator._publish_registry_state,
    )
    _bind_method(
        fake,
        "_semantic_state_changes",
        coordinator_module.Ksx4506Coordinator._semantic_state_changes,
    )
    frame = protocol_module.KsFrame(
        addr=0x0E,
        sub_id=0x15,
        cmd=0x81,
        payload=bytes.fromhex("00 01"),
        checksum=0,
        raw=b"",
    )

    asyncio.run(on_frame(frame))
    asyncio.run(on_frame(frame))

    assert (
        const_module.SIGNAL_DEVICE_REMOVED,
        "0E15_light_2",
    ) in dispatched


async def _assert_coordinator_publishes_registry_state_on_ew11_health_change():
    install_homeassistant_stubs()
    const_module = load_integration_module("const")
    coordinator_module = load_integration_module("coordinator")

    coordinator = coordinator_module.Ksx4506Coordinator(
        object(),
        {
            const_module.CONF_HOST: "ew11.example.invalid",
            const_module.CONF_PORT: 8899,
            const_module.CONF_TIMEOUT: 3.0,
            const_module.CONF_RETRY: 2,
            const_module.CONF_STX: const_module.DEFAULT_STX,
            const_module.CONF_ETX: const_module.DEFAULT_ETX,
            const_module.CONF_CHECKSUM: const_module.DEFAULT_CHECKSUM,
        },
    )
    coordinator.registry.devices["light:sample"] = types.SimpleNamespace(
        state={"is_on": True}
    )

    coordinator._client._mark_connected()

    assert coordinator.data == {"light:sample": {"is_on": True}}


def test_common_entrance_call_info_log_does_not_expose_raw_packet(caplog):
    install_homeassistant_stubs()
    coordinator_module = load_integration_module("coordinator")
    protocol_module = load_integration_module("protocol")

    class FakeCoordinator:
        def __init__(self):
            self.registry = coordinator_module.DeviceRegistry()
            self.hass = object()
            self.data = None
            self._last_published_device_states = {}

        def async_set_updated_data(self, data):
            self.data = data

        def _notify_frame_waiters(self, frame):
            _ = frame
            return None

    fake = FakeCoordinator()
    on_frame = _bind_method(
        fake,
        "_on_frame",
        coordinator_module.Ksx4506Coordinator._on_frame,
    )
    _bind_method(
        fake,
        "_publish_registry_state",
        coordinator_module.Ksx4506Coordinator._publish_registry_state,
    )
    _bind_method(
        fake,
        "_semantic_state_changes",
        coordinator_module.Ksx4506Coordinator._semantic_state_changes,
    )
    frame = protocol_module.KsFrame(
        addr=0x40,
        sub_id=0x02,
        cmd=0x10,
        payload=bytes.fromhex("62 02 00 00 00 00"),
        checksum=0,
        raw=bytes.fromhex("F7 40 02 10 06 62 02 00 00 00 00 C3 76"),
    )

    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11.coordinator")

    asyncio.run(on_frame(frame))

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "Common entrance call event sub=0x02 detected=True" in messages
    assert "F740021006620200000000C376" not in messages.upper()
    assert "620200000000" not in messages
