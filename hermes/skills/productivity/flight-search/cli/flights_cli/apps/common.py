from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..contracts.registry import current_contract
from ..contracts.schema_errors import validation_error_detail
from ..errors import CliError


def read_json_document(path: str) -> dict[str, Any]:
    if path == "-":
        import sys

        text = sys.stdin.read()
        source = "stdin"
    else:
        source = path
        try:
            text = Path(path).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise CliError(f"could not read JSON input {path!r}: {exc}", error_type="not_found") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON in {source}: {exc.msg}", error_type="validation_error") from exc
    if not isinstance(payload, dict):
        raise CliError("JSON input must be an object", error_type="validation_error")
    return payload


@lru_cache(maxsize=None)
def load_contract_schema(contract_name: str) -> dict[str, Any]:
    contract = current_contract(contract_name)
    text = resources.files("flights_cli.contracts").joinpath(contract["schema_resource"]).read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


def validate_contract_payload(contract_name: str, payload: dict[str, Any], *, error_type: str = "contract_error") -> None:
    validator = Draft202012Validator(load_contract_schema(contract_name))
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        contract = current_contract(contract_name)
        raise CliError(
            f"{contract['schema_version']} failed contract validation",
            error_type=error_type,
            details={
                "schema_version": contract["schema_version"],
                "errors": [validation_error_detail(error) for error in errors[:10]],
            },
        )
