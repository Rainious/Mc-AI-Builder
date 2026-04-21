# GitHub Copilot Instructions for Minecraft AI Builder

This repository is a personal project to create a local Minecraft AI builder.

Key Instructions:

* Target Minecraft version: Java 1.20.4.
* Primary workflow: AI generates BuildSpec JSON → validate → export .schem → manual import with WorldEdit.
* AI must not output direct WorldEdit commands or binary schematic files.
* All outputs must pass schema validation.
* Prefer Python for all scripts.
* Ignore multiplayer, rankings, Docker orchestration, and mineflayer bot for first phase.
* Use examples in the `examples/` folder as few-shot reference.
* Follow `schema/build_schema.json` strictly.

- For context, Copilot may refer to documents and libraries located in `References/`.
- Sometimes the existing materials  may not be entirely accurate. If errors are discovered during the development process, please attempt to locate the referenced materials for correction
