import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_skill.py"
spec = importlib.util.spec_from_file_location("audit_skill", SCRIPT_PATH)
audit_skill = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_skill)


def write_skill(repo: Path, name: str, files: dict[str, str]) -> Path:
    skill_dir = repo / "skills" / "software-development" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    default_skill = """---
name: {name}
description: Use when testing static CLI inventory.
---

# {name}

## Overview
Fixture skill.

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
""".format(name=name)
    (skill_dir / "SKILL.md").write_text(files.pop("SKILL.md", default_skill), encoding="utf-8")
    for rel, content in files.items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return skill_dir / "SKILL.md"


class StaticCliInventoryTests(unittest.TestCase):
    def make_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        (repo / "skills").mkdir()
        return repo

    def report_for(self, repo: Path, skill_path: Path) -> dict:
        return audit_skill.audit_skill_report(skill_path, repo, audit_skill.collect_skill_map(repo))

    def test_skill_without_cli_marks_cli_contract_not_applicable(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "skill-without-cli", {})

        report = self.report_for(repo, skill_path)

        self.assertFalse(report["cli"]["exists"])
        self.assertEqual(report["checks"]["cli_contract"]["status"], "not_applicable")
        self.assertEqual(report["checks"]["cli_contract"]["execution_performed"], False)

    def test_skill_with_cli_pyproject_inventories_project_script(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "skill-with-cli-pyproject", {
            "cli/pyproject.toml": """[project]
name = "sample-cli"

[project.scripts]
sample-cli = "sample_cli.main:main"
""",
            "cli/sample_cli/main.py": "def main():\n    return 0\n",
        })

        report = self.report_for(repo, skill_path)

        self.assertEqual(report["checks"]["cli_contract"]["status"], "pass")
        self.assertEqual(report["checks"]["cli_contract"]["mode"], "static")
        self.assertEqual(report["checks"]["cli_contract"]["execution_performed"], False)
        self.assertTrue(any(item["kind"] == "project_script" and item["confidence"] == "high" for item in report["cli"]["entrypoints"]))

    def test_cli_contract_schema_is_reported(self):
        repo = self.make_repo()
        schema = json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "example", "type": "object"})
        skill_path = write_skill(repo, "skill-with-cli-contract-schema", {
            "cli/pkg/contracts/example.v1.schema.json": schema,
            "cli/pkg/__main__.py": "def main():\n    return 0\n",
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(any(item["path"].endswith("cli/pkg/contracts/example.v1.schema.json") for item in report["cli_contract_schemas"]))
        self.assertTrue(any(item["rule_id"] == "CLI_CONTRACT_SCHEMA_DETECTED" for item in report["findings"]))

    def test_json_claim_without_schema_warns(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "skill-with-json-claim-no-schema", {
            "cli/tool.py": "# Supports --json output with ok and issues fields\n",
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(report["cli"]["json_output_claims"])
        self.assertTrue(any(item["rule_id"] == "JSON_OUTPUT_CLAIM_WITHOUT_SCHEMA" and item["severity"] == "warning" for item in report["findings"]))

    def test_mutation_candidate_is_inventory_only(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "skill-with-mutation-candidate", {
            "cli/tool.py": "from pathlib import Path\n\ndef apply():\n    Path('x').write_text('changed')\n# --apply\n",
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(report["cli"]["mutating_command_candidates"])
        self.assertFalse(any(item["rule_id"] == "CLI_MUTATION_CANDIDATE_DETECTED" and item["severity"] == "blocker" for item in report["findings"]))


if __name__ == "__main__":
    unittest.main()
