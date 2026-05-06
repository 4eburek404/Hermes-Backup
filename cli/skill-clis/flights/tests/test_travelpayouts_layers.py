from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flights_cli.errors import CliError
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


if __name__ == "__main__":
    unittest.main()
