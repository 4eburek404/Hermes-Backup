from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flights_cli.config import CACHE_DIR
from flights_cli.errors import CliError
from flights_cli.providers.static_catalog import (
    STATIC_CATALOG_BY_NAME,
    STATIC_CATALOG_SCHEMA_VERSION,
    catalog_staleness,
    download_static_catalog,
    refresh_static_catalog_if_needed,
)

from helpers import PROJECT


class StaticCatalogLayerTests(unittest.TestCase):
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
            self.assertEqual(STATIC_CATALOG_SCHEMA_VERSION, "static-catalog-v1")
            self.assertEqual(manifest["schema_version"], "static-catalog-v1")
            self.assertEqual(manifest["entries"]["countries"]["filename"], "countries.json")
            self.assertEqual(manifest["entries"]["countries"]["schema_version"], "static-catalog-v1")
            self.assertEqual(manifest["entries"]["countries"]["source"], "public_static_catalog")
            self.assertNotIn("url", manifest["entries"]["countries"])
            self.assertNotIn("aliases", manifest["entries"]["countries"])
            self.assertEqual(manifest["entries"]["planes"]["count"], 1)
            self.assertEqual(
                manifest["entries"]["planes"]["stale_note"],
                "planes.json is upstream-marked as not maintained; use it only as metadata.",
            )
            self.assertNotIn("routes", manifest["entries"])

            dry_run = download_static_catalog(cache_dir, names=["countries"], dry_run=True)
            self.assertEqual(dry_run["planned"][0]["source"], "public_static_catalog")
            self.assertNotIn("url", dry_run["planned"][0])

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

    def test_provider_modules_are_active_surfaces_only(self) -> None:
        provider_dir = PROJECT / "flights_cli" / "providers"
        allowed = {
            "__init__.py",
            "fli_mcp.py",
            "kupibilet.py",
            "live_cache.py",
            "route_intel.py",
            "segment_normalization.py",
            "static_catalog.py",
        }
        modules = {path.name for path in provider_dir.glob("*.py")}
        self.assertEqual(modules, allowed)

    def test_default_cache_path_is_skill_scoped(self) -> None:
        self.assertEqual(CACHE_DIR, Path.home() / ".hermes" / "cache" / "flight-search")


if __name__ == "__main__":
    unittest.main()
