"""Generate a BuildSpec from natural language and export it to .schem."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema

from main import run_pipeline
from validate_spec import REQUIRED_FIELDS, validate_buildspec


class NaturalBuildError(Exception):
    """Raised when the natural language build pipeline fails."""


def _repo_root() -> Path:
    """Return repository root path from this script location."""
    return Path(__file__).resolve().parents[1]


def _default_schema_path() -> Path:
    """Return default schema file path."""
    return _repo_root() / "schema" / "build_schema.json"


def _default_catalog_path() -> Path:
    """Return default block catalog path."""
    return _repo_root() / "data" / "block_catalog.json"


def _load_json_file(path: Path, label: str) -> Any:
    """Load JSON from disk with clear errors."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise NaturalBuildError(f"{label} file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise NaturalBuildError(f"Invalid JSON in {label} file ({path}): {exc}") from exc
    except OSError as exc:
        raise NaturalBuildError(f"Failed to read {label} file ({path}): {exc}") from exc


def _build_request_payload(
    description: str,
    schema_data: Any,
    catalog_data: Any,
    model: str | None,
    temperature: float,
    response_format_mode: str,
) -> dict[str, Any]:
    """Create an OpenAI-compatible chat-completions payload."""
    system_prompt = (
        "You are a Minecraft BuildSpec generator for Java 1.20.4. "
        "Return ONLY valid JSON (no markdown/code fences). "
        "The JSON must strictly conform to the provided schema. "
        "Palette values must use only blocks from the provided block catalog. "
        "Use operations among: set, box, box_hollow, line."
    )
    user_prompt = (
        "Generate a BuildSpec JSON for this request:\n"
        f"{description}\n\n"
        "JSON Schema:\n"
        f"{json.dumps(schema_data, ensure_ascii=False)}\n\n"
        "Allowed block catalog:\n"
        f"{json.dumps(catalog_data, ensure_ascii=False)}"
    )

    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    # Compatibility strategy:
    # - json_schema: best for providers that support schema-constrained decoding.
    # - json_object: required by DeepSeek for JSON mode compatibility.
    # - prompt_only: no response_format; rely on prompt + local validation.
    if response_format_mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "buildspec",
                "schema": schema_data,
            },
        }
    elif response_format_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}
    elif response_format_mode != "prompt_only":
        raise NaturalBuildError(
            "Invalid response format mode. Use one of: json_schema, json_object, prompt_only"
        )
    if model:
        payload["model"] = model
    return payload


def _resolve_response_format_mode(
    model_url: str,
    response_format_mode: str | None,
    include_schema_response_format: bool,
) -> str:
    """Resolve response_format mode from explicit setting, legacy flag, and provider defaults."""
    if response_format_mode is not None:
        return response_format_mode

    # Backward-compatible override from existing CLI flag.
    if not include_schema_response_format:
        return "prompt_only"

    parsed = urllib.parse.urlparse(model_url)
    host = (parsed.hostname or "").lower()
    if not host and "://" not in model_url:
        # Support host-like endpoints (for example: api.deepseek.com/v1/chat/completions).
        parsed_with_scheme = urllib.parse.urlparse(f"https://{model_url}")
        host = (parsed_with_scheme.hostname or "").lower()

    # DeepSeek's chat-completions compatibility expects json_object mode.
    if host == "deepseek.com" or host.endswith(".deepseek.com"):
        return "json_object"
    # Keep OpenAI as schema-first baseline.
    if host == "openai.com" or host.endswith(".openai.com"):
        return "json_schema"
    # Unknown providers: omit response_format for broad compatibility.
    return "prompt_only"


def _extract_json_from_text(raw_text: str) -> Any:
    """Parse JSON text, including common fenced output formats."""
    stripped = raw_text.strip()
    if not stripped:
        raise NaturalBuildError("Model returned empty text response")

    # Try direct JSON first.
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from fenced code block.
    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", stripped, re.DOTALL)
    if not match:
        raise NaturalBuildError("Model text response is not valid JSON")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise NaturalBuildError(f"Failed to parse JSON from fenced model response: {exc}") from exc


def _required_fields_from_schema(schema_data: Any) -> set[str]:
    """Return required top-level fields from schema when available."""
    if isinstance(schema_data, dict):
        required = schema_data.get("required")
        if isinstance(required, list) and all(isinstance(item, str) for item in required):
            return set(required)
    # Fallback to the validator's required fields to keep behavior consistent.
    return set(REQUIRED_FIELDS)


