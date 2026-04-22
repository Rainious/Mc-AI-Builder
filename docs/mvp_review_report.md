# MVP Pipeline Review Report

## Current pipeline overview

Current implemented flow in `src/`:

1. `validate_spec.py`: validates BuildSpec structure and palette blocks against `data/block_catalog.json`.
2. `compile_spec.py`: expands BuildSpec ops into explicit block placements (`[{x,y,z,block}, ...]`) with bounds checks and deterministic ordering.
3. `export_schem.py`: loads compiled placements and exports a `.schem` via `mcschematic` for Java `1.20.4`.

This is consistent with the project intent: BuildSpec JSON → validate → export `.schem` for WorldEdit import.

## Components reviewed

- `.github/copilot-instructions.md`
- `PROJECT_BRIEF.md`
- `docs/architecture.md`
- `schema/build_schema.json`
- `data/block_catalog.json`
- `examples/test_tower.json`
- `examples/test1.json`
- `src/validate_spec.py`
- `src/compile_spec.py`
- `src/export_schem.py`

## What is working

- Core scripts are focused and modular (validator/compiler/exporter separation).
- Compiler enforces important runtime rules:
  - size-bounds checks
  - palette key resolution
  - operation support (`set`, `box`, `box_hollow`, `line`)
  - deterministic output order for reproducibility
- Exporter has clear error handling for missing files, bad JSON, and missing `mcschematic`.
- `test_tower.json` passes validation and compiles successfully.

## What is inconsistent or risky

- **Validator/compiler mismatch (fixed in this review):**
  - validator previously allowed specs that would fail in compiler (missing coordinate shape checks, unknown palette keys in ops, line axis constraints, bounds checks).
- **Broken example (fixed in this review):**
  - `examples/test1.json` used `minecraft:spruce_stairs` (not in current catalog) and a non-axis-aligned/out-of-bounds `line`, so it did not pass the pipeline.
- **Schema vs runtime behavior mismatch (not changed in this round):**
  - `schema/build_schema.json` is permissive for op coordinate fields (via `anyOf`) and does not encode compiler-specific constraints like axis-aligned `line`.
  - Current validator is custom/manual and does not directly execute JSON Schema validation from `schema/build_schema.json`.
- **Environment dependency risk:**
  - export step requires `mcschematic`; missing dependency blocks end-to-end export test in a clean environment.
- **No repository test runner currently available:**
  - `pytest` is not installed, and no formal automated tests were found in this repository snapshot.

## What was fixed in this review

1. **Strengthened `src/validate_spec.py` checks** to align with actual compiler/runtime expectations:
   - validates `size` object and axis values (`>=1`)
   - validates op coordinate field shape/type (`[int, int, int]`)
   - validates op block references existing palette keys
   - validates op coordinates are within declared `size` bounds
   - validates `line` ops are axis-aligned (matching compiler behavior)

2. **Repaired `examples/test1.json`**:
   - changed roof block to catalog-allowed `minecraft:oak_stairs`
   - changed roof `line` coordinates to axis-aligned and in-bounds

## What still needs manual testing

- Full export smoke test after installing dependency:
  - `pip install mcschematic`
  - run `validate_spec.py`, `compile_spec.py`, `export_schem.py` end-to-end for both examples
- Import resulting `.schem` files in WorldEdit on Java `1.20.4` and verify placement/orientation behavior.

## Recommended next step

Run one clean end-to-end manual smoke test (validate → compile → export → WorldEdit import) for both examples after installing `mcschematic`, then decide whether to encode compiler constraints more explicitly in `schema/build_schema.json` to reduce future drift.
