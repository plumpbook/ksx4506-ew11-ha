from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components"
INTEGRATION_ROOT = PACKAGE_ROOT / "ksx4506_ew11"


def load_integration_module(name: str):
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
    module_path = INTEGRATION_ROOT / Path(*name.split(".")).with_suffix(".py")
    spec = spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
