import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from systemd_web_service_cli.__main__ import parse_env_file, redact_text


class RedactionTests(unittest.TestCase):
    def test_redacts_secret_assignments(self):
        text = "APP_PASSWORD=super-secret\nAuthorization: Bearer abcdefghijklmnop\nDATABASE_URL=postgres://user:pass@example/db"
        redacted = redact_text(text)
        self.assertNotIn("super-secret", redacted)
        self.assertNotIn("abcdefghijklmnop", redacted)
        self.assertNotIn("user:pass", redacted)
        self.assertIn("APP_PASSWORD=[REDACTED]", redacted)
        self.assertIn("DATABASE_URL=[REDACTED]", redacted)


class EnvFileTests(unittest.TestCase):
    def test_parse_env_file_returns_keys_without_outputting_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "service.env"
            path.write_text("APP_USERNAME=user\nAPP_PASSWORD=secret\n")
            values, issues, meta = parse_env_file(str(path))
        self.assertFalse([i for i in issues if i["severity"] == "error"])
        self.assertEqual(values["APP_USERNAME"], "user")
        self.assertEqual(values["APP_PASSWORD"], "secret")
        self.assertEqual(meta["keys"], ["APP_PASSWORD", "APP_USERNAME"])
        self.assertNotIn("secret", json.dumps(meta))


class CliTests(unittest.TestCase):
    def test_doctor_json_shape(self):
        env = os.environ.copy()
        proc = subprocess.run(
            [sys.executable, "-m", "systemd_web_service_cli", "--json", "doctor"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertIn(proc.returncode, (0, 1))
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["command"], "doctor")
        self.assertIn("ok", payload)
        self.assertIn("issues", payload)
        self.assertIn("data", payload)

    def test_verify_local_url_with_marker(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"hello Dashboard marker"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "systemd_web_service_cli",
                    "--json",
                    "verify",
                    "--url",
                    url,
                    "--expect-status",
                    "200",
                    "--content-marker",
                    "Dashboard",
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "verify")
        self.assertTrue(payload["data"]["urls"][0]["marker_found"])

    def test_auth_verify_does_not_follow_redirects(self):
        class Handler(BaseHTTPRequestHandler):
            redirected_hit = False

            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/capture")
                    self.end_headers()
                    return
                Handler.redirected_hit = True
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_file = Path(tmp) / "service.env"
                env_file.write_text("APP_USERNAME=user\nAPP_PASSWORD=secret\n")
                url = f"http://127.0.0.1:{server.server_port}/redirect"
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "systemd_web_service_cli",
                        "--json",
                        "verify",
                        "--url",
                        url,
                        "--expect-status",
                        "302",
                        "--env-file",
                        str(env_file),
                        "--auth-user-env",
                        "APP_USERNAME",
                        "--auth-password-env",
                        "APP_PASSWORD",
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(Handler.redirected_hit)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["urls"][0]["redirect_not_followed"])
        self.assertNotIn("secret", proc.stdout)


if __name__ == "__main__":
    unittest.main()
