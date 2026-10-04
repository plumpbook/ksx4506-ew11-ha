"""Synthetic byte-stream fixtures; no production packet capture is required."""
import random

from ._integration_loader import load_integration_module


def _codec():
    return load_integration_module("protocol").Ksx4506Codec()


def test_f7_header_bytes_in_address_and_payload_survive_every_tcp_split():
    builder = _codec()
    packets = [
        builder.build_f7(0x02, 0x11, 0x81, b"\x00\x01\x02\xf7\x03\x04"),
        builder.build_f7(0x36, 0x1F, 0x81, b"\x00\x02\xf7\x03\x04\x05"),
    ]
    for packet in packets:
        for split in range(1, len(packet)):
            codec = _codec()
            frames = codec.feed(packet[:split]) + codec.feed(packet[split:])
            assert [frame.raw for frame in frames] == [packet], f"split={split}"


def test_stx_header_bytes_in_payload_survive_every_tcp_split():
    packet = _codec().build(0x11, 0x22, b"\x01\x02\xf7\x03\x04\x05")
    for split in range(1, len(packet)):
        codec = _codec()
        frames = codec.feed(packet[:split]) + codec.feed(packet[split:])
        assert [frame.raw for frame in frames] == [packet], f"split={split}"


def test_corrupt_length_does_not_discard_a_split_valid_successor():
    packet = _codec().build_f7(0x0E, 0x11, 0x81, b"\x00\x01")
    # The corrupt prefix claims 255 data bytes; the actual next frame is shorter.
    prefix = b"\xf7\x36\x1f\x81\xff\x00\x00"
    codec = _codec()
    assert codec.feed(prefix + packet[:6]) == []
    assert codec.feed(packet[6:]) == []
    # Only once the claimed candidate is complete can checksum failure prove
    # that the inner header may be a successor instead of ordinary payload.
    assert [f.raw for f in codec.feed(b"\x00" * 262)] == [packet]


def test_checksum_valid_nested_frame_remains_outer_payload_through_read_timeouts():
    builder = _codec()
    nested = builder.build_f7(0x0E, 0x11, 0x81, b"\x00\x01")
    packets = [builder.build_f7(0x30, 0x01, 0x81, nested + b"\x00" * 5),
               builder.build(0x11, 0x22, nested + b"\x00" * 5)]
    for packet in packets:
        for split in range(1, len(packet)):
            codec = _codec()
            frames = codec.feed(packet[:split])
            assert not codec.expire_partial_frame()
            frames += codec.feed(b"") + codec.feed(packet[split:])
            assert [f.raw for f in frames] == [packet], f"split={split}"


def test_expired_fragment_never_promotes_embedded_payload_to_response():
    builder = _codec()
    nested = builder.build_f7(0x12, 0x01, 0x81, b"\x00\x02")
    for packet in (builder.build_f7(0x60, 0x01, 0x81, nested + b"\x00" * 10),
                   builder.build(0x11, 0x22, nested + b"\x00" * 10)):
        codec = _codec()
        assert codec.feed(packet[:-5]) == []
        assert codec._fragment_started is not None
        codec._fragment_started -= 31
        assert codec.expire_partial_frame()
        assert codec.feed(b"") == []
        assert [f.raw for f in codec.feed(nested)] == [nested]


def test_empty_stx_payload_roundtrip():
    packet = _codec().build(0x11, 0x22, b"")
    assert [f.raw for f in _codec().feed(packet)] == [packet]


def test_random_chunking_noise_and_duplicate_frames_preserve_valid_frames():
    rng = random.Random(4506)
    builder = _codec()
    for _ in range(100):
        packets = [builder.build_f7(0x0E, 0x11, 0x81,
                                   bytes(rng.randrange(256) for _ in range(16)))
                   for _ in range(3)]
        packets.append(packets[-1])
        stream = b"\x99\x00\x55".join(packets)
        codec = _codec()
        frames = []
        while stream:
            size = rng.randint(1, 12)
            frames.extend(codec.feed(stream[:size]))
            stream = stream[size:]
        assert [f.raw for f in frames] == packets


def test_reconnect_drops_partial_frame_without_combining_streams():
    packet = _codec().build_f7(0x36, 0x1F, 0x81, b"\x00\x02\xf7\x03\x04\x05")
    codec = _codec()
    assert codec.feed(packet[:8]) == []
    codec.reset_stream()
    assert [f.raw for f in codec.feed(packet)] == [packet]
