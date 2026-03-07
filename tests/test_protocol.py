from custom_components.ksx4506_ew11.protocol import Ksx4506Codec


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
