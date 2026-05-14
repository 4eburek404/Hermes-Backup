from __future__ import annotations

import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def load_cli_module():
    project = str(PROJECT)
    if project not in sys.path:
        sys.path.insert(0, project)
    return importlib.import_module("knowledge_cli.__main__")


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


def create_memory_db(db: Path, facts: list[tuple]) -> None:
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
        """
    )
    con.executemany("insert into facts values (?, ?, ?, ?, ?, ?, ?, ?, ?)", facts)
    con.executemany("insert into facts_fts values (?)", [(item[1],) for item in facts])
    con.commit()
    con.close()


class KnowledgeCliOfflineTests(unittest.TestCase):
    def test_default_worker_script_points_to_bundled_source_worker(self) -> None:
        cli = load_cli_module()

        expected = PROJECT.parent / "scripts" / "distillation_worker.py"

        self.assertEqual(cli.DEFAULT_WORKER_SCRIPT, expected)
        self.assertTrue(cli.DEFAULT_WORKER_SCRIPT.exists(), str(cli.DEFAULT_WORKER_SCRIPT))

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

    def test_memory_metrics_opens_existing_sqlite_read_only(self) -> None:
        cli = load_cli_module()
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
                insert into facts values (1, 'redacted', 'tool', '', 0.5, 0, 0, '2026-05-01', '2026-05-01');
                """
            )
            con.commit()
            con.close()

            calls = []
            original_connect = cli.sqlite3.connect

            def recording_connect(target, *args, **kwargs):
                calls.append((target, kwargs))
                return original_connect(target, *args, **kwargs)

            cli.sqlite3.connect = recording_connect
            try:
                cli.memory_metrics_data(hermes)
            finally:
                cli.sqlite3.connect = original_connect

            self.assertTrue(calls)
            target, kwargs = calls[0]
            self.assertIsInstance(target, str)
            self.assertIn("mode=ro", target)
            self.assertTrue(kwargs.get("uri"))

    def test_memory_metrics_checks_root_soul_and_memories_user_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes = Path(tmp) / ".hermes"
            memories = hermes / "memories"
            memories.mkdir(parents=True)
            (memories / "USER.md").write_text("# User\n", encoding="utf-8")
            (memories / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
            (hermes / "SOUL.md").write_text("# Soul\n", encoding="utf-8")

            result = run_cli("--hermes-home", str(hermes), "memory", "metrics")
            files = {item["name"]: item for item in result["data"]["memory_files"]}

            self.assertTrue(files["USER.md"]["exists"])
            self.assertTrue(files["MEMORY.md"]["exists"])
            self.assertTrue(files["SOUL.md"]["exists"])
            self.assertEqual(files["SOUL.md"]["path"], str(hermes / "SOUL.md"))

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

    def test_skill_companion_parses_folded_frontmatter_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "knowledge-cli" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                """---
name: knowledge-cli
description: >-
  Use when auditing knowledge architecture with the knowledge CLI.
  It is read-only evidence, not permission to mutate docs or memory.
---

# knowledge CLI

Run `knowledge --json skill companion` first.
Run `knowledge --json report --all` for broad audits.
Mutation boundary: ask before editing docs, memory, skills, config, or cron.
Use `--live-models` only with explicit permission.
""",
                encoding="utf-8",
            )

            result = run_cli("skill", "companion", "--path", str(skill))
            description = result["data"]["description"]

            self.assertIsNotNone(description)
            self.assertNotEqual(description, ">-")
            self.assertTrue(description.startswith("Use when auditing knowledge architecture"))
            self.assertIn("read-only evidence", description)

    def test_report_all_includes_docs_audit_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            plans = root / "plans"
            plans.mkdir(parents=True)
            (plans / "README.md").write_text("# Plans\n", encoding="utf-8")
            (plans / "missing-status.md").write_text("# Missing Status\n", encoding="utf-8")

            result = run_cli("--docs-root", str(root), "report", "--all")
            docs = result["data"]["docs"]
            classes = [item["class"] for item in docs["findings"]]

            self.assertEqual(result["command"], "report")
            self.assertGreaterEqual(docs["finding_count"], 2)
            self.assertIn("missing_index", classes)
            self.assertIn("plan_status_drift", classes)

    def test_report_all_respects_max_depth_for_docs_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (root / "README.md").write_text("# Docs\n", encoding="utf-8")
            (nested / "untitled.md").write_text("no title\n", encoding="utf-8")

            result = run_cli("--docs-root", str(root), "report", "--all", "--max-depth", "1")
            docs = result["data"]["docs"]
            finding_paths = [item["path"] for item in docs["findings"]]

            self.assertEqual(docs["file_count"], 1)
            self.assertFalse(any("untitled.md" in path for path in finding_paths))

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

    def test_paths_audit_reports_core_paths_without_reading_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            plans = docs / "plans"
            hermes = root / ".hermes"
            memories = hermes / "memories"
            worker = root / "skill" / "scripts" / "distillation_worker.py"
            companion = root / "knowledge-cli" / "SKILL.md"
            plans.mkdir(parents=True)
            memories.mkdir(parents=True)
            worker.parent.mkdir(parents=True)
            companion.parent.mkdir(parents=True)
            (docs / "README.md").write_text("# Docs\n", encoding="utf-8")
            (plans / "README.md").write_text("# Plans\n", encoding="utf-8")
            (memories / "USER.md").write_text("user sensitive-marker do-not-print\n", encoding="utf-8")
            (memories / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
            (hermes / "SOUL.md").write_text("# Soul\n", encoding="utf-8")
            worker.write_text("def run_distillation(text):\n    return {'candidates': []}\n", encoding="utf-8")
            companion.write_text("---\nname: knowledge-cli\n---\n# Skill\n", encoding="utf-8")

            result = run_cli(
                "--docs-root",
                str(docs),
                "--hermes-home",
                str(hermes),
                "paths",
                "audit",
                "--worker-script",
                str(worker),
                "--companion-skill",
                str(companion),
            )
            data = result["data"]
            text = json.dumps(result, ensure_ascii=False)

            self.assertEqual(result["command"], "paths audit")
            self.assertTrue(data["paths"]["docs_root"]["exists"])
            self.assertTrue(data["paths"]["soul_root"]["exists"])
            self.assertTrue(data["paths"]["worker_script"]["exists"])
            self.assertFalse(any(item["class"] == "missing_required_path" for item in data["findings"]))
            self.assertNotIn("do-not-print", text)

    def test_distill_worker_check_is_read_only_and_reports_missing_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing_worker.py"
            result = run_cli("distill", "worker-check", "--worker-script", str(missing))
            data = result["data"]
            classes = [item["class"] for item in data["findings"]]

            self.assertEqual(result["command"], "distill worker-check")
            self.assertFalse(data["exists"])
            self.assertFalse(data["ready_for_live_models"])
            self.assertIn("missing_worker", classes)
            self.assertFalse(data["live_model_calls"])

    def test_skill_audit_flags_missing_when_to_use_and_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "sample-skill"
            skill_dir.mkdir()
            skill_file = skill_dir / "SKILL.md"
            generated = skill_dir / "__pycache__"
            generated.mkdir()
            (generated / "module.pyc").write_bytes(b"pyc")
            skill_file.write_text(
                "---\nname: sample\ndescription: sample skill\n---\n\n# Sample\n\n"
                + ("Long line.\n" * 180),
                encoding="utf-8",
            )

            result = run_cli("skill", "audit", "--path", str(skill_file), "--max-lines", "50")
            data = result["data"]
            classes = [item["class"] for item in data["findings"]]
            actions = [item.get("action") for item in data["findings"]]

            self.assertEqual(result["command"], "skill audit")
            self.assertIn("missing_section", classes)
            self.assertIn("skill_large", classes)
            self.assertIn("generated_artifact", classes)
            self.assertIn("add_when_to_use_section", actions)

    def test_report_all_includes_p2_health_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            plans = docs / "plans"
            hermes = root / ".hermes"
            memories = hermes / "memories"
            skill_dir = root / "skill"
            worker = skill_dir / "scripts" / "distillation_worker.py"
            companion = root / "knowledge-cli" / "SKILL.md"
            plans.mkdir(parents=True)
            memories.mkdir(parents=True)
            worker.parent.mkdir(parents=True)
            companion.parent.mkdir(parents=True)
            (docs / "README.md").write_text("# Docs\n", encoding="utf-8")
            (plans / "README.md").write_text("# Plans\n", encoding="utf-8")
            (memories / "USER.md").write_text("# User\n", encoding="utf-8")
            (memories / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
            (hermes / "SOUL.md").write_text("# Soul\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "---\nname: knowledge-architecture\ndescription: sample\n---\n\n# Skill\n\n## When to Use\n\nUse this.\n",
                encoding="utf-8",
            )
            worker.write_text("def run_distillation(text):\n    return {'candidates': []}\n", encoding="utf-8")
            companion.write_text("---\nname: knowledge-cli\n---\n# Skill\n", encoding="utf-8")

            result = run_cli(
                "--docs-root",
                str(docs),
                "--hermes-home",
                str(hermes),
                "report",
                "--all",
                "--skill-path",
                str(skill_dir / "SKILL.md"),
                "--worker-script",
                str(worker),
                "--companion-skill",
                str(companion),
            )
            data = result["data"]

            self.assertIn("paths", data)
            self.assertIn("skill", data)
            self.assertIn("distill_worker", data)
            self.assertEqual(data["skill"]["finding_count"], 0)
            self.assertTrue(data["distill_worker"]["ready_for_live_models"])
    def test_memory_policy_audit_flags_candidates_without_dumping_content(self) -> None:
        stale_path = "/home/konstantin/code/" "clis/knowledge"
        secret_assignment = "SECRET_TOKEN" "=supers...ue"
        with tempfile.TemporaryDirectory() as tmp:
            hermes = Path(tmp) / ".hermes"
            hermes.mkdir()
            db = hermes / "memory_store.db"
            create_memory_db(
                db,
                [
                    (
                        1,
                        f"knowledge CLI used to live at {stale_path} and {secret_assignment}",
                        "tool",
                        "",
                        0.5,
                        0,
                        0,
                        "2026-05-01",
                        "2026-05-01",
                    ),
                    (
                        2,
                        "Procedure: run pytest, then update the skill. Step 1: write tests. Step 2: patch code.",
                        "general",
                        "",
                        0.5,
                        0,
                        0,
                        "2026-05-02",
                        "2026-05-02",
                    ),
                    (
                        3,
                        "Gateway service was active during a one-time check.",
                        "project",
                        "volatile,hermes",
                        0.5,
                        0,
                        0,
                        "2026-03-01",
                        "2026-03-01",
                    ),
                    (
                        4,
                        "Old low confidence scratch fact.",
                        "general",
                        "",
                        0.2,
                        0,
                        0,
                        "2026-05-01",
                        "2026-05-01",
                    ),
                ],
            )

            result = run_cli(
                "--hermes-home",
                str(hermes),
                "memory",
                "policy",
                "audit",
                "--now",
                "2026-05-08",
                "--stale-days",
                "30",
            )
            data = result["data"]
            text = json.dumps(result, ensure_ascii=False)
            classes = [item["class"] for item in data["findings"]]

            self.assertEqual(result["command"], "memory policy audit")
            self.assertFalse(data["mutations_performed"])
            self.assertEqual(data["fact_count"], 4)
            self.assertIn("stale_path_reference", classes)
            self.assertIn("secret_like_memory", classes)
            self.assertIn("procedure_in_fact", classes)
            self.assertIn("volatile_stale", classes)
            self.assertIn("low_trust_unhelpful", classes)
            self.assertNotIn("supers...ue", text)
            self.assertNotIn(stale_path, text)
            self.assertNotIn("Procedure: run pytest", text)

    def test_memory_policy_audit_opens_existing_sqlite_read_only(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            hermes = Path(tmp) / ".hermes"
            hermes.mkdir()
            db = hermes / "memory_store.db"
            create_memory_db(
                db,
                [(1, "redacted", "tool", "", 0.5, 0, 0, "2026-05-01", "2026-05-01")],
            )

            calls = []
            original_connect = cli.sqlite3.connect

            def recording_connect(target, *args, **kwargs):
                calls.append((target, kwargs))
                return original_connect(target, *args, **kwargs)

            cli.sqlite3.connect = recording_connect
            try:
                cli.memory_policy_audit_data(hermes, now="2026-05-08")
            finally:
                cli.sqlite3.connect = original_connect

            self.assertTrue(calls)
            target, kwargs = calls[0]
            self.assertIsInstance(target, str)
            self.assertIn("mode=ro", target)
            self.assertTrue(kwargs.get("uri"))

    def test_report_all_includes_memory_policy_rollup(self) -> None:
        stale_path = "/home/konstantin/code/" "clis/knowledge"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            plans = docs / "plans"
            hermes = root / ".hermes"
            memories = hermes / "memories"
            plans.mkdir(parents=True)
            memories.mkdir(parents=True)
            (docs / "README.md").write_text("# Docs\n", encoding="utf-8")
            (plans / "README.md").write_text("# Plans\n", encoding="utf-8")
            (memories / "USER.md").write_text("# User\n", encoding="utf-8")
            (memories / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
            (hermes / "SOUL.md").write_text("# Soul\n", encoding="utf-8")
            create_memory_db(
                hermes / "memory_store.db",
                [
                    (
                        1,
                        f"knowledge CLI used to live at {stale_path}",
                        "tool",
                        "",
                        0.5,
                        0,
                        0,
                        "2026-05-01",
                        "2026-05-01",
                    )
                ],
            )

            result = run_cli(
                "--docs-root",
                str(docs),
                "--hermes-home",
                str(hermes),
                "report",
                "--all",
                "--now",
                "2026-05-08",
            )
            data = result["data"]

            self.assertIn("memory_policy", data)
            self.assertGreaterEqual(data["memory_policy"]["finding_count"], 1)
            self.assertIn("stale_path_reference", data["memory_policy"]["findings_by_code"])


if __name__ == "__main__":
    unittest.main()
