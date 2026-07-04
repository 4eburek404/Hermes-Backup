from __future__ import annotations

import re
import unittest
from pathlib import Path

from flights_cli.contracts.registry import current_contract


SKILL_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_REFERENCES = {
    "index.md",
    "report-contract.md",
    "source-boundaries.md",
    "provider-aware-airport-priority.md",
    "pipeline-reference.md",
    "debug-playbook.md",
    "direct-date-window.md",
    "rail-rzd-live-pricing.md",
    "cli-maintenance.md",
    "tutu-mcp-provider.md",
    "route-network-discovery.md",
}
REMOVED_COMMAND_PATTERNS = (
    r"\broute\s+live-assemble\b",
    r"(?<!maint\s)\bdoctor\b",
    r"(?<!maint\s)\bcatalog\s+update\b",
    r"\bmaintenance\s+check\b",
)
VERSION_TOKEN_RE = re.compile(
    r"\b(agent_report|(?:flight_search_)?user_answer|(?:flight_search_)?result)\.v(\d+)\b"
)


def docs_text() -> str:
    paths = [SKILL_ROOT / "SKILL.md", *(SKILL_ROOT / "references").glob("*.md")]
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(paths))


def expected_version_major(contract_name: str) -> int:
    version = str(current_contract(contract_name)["schema_version"])
    return int(version.rsplit(".v", 1)[1])


def token_family(raw: str) -> str:
    if raw == "agent_report":
        return "agent_report"
    if raw.endswith("user_answer"):
        return "user_answer"
    return "search_result"


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

    def test_documented_contract_versions_match_registry(self) -> None:
        expected = {
            "agent_report": expected_version_major("agent_report"),
            "user_answer": expected_version_major("user_answer"),
            "search_result": expected_version_major("search_result"),
        }
        mismatches = []
        for match in VERSION_TOKEN_RE.finditer(docs_text()):
            family = token_family(match.group(1))
            observed = int(match.group(2))
            if observed != expected[family]:
                mismatches.append(
                    f"{match.group(0)} expected v{expected[family]}"
                )
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
