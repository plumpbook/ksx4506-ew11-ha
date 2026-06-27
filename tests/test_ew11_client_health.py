from pathlib import Path
import asyncio
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
    assert report["rx_stale_after"] == 120.0
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
