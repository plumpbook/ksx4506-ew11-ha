from pathlib import Path
import asyncio  # noqa: ANYIO_OK
from datetime import datetime, timezone
import logging
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ._integration_loader import load_integration_module  # noqa: E402


def test_ew11_client_reports_disconnected_before_start():
    asyncio.run(_assert_disconnected_before_start())


def test_ew11_client_reports_not_running_command_failure():
    asyncio.run(_assert_not_running_command_failure_is_reported())


def test_ew11_client_notifies_each_command_result_change():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    async def on_frame(_frame):
        return None

    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=3.0,
        retry=2,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )
    notifications = []
    client.set_health_listener(lambda: notifications.append(True))

    client._record_tx_result(status="not_running", attempts=0, error="first")
    client._record_tx_result(status="queue_full", attempts=0, error="second")

    assert len(notifications) == 2


async def _assert_not_running_command_failure_is_reported():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    async def on_frame(_frame):
        return None

    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=3.0,
        retry=2,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )

    assert await client.send_with_retry(b"command") is False
    report = client.health_report()

    assert report["last_tx_status"] == "not_running"
    assert report["last_tx_error"] == "EW11 client is not running"


async def _assert_disconnected_before_start():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    async def on_frame(_frame):
        return None

    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=3.0,
        retry=2,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )

    report = client.health_report()

    assert report["state"] == "disconnected"
    assert report["connected"] is False
    assert report["rx_stale_after"] == 20.0
    assert report["last_rx_at"] is None
    assert report["seconds_since_last_rx"] is None


def test_ew11_client_reports_no_rx_for_new_connection_after_previous_rx():
    asyncio.run(_assert_no_rx_for_new_connection_after_previous_rx())


async def _assert_no_rx_for_new_connection_after_previous_rx():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    async def on_frame(_frame):
        return None

    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=3.0,
        retry=2,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )
    client._last_rx_at = datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc)
    client._mark_connected()

    report = client.health_report()

    assert report["state"] == "connected_no_rx"
    assert report["last_rx_at"] == "2026-06-14T10:00:00+00:00"


def test_ew11_client_keeps_connection_open_when_rx_is_stale(monkeypatch):
    asyncio.run(_assert_connection_stays_open_when_rx_is_stale(monkeypatch))


def test_ew11_client_closes_connection_when_rx_reconnect_threshold_is_exceeded(monkeypatch):
    asyncio.run(_assert_connection_closes_when_rx_reconnect_threshold_is_exceeded(monkeypatch))


def test_ew11_client_notifies_health_changes_without_rx_frames(monkeypatch):
    asyncio.run(_assert_health_change_notifications_without_rx_frames(monkeypatch))


def test_ew11_client_does_not_mark_invalid_chunks_as_rx(monkeypatch):
    asyncio.run(_assert_invalid_chunks_do_not_mark_valid_rx(monkeypatch))


def test_ew11_client_tracks_disconnect_history():
    asyncio.run(_assert_disconnect_history_is_tracked())


def test_timed_out_queued_command_is_not_sent_later():
    asyncio.run(_assert_timed_out_queued_command_is_not_sent_later())


def test_stalled_drain_is_aborted_and_returns_failure():
    asyncio.run(_assert_stalled_drain_is_aborted_and_returns_failure())


def test_stop_resolves_an_active_command_and_awaits_worker():
    asyncio.run(_assert_stop_resolves_an_active_command_and_awaits_worker())


def test_client_exchanges_frames_over_loopback_tcp(caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11")
    asyncio.run(_assert_client_exchanges_frames_over_loopback_tcp())

    messages = "\n".join(record.getMessage() for record in caplog.records).lower()
    assert "f70e1101001e2d" not in messages
    assert "f70e11810200016a04" not in messages


async def _assert_connection_stays_open_when_rx_is_stale(monkeypatch):
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class NeverReceivingReader:
        async def read(self, _size):
            await asyncio.sleep(60)
            return b""

    class FakeWriter:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            return None

    reader = NeverReceivingReader()
    writer = FakeWriter()

    async def open_connection(_host, _port):
        return reader, writer

    async def on_frame(_frame):
        return None

    monkeypatch.setattr(ew11_client.asyncio, "open_connection", open_connection)
    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=0.01,
        retry=0,
        rx_stale_after=0.02,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )

    await client.start()
    try:
        await asyncio.sleep(0.08)
        report = client.health_report()

        assert report["state"] == "stale"
        assert report["connected"] is True
        assert report["last_error"] is None
        assert writer.closed is False
    finally:
        await client.stop()


