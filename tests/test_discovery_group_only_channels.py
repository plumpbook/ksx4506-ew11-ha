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


def test_group_light_creates_channels_only_no_group_entity():
    reg = DeviceRegistry()
    reg.upsert_from_frame(0x0E, 0x1F, 0x81, bytes([0x00, 0x01, 0x00, 0x01]), "f7...")

    assert "0E1F_light" not in reg.devices
    assert "0E1F_light_1" in reg.devices
    assert "0E1F_light_2" in reg.devices
    assert "0E1F_light_3" in reg.devices