def _allowed_blocks_from_catalog_data(catalog_data: Any) -> set[str]:
    """Extract allowed block names from loaded catalog JSON."""
    if not isinstance(catalog_data, list):
        raise NaturalBuildError("Invalid block catalog format: expected a JSON array")

    allowed: set[str] = set()
    for item in catalog_data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str):
            allowed.add(name)

    if not allowed:
        raise NaturalBuildError("No valid block names found in block catalog")
    return allowed


def _extract_buildspec_from_response(response_json: Any, required_fields: set[str]) -> Any:
    """Extract BuildSpec JSON from common model API response formats."""
    # Some APIs return raw BuildSpec object directly.
    if isinstance(response_json, dict) and required_fields.issubset(response_json.keys()):
        return response_json

    if isinstance(response_json, dict):
        # Common wrappers from different APIs.
        for key in ("buildspec", "output", "result", "data"):
            candidate = response_json.get(key)
            if isinstance(candidate, dict):
                return candidate
            if isinstance(candidate, str):
                return _extract_json_from_text(candidate)

        # OpenAI-compatible chat completions format.
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return _extract_json_from_text(content)
                    # Some APIs return structured content chunks.
                    if isinstance(content, list):
                        combined = "".join(
                            text
                            for item in content
                            if isinstance(item, dict) and isinstance((text := item.get("text")), str)
                        )
                        if combined:
                            return _extract_json_from_text(combined)

                # Fallback for plain text output field.
                text = first_choice.get("text")
                if isinstance(text, str):
                    return _extract_json_from_text(text)

    raise NaturalBuildError("Could not extract BuildSpec JSON from model API response")


