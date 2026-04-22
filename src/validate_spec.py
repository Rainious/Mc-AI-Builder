import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ["version", "mc_version", "name", "size", "palette", "ops"]
ALLOWED_OPS = {"set", "box", "box_hollow", "line"}
TARGET_MC_VERSION = "1.20.4"


def _normalize_block_name(block_id: str) -> str:
    """Normalize block ids (e.g. stone or minecraft:stone[...]) to base block name."""
    name = block_id.split(":", 1)[-1]
    return name.split("[", 1)[0]


def load_block_catalog(catalog_path: Path) -> set[str]:
    """Load block catalog JSON and return allowed block names."""
    try:
        with catalog_path.open("r", encoding="utf-8") as f:
            catalog = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Block catalog not found: {catalog_path}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in block catalog ({catalog_path}): {exc}")

    if not isinstance(catalog, list):
        raise RuntimeError(f"Invalid block catalog format in {catalog_path}: expected a JSON array")

    allowed: set[str] = set()
    for item in catalog:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str):
            allowed.add(name)
    if not allowed:
        raise RuntimeError(f"No valid block names found in block catalog: {catalog_path}")
    return allowed


def validate_buildspec(spec: Any, allowed_blocks: set[str]) -> list[str]:
    """Validate BuildSpec structure and content, returning error messages."""
    errors: list[str] = []

    if not isinstance(spec, dict):
        return ["BuildSpec root must be a JSON object"]

    for field in REQUIRED_FIELDS:
        if field not in spec:
            errors.append(f"Missing required field: {field}")

    mc_version = spec.get("mc_version")
    if isinstance(mc_version, str) and mc_version != TARGET_MC_VERSION:
        errors.append(
            f"mc_version must be {TARGET_MC_VERSION!r}, got: {mc_version!r}"
        )

    size = spec.get("size")
    size_tuple: tuple[int, int, int] | None = None
    if isinstance(size, dict):
        size_values: list[int] = []
        for axis in ("x", "y", "z"):
            axis_value = size.get(axis)
            if not isinstance(axis_value, int) or axis_value < 1:
                errors.append(f"size.{axis} must be an integer >= 1")
            else:
                size_values.append(axis_value)
        if len(size_values) == 3:
            size_tuple = (size_values[0], size_values[1], size_values[2])
    elif "size" in spec:
        errors.append("Field 'size' must be an object")

    ops = spec.get("ops")
    palette = spec.get("palette")
    palette_keys: set[str] = set()
    if isinstance(palette, dict):
        for key, value in palette.items():
            if not isinstance(value, str):
                errors.append(f"palette['{key}'] must be a string block id")
                continue
            palette_keys.add(key)
            normalized = _normalize_block_name(value)
            if normalized not in allowed_blocks:
                errors.append(
                    f"palette['{key}'] contains unknown block: {value!r}"
                )
    elif "palette" in spec:
        errors.append("Field 'palette' must be an object")

    def validate_point(op_index: int, field_name: str, point: Any) -> tuple[int, int, int] | None:
        if not isinstance(point, list) or len(point) != 3:
            errors.append(f"ops[{op_index}].{field_name} must be an array of 3 integers")
            return None
        if not all(isinstance(v, int) for v in point):
            errors.append(f"ops[{op_index}].{field_name} must contain only integers")
            return None

        coord = (point[0], point[1], point[2])
        if size_tuple is not None:
            sx, sy, sz = size_tuple
            x, y, z = coord
            if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
                errors.append(
                    "Out-of-bounds placement at "
                    f"{coord} in ops[{op_index}] (valid ranges: "
                    f"x=0..{sx - 1}, y=0..{sy - 1}, z=0..{sz - 1})"
                )
        return coord

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
                continue

            block_key = item.get("block")
            if not isinstance(block_key, str):
                errors.append(f"ops[{i}].block must be a palette key string")
                continue
            if palette_keys and block_key not in palette_keys:
                errors.append(f"ops[{i}] references unknown palette key: {block_key!r}")

            if op == "set":
                validate_point(i, "at", item.get("at"))
                continue

            start = validate_point(i, "from", item.get("from"))
            end = validate_point(i, "to", item.get("to"))
            if op == "line" and start is not None and end is not None:
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                dz = end[2] - start[2]
                changed_axes = sum(delta != 0 for delta in (dx, dy, dz))
                if changed_axes > 1:
                    errors.append(
                        f"ops[{i}] line must be axis-aligned: from={start} to={end}"
                    )
    elif "ops" in spec:
        errors.append("Field 'ops' must be an array")

    return errors


def main() -> int:
    """Run BuildSpec validation CLI and return process exit code."""
    parser = argparse.ArgumentParser(description="Validate BuildSpec JSON")
    parser.add_argument("buildspec", help="Path to BuildSpec JSON file")
    parser.add_argument(
        "--catalog",
        default=str(Path(__file__).resolve().parents[1] / "data" / "block_catalog.json"),
        help="Path to block catalog JSON file (default: data/block_catalog.json in repo root)",
    )
    args = parser.parse_args()

    buildspec_path = Path(args.buildspec)
    block_catalog_path = Path(args.catalog)

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
