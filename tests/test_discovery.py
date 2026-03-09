from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


_DISCOVERY_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "ksx4506_ew11" / "discovery.py"
_spec = spec_from_file_location("ksx4506_discovery", _DISCOVERY_PATH)
_module = module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
DeviceRegistry = _module.DeviceRegistry


def test_light_single_subid_multichannel_payload_expands_channels():
    reg = DeviceRegistry()
    # vendor variant: sub_id(0x01) + multi-channel payload [err, ch1, ch2, ch3]
    changes = reg.upsert_from_frame(0x0E, 0x01, 0x81, bytes([0x00, 0x01, 0x00, 0x01]), "f7...")

    assert len(changes) == 3
    keys = sorted(k for k in reg.devices.keys())
    assert keys == ["0E1F_light_1", "0E1F_light_2", "0E1F_light_3"]
    assert reg.devices["0E1F_light_1"].state["on"] is True
    assert reg.devices["0E1F_light_1"].state["dimmable"] is False
    assert reg.devices["0E1F_light_2"].state["on"] is False
    assert reg.devices["0E1F_light_3"].state["on"] is True


def test_light_status_byte_dimming_decode():
    reg = DeviceRegistry()
    # [err=0x00, state=0xA3] => dim step 10, dimmable, ON
    reg.upsert_from_frame(0x0E, 0x01, 0x81, bytes([0x00, 0xA3]), "f7...")
    d = reg.devices["0E1F_light_1"]
    assert d.state["on"] is True
    assert d.state["dimmable"] is True
    assert d.state["brightness_step"] == 0x0A
