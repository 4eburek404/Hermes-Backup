"""Shared assertions for the public JSON CLI envelope."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "cli-envelope.v1.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def assert_valid_cli_envelope(
    test: unittest.TestCase, payload: dict[str, Any]
) -> None:
    errors = list(VALIDATOR.iter_errors(payload))
    test.assertEqual(errors, [], "CLI envelope failed tracked schema validation")
