"""Run the installed Home Assistant, not the unit suite's HA stubs."""
from pathlib import Path
import subprocess
import sys


def test_discovery_with_real_homeassistant_and_loopback():
    result = subprocess.run(
        [sys.executable, "-m", "tests.runtime_discovery_smoke"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_review_shortcuts_with_real_homeassistant_registries():
    result = subprocess.run(
        [sys.executable, "-m", "tests.runtime_discovery_links"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
