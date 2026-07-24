from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_ha_entity_refs.py"


def test_check_ha_entity_refs_reports_stale_dashboard_reference(tmp_path):
    config_dir = tmp_path / "config"
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir(parents=True)

    (storage_dir / "core.entity_registry").write_text(
        json.dumps(
            {
                "data": {
                    "entities": [
                        {"entity_id": "light.kitchen_light"},
                        {"entity_id": "switch.living_room_outlet"},
                    ]
                }
            }
        )
    )
    (storage_dir / "lovelace.home_next").write_text(
        json.dumps(
            {
                "views": [
                    {
                        "cards": [
                            {"entity": "light.kitchen_light"},
                            {"entity": "light.removed_light"},
                        ]
                    }
                ]
            }
        )
    )
    (config_dir / "automations.yaml").write_text(
        "- alias: ok\n"
        "  trigger:\n"
        "    - platform: state\n"
        "      entity_id: switch.living_room_outlet\n"
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(config_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "light.removed_light" in result.stdout
    assert "lovelace.home_next" in result.stdout


def test_check_ha_entity_refs_accepts_clean_references(tmp_path):
    config_dir = tmp_path / "config"
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir(parents=True)

    (storage_dir / "core.entity_registry").write_text(
        json.dumps({"data": {"entities": [{"entity_id": "light.kitchen_light"}]}})
    )
    (config_dir / "automations.yaml").write_text(
        "- alias: ok\n"
        "  action:\n"
        "    - service: light.turn_on\n"
        "      target:\n"
        "        entity_id: light.kitchen_light\n"
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(config_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "No stale entity references found" in result.stdout