def _post_json(url: str, payload: dict[str, Any], api_key: str | None, timeout: float) -> Any:
    """Send JSON POST request and parse JSON response."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise NaturalBuildError(f"Model API HTTP error {exc.code}: {error_text}") from exc
    except urllib.error.URLError as exc:
        raise NaturalBuildError(f"Failed to reach model API: {exc.reason}") from exc
    except socket.timeout as exc:
        raise NaturalBuildError("Timed out waiting for model API response") from exc

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise NaturalBuildError(f"Model API returned invalid JSON response: {exc}") from exc


def _validate_generated_buildspec(spec: Any, schema_data: Any, allowed_blocks: set[str]) -> None:
    """Validate generated BuildSpec against JSON schema and local project checks."""
    # First validate against JSON schema.
    try:
        validate_json_schema(instance=spec, schema=schema_data)
    except JsonSchemaValidationError as exc:
        raise NaturalBuildError(f"Generated BuildSpec failed schema validation: {exc.message}") from exc

    # Then enforce project-specific checks from existing validator.
    errors = validate_buildspec(spec, allowed_blocks)
    if errors:
        raise NaturalBuildError("Generated BuildSpec failed local validation:\n" + "\n".join(errors))


def generate_and_export_schematic(
    description: str,
    model_url: str,
    model: str | None = None,
    outdir: Path | None = None,
    schema_path: Path | None = None,
    catalog_path: Path | None = None,
    api_key: str | None = None,
    timeout: float = 120.0,
    keep_temp: bool = False,
    temperature: float = 0.2,
    include_schema_response_format: bool = True,
    response_format_mode: str | None = None,
) -> tuple[Path, Path]:
    """Run natural language to .schem pipeline and return (.schem path, temp JSON path)."""
    resolved_schema_path = schema_path or _default_schema_path()
    resolved_catalog_path = catalog_path or _default_catalog_path()
    resolved_outdir = outdir or (_repo_root() / "out")

    # Step 1: Read schema and block catalog from repository files.
    schema_data = _load_json_file(resolved_schema_path, "schema")
    catalog_data = _load_json_file(resolved_catalog_path, "block catalog")
    allowed_blocks = _allowed_blocks_from_catalog_data(catalog_data)

    # Step 2: Build API payload containing prompt + schema + catalog context.
    resolved_response_format_mode = _resolve_response_format_mode(
        model_url=model_url,
        response_format_mode=response_format_mode,
        include_schema_response_format=include_schema_response_format,
    )
    payload = _build_request_payload(
        description=description,
        schema_data=schema_data,
        catalog_data=catalog_data,
        model=model,
        temperature=temperature,
        response_format_mode=resolved_response_format_mode,
    )

    # Step 3-4: Call model API and extract BuildSpec JSON from response.
    response_json = _post_json(model_url, payload, api_key=api_key, timeout=timeout)
    required_fields = _required_fields_from_schema(schema_data)
    generated_spec = _extract_buildspec_from_response(response_json, required_fields)

    # Step 5: Validate generated BuildSpec locally before export.
    _validate_generated_buildspec(generated_spec, schema_data, allowed_blocks)

    # Step 6: Save generated BuildSpec to a temporary JSON file.
    temp_dir = tempfile.mkdtemp(prefix="minecraft_ai_builder_")
    temp_path = Path(temp_dir) / "generated_buildspec.json"
    schem_path: Path | None = None
    try:
        # Step 7-8: Save temp BuildSpec and call existing main.py pipeline programmatically.
        output_name = generated_spec.get("name") if isinstance(generated_spec, dict) else None
        output_name = output_name if isinstance(output_name, str) and output_name.strip() else None

        try:
            temp_path.write_text(
                json.dumps(generated_spec, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise NaturalBuildError(f"Failed to write temporary BuildSpec file ({temp_path}): {exc}") from exc

        try:
            schem_path = run_pipeline(
                buildspec_path=temp_path,
                catalog_path=resolved_catalog_path,
                outdir=resolved_outdir,
                name=output_name,
            )
        except Exception as exc:
            raise NaturalBuildError(f"Pipeline failed while creating schematic: {exc}") from exc
    finally:
        # Remove temp file by default, unless requested to keep it for debugging.
        if not keep_temp:
            # Cleanup is best-effort only; generation may have already succeeded/failed.
            shutil.rmtree(temp_path.parent, ignore_errors=True)

    if schem_path is None:
        raise NaturalBuildError("Pipeline failed to produce schematic output path")
    return schem_path, temp_path


def main() -> int:
    """CLI entrypoint for natural language BuildSpec generation + schematic export."""
    parser = argparse.ArgumentParser(
        description="Generate BuildSpec from natural language via model API and export .schem"
    )
    parser.add_argument("description", help="Natural language description of the building")
    parser.add_argument("--model-url", required=True, help="Model API URL/endpoint")
    parser.add_argument("--model", help="Optional model name/identifier")
    parser.add_argument("--outdir", default=None, help="Optional output directory for .schem")
    parser.add_argument("--schema", default=None, help="Optional schema path (default: schema/build_schema.json)")
    parser.add_argument("--catalog", default=None, help="Optional block catalog path (default: data/block_catalog.json)")
    parser.add_argument("--api-key", default=None, help="Optional API key (default: MODEL_API_KEY env var)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Model API timeout in seconds (default: 120)")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature sent to the model API (default: 0.2)",
    )
    parser.add_argument(
        "--no-schema-response-format",
        action="store_true",
        help="Deprecated legacy switch to force prompt_only mode (prefer --response-format-mode)",
    )
    parser.add_argument(
        "--response-format-mode",
        choices=("json_schema", "json_object", "prompt_only"),
        default=None,
        help=(
            "Optional response_format compatibility mode. "
            "Default: provider-aware auto mode (DeepSeek=json_object, OpenAI=json_schema, others=prompt_only)."
        ),
    )
    parser.add_argument("--keep-temp", action="store_true", help="Keep generated temporary BuildSpec JSON file")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("MODEL_API_KEY")
    outdir = Path(args.outdir) if args.outdir else None
    schema = Path(args.schema) if args.schema else None
    catalog = Path(args.catalog) if args.catalog else None

    try:
        schem_path, temp_path = generate_and_export_schematic(
            description=args.description,
            model_url=args.model_url,
            model=args.model,
            outdir=outdir,
            schema_path=schema,
            catalog_path=catalog,
            api_key=api_key,
            timeout=args.timeout,
            keep_temp=args.keep_temp,
            temperature=args.temperature,
            include_schema_response_format=not args.no_schema_response_format,
            response_format_mode=args.response_format_mode,
        )
    except NaturalBuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(str(schem_path))
    if args.keep_temp:
        print(f"Temporary BuildSpec: {temp_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
