from importlib.util import module_from_spec, spec_from_file_location
import logging
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components"
INTEGRATION_ROOT = PACKAGE_ROOT / "ksx4506_ew11"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(PACKAGE_ROOT)]
integration = types.ModuleType("custom_components.ksx4506_ew11")
integration.__path__ = [str(INTEGRATION_ROOT)]
sys.modules.setdefault("custom_components", custom_components)
sys.modules.setdefault("custom_components.ksx4506_ew11", integration)

_PROTOCOL_PATH = INTEGRATION_ROOT / "protocol.py"
_spec = spec_from_file_location("custom_components.ksx4506_ew11.protocol", _PROTOCOL_PATH)
assert _spec is not None and _spec.loader is not None
_module = module_from_spec(_spec)
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


def test_bad_checksum_dropped(caplog):
    c = Ksx4506Codec()
    pkt = bytearray(c.build(0x11, 0x22, b"\x01"))
    pkt[-2] ^= 0xFF
    raw_hex = bytes(pkt).hex()

    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11.protocol")

    assert c.feed(bytes(pkt)) == []
    assert raw_hex not in "\n".join(record.getMessage() for record in caplog.records)


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


def test_bad_f7_checksum_warning_does_not_expose_raw_packet(caplog):
    c = Ksx4506Codec()
    pkt = bytearray(_build_f7(0x40, 0x02, 0x10, bytes.fromhex("62 02 00 00 00 00")))
    pkt[-1] ^= 0xFF
    raw_hex = bytes(pkt).hex()

    caplog.set_level(logging.DEBUG, logger="custom_components.ksx4506_ew11.protocol")

    assert c.feed(bytes(pkt)) == []

    warning_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    debug_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.DEBUG
    ]
    assert warning_messages
    assert raw_hex not in "\n".join(warning_messages)
    assert raw_hex not in "\n".join(debug_messages)
    assert bytes(pkt)[5:-2].hex() not in "\n".join(debug_messages)
