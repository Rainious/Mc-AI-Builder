"""Export compiled block placements JSON to a WorldEdit-compatible .schem file."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

class ExportSchemError(Exception):
    """Raised when export to .schem fails."""


def _validate_one_placement(item: Any, index: int) -> dict[str, Any]:
    """Validate one compiled placement object and return normalized mapping."""
    if not isinstance(item, dict):
        raise ExportSchemError(f"placements[{index}] must be an object")

    for axis in ("x", "y", "z"):
        value = item.get(axis)
        if type(value) is not int:
            raise ExportSchemError(f"placements[{index}].{axis} must be an integer")

    block = item.get("block")
    if not isinstance(block, str):
        raise ExportSchemError(f"placements[{index}].block must be a string")

    return {"x": item["x"], "y": item["y"], "z": item["z"], "block": block}


def _load_compiled_placements(path: Path) -> list[dict[str, Any]]:
    """Load and validate compiled placement JSON array from disk."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise ExportSchemError(f"Compiled placement file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ExportSchemError(f"Invalid JSON in compiled placement file ({path}): {exc}") from exc
    except OSError as exc:
        raise ExportSchemError(f"Failed to read compiled placement file ({path}): {exc}") from exc

    if not isinstance(data, list):
        raise ExportSchemError("Compiled placement root must be a JSON array")

    return [_validate_one_placement(item, i) for i, item in enumerate(data)]


def _resolve_mc_version() -> Any:
    """Resolve mcschematic enum value for Minecraft Java 1.20.4."""
    mcschematic = _load_mcschematic()
    try:
        return mcschematic.Version.JE_1_20_4
    except AttributeError as exc:
        raise ExportSchemError("mcschematic does not support JE_1_20_4 in this environment") from exc


def _load_mcschematic() -> Any:
    """Import mcschematic lazily and provide a clear dependency error."""
    try:
        import mcschematic  # type: ignore
    except ModuleNotFoundError as exc:
        raise ExportSchemError(
            "Missing dependency: mcschematic. Install it with `pip install mcschematic`."
        ) from exc
    return mcschematic


def _export_to_mcschematic(
    placements: list[dict[str, Any]],
    outdir: Path,
    schem_name: str,
) -> Path:
    """Write placements into one MCSchematic object and save a .schem file."""
    mcschematic = _load_mcschematic()
    schematic = mcschematic.MCSchematic()

    for placement in placements:
        schematic.setBlock(
            (placement["x"], placement["y"], placement["z"]),
            placement["block"],
        )

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportSchemError(f"Failed to create output directory ({outdir}): {exc}") from exc

    try:
        schematic.save(
            outputFolderPath=str(outdir),
            schemName=schem_name,
            version=_resolve_mc_version(),
        )
    except OSError as exc:
        raise ExportSchemError(f"Failed to save schematic file in {outdir}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - depends on mcschematic runtime errors
        raise ExportSchemError(f"Failed to export schematic: {exc}") from exc

    return outdir / f"{schem_name}.schem"


def _derive_schem_name(input_path: Path, explicit_name: str | None) -> str:
    """Choose schematic name from CLI option or input filename stem."""
    name = explicit_name or input_path.stem
    if not name:
        raise ExportSchemError("Schematic name is empty")
    return name


def main() -> int:
    """Run CLI flow to export compiled placements JSON to .schem."""
    parser = argparse.ArgumentParser(description="Export compiled placements JSON to .schem")
    parser.add_argument("compiled", help="Path to compiled placements JSON file")
    parser.add_argument("--outdir", default="./out", help="Output directory for .schem (default: ./out)")
    parser.add_argument("--name", help="Output schematic name (without .schem)")
    args = parser.parse_args()

    input_path = Path(args.compiled)
    outdir = Path(args.outdir)

    try:
        placements = _load_compiled_placements(input_path)
        schem_name = _derive_schem_name(input_path, args.name)
        output_path = _export_to_mcschematic(placements, outdir, schem_name)
    except ExportSchemError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(str(output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
