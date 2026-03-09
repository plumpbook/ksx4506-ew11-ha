from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


_PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "ksx4506_ew11" / "protocol.py"
_spec = spec_from_file_location("ksx4506_protocol", _PROTOCOL_PATH)
_module = module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
Ksx4506Codec = _module.Ksx4506Codec


def test_build_and_parse_sum8():
    c = Ksx4506Codec(checksum_mode="sum8")
    pkt = c.build(addr=0x11, cmd=0x22, payload=b"\x01\x02")
    frames = c.feed(pkt)
    assert len(frames) == 1
    f = frames[0]
    assert f.addr == 0x11
    assert f.cmd == 0x22
    assert f.payload == b"\x01\x02"


def test_bad_checksum_dropped():
    c = Ksx4506Codec()
    pkt = bytearray(c.build(0x11, 0x22, b"\x01"))
    pkt[-2] ^= 0xFF
    assert c.feed(bytes(pkt)) == []


def _build_f7(dev: int, sub: int, cmd: int, payload: bytes) -> bytes:
    src = [0xF7, dev & 0xFF, sub & 0xFF, cmd & 0xFF, len(payload) & 0xFF, *payload]
    x = 0
    for v in src:
        x ^= v & 0xFF
    x &= 0xFF

    a = 0
    for v in [*src, x]:
        a = (a + (v & 0xFF)) & 0xFF

    return bytes([*src, x, a])


def test_f7_split_chunk_parse_ok():
    c = Ksx4506Codec()
    pkt = _build_f7(0x36, 0x01, 0x81, b"\x10\x20\x30\x40")

    a = pkt[:5]
    b = pkt[5:]

    assert c.feed(a) == []
    frames = c.feed(b)
    assert len(frames) == 1
    f = frames[0]
    assert f.addr == 0x36
    assert f.sub_id == 0x01
    assert f.cmd == 0x81
    assert f.payload == b"\x10\x20\x30\x40"


def test_build_f7_packet_roundtrip():
    c = Ksx4506Codec()
    pkt = c.build_f7(0x0E, 0x01, 0x41, b"\x02\x01\x00")
    frames = c.feed(pkt)
    assert len(frames) == 1
    f = frames[0]
    assert f.addr == 0x0E
    assert f.sub_id == 0x01
    assert f.cmd == 0x41
    assert f.payload == b"\x02\x01\x00"
