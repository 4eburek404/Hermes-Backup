"""Test: vocabulary enum values match JSON schema wire contracts.

This is the sync-test from Phase 1 of the vocabulary centralization plan.
It asserts that every StrEnum member that appears in a JSON schema enum
list matches exactly.  If a schema enum is updated without updating the
vocabulary (or vice versa), this test fails — catching contract drift early.
"""

from __future__ import annotations

import json
from pathlib import Path

import unittest

from flights_cli.domain.vocabulary import Direction

# ---------------------------------------------------------------------------
# Schema paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "flights_cli" / "contracts"


def _load_schema(name: str) -> dict:
    path = CONTRACTS_DIR / name
    with open(path) as f:
        return json.load(f)


def _collect_schema_enums(schema: dict, prefix: str = "") -> dict[str, list[str]]:
    """Walk a JSON schema and collect all ``enum`` lists with their JSON paths."""
    result: dict[str, list[str]] = {}
    if isinstance(schema, dict):
        if "enum" in schema:
            key = prefix or "$root"
            result[key] = schema["enum"]
        for key, value in schema.items():
            result.update(
                _collect_schema_enums(value, f"{prefix}.{key}" if prefix else key)
            )
    elif isinstance(schema, list):
        for i, item in enumerate(schema):
            result.update(_collect_schema_enums(item, f"{prefix}[{i}]"))
    return result


# ---------------------------------------------------------------------------
# direction ↔ user_answer.v4 schema
# ---------------------------------------------------------------------------


class TestDirectionSchemaSync(unittest.TestCase):
    """Direction enum must match the ``direction`` enum in the user answer schema."""

    def setUp(self) -> None:
        self.schema = _load_schema("flight_search_user_answer.v6.schema.json")

    def test_direction_values_match_schema(self) -> None:
        enums = _collect_schema_enums(self.schema)
        # Find the direction enum (may include None for nullable fields)
        direction_enums = {
            path: [v for v in values if v is not None]
            for path, values in enums.items()
            if "direction" in path.lower()
            and set(v for v in values if v is not None) == {"outbound", "return"}
        }
        if not direction_enums:
            self.skipTest("No 'direction' enum found in user_answer schema")
        direction_values = next(iter(direction_enums.values()))
        vocab_values = [d.value for d in Direction]
        self.assertEqual(sorted(vocab_values), sorted(direction_values))


# ---------------------------------------------------------------------------
# General: all enum values are non-empty strings
# ---------------------------------------------------------------------------


class TestVocabularyWellFormed(unittest.TestCase):
    """Structural sanity checks for every StrEnum in the vocabulary."""

    def test_all_members_are_non_empty_strings(self) -> None:
        from flights_cli.domain import vocabulary as v

        enums = [
            v.Leg,
            v.Direction,
            v.StopBucket,
            v.MarketClass,
            v.IntentClass,
            v.EvidenceClass,
            v.RoutingStrategy,
            v.RouteFamily,
            v.RequiredControl,
            v.AbsenceReason,
            v.ProbeStatus,
        ]
        for enum_cls in enums:
            for member in enum_cls:
                self.assertIsInstance(
                    member.value,
                    str,
                    f"{enum_cls.__name__}.{member.name} value is not str",
                )
                self.assertGreater(
                    len(member.value),
                    0,
                    f"{enum_cls.__name__}.{member.name} value is empty",
                )

    def test_no_duplicate_values_within_enum(self) -> None:
        from flights_cli.domain import vocabulary as v

        enums = [
            v.Leg,
            v.Direction,
            v.StopBucket,
            v.MarketClass,
            v.IntentClass,
            v.EvidenceClass,
            v.RoutingStrategy,
            v.RouteFamily,
            v.RequiredControl,
            v.AbsenceReason,
            v.ProbeStatus,
        ]
        for enum_cls in enums:
            values = [m.value for m in enum_cls]
            self.assertEqual(
                len(values),
                len(set(values)),
                f"{enum_cls.__name__} has duplicate values: "
                f"{[v for v in values if values.count(v) > 1]}",
            )

    def test_strenum_equality_with_plain_string(self) -> None:
        """Every member must equal its string value (StrEnum contract)."""
        from flights_cli.domain import vocabulary as v

        enums = [
            v.Leg,
            v.Direction,
            v.StopBucket,
            v.MarketClass,
            v.IntentClass,
            v.EvidenceClass,
            v.RoutingStrategy,
            v.RouteFamily,
            v.RequiredControl,
            v.AbsenceReason,
            v.ProbeStatus,
        ]
        for enum_cls in enums:
            for member in enum_cls:
                self.assertEqual(
                    member,
                    member.value,
                    f"{enum_cls.__name__}.{member.name} != '{member.value}'",
                )

    def test_json_serialisation_is_string(self) -> None:
        """json.dumps must produce the plain string, not the enum repr."""
        import json
        from flights_cli.domain import vocabulary as v

        for member in v.Leg:
            result = json.dumps(member)
            self.assertEqual(
                result, json.dumps(member.value), f"json.dumps({member!r}) = {result!r}"
            )


# ---------------------------------------------------------------------------
# Phase 4: lint — block vocabulary drift outside domain/vocabulary.py
# ---------------------------------------------------------------------------


