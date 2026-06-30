from __future__ import annotations

from pathlib import Path
import re
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_REFERENCES = {
    "index.md",
    "report-contract.md",
    "source-boundaries.md",
    "provider-aware-airport-priority.md",
    "pipeline-reference.md",
    "gateway-hardcode-map.md",
    "debug-playbook.md",
    "direct-date-window.md",
    "rail-rzd-live-pricing.md",
    "cli-maintenance.md",
    "provider-failover.md",
    "tutu-mcp-provider.md",
}
REMOVED_COMMAND_PATTERNS = (
    r"\broute\s+live-assemble\b",
    r"(?<!maint\s)\bdoctor\b",
    r"(?<!maint\s)\bcatalog\s+update\b",
    r"\bmaintenance\s+check\b",
)


class FlightSearchSkillDocsContractTests(unittest.TestCase):
    def test_skill_references_only_canonical_reference_markdown(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        referenced = set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", skill_text))
        self.assertTrue(referenced)
        self.assertTrue(
            referenced <= CANONICAL_REFERENCES,
            f"noncanonical references in SKILL.md: {sorted(referenced - CANONICAL_REFERENCES)}",
        )

    def test_no_new_active_reference_markdown_files_are_present(self) -> None:
        actual = {path.name for path in (SKILL_ROOT / "references").glob("*.md")}
        self.assertEqual(actual, CANONICAL_REFERENCES)

    def test_skill_uses_canonical_search_and_answer_path_without_removed_commands(
        self,
    ) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m flights_cli --json search --request", text)
        self.assertIn("data.agent_report.user_answer.rendered_text", text)
        self.assertNotIn("diagnostics.human_answer", text)
        self.assertNotIn("diagnostics.display", text)
        self.assertNotIn("answer_lines", text)
        for pattern in REMOVED_COMMAND_PATTERNS:
            self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main()
