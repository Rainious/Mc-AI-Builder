"""Compile a validated BuildSpec JSON into explicit block placements."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator


class CompileSpecError(Exception):
    """Raised when BuildSpec compilation fails."""


def _load_json_file(path: Path) -> Any:
    """Load JSON from disk with clear file/format errors."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise CompileSpecError(f"BuildSpec file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompileSpecError(f"Invalid JSON in BuildSpec file ({path}): {exc}") from exc


def _require_point(value: Any, field_name: str, op_index: int) -> tuple[int, int, int]:
    """Validate and return a 3D integer point."""
    if not (isinstance(value, list) and len(value) == 3):
        raise CompileSpecError(f"ops[{op_index}].{field_name} must be an array of 3 integers")
    if not all(isinstance(v, int) for v in value):
        raise CompileSpecError(f"ops[{op_index}].{field_name} must contain only integers")
    return int(value[0]), int(value[1]), int(value[2])


def _require_size(spec: dict[str, Any]) -> tuple[int, int, int]:
    """Validate and return declared build size bounds."""
    size = spec.get("size")
    if not isinstance(size, dict):
        raise CompileSpecError("Field 'size' must be an object")

    values: list[int] = []
    for axis in ("x", "y", "z"):
        axis_value = size.get(axis)
        if not isinstance(axis_value, int) or axis_value < 1:
            raise CompileSpecError(f"size.{axis} must be an integer >= 1")
        values.append(axis_value)
    return values[0], values[1], values[2]


def _require_palette(spec: dict[str, Any]) -> dict[str, str]:
    """Validate and return palette mapping for block resolution."""
    palette = spec.get("palette")
    if not isinstance(palette, dict):
        raise CompileSpecError("Field 'palette' must be an object")

    result: dict[str, str] = {}
    for key, value in palette.items():
        if not isinstance(key, str):
            raise CompileSpecError("Palette keys must be strings")
        if not isinstance(value, str):
            raise CompileSpecError(f"palette['{key}'] must map to a string block id")
        result[key] = value
    return result


