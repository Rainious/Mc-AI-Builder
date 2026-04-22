"""Run the BuildSpec MVP pipeline: validate -> compile -> export .schem."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from compile_spec import CompileSpecError, compile_buildspec
from export_schem import ExportSchemError, export_placements_to_schem
from validate_spec import load_block_catalog, validate_buildspec


def _load_json_file(path: Path) -> Any:
    """Load JSON from file with clear error messages."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"BuildSpec file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in BuildSpec file ({path}): {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to read BuildSpec file ({path}): {exc}") from exc


def run_pipeline(
    buildspec_path: Path,
    catalog_path: Path,
    outdir: Path,
    name: str | None = None,
) -> Path:
    """Run validate -> compile -> export and return output .schem path."""
    spec = _load_json_file(buildspec_path)

    allowed_blocks = load_block_catalog(catalog_path)
    errors = validate_buildspec(spec, allowed_blocks)
    if errors:
        raise RuntimeError("\n".join(errors))

    placements = compile_buildspec(spec)
    output_name = name or buildspec_path.stem
    if not output_name:
        raise RuntimeError("Schematic name is empty")

    return export_placements_to_schem(placements, outdir, output_name)


def main() -> int:
    """CLI entrypoint for end-to-end BuildSpec pipeline."""
    parser = argparse.ArgumentParser(
        description="Run BuildSpec pipeline: validate -> compile -> export .schem"
    )
    parser.add_argument("buildspec", help="Path to BuildSpec JSON file")
    parser.add_argument(
        "--catalog",
        default=str(Path(__file__).resolve().parents[1] / "data" / "block_catalog.json"),
        help="Path to block catalog JSON file (default: data/block_catalog.json in repo root)",
    )
    parser.add_argument(
        "--outdir",
        default="./out",
        help="Output directory for .schem (default: ./out)",
    )
    parser.add_argument("--name", help="Output schematic name (without .schem)")
    args = parser.parse_args()

    try:
        output_path = run_pipeline(
            buildspec_path=Path(args.buildspec),
            catalog_path=Path(args.catalog),
            outdir=Path(args.outdir),
            name=args.name,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except CompileSpecError as exc:
        print(f"Compilation Error: {exc}", file=sys.stderr)
        return 1
    except ExportSchemError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(str(output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
