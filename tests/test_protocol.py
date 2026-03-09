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