def _require_ops(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and return ops list."""
    ops = spec.get("ops")
    if not isinstance(ops, list):
        raise CompileSpecError("Field 'ops' must be an array")

    normalized: list[dict[str, Any]] = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise CompileSpecError(f"ops[{i}] must be an object")
        normalized.append(op)
    return normalized


def _check_bounds(coord: tuple[int, int, int], size: tuple[int, int, int], op_index: int) -> None:
    """Ensure coordinate is inside declared size bounds."""
    x, y, z = coord
    sx, sy, sz = size
    if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
        raise CompileSpecError(
            "Out-of-bounds placement at "
            f"{coord} in ops[{op_index}] (valid ranges: "
            f"x=0..{sx - 1}, y=0..{sy - 1}, z=0..{sz - 1})"
        )


def _resolve_block_id(op: dict[str, Any], palette: dict[str, str], op_index: int) -> str:
    """Resolve op block palette key to concrete Minecraft block id."""
    palette_key = op.get("block")
    if not isinstance(palette_key, str):
        raise CompileSpecError(f"ops[{op_index}].block must be a palette key string")

    block_id = palette.get(palette_key)
    if block_id is None:
        raise CompileSpecError(
            f"ops[{op_index}] references unknown palette key: {palette_key!r}"
        )
    return block_id


def _iter_box(
    start: tuple[int, int, int], end: tuple[int, int, int]
) -> Iterator[tuple[int, int, int]]:
    """Yield all coordinates in an inclusive rectangular box."""
    min_x, max_x = sorted((start[0], end[0]))
    min_y, max_y = sorted((start[1], end[1]))
    min_z, max_z = sorted((start[2], end[2]))

    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            for z in range(min_z, max_z + 1):
                yield (x, y, z)


def _iter_box_hollow(
    start: tuple[int, int, int], end: tuple[int, int, int]
) -> Iterator[tuple[int, int, int]]:
    """Yield only shell coordinates in an inclusive rectangular box."""
    min_x, max_x = sorted((start[0], end[0]))
    min_y, max_y = sorted((start[1], end[1]))
    min_z, max_z = sorted((start[2], end[2]))

    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            for z in range(min_z, max_z + 1):
                if (
                    x in (min_x, max_x)
                    or y in (min_y, max_y)
                    or z in (min_z, max_z)
                ):
                    yield (x, y, z)


def _iter_line(
    start: tuple[int, int, int], end: tuple[int, int, int], op_index: int
) -> Iterator[tuple[int, int, int]]:
    """Yield coordinates for an axis-aligned inclusive line."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]

    changed_axes = sum(delta != 0 for delta in (dx, dy, dz))
    if changed_axes > 1:
        raise CompileSpecError(
            f"ops[{op_index}] line must be axis-aligned: from={list(start)} to={list(end)}"
        )

    if changed_axes == 0:
        yield start
        return

    if dx != 0:
        step = 1 if dx > 0 else -1
        for x in range(start[0], end[0] + step, step):
            yield (x, start[1], start[2])
        return

    if dy != 0:
        step = 1 if dy > 0 else -1
        for y in range(start[1], end[1] + step, step):
            yield (start[0], y, start[2])
        return

    step = 1 if dz > 0 else -1
    for z in range(start[2], end[2] + step, step):
        yield (start[0], start[1], z)


def compile_buildspec(spec: Any) -> list[dict[str, Any]]:
    """Compile BuildSpec into explicit, deduplicated block placements."""
    if not isinstance(spec, dict):
        raise CompileSpecError("BuildSpec root must be a JSON object")

    size = _require_size(spec)
    palette = _require_palette(spec)
    ops = _require_ops(spec)

    # Later writes should overwrite earlier ones for the same coordinate.
    placed: dict[tuple[int, int, int], str] = {}

    for i, op in enumerate(ops):
        op_name = op.get("op")
        if not isinstance(op_name, str):
            raise CompileSpecError(f"ops[{i}].op must be a string")

        block_id = _resolve_block_id(op, palette, i)

        if op_name == "set":
            at = _require_point(op.get("at"), "at", i)
            _check_bounds(at, size, i)
            placed[at] = block_id
            continue

        if op_name == "box":
            start = _require_point(op.get("from"), "from", i)
            end = _require_point(op.get("to"), "to", i)
            for coord in _iter_box(start, end):
                _check_bounds(coord, size, i)
                placed[coord] = block_id
            continue

        if op_name == "box_hollow":
            start = _require_point(op.get("from"), "from", i)
            end = _require_point(op.get("to"), "to", i)
            for coord in _iter_box_hollow(start, end):
                _check_bounds(coord, size, i)
                placed[coord] = block_id
            continue

        if op_name == "line":
            start = _require_point(op.get("from"), "from", i)
            end = _require_point(op.get("to"), "to", i)
            for coord in _iter_line(start, end, i):
                _check_bounds(coord, size, i)
                placed[coord] = block_id
            continue

        raise CompileSpecError(
            f"ops[{i}].op must be one of ['set', 'box', 'box_hollow', 'line'], got: {op_name!r}"
        )

    placements: list[dict[str, Any]] = []
    for (x, y, z), block in sorted(placed.items()):
        placements.append({"x": x, "y": y, "z": z, "block": block})
    return placements


def main() -> int:
    """Compile BuildSpec from CLI and print explicit placements as pretty JSON."""
    parser = argparse.ArgumentParser(description="Compile BuildSpec JSON into explicit block placements")
    parser.add_argument("buildspec", help="Path to BuildSpec JSON file")
    parser.add_argument("--out", help="Optional output file path for compiled JSON")
    args = parser.parse_args()

    try:
        spec = _load_json_file(Path(args.buildspec))
        placements = compile_buildspec(spec)
    except CompileSpecError as exc:
        print(f"Compilation Error: {exc}", file=sys.stderr)
        return 1

    output_text = json.dumps(placements, indent=2, ensure_ascii=False)
    print(output_text)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(f"{output_text}\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