async def _assert_health_change_notifications_without_rx_frames(monkeypatch):
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class NeverReceivingReader:
        async def read(self, _size):
            await asyncio.sleep(60)
            return b""

    class FakeWriter:
        def close(self):
            return None

        async def wait_closed(self):
            return None

    reader = NeverReceivingReader()
    writer = FakeWriter()

    async def open_connection(_host, _port):
        return reader, writer

    async def on_frame(_frame):
        return None

    health_states = []

    def on_health_change():
        health_states.append(client.health_report()["state"])

    monkeypatch.setattr(ew11_client, "DEFAULT_RX_RECONNECT_AFTER", 0.04)
    monkeypatch.setattr(ew11_client.asyncio, "open_connection", open_connection)
    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=0.01,
        retry=0,
        rx_stale_after=0.02,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )
    client.set_health_listener(on_health_change)

    await client.start()
    try:
        await asyncio.sleep(0.08)

        assert "connected_no_rx" in health_states
        assert "stale" in health_states
        assert "disconnected" in health_states
    finally:
        await client.stop()


async def _assert_invalid_chunks_do_not_mark_valid_rx(monkeypatch):
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class InvalidFrameReader:
        def __init__(self):
            self.read_event = asyncio.Event()
            self.reads = 0

        async def read(self, _size):
            if self.reads == 0:
                self.reads += 1
                self.read_event.set()
                return bytes.fromhex("f70e13810200006984")
            await asyncio.sleep(60)
            return b""

    class FakeWriter:
        def close(self):
            return None

        async def wait_closed(self):
            return None

    reader = InvalidFrameReader()
    writer = FakeWriter()

    async def open_connection(_host, _port):
        return reader, writer

    async def on_frame(_frame):
        return None

    monkeypatch.setattr(ew11_client.asyncio, "open_connection", open_connection)
    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=0.05,
        retry=0,
        rx_stale_after=1.0,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )

    await client.start()
    try:
        await asyncio.wait_for(reader.read_event.wait(), timeout=1)
        await asyncio.sleep(0)
        report = client.health_report()

        assert report["state"] == "connected_no_rx"
        assert report["last_rx_at"] is None
        assert report["seconds_since_last_rx"] is None
    finally:
        await client.stop()


async def _assert_disconnect_history_is_tracked():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    async def on_frame(_frame):
        return None

    def new_client():
        return ew11_client.Ew11Client(
            "ew11.example.invalid", 8899, 3.0, 2, protocol.Ksx4506Codec(), on_frame
        )

    client = new_client()
    client._mark_connected()
    await client._close(
        reason="EW11 connection closed",
        count_disconnect=True,
    )

    report = client.health_report()

    assert report["disconnect_count"] == 1
    assert report["last_disconnect_at"] is not None
    assert report["last_disconnect_reason"] == "EW11 connection closed"
    assert report["last_connected_duration_seconds"] is not None

    planned_stop_client = new_client()
    planned_stop_client._mark_connected()
    await planned_stop_client.stop()
    planned_stop_report = planned_stop_client.health_report()
    assert planned_stop_report["disconnect_count"] == 0
    assert planned_stop_report["last_disconnect_at"] is None


async def _assert_timed_out_queued_command_is_not_sent_later():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class FakeWriter:
        def __init__(self):
            self.writes = []

        def write(self, payload):
            self.writes.append(payload)

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def on_frame(_frame):
        return None

    writer = FakeWriter()
    client = ew11_client.Ew11Client(
        "ew11.example.invalid", 8899, 0.1, 0, protocol.Ksx4506Codec(), on_frame
    )
    client._running = True
    client._writer = writer
    client._command_timeout = lambda: 0.01

    assert await client.send_with_retry(b"expired") is False

    client._worker_task = asyncio.create_task(client._command_worker())
    await asyncio.wait_for(client._cmd_queue.join(), timeout=1)
    await client.stop()

    assert writer.writes == []


