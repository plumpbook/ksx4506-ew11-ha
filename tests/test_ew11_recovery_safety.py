"""Transport recovery proofs use fake streams, virtual waits and no network."""
import asyncio

import pytest

from ._integration_loader import load_integration_module


def _client():
    module = load_integration_module("ew11_client")
    codec = load_integration_module("protocol").Ksx4506Codec()

    async def on_frame(frame):
        return None

    return module, module.Ew11Client("ew11.example.invalid", 8899, 0.1, 0, codec, on_frame)


@pytest.mark.parametrize("connected", [True, False])
def test_repeated_eof_and_connect_failure_share_exponential_backoff(monkeypatch, connected):
    async def scenario():
        module, client = _client()
        delays = []

        class Reader:
            async def read(self, size):
                return b""

        class Writer:
            def close(self):
                return None

            async def wait_closed(self):
                return None

        async def connect(host, port):
            if not connected:
                raise ConnectionRefusedError("synthetic failure")
            return Reader(), Writer()

        async def virtual_wait(delay):
            delays.append(delay)
            if len(delays) == 8:
                client._running = False

        monkeypatch.setattr(module.asyncio, "open_connection", connect)
        monkeypatch.setattr(module.asyncio, "sleep", virtual_wait)
        client._running = True
        await client._run_loop()
        assert delays == [1, 2, 4, 8, 16, 32, 60, 60]
        assert client.health_report()["consecutive_connection_failures"] == 8

    asyncio.run(scenario())


def test_quiet_and_low_traffic_connections_need_fault_evidence_before_reconnect():
    module, client = _client()
    client._mark_connected()
    assert client._connected_monotonic is not None
    client._connected_monotonic -= 121
    assert not client._should_reconnect_for_rx_silence()
    # A once-active but quiet link is also not proof of failure.
    client._mark_rx()
    assert client._last_rx_monotonic is not None
    client._last_rx_monotonic -= 121
    assert not client._should_reconnect_for_rx_silence()
    for _ in range(2):
        client.record_response_timeout()
    assert not client._should_reconnect_for_rx_silence()
    client.record_response_timeout()
    assert client._should_reconnect_for_rx_silence()
    client._mark_rx()
    assert not client._should_reconnect_for_rx_silence()


def test_noise_without_valid_frames_can_trigger_bounded_socket_recovery():
    module, client = _client()
    client._mark_connected()
    assert client._connected_monotonic is not None
    client._connected_monotonic -= 121
    client._unvalidated_rx = True
    assert client._should_reconnect_for_rx_silence()
    assert client.health_report()["rx_fault_evidence"] == "unvalidated_bytes"


def _run_quiet_stream(monkeypatch, chunks, *, response_failures=0, expire_at_read=None):
    async def scenario():
        module, client = _client()
        pending = list(chunks)
        frames = []
        reads = 0

        async def on_frame(frame):
            frames.append(frame.raw)

        class Reader:
            async def read(self, size):
                nonlocal reads
                reads += 1
                if reads == 3:
                    for _ in range(response_failures):
                        client.record_response_timeout()
                if reads == expire_at_read:
                    assert client._codec._fragment_started is not None
                    client._codec._fragment_started -= 31
                if not pending:
                    return b""
                chunk = pending.pop(0)
                if chunk is None:
                    raise TimeoutError("synthetic idle read")
                return chunk

        class Writer:
            def close(self):
                return None

            async def wait_closed(self):
                return None

        async def connect(host, port):
            return Reader(), Writer()

        async def virtual_wait(delay):
            client._running = False

        mark_connected = client._mark_connected

        def mark_quiet():
            mark_connected()
            assert client._connected_monotonic is not None
            client._connected_monotonic -= 121

        monkeypatch.setattr(module.asyncio, "open_connection", connect)
        monkeypatch.setattr(module.asyncio, "sleep", virtual_wait)
        client._mark_connected = mark_quiet
        client._on_frame = on_frame
        client._running = True
        await client._run_loop()
        return frames, pending, reads, client.health_report()

    return asyncio.run(scenario())


