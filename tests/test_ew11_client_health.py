from pathlib import Path
import asyncio  # noqa: ANYIO_OK
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402


def test_ew11_client_reports_disconnected_before_start():
    asyncio.run(_assert_disconnected_before_start())


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
