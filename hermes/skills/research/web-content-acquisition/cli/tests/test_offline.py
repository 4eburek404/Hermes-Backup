from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixtures" / "sample.html"


def run_cli(*args: str, input_text: str | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "article_cli", "--json", *args],
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


class ArticleCliOfflineTests(unittest.TestCase):
    def test_doctor_needs_no_auth(self) -> None:
        result = run_cli("doctor")
        self.assertEqual(result["command"], "doctor")
        self.assertFalse(result["data"]["auth_required"])
        self.assertFalse(result["data"]["network_required"])

    def test_read_extracts_article_markdown(self) -> None:
        result = run_cli("read", str(FIXTURE))
        data = result["data"]
        self.assertEqual(result["command"], "read")
        self.assertEqual(data["selector_used"], "article")
        self.assertIn("# Sample Article", data["content"])
        self.assertIn("The article body has enough text", data["content"])
        self.assertEqual(data["stats"]["heading_count"], 2)
        self.assertEqual(data["stats"]["link_count"], 1)
        self.assertEqual(data["stats"]["image_count"], 1)

    def test_summary_input_truncates(self) -> None:
        result = run_cli("summary-input", str(FIXTURE), "--max-chars", "80")
        data = result["data"]
        self.assertEqual(result["command"], "summary-input")
        self.assertTrue(data["truncated"])
        self.assertLessEqual(len(data["content"]), 81)

    def test_request_get_returns_preview(self) -> None:
        result = run_cli("request", "get", str(FIXTURE), "--preview-chars", "30")
        data = result["data"]
        self.assertEqual(result["command"], "request get")
        self.assertIn("<!doctype html>", data["body_preview"])
        self.assertTrue(data["body_preview_truncated"])


if __name__ == "__main__":
    unittest.main()
