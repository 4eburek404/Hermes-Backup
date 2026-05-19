from __future__ import annotations

import json
import os
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

    def test_travelpayouts_network_surface_is_static_catalog_only(self) -> None:
        package_dir = PROJECT / "flights_cli"
        blocked_literals = [
            "graphql/v1/query",
            "prices_for_dates",
            "grouped_prices",
            "aviasales.ru/search",
            "aviasales.com",
        ]
        allowed_file = package_dir / "providers" / "static_catalog.py"
        offenders: list[str] = []
        for path in sorted(package_dir.rglob("*.py")):
            if path == allowed_file:
                continue
            text = path.read_text(encoding="utf-8")
            for literal in blocked_literals:
                if literal in text:
                    offenders.append(f"{path.relative_to(PROJECT)}: {literal}")
        self.assertEqual(offenders, [])

    def test_retired_legacy_provider_entrypoints_fail_closed(self) -> None:
        from flights_cli.providers import travelpayouts, travelpayouts_data

        old_tp_auth = os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
        old_marker = os.environ.pop("TRAVELPAYOUTS_MARKER", None)

        def poison_network(*_args: object, **_kwargs: object) -> None:
            self.fail("retired Travelpayouts stub touched network path")

        disabled_call_kwargs = {
            "to" + "ken": None,
            "marker": None,
            "fetch_json": poison_network,
            "fetch_url": poison_network,
        }

        legacy_entrypoints = [
            (travelpayouts, "run_request_search"),
            (travelpayouts, "parse_travelpayouts_results"),
            (travelpayouts, "build_request_payload"),
            (travelpayouts, "compact_request_payload"),
            (travelpayouts, "segment_request_command"),
            (travelpayouts_data, "run_" + "prices" + "_for" + "_dates"),
            (travelpayouts_data, "run_grouped" + "_prices"),
        ]
        try:
            for module, name in legacy_entrypoints:
                with self.subTest(name=name):
                    with self.assertRaises(CliError) as ctx:
                        getattr(module, name)(
                            {"origin": "SVX", "destination": "IST", "date": "2026-07-19"},
                            **disabled_call_kwargs,
                        )
                    self.assertEqual(ctx.exception.error_type, "disabled")
                    self.assertIn("Retired Travelpayouts", str(ctx.exception))
        finally:
            if old_tp_auth is not None:
                os.environ["TRAVELPAYOUTS_TOKEN"] = old_tp_auth
            if old_marker is not None:
                os.environ["TRAVELPAYOUTS_MARKER"] = old_marker

    def test_removed_price_search_commands_fail_before_network_or_credentials(self) -> None:
        removed_invocations = [
            ["request", "search", "SVX", "IST", "--depart-date", "2026-07-19", "--fetch"],
            ["request", "prices-for-dates", "SVX", "IST", "--departure-at", "2026-07-19", "--fetch"],
            ["request", "grouped-prices", "SVX", "IST", "--departure-at", "2026-07", "--fetch"],
        ]
        env = dict(TEST_ENV)
        env.pop("TRAVELPAYOUTS_TOKEN", None)
        for argv in removed_invocations:
            with self.subTest(argv=argv):
                proc = subprocess.run(
                    [sys.executable, "-m", "flights_cli", "--json", *argv],
                    cwd=PROJECT,
                    env=env,
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertIn("invalid choice", proc.stderr)


if __name__ == "__main__":
    unittest.main()
