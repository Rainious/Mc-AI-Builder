import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ["version", "mc_version", "name", "size", "palette", "ops"]
ALLOWED_OPS = {"set", "box", "box_hollow", "line"}


def _normalize_block_name(block_id: str) -> str:
    name = block_id.split(":", 1)[-1]
    return name.split("[", 1)[0]


def load_block_catalog(catalog_path: Path) -> set[str]:
    try:
        with catalog_path.open("r", encoding="utf-8") as f:
            catalog = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Block catalog not found: {catalog_path}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in block catalog ({catalog_path}): {exc}")

    if not isinstance(catalog, list):
        raise RuntimeError(f"Invalid block catalog format in {catalog_path}: expected a JSON array")

    allowed = {
        item.get("name")
        for item in catalog
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not allowed:
        raise RuntimeError(f"No valid block names found in block catalog: {catalog_path}")
    return allowed


def validate_buildspec(spec: Any, allowed_blocks: set[str]) -> list[str]:
    errors: list[str] = []

    if not isinstance(spec, dict):
        return ["BuildSpec root must be a JSON object"]

    for field in REQUIRED_FIELDS:
        if field not in spec:
            errors.append(f"Missing required field: {field}")

    ops = spec.get("ops")
    if isinstance(ops, list):
        for i, item in enumerate(ops):
            if not isinstance(item, dict):
                errors.append(f"ops[{i}] must be an object")
                continue
            op = item.get("op")
            if op not in ALLOWED_OPS:
                errors.append(
                    f"ops[{i}].op must be one of {sorted(ALLOWED_OPS)}, got: {op!r}"
                )
    elif "ops" in spec:
        errors.append("Field 'ops' must be an array")

    palette = spec.get("palette")
    if isinstance(palette, dict):
        for key, value in palette.items():
            if not isinstance(value, str):
                errors.append(f"palette['{key}'] must be a string block id")
                continue
            normalized = _normalize_block_name(value)
            if normalized not in allowed_blocks:
                errors.append(
                    f"palette['{key}'] contains unknown block: {value!r}"
                )
    elif "palette" in spec:
        errors.append("Field 'palette' must be an object")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BuildSpec JSON")
    parser.add_argument("buildspec", help="Path to BuildSpec JSON file")
    args = parser.parse_args()

    buildspec_path = Path(args.buildspec)
    repo_root = Path(__file__).resolve().parents[1]
    block_catalog_path = repo_root / "data" / "block_catalog.json"

    try:
        with buildspec_path.open("r", encoding="utf-8") as f:
            spec = json.load(f)
    except FileNotFoundError:
        print(f"Error: BuildSpec file not found: {buildspec_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in BuildSpec file ({buildspec_path}): {exc}")
        return 1

    try:
        allowed_blocks = load_block_catalog(block_catalog_path)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    errors = validate_buildspec(spec, allowed_blocks)
    if errors:
        for err in errors:
            print(f"Error: {err}")
        return 1

    print("BuildSpec valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