async def _assert_stalled_drain_is_aborted_and_returns_failure():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class FakeTransport:
        def __init__(self):
            self.aborted = False

        def abort(self):
            self.aborted = True

    class FakeWriter:
        def __init__(self):
            self.transport = FakeTransport()
            self.drain_started = asyncio.Event()

        def write(self, _payload):
            return None

        async def drain(self):
            self.drain_started.set()
            await asyncio.Event().wait()

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def on_frame(_frame):
        return None

    writer = FakeWriter()
    client = ew11_client.Ew11Client(
        "ew11.example.invalid", 8899, 0.01, 0, protocol.Ksx4506Codec(), on_frame
    )
    client._running = True
    client._writer = writer
    client._worker_task = asyncio.create_task(client._command_worker())

    result = await asyncio.wait_for(client.send_with_retry(b"blocked"), timeout=1)
    await client.stop()

    assert result is False
    assert writer.transport.aborted is True


async def _assert_stop_resolves_an_active_command_and_awaits_worker():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class FakeWriter:
        def __init__(self):
            self.drain_started = asyncio.Event()

        def write(self, _payload):
            return None

        async def drain(self):
            self.drain_started.set()
            await asyncio.Event().wait()

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def on_frame(_frame):
        return None

    writer = FakeWriter()
    client = ew11_client.Ew11Client(
        "ew11.example.invalid", 8899, 60.0, 0, protocol.Ksx4506Codec(), on_frame
    )
    client._running = True
    client._writer = writer
    client._worker_task = asyncio.create_task(client._command_worker())
    send_task = asyncio.create_task(client.send_with_retry(b"active"))
    await asyncio.wait_for(writer.drain_started.wait(), timeout=1)

    await asyncio.wait_for(client.stop(), timeout=1)

    assert await send_task is False
    assert client._worker_task is None


async def _assert_client_exchanges_frames_over_loopback_tcp():
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")
    command = bytes.fromhex("F70E1101001E2D")
    response = protocol.Ksx4506Codec().build_f7(0x0E, 0x11, 0x81, b"\x00\x01")
    received_packet = asyncio.get_running_loop().create_future()
    received_frame = asyncio.get_running_loop().create_future()
    handler_done = asyncio.Event()

    async def handle_connection(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            received_packet.set_result(await reader.readexactly(len(command)))
            writer.write(response)
            await writer.drain()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            handler_done.set()

    server = await asyncio.start_server(
        handle_connection,
        host="localhost",
        port=0,
        family=socket.AF_INET,
    )
    server_socket = server.sockets[0]
    host, port = server_socket.getsockname()[:2]

    async def on_frame(frame) -> None:
        if not received_frame.done():
            received_frame.set_result(frame)

    client = ew11_client.Ew11Client(
        host,
        port,
        0.5,
        0,
        protocol.Ksx4506Codec(),
        on_frame,
    )
    try:
        await client.start()
        assert await asyncio.wait_for(client.send_with_retry(command), timeout=2)
        assert await asyncio.wait_for(received_packet, timeout=2) == command
        frame = await asyncio.wait_for(received_frame, timeout=2)
        assert (frame.addr, frame.sub_id, frame.cmd, frame.payload) == (
            0x0E,
            0x11,
            0x81,
            b"\x00\x01",
        )
        assert client.health_report()["state"] == "receiving"
    finally:
        await client.stop()
        await asyncio.wait_for(handler_done.wait(), timeout=2)
        server.close()
        await server.wait_closed()


async def _assert_connection_closes_when_rx_reconnect_threshold_is_exceeded(monkeypatch):
    ew11_client = load_integration_module("ew11_client")
    protocol = load_integration_module("protocol")

    class NeverReceivingReader:
        async def read(self, _size):
            await asyncio.sleep(60)
            return b""

    class FakeWriter:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            return None

    reader = NeverReceivingReader()
    writer = FakeWriter()

    async def open_connection(_host, _port):
        return reader, writer

    async def on_frame(_frame):
        return None

    monkeypatch.setattr(ew11_client, "DEFAULT_RX_RECONNECT_AFTER", 0.04)
    monkeypatch.setattr(ew11_client.asyncio, "open_connection", open_connection)
    client = ew11_client.Ew11Client(
        host="ew11.example.invalid",
        port=8899,
        timeout=0.01,
        retry=0,
        rx_stale_after=0.02,
        codec=protocol.Ksx4506Codec(),
        on_frame=on_frame,
    )

    await client.start()
    try:
        await asyncio.sleep(0.08)
        report = client.health_report()

        assert writer.closed is True
        assert report["state"] == "disconnected"
        assert "EW11 RX stale" in report["last_error"]
        assert report["rx_reconnect_after"] == 0.04
    finally:
        await client.stop()
