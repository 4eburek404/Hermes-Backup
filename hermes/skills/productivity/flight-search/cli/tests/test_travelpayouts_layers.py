from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from flights_cli.errors import CliError
from flights_cli.output import render_human
from flights_cli.providers import travelpayouts_data
from flights_cli.providers.static_catalog import (
    STATIC_CATALOG_BY_NAME,
    catalog_staleness,
    download_static_catalog,
    refresh_static_catalog_if_needed,
)

from helpers import PROJECT, TEST_ENV


class TravelpayoutsLayerTests(unittest.TestCase):
    def test_static_catalog_update_writes_canonical_files_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            payloads = {
                STATIC_CATALOG_BY_NAME["countries"].url: [{"code": "AE", "name": "United Arab Emirates"}],
                STATIC_CATALOG_BY_NAME["planes"].url: [{"code": "320", "name": "Airbus A320"}],
            }

            def fake_fetch(url: str, timeout: int) -> bytes:
                del timeout
                return json.dumps(payloads[url]).encode("utf-8")

            result = download_static_catalog(
                cache_dir,
                names=["countries", "planes"],
                fetch_url=fake_fetch,
                now=datetime(2026, 5, 6, tzinfo=timezone.utc),
            )

            self.assertFalse(result["dry_run"])
            self.assertTrue((cache_dir / "countries.json").exists())
            self.assertTrue((cache_dir / "planes.json").exists())
            self.assertFalse((cache_dir / "routes.json").exists())
            self.assertFalse((cache_dir / "countries_en.json").exists())
            manifest = json.loads((cache_dir / "catalog_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["entries"]["countries"]["filename"], "countries.json")
            self.assertNotIn("aliases", manifest["entries"]["countries"])
            self.assertEqual(manifest["entries"]["planes"]["count"], 1)
            self.assertNotIn("routes", manifest["entries"])

    def test_static_catalog_auto_refresh_updates_missing_or_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            payloads = {
                STATIC_CATALOG_BY_NAME["countries"].url: [{"code": "AE", "name": "United Arab Emirates"}],
                STATIC_CATALOG_BY_NAME["planes"].url: [{"code": "320", "name": "Airbus A320"}],
            }

            def fake_fetch(url: str, timeout: int) -> bytes:
                del timeout
                return json.dumps(payloads[url]).encode("utf-8")

            first = refresh_static_catalog_if_needed(
                cache_dir,
                names=["countries", "planes"],
                fetch_url=fake_fetch,
                now=datetime(2026, 5, 6, tzinfo=timezone.utc),
            )
            self.assertTrue(first["refreshed"])
            self.assertEqual(first["checked"]["stale_count"], 2)
            self.assertEqual(first["update"]["updated_count"], 2)

            fresh = refresh_static_catalog_if_needed(
                cache_dir,
                names=["countries", "planes"],
                fetch_url=fake_fetch,
                now=datetime(2026, 5, 7, tzinfo=timezone.utc),
            )
            self.assertFalse(fresh["refreshed"])
            self.assertEqual(fresh["reason"], "fresh")

            stale = catalog_staleness(
                cache_dir,
                names=["countries", "planes"],
                max_age_seconds=24 * 60 * 60,
                now=datetime(2026, 5, 8, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(stale["stale_count"], 2)
            self.assertIn("expired", stale["stale"][0]["reasons"])

    def test_routes_catalog_item_is_removed(self) -> None:
        self.assertNotIn("routes", STATIC_CATALOG_BY_NAME)
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            (cache_dir / "catalog_manifest.json").write_text(
                json.dumps(
                    {
                        "entries": {
                            "countries": {"filename": "countries.json"},
                            "routes": {"filename": "routes.json"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            dry_run = download_static_catalog(cache_dir, dry_run=True)
            self.assertNotIn("routes", dry_run["manifest"]["entries"])
            with self.assertRaises(CliError):
                download_static_catalog(cache_dir, names=["routes"])

    def test_cached_rest_prices_probe_is_fetch_not_live(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "request",
                "prices-for-dates",
                "SVX",
                "IST",
                "--departure-at",
                "2026-07-19",
                "--direct",
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["command"], "request prices-for-dates")
        self.assertTrue(payload["data"]["dry_run"])
        self.assertEqual(payload["data"]["request"]["params"]["one_way"], "true")
        self.assertEqual(payload["data"]["request"]["params"]["direct"], "true")
        self.assertNotIn("token", payload["data"]["request"]["params"])
        self.assertNotIn("live", payload["data"])

    def test_data_api_fetch_uses_header_auth_without_url_token_param(self) -> None:
        seen: dict[str, object] = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self) -> bytes:
                return json.dumps({"success": True, "data": []}).encode("utf-8")

        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            seen["headers"] = dict(request.header_items())  # type: ignore[attr-defined]
            return FakeResponse()

        sentinel = "test-placeholder-001"
        params = {"origin": "SVX", "destination": "IST", "departure_at": "2026-07-19"}
        with mock.patch.dict(os.environ, {"TRAVELPAYOUTS_TOKEN": sentinel}, clear=False):
            with mock.patch.object(travelpayouts_data.urllib.request, "urlopen", side_effect=fake_urlopen):
                status, payload = travelpayouts_data.call_data_api(
                    travelpayouts_data.PRICES_FOR_DATES_URL,
                    params,
                    timeout=11,
                )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"success": True, "data": []})
        parsed = urllib.parse.urlparse(str(seen["url"]))
        query = urllib.parse.parse_qs(parsed.query)
        self.assertNotIn("token", query)
        self.assertNotIn("X-Access-Token", str(seen["url"]))
        self.assertEqual(seen["headers"].get("X-access-token"), sentinel)
        self.assertEqual(seen["timeout"], 11)

    def test_data_api_fetch_rejects_query_auth_params_before_urlopen(self) -> None:
        params = {"origin": "SVX", "destination": "IST"}
        params.update(dict([("token", "test-placeholder-query")]))
        with mock.patch.dict(os.environ, {"TRAVELPAYOUTS_TOKEN": "test-placeholder-env"}, clear=False):
            with mock.patch.object(travelpayouts_data.urllib.request, "urlopen") as urlopen:
                with self.assertRaises(CliError) as ctx:
                    travelpayouts_data.call_data_api(
                        travelpayouts_data.PRICES_FOR_DATES_URL,
                        params,
                        timeout=11,
                    )
        self.assertEqual(ctx.exception.error_type, "validation_error")
        urlopen.assert_not_called()

    def test_data_api_request_payload_rejects_query_auth_params(self) -> None:
        params = {"origin": "SVX", "destination": "IST"}
        params.update(dict([("api_key", "test-placeholder-query")]))
        with self.assertRaises(CliError) as ctx:
            travelpayouts_data.request_payload(travelpayouts_data.PRICES_FOR_DATES_URL, params)
        self.assertEqual(ctx.exception.error_type, "validation_error")

    def test_data_api_fetch_without_auth_keeps_missing_credentials_error(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CliError) as ctx:
                travelpayouts_data.call_data_api(
                    travelpayouts_data.PRICES_FOR_DATES_URL,
                    {"origin": "SVX", "destination": "IST", "departure_at": "2026-07-19"},
                    timeout=5,
                )

        self.assertEqual(ctx.exception.error_type, "missing_credentials")

    def test_data_api_request_metadata_reports_auth_status_without_secret_value(self) -> None:
        sentinel = "test-placeholder-002"
        with mock.patch.dict(os.environ, {"TRAVELPAYOUTS_TOKEN": sentinel}, clear=False):
            payload = travelpayouts_data.request_payload(
                travelpayouts_data.PRICES_FOR_DATES_URL,
                {"origin": "SVX", "destination": "IST"},
            )

        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(sentinel, serialized)
        self.assertEqual(payload["auth"], {"status": "present", "transport": "header"})

    def test_data_api_human_renderer_never_prints_credential_value(self) -> None:
        sentinel = "test-placeholder-003"
        text = render_human(
            "request prices-for-dates",
            {
                "dry_run": True,
                "request": {
                    "method": "GET",
                    "endpoint": travelpayouts_data.PRICES_FOR_DATES_URL,
                    "params": {"origin": "SVX", "destination": "IST"},
                    "auth": dict([("token", sentinel)]),
                },
            },
        )

        self.assertNotIn(sentinel, text)
        self.assertNotIn("token", text.casefold())
        self.assertIn("auth:", text)


if __name__ == "__main__":
    unittest.main()
