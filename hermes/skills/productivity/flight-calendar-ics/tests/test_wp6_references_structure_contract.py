"""Contract test for WP-6: references restructuring for small-context agents.

Locks the target reference tree (4 carrier files merged into one, core pairs
merged, registry reduced to a pure ownership map), the single-owner rule for
the sensitive-data class list, removal of operational API flows from carrier
prose (they are code-owned), the total context budget, and a green
``maint refs registry-check``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REFS = SKILL_ROOT / "references"
CLI = SKILL_ROOT / "scripts" / "flight_calendar_ics.py"

EXPECTED_TREE = {
    "registry.md",
    "carriers.md",
    "core/architecture.md",
    "core/itinerary.md",
    "core/privacy-hardening.md",
    "core/timezone-catalog.md",
    "maintenance/operations.md",
    "maintenance/evaluation.md",
}

# Distinctive line from the canonical sensitive-class list.
PRIVACY_SIGNATURE = "passenger names and identity fields"

# Operational API details that must live in code, not in carrier prose.
CODE_OWNED_MARKERS = ["/se/api/", "graphql", "oauth/token", "X-Api-Key", "X-App-Identity", "api/v3/orders"]


def all_reference_files() -> set[str]:
    return {p.relative_to(REFS).as_posix() for p in REFS.rglob("*.md")}


class ReferencesStructureContract(unittest.TestCase):
    def test_reference_tree_matches_target(self) -> None:
        self.assertEqual(all_reference_files(), EXPECTED_TREE)

    def test_registry_is_a_pure_ownership_map(self) -> None:
        text = (REFS / "registry.md").read_text(encoding="utf-8")
        self.assertNotIn("## Principles", text)
        self.assertNotIn("## Absorbed legacy map", text)
        self.assertNotIn("## Add/change rules", text)
        self.assertLessEqual(len(text.splitlines()), 30)

    def test_sensitive_class_list_has_single_owner(self) -> None:
        owners = []
        for path in [SKILL_ROOT / "SKILL.md", *sorted(REFS.rglob("*.md"))]:
            if PRIVACY_SIGNATURE in path.read_text(encoding="utf-8"):
                owners.append(path.relative_to(SKILL_ROOT).as_posix())
        self.assertEqual(owners, ["references/core/privacy-hardening.md"])

    def test_carrier_prose_has_no_code_owned_api_flows(self) -> None:
        text = (REFS / "carriers.md").read_text(encoding="utf-8")
        for marker in CODE_OWNED_MARKERS:
            self.assertNotIn(marker, text, f"operational detail '{marker}' belongs in code, not prose")

    def test_reference_context_budget(self) -> None:
        total = sum(p.stat().st_size for p in REFS.rglob("*.md"))
        self.assertLessEqual(total, 26000, f"references total {total} chars exceeds small-context budget")
        self.assertLessEqual((REFS / "carriers.md").stat().st_size, 6500)

    def test_skill_md_points_only_to_existing_references(self) -> None:
        import re

        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for ref in re.findall(r"`references/([^`]+\.md)`", text):
            self.assertIn(ref, EXPECTED_TREE, f"SKILL.md links to missing references/{ref}")

    def test_maint_refs_registry_check_is_green(self) -> None:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [sys.executable, str(CLI), "--json", "maint", "refs", "registry-check"],
            cwd=SKILL_ROOT, env=env, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)["data"]
        self.assertTrue(data["ok"], data)


if __name__ == "__main__":
    unittest.main()
