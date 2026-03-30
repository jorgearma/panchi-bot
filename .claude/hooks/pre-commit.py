#!/usr/bin/env python3
"""Valida la estructura activa del plugin y los artefactos JSON actuales."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import SCHEMA_MAP, validate_artifact


PLUGIN_DIR = Path(__file__).resolve().parents[1]
ROOT = PLUGIN_DIR.parent
PLUGIN_JSON = PLUGIN_DIR / "plugin.json"
IS_SOURCE_REPO_LAYOUT = PLUGIN_DIR.name == "claude"

EXTRA_REQUIRED_PATHS = [
    PLUGIN_DIR / "settings.local.json",
    PLUGIN_DIR / "hooks" / "reader-only.py",
    PLUGIN_DIR / "hooks" / "planner-only.py",
    PLUGIN_DIR / "hooks" / "writer-only.py",
    PLUGIN_DIR / "hooks" / "guard-reader.py",
    PLUGIN_DIR / "hooks" / "guard-planner.py",
    PLUGIN_DIR / "hooks" / "guard-writer.py",
]

if IS_SOURCE_REPO_LAYOUT:
    EXTRA_REQUIRED_PATHS.insert(0, ROOT / "CLAUDE.md")

MAP_SCHEMA_FILES = [
    PLUGIN_DIR / "schemas" / "routing-map.json",
    PLUGIN_DIR / "schemas" / "domain-index.json",
    PLUGIN_DIR / "schemas" / "contract-map.json",
    PLUGIN_DIR / "schemas" / "dependency-map.json",
]

MAP_ARTIFACTS = {
    "ROUTING_MAP.json",
    "DOMAIN_INDEX_api.json",
    "DOMAIN_INDEX_data.json",
    "DOMAIN_INDEX_ui.json",
    "DOMAIN_INDEX_services.json",
    "DOMAIN_INDEX_jobs.json",
    "CONTRACT_MAP.json",
    "DEPENDENCY_MAP.json",
}


def plugin_path_from_manifest(rel_path: str) -> Path:
    """Resuelve una ruta declarada en plugin.json al layout real actual."""
    if rel_path.startswith(".claude/"):
        rel_path = rel_path.removeprefix(".claude/")
    elif rel_path.startswith("claude/"):
        rel_path = rel_path.removeprefix("claude/")
    return PLUGIN_DIR / rel_path


def validate_json_file(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            json.load(fh)
    except json.JSONDecodeError as exc:
        return f"{path.relative_to(ROOT)}: invalid JSON at line {exc.lineno} column {exc.colno}"
    except OSError as exc:
        return f"{path.relative_to(ROOT)}: cannot be read ({exc})"
    return None


def load_manifest() -> dict:
    with PLUGIN_JSON.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def required_paths_from_manifest(manifest: dict) -> list[Path]:
    paths = [PLUGIN_JSON]

    for agent in manifest.get("agents", []):
        paths.append(PLUGIN_DIR / "agents" / f"{agent}.md")

    for command in manifest.get("commands", []):
        paths.append(PLUGIN_DIR / "commands" / f"{command}.md")

    for hook in manifest.get("hooks", []):
        paths.append(PLUGIN_DIR / "hooks" / hook)

    for map_name in manifest.get("maps", []):
        paths.append(PLUGIN_DIR / "maps" / map_name)

    for schema_rel in manifest.get("schemas", {}).values():
        paths.append(plugin_path_from_manifest(schema_rel))

    return paths


def optional_runtime_json_paths(manifest: dict) -> list[Path]:
    paths: list[Path] = []
    for runtime_rel in manifest.get("runtime", {}).values():
        path = plugin_path_from_manifest(runtime_rel)
        if path.exists():
            paths.append(path)
    return paths


def validate_artifact_file(name: str, path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    vr = validate_artifact(name, data)
    if vr.ok:
        return None
    return f"{path.relative_to(ROOT)}: schema violations\n{vr.format()}"


def validate_known_maps(map_dir: Path) -> list[str]:
    errors: list[str] = []
    for artifact_name in sorted(MAP_ARTIFACTS):
        path = map_dir / artifact_name
        if not path.exists():
            continue
        err = validate_artifact_file(artifact_name, path)
        if err:
            errors.append(err)
    return errors


def main() -> int:
    manifest_error = validate_json_file(PLUGIN_JSON)
    if manifest_error:
        print("Invalid plugin manifest:")
        print(f"  - {manifest_error}")
        return 1

    manifest = load_manifest()

    required_paths = required_paths_from_manifest(manifest) + EXTRA_REQUIRED_PATHS + MAP_SCHEMA_FILES
    missing = sorted({str(path.relative_to(ROOT)) for path in required_paths if not path.exists()})
    if missing:
        print("Missing required Claude plugin files:")
        for rel in missing:
            print(f"  - {rel}")
        return 1

    static_json_files = {
        PLUGIN_JSON,
        PLUGIN_DIR / "settings.local.json",
        *[plugin_path_from_manifest(rel) for rel in manifest.get("schemas", {}).values()],
        *MAP_SCHEMA_FILES,
        *[PLUGIN_DIR / "maps" / name for name in manifest.get("maps", [])],
    }

    invalid_json = sorted(
        err for path in static_json_files
        if (err := validate_json_file(path))
    )
    if invalid_json:
        print("Invalid JSON files detected:")
        for err in invalid_json:
            print(f"  - {err}")
        return 1

    schema_errors = validate_known_maps(PLUGIN_DIR / "maps")
    if schema_errors:
        print("Versioned map files with schema violations:")
        for err in schema_errors:
            print(f"  - {err}")
        return 1

    runtime_json_errors: list[str] = []
    for path in optional_runtime_json_paths(manifest):
        err = validate_json_file(path)
        if err:
            runtime_json_errors.append(err)
            continue
        if path.name in SCHEMA_MAP:
            schema_err = validate_artifact_file(path.name, path)
            if schema_err:
                runtime_json_errors.append(schema_err)

    runtime_map_dir = ROOT / ".claude" / "maps"
    runtime_map_errors = validate_known_maps(runtime_map_dir) if runtime_map_dir.exists() else []

    if runtime_json_errors or runtime_map_errors:
        print("Runtime artifacts with validation issues:")
        for err in runtime_json_errors + runtime_map_errors:
            print(f"  - {err}")
        return 1

    print("Claude plugin structure ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
