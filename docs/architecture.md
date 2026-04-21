# Architecture: Local Minecraft AI Builder

## 1. Purpose

This document defines the architecture of the Minecraft AI Builder project. It clarifies the responsibilities of each module, the data flow, and serves as a reference for Copilot to follow project conventions.

## 2. Core Modules

| Module Name   | Responsibility                                    | Input                  | Output                 | Notes                                                  |
| ------------- | ------------------------------------------------- | ---------------------- | ---------------------- | ------------------------------------------------------ |
| prompt_ingest | Processes natural language requests               | User prompt            | BuildSpec JSON         | AI-generated JSON BuildSpec                            |
| validator     | Validates BuildSpec JSON against schema           | BuildSpec JSON         | Pass/Error report      | Checks block IDs, allowed operations, and size bounds  |
| compiler      | Expands BuildSpec primitives into discrete blocks | BuildSpec JSON         | Block coordinates list | Supports `box`, `line`, `set`, `box_hollow` primitives |
| exporter      | Uses mcschematic to export schematic file         | Block coordinates list | `.schem` file          | For WorldEdit import                                   |
| examples      | Contains sample BuildSpec files                   | JSON BuildSpec         | `.schem` files         | Provides few-shot reference for AI                     |

## 3. Data Flow

```
User prompt -> prompt_ingest -> BuildSpec JSON
       -> validator -> compiled_blocks
       -> exporter -> .schem
       -> WorldEdit import
```

## 4. References

* `.github/copilot-instructions.md` for Copilot repository context ([docs.github.com](https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot))
* Deep Research Report modules and diagrams ([deep-research-report.md](sandbox:/mnt/data/deep-research-report.md))
* MC-Bench `orchestrator` modular approach ([GitHub MC-Bench Orchestrator](https://github.com/mc-bench/orchestrator))
* WorldEdit schematic documentation ([worldedit.enginehub.org](https://worldedit.enginehub.org/en/latest/commands/?utm_source=chatgpt.com))
* PrismarineJS `minecraft-data` / `mineflayer` API ([github.com/prismarinejs/mineflayer](https://github.com/prismarinejs/mineflayer))

## 5. Formatting Notes

* Markdown format is used with tables and ASCII flowchart.
* Module description should be 3-5 lines each.
* No implementation code, only module responsibilities and I/O.