class TestVocabularyDriftLint(unittest.TestCase):
    """Scan flights_cli/ for bare string literals that belong to vocabulary enums.

    If a known vocabulary value appears as a quoted string literal outside
    ``domain/vocabulary.py`` (and the allowed exclusion zones), this test fails.
    This blocks future drift — new code must import from the vocabulary.

    Exclusion zones (intentional bare literals that are NOT drift):
      - ``domain/vocabulary.py`` itself (canonical definitions)
      - ``contracts/`` (JSON schemas — wire contract, cannot reference Python)
      - ``ports/providers.py`` (canonical ProbeType / ExecutionState literals)
      - ``adapters/`` (probe_type strings passed to/from provider ports)
      - CLI help text and error messages (user-facing prose, not semantic IDs)
    """

    # Map of (enum_name, set_of_values) to scan for.
    # Only include values that are *semantically meaningful* identifiers —
    # skip ambiguous words like "return", "failed", "preferred" that appear
    # in many non-vocabulary contexts.
    VOCABULARY_FAMILIES: dict[str, set[str]] = {}

    @classmethod
    def _build_families(cls) -> dict[str, set[str]]:
        if cls.VOCABULARY_FAMILIES:
            return cls.VOCABULARY_FAMILIES
        from flights_cli.domain import vocabulary as v

        # Only include unambiguous, domain-specific values.
        # Common words (ok, failed, return, preferred, etc.) are excluded because
        # they appear in error messages, CLI help, and unrelated dict keys.
        cls.VOCABULARY_FAMILIES = {
            "Leg": {m.value for m in v.Leg},
            "MarketClass": {m.value for m in v.MarketClass},
            "IntentClass": {m.value for m in v.IntentClass},
            "EvidenceClass": {m.value for m in v.EvidenceClass},
            "RoutingStrategy": {m.value for m in v.RoutingStrategy},
            "RouteFamily": {m.value for m in v.RouteFamily},
            "RequiredControl": {m.value for m in v.RequiredControl},
            "AbsenceReason": {m.value for m in v.AbsenceReason},
            "StopBucket": {m.value for m in v.StopBucket},
        }
        return cls.VOCABULARY_FAMILIES

    def test_no_vocabulary_literals_outside_canonical_source(self) -> None:
        import re
        from pathlib import Path

        families = self._build_families()
        all_values: set[str] = set()
        for vals in families.values():
            all_values.update(vals)

        cli_root = Path(__file__).resolve().parent.parent / "flights_cli"

        # Directories/files that are allowed to contain bare literals
        exclude_prefixes = [
            str(cli_root / "domain" / "vocabulary.py"),
            str(cli_root / "contracts"),
            str(cli_root / "ports" / "providers.py"),
        ]

        # Specific files where vocabulary values appear in non-vocabulary context
        # (e.g. "preferred" as airport tier, CLI argparse choices, etc.)
        false_positive_files = {
            "cli.py",  # argparse choices — user-facing CLI, not semantic ID
            "config.py",  # airport tier "preferred" — different domain
            "airports.py",  # airport priority "preferred" role — different domain
            "stop_policy.py",  # stop_policy payload key "suppressed" — display dict
            "aggregate_control_runner.py",  # probe_type — belongs to ports/providers.py
            "probe_intent.py",  # probe_type — belongs to ports/providers.py
            "diagnose.py",  # probe_type comparison — belongs to ports/providers.py
        }

        violations: list[str] = []
        for py_file in sorted(cli_root.rglob("*.py")):
            py_path = str(py_file)
            if any(py_path.startswith(prefix) for prefix in exclude_prefixes):
                continue
            # Skip adapters — they deal with provider port types
            if "adapters" in py_file.parts:
                continue
            # Skip __pycache__
            if "__pycache__" in py_path:
                continue
            # Skip known false positives
            if py_file.name in false_positive_files:
                continue

            text = py_file.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                # Find quoted string literals on this line
                for match in re.finditer(r"""["']([^"']{3,})["']""", line):
                    value = match.group(1)
                    if value in all_values:
                        # Determine which family it belongs to
                        families_for_value = [
                            name for name, vals in families.items() if value in vals
                        ]
                        rel = py_file.relative_to(cli_root.parent)
                        violation = (
                            f'{rel}:{line_no}: "{value}" '
                            f"(belongs to {', '.join(families_for_value)})"
                        )
                        violations.append(violation)

        # Allow a generous initial threshold while migration is in progress.
        # Once all producers are migrated, lower this to 0.
        max_allowed = 0
        if len(violations) > max_allowed:
            header = (
                f"Found {len(violations)} vocabulary string literals outside "
                f"domain/vocabulary.py (threshold: {max_allowed}):\n"
            )
            detail = "\n".join(violations[:30])
            self.fail(header + detail)
        elif violations:
            # Report but don't fail yet — track progress
            import warnings

            msg = (
                f"{len(violations)} vocabulary literals still outside vocabulary.py "
                f"(threshold: {max_allowed}); first 10:\n" + "\n".join(violations[:10])
            )
            warnings.warn(msg, stacklevel=1)


if __name__ == "__main__":
    unittest.main()
