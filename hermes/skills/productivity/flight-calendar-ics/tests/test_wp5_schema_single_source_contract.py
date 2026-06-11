"""Contract test for WP-5: envelope schema single-source consolidation.

The envelope schema must define shared vocabularies (bundle routes, commands,
private file modes) exactly once in ``$defs`` and reference them everywhere,
and those vocabularies must stay locked to the code-owned lists in
``flight_calendar.contracts``.
"""
from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "schemas" / "cli-envelope.v1.schema.json"


def load_contracts():
    script_dir = str((SKILL_ROOT / "scripts").resolve())
    old_path = list(sys.path)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        return importlib.import_module("flight_calendar.contracts")
    finally:
        sys.path[:] = old_path


class EnvelopeSchemaSingleSourceContract(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.defs = self.schema.get("$defs") or {}

    def test_shared_vocabularies_live_in_defs(self) -> None:
        for name in ["bundle_route", "command", "file_mode"]:
            self.assertIn(name, self.defs, f"$defs.{name} must exist")

    def test_defs_are_locked_to_code_owned_contracts(self) -> None:
        contracts = load_contracts()
        self.assertEqual(self.defs["bundle_route"]["enum"], contracts.BUNDLE_ROUTES)
        self.assertEqual(self.defs["command"]["enum"], [*contracts.COMMANDS, "unknown"])
        self.assertEqual(self.defs["file_mode"]["pattern"], "^[0-7]{3,4}$")

    def test_no_inline_duplicates_outside_defs(self) -> None:
        body = {k: v for k, v in self.schema.items() if k != "$defs"}
        serialized = json.dumps(body, sort_keys=True)
        contracts = load_contracts()
        self.assertNotIn(json.dumps(contracts.BUNDLE_ROUTES), serialized,
                         "route enum must appear only in $defs")
        self.assertNotIn(json.dumps([*contracts.COMMANDS, "unknown"]), serialized,
                         "command enum must appear only in $defs")
        self.assertNotIn("^[0-7]{3,4}$", serialized,
                         "file mode pattern must appear only in $defs")

    def test_refs_are_actually_used(self) -> None:
        serialized = json.dumps(self.schema)
        for name, min_uses in [("bundle_route", 4), ("command", 2), ("file_mode", 4)]:
            uses = serialized.count(f"#/$defs/{name}")
            self.assertGreaterEqual(uses, min_uses, f"$defs/{name} must be referenced >= {min_uses}x")


if __name__ == "__main__":
    unittest.main()
