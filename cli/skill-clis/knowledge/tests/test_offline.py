from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, input_text: str | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "knowledge_cli", "--json", *args],
        cwd=PROJECT,
        env=env,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"CLI failed: {proc.stderr}")
    return json.loads(proc.stdout)


class KnowledgeCliOfflineTests(unittest.TestCase):
    def test_plans_audit_detects_missing_status_and_closed_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            plans = root / "plans"
            plans.mkdir(parents=True)
            (root / "README.md").write_text("# Docs\n", encoding="utf-8")
            (plans / "README.md").write_text("# Plans\n", encoding="utf-8")
            (plans / "missing.md").write_text("# Missing Status\n", encoding="utf-8")
            (plans / "done.md").write_text(
                "# Done\n\nCurrent status: completed\n", encoding="utf-8"
            )

            result = run_cli("--docs-root", str(root), "plans", "audit")
            findings = result["data"]["findings"]
            classes = [item["class"] for item in findings]
            actions = [item.get("action") for item in findings]

            self.assertEqual(result["command"], "plans audit")
            self.assertIn("plan_status_drift", classes)
            self.assertIn("add_current_status", actions)
            self.assertIn("archive_plan", actions)

    def test_memory_metrics_uses_counts_without_dumping_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes = Path(tmp) / ".hermes"
            hermes.mkdir()
            db = hermes / "memory_store.db"
            con = sqlite3.connect(db)
            con.executescript(
                """
                create table facts (
                  fact_id integer primary key,
                  content text not null,
                  category text,
                  tags text,
                  trust_score real,
                  retrieval_count integer,
                  helpful_count integer,
                  created_at text,
                  updated_at text
                );
                create table facts_fts (content text);
                create table entities (entity_id integer primary key, name text);
                create table fact_entities (fact_id integer, entity_id integer);
                create table memory_banks (bank_id integer primary key, bank_name text);
                insert into facts values (1, 'secret content should not be printed', 'tool', '', 0.5, 0, 2, '2026-05-01', '2026-05-01');
                insert into facts_fts values ('secret content should not be printed');
                """
            )
            con.commit()
            con.close()

            result = run_cli("--hermes-home", str(hermes), "memory", "metrics")
            text = json.dumps(result, ensure_ascii=False)

            self.assertEqual(result["data"]["counts"]["facts"], 1)
            self.assertTrue(result["data"]["fts_consistent"])
            self.assertNotIn("secret content should not be printed", text)

    def test_distill_candidates_is_offline_by_default(self) -> None:
        result = run_cli(
            "distill",
            "candidates",
            "--input",
            "-",
            input_text="User corrected: do not touch Docker Hermes when analyzing local Hermes skills.",
        )

        self.assertEqual(result["command"], "distill candidates")
        self.assertEqual(result["data"]["mode"], "offline_heuristic")
        self.assertFalse(result["data"]["stats"]["live_model_calls"])
        self.assertGreaterEqual(result["data"]["stats"]["candidate_count"], 1)

    def test_skill_companion_reports_contract_without_dumping_full_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "knowledge-cli" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                """---
name: knowledge-cli
description: Use when auditing knowledge architecture with the knowledge CLI.
---

# knowledge CLI

Run `knowledge --json skill companion` first.
Then run `knowledge --json report --all`.
Never use CLI output as permission to edit docs, memory, skills, config, or cron.
""",
                encoding="utf-8",
            )

            result = run_cli("skill", "companion", "--path", str(skill))
            data = result["data"]
            text = json.dumps(result, ensure_ascii=False)

            self.assertEqual(result["command"], "skill companion")
            self.assertTrue(data["exists"])
            self.assertEqual(data["name"], "knowledge-cli")
            self.assertTrue(data["contract"]["mentions_self_check"])
            self.assertTrue(data["contract"]["mentions_report_all"])
            self.assertTrue(data["contract"]["mentions_mutation_boundary"])
            self.assertIn("knowledge --json skill companion", data["recommended_sequence"])
            self.assertNotIn("Never use CLI output as permission", text)

    def test_skill_companion_markdown_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "knowledge-cli" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                """---
name: knowledge-cli
description: Use when auditing knowledge architecture with the knowledge CLI.
---

# knowledge CLI

Run `knowledge --json skill companion` first.
Run `knowledge --json report --all` for broad audits.
Mutation boundary: ask before editing docs, memory, skills, config, or cron.
""",
                encoding="utf-8",
            )

            env = dict(os.environ)
            env["PYTHONPATH"] = str(PROJECT) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [sys.executable, "-m", "knowledge_cli", "skill", "companion", "--path", str(skill), "--format", "md"],
                cwd=PROJECT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("# knowledge-cli Companion Contract", proc.stdout)
            self.assertIn("knowledge --json report --all", proc.stdout)
            self.assertIn("Mutation boundary", proc.stdout)


if __name__ == "__main__":
    unittest.main()
