import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hh_ru_cli.__main__ import redact_headers


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "config.json"
        proc = subprocess.run(
            [sys.executable, "-m", "hh_ru_cli", "--json", "--config", str(config), *args],
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    return proc


class OfflineCliTests(unittest.TestCase):
    def test_doctor_is_offline_by_default(self):
        proc = run_cli("doctor")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["api_check"]["ran"])
        self.assertEqual(payload["data"]["token_source"], "missing")

    def test_vacancy_search_dry_run(self):
        proc = run_cli("vacancies", "search", "Python", "--area", "1", "--per-page", "5", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        request = payload["data"]["request"]
        self.assertEqual(request["method"], "GET")
        self.assertIn("/vacancies?", request["url"])
        self.assertIn("text=Python", request["url"])
        self.assertIn("area=1", request["url"])
        self.assertIn("per_page=5", request["url"])

    def test_area_resolve_dry_run(self):
        proc = run_cli("areas", "resolve", "--name", "Ekaterinburg", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["data"]["dry_run"])
        self.assertIn("/areas/113", payload["data"]["request"]["url"])

    def test_auth_url_without_network(self):
        proc = run_cli("auth", "authorize-url", "--client-id", "abc", "--state", "s1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("https://hh.ru/oauth/authorize?", payload["data"]["url"])
        self.assertIn("client_id=abc", payload["data"]["url"])
        self.assertIn("state=s1", payload["data"]["url"])

    def test_redact_headers_covers_response_cookies(self):
        headers = {
            "Authorization": "Bearer secret-token",
            "Set-Cookie": "__ddg1_=secret-cookie; HttpOnly",
            "Cookie": "session=secret-cookie",
            "Proxy-Authorization": "Basic secret",
            "X-Api-Key": "secret-api-key",
            "Content-Type": "application/json",
        }
        redacted = redact_headers(headers)
        self.assertEqual(redacted["Authorization"], "***")
        self.assertEqual(redacted["Set-Cookie"], "***")
        self.assertEqual(redacted["Cookie"], "***")
        self.assertEqual(redacted["Proxy-Authorization"], "***")
        self.assertEqual(redacted["X-Api-Key"], "***")
        self.assertEqual(redacted["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()

