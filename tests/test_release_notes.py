from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _release_note_versions() -> set[str]:
    text = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    return set(re.findall(r"^## (v\d+\.\d+\.\d+)\s*$", text, flags=re.MULTILINE))


def _local_release_tags() -> set[str]:
    output = subprocess.check_output(
        ["git", "tag", "--list", "v[0-9]*", "--sort=version:refname"],
        cwd=ROOT,
        text=True,
    )
    return {line.strip() for line in output.splitlines() if line.strip()}


def test_release_notes_include_current_manifest_version():
    manifest = json.loads(
        (ROOT / "custom_components/ksx4506_ew11/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert f"v{manifest['version']}" in _release_note_versions()


def test_release_notes_include_all_local_release_tags():
    missing = sorted(_local_release_tags() - _release_note_versions())

    assert missing == []
