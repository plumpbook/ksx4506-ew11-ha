from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402

install_homeassistant_stubs()
config = load_integration_module("config")


def test_effective_config_overlays_options_on_data():
    entry = types.SimpleNamespace(
        data={
            "host": "ew11.example.invalid",
            "timeout": 3.0,
            "expose_packet_samples": False,
        },
        options={
            "timeout": 5.0,
            "expose_packet_samples": True,
        },
    )

    assert config.effective_config(entry) == {
        "host": "ew11.example.invalid",
        "timeout": 5.0,
        "expose_packet_samples": True,
    }


def test_effective_config_accepts_entries_without_options():
    entry = types.SimpleNamespace(data={"host": "ew11.example.invalid"})

    assert config.effective_config(entry) == {"host": "ew11.example.invalid"}
