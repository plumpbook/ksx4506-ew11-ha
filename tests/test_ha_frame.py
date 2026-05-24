from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components"
INTEGRATION_ROOT = PACKAGE_ROOT / "ksx4506_ew11"


def _load_integration_module(name: str):
    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(PACKAGE_ROOT)]
    integration = types.ModuleType("custom_components.ksx4506_ew11")
    integration.__path__ = [str(INTEGRATION_ROOT)]
    devices = types.ModuleType("custom_components.ksx4506_ew11.devices")
    devices.__path__ = [str(INTEGRATION_ROOT / "devices")]
    sys.modules.setdefault("custom_components", custom_components)
    sys.modules.setdefault("custom_components.ksx4506_ew11", integration)
    sys.modules.setdefault("custom_components.ksx4506_ew11.devices", devices)

    module_name = f"custom_components.ksx4506_ew11.{name}"
    spec = spec_from_file_location(
        module_name,
        INTEGRATION_ROOT / Path(*name.split(".")).with_suffix(".py"),
    )
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


frame_module = _load_integration_module("frame")
protocol_module = _load_integration_module("protocol")
lighting_module = _load_integration_module("devices.lighting")

Frame = frame_module.Frame
FrameStreamDecoder = frame_module.FrameStreamDecoder
Ksx4506Codec = protocol_module.Ksx4506Codec


def test_frame_encodes_known_gas_status_request():
    frame = Frame(device_id=0x12, sub_id=0x01, command_type=0x01)

    assert frame.to_bytes() == bytes.fromhex("F7 12 01 01 00 E5 F0")


def test_stream_decoder_handles_split_f7_frame():
    decoder = FrameStreamDecoder()
    raw = bytes.fromhex("F7 0E 01 81 02 00 01 7A 04")

    assert decoder.feed(raw[:4]) == []
    frames = decoder.feed(raw[4:])

    assert len(frames) == 1
    assert frames[0].device_id == 0x0E
    assert frames[0].sub_id == 0x01
    assert frames[0].command_type == 0x81
    assert frames[0].data == b"\x00\x01"


def test_codec_f7_path_uses_standard_frame_model():
    codec = Ksx4506Codec()
    raw = codec.build_f7(0x0E, 0x01, 0x41, b"\x01")

    assert raw == Frame(0x0E, 0x01, 0x41, b"\x01").to_bytes()

    frames = codec.feed(raw)

    assert len(frames) == 1
    assert frames[0].addr == 0x0E
    assert frames[0].sub_id == 0x01
    assert frames[0].cmd == 0x41
    assert frames[0].payload == b"\x01"


def test_lighting_helpers_build_standard_and_vendor_payloads():
    assert lighting_module.build_light_control_payload(turn_on=True) == b"\x01"
    assert (
        lighting_module.build_light_control_payload(
            turn_on=True,
            brightness_step=10,
        )
        == b"\xA1"
    )
    assert (
        lighting_module.build_vendor_channel_control_payload(
            channel=2,
            turn_on=False,
        )
        == b"\x02\x00\x00"
    )
    assert lighting_module.f7_individual_sub_id(0x1F, 2) == 0x12
    assert lighting_module.f7_individual_sub_id(0x2F, 1) == 0x21
