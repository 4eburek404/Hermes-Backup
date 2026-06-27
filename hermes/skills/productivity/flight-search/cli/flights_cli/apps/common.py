from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

from ..contracts.registry import current_contract
from ..contracts.schema_errors import validation_error_detail
from ..errors import CliError


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
