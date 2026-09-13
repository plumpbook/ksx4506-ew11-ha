from pathlib import Path
import subprocess
import sys


def test_device_alerts_with_real_homeassistant_runtime():
    result = subprocess.run(
        [sys.executable, "-m", "tests.runtime_device_alerts_smoke"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
