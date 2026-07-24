#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys


ENTITY_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])([a-z_][a-z0-9_]*\.[a-z0-9_]+)(?![A-Za-z0-9_.-])"
)
SERVICE_ACTIONS = {
    "close_cover",
    "open_cover",
    "reload",
    "select_option",
    "set_hvac_mode",
    "set_temperature",
    "set_value",
    "stop_cover",
    "toggle",
    "turn_off",
    "turn_on",
}
TEXT_SOURCE_NAMES = ("automations.yaml", "scripts.yaml", "scenes.yaml")
ENTITY_TEXT_KEYS = ("entity:", "entity_id:")
JSON_ENTITY_KEYS = {"entity", "entity_id"}


@dataclass(frozen=True)
class EntityReference:
    entity_id: str
    path: Path
    line: int


@dataclass(frozen=True)
class ReferenceReport:
    known_count: int
    reference_count: int
    stale_references: tuple[EntityReference, ...]


class ConfigReadError(RuntimeError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")


def check_config(config_dir: Path) -> ReferenceReport:
    known_entities = _load_entity_registry(config_dir)
    references = tuple(_iter_references(config_dir))
    stale = tuple(
        sorted(
            (reference for reference in references if reference.entity_id not in known_entities),
            key=lambda item: (item.entity_id, str(item.path), item.line),
        )
    )
    return ReferenceReport(
        known_count=len(known_entities),
        reference_count=len(references),
        stale_references=stale,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: check_ha_entity_refs.py <home-assistant-config-dir>", file=sys.stderr)
        return 2

    config_dir = Path(argv[1]).expanduser()
    try:
        report = check_config(config_dir)
    except ConfigReadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"Checked {report.reference_count} entity references "
        f"against {report.known_count} registry entities."
    )
    if not report.stale_references:
        print("No stale entity references found.")
        return 0

    print("Stale entity references:")
    for reference in report.stale_references:
        print(f"- {reference.entity_id} ({_display_path(config_dir, reference.path)}:{reference.line})")
    return 1


def _load_entity_registry(config_dir: Path) -> frozenset[str]:
    registry_path = config_dir / ".storage" / "core.entity_registry"
    if not registry_path.exists():
        raise ConfigReadError(registry_path, "entity registry file does not exist")

    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigReadError(registry_path, f"invalid JSON: {exc}") from exc

    data = raw.get("data", {})
    entries = data.get("entities", [])
    entity_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entity_id = entry.get("entity_id")
        if isinstance(entity_id, str):
            entity_ids.add(entity_id)
    return frozenset(entity_ids)


def _iter_references(config_dir: Path):
    for path in _iter_source_paths(config_dir):
        if _is_lovelace_storage(path):
            yield from _iter_lovelace_references(path)
        else:
            yield from _iter_text_references(path)


def _iter_source_paths(config_dir: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for name in TEXT_SOURCE_NAMES:
        path = config_dir / name
        if path.exists():
            paths.append(path)

    storage_dir = config_dir / ".storage"
    if storage_dir.exists():
        paths.extend(
            path
            for path in sorted(storage_dir.glob("lovelace*"))
            if path.is_file() and _is_active_lovelace_file(path)
        )
    return tuple(paths)


def _iter_text_references(path: Path):
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not _contains_entity_key(line):
            continue
        for match in ENTITY_ID_RE.finditer(line):
            entity_id = match.group(1)
            if _looks_like_service(entity_id):
                continue
            yield EntityReference(entity_id=entity_id, path=path, line=line_number)


def _iter_lovelace_references(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        yield from _iter_text_references(path)
        return

    for entity_id in sorted(_collect_json_entity_ids(raw)):
        line = text[: text.find(entity_id)].count("\n") + 1
        yield EntityReference(entity_id=entity_id, path=path, line=line)


def _collect_json_entity_ids(value) -> frozenset[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in JSON_ENTITY_KEYS and isinstance(item, str) and _is_entity_id(item):
                found.add(item)
            elif key == "entities" and isinstance(item, list):
                found.update(_collect_json_entity_ids(item))
            else:
                found.update(_collect_json_entity_ids(item))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and _is_entity_id(item):
                found.add(item)
            else:
                found.update(_collect_json_entity_ids(item))
    return frozenset(found)


def _contains_entity_key(line: str) -> bool:
    lowered = line.lower()
    return any(key in lowered for key in ENTITY_TEXT_KEYS)


def _is_active_lovelace_file(path: Path) -> bool:
    name = path.name
    return name == "lovelace" or (name.startswith("lovelace.") and name.count(".") == 1)


def _is_lovelace_storage(path: Path) -> bool:
    return path.name == "lovelace" or path.name.startswith("lovelace.")


def _is_entity_id(value: str) -> bool:
    return ENTITY_ID_RE.fullmatch(value) is not None and not _looks_like_service(value)


def _looks_like_service(entity_id: str) -> bool:
    _domain, service_name = entity_id.split(".", 1)
    return service_name in SERVICE_ACTIONS


def _display_path(config_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(config_dir))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
