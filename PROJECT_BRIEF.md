# Project Brief: Local Minecraft AI Builder

## Project Goal

Build a system where natural language requests are converted by AI into structured JSON BuildSpec and exported as `.schem` files for WorldEdit import in Minecraft Java 1.20.4.

## Non-Goals

* Multiplayer, online benchmarking, or rankings.
* Containerized orchestration.
* Mineflayer bot auto-building (for first phase).

## Technology Stack

* Python 3.x
* mcschematic library
* WorldEdit plugin on Paper 1.20.4 server
* JSON schema validation

## Phase 1 Tasks

* Implement JSON schema validation.
* Implement BuildSpec to `.schem` export.
* Provide 1–3 working examples in `examples/`.
* Ensure all generated `.schem` files are compatible with WorldEdit import.

## References

* Follow `.github/copilot-instructions.md` for Copilot context.
* Use `docs/architecture.md` and `schema/build_schema.json` for project rules and constraints.