@pytest.mark.parametrize("framing", ["f7", "stx"])
@pytest.mark.parametrize("response_failures", [0, 3])
def test_quiet_stream_preserves_every_split_and_bytewise_frame(
    monkeypatch, framing, response_failures
):
    _, client = _client()
    packets = ([client._codec.build_f7(0x0E, 0x11, 0x81, payload)
                for payload in (b"\x00\x01", b"\x00\x01\x02\xf7")]
               if framing == "f7" else
               [client._codec.build(0x11, 0x22, payload)
                for payload in (b"\x01", b"\x02\xf7\x01")])
    for packet in packets:
        plans = [[packet[:split], None, packet[split:]] for split in range(1, len(packet))]
        plans.extend([[packet], [bytes([byte]) for byte in packet]])
        for chunks in plans:
            frames, pending, reads, report = _run_quiet_stream(
                monkeypatch, [None, None, *chunks], response_failures=response_failures
            )
            assert frames == [packet], f"{framing} chunks={chunks!r}"
            assert pending == []
            assert reads == len(chunks) + 3  # Two quiet reads and final synthetic EOF.
            assert "connection closed" in report["last_error"]
            assert report["rx_fault_evidence"] == "none"


@pytest.mark.parametrize("framing", ["f7", "stx"])
def test_quiet_stream_recovers_only_after_partial_assembly_expires(monkeypatch, framing):
    _, client = _client()
    packet = (client._codec.build_f7(0x0E, 0x11, 0x81, b"\x00\x01")
              if framing == "f7" else client._codec.build(0x11, 0x22, b"\x01"))
    frames, pending, reads, report = _run_quiet_stream(
        monkeypatch, [packet[:-1], None, packet[-1:]], expire_at_read=2
    )
    assert frames == []
    assert reads == 2
    assert pending == [packet[-1:]]
    assert "RX stale" in report["last_error"]
    assert report["rx_fault_evidence"] == "assembly_timeout"


@pytest.mark.parametrize("bad_input,expire_at", [
    (b"\x99\x55\x00", None),  # Bytes without a protocol header.
    (b"\xf7\x36\x11\x81\x01\x00\x51\x02", 2),  # Bad XOR + ambiguous STX.
    (b"\x02\x11\x22\x01\x01\x00\x03", None),  # Failed STX checksum.
])
def test_quiet_stream_rejects_noise_and_bad_checksums_before_recovery(
    monkeypatch, bad_input, expire_at
):
    frames, pending, reads, report = _run_quiet_stream(
        monkeypatch, [bad_input, None], expire_at_read=expire_at
    )
    assert frames == []
    assert reads == (expire_at or 1)
    assert report["rx_fault_evidence"] == (
        "assembly_timeout" if expire_at else "unvalidated_bytes"
    )
    assert "no valid frames" in report["last_error"] or "RX stale" in report["last_error"]


def test_repeated_new_headers_cannot_extend_expired_assembly_forever(monkeypatch):
    frames, pending, reads, report = _run_quiet_stream(
        monkeypatch, [b"\xf7", b"\x02", b"\xf7"], expire_at_read=2
    )
    assert frames == []
    assert reads == 2
    assert pending == [b"\xf7"]
    assert report["rx_fault_evidence"] == "assembly_timeout"


def test_stop_wins_over_reconnect_and_leaves_no_orphan_tasks():
    async def scenario():
        module, client = _client()
        cancelled = asyncio.Event()
        release = asyncio.Event()
        created = []

        async def run():
            created.append(asyncio.current_task())
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
                raise

        async def worker():
            created.append(asyncio.current_task())
            await asyncio.Event().wait()

        monkey_run, monkey_worker = client._run_loop, client._command_worker
        client._run_loop, client._command_worker = run, worker
        try:
            await client.start()
            await asyncio.sleep(0)
            reconnect = asyncio.create_task(client.async_reconnect())
            await cancelled.wait()
            stop = asyncio.create_task(client.stop())
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(reconnect, stop)
            assert not client._running
            assert client._task is None and client._worker_task is None
            assert all(task.done() for task in created)
            # A reconnect request after shutdown cannot start a new client.
            await client.async_reconnect()
            assert not client._running
        finally:
            release.set()
            await client.stop()
            client._run_loop, client._command_worker = monkey_run, monkey_worker

    asyncio.run(scenario())
