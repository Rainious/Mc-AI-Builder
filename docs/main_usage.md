# main.py usage

`src/main.py` runs the MVP pipeline end-to-end in one command:

1. Validate BuildSpec JSON
2. Compile ops to explicit block placements
3. Export placements to a WorldEdit-compatible `.schem` file

## Run

From repository root:

```bash
python src/main.py examples/test_tower.json
```

Optional flags:

- `--catalog <path>`: block catalog JSON (default: `data/block_catalog.json`)
- `--outdir <path>`: output folder for `.schem` (default: `./out`)
- `--name <schem_name>`: output schematic name without `.schem`

Example:

```bash
python src/main.py examples/test1.json --outdir out --name cottage
```

## Input

- One BuildSpec JSON file matching project conventions (`schema/build_schema.json`)
- Palette block IDs should match allowed blocks in `data/block_catalog.json`

## Output

- Prints the generated schematic path
- Writes `<name>.schem` in the output directory

## Manual step after export

Import the generated `.schem` file into Minecraft (Java 1.20.4) with WorldEdit.
