from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flights_cli.orchestrators.route_plan import build_route_plan
from flights_cli.providers.static_catalog import (
    STATIC_CATALOG_BY_NAME,
    catalog_staleness,
    download_static_catalog,
    refresh_static_catalog_if_needed,
)
from flights_cli.store import Store

from helpers import PROJECT, TEST_ENV


class TravelpayoutsLayerTests(unittest.TestCase):
    def test_static_catalog_update_writes_canonical_files_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            payloads = {
                STATIC_CATALOG_BY_NAME["countries"].url: [{"code": "AE", "name": "United Arab Emirates"}],
                STATIC_CATALOG_BY_NAME["routes"].url: [
                    {
                        "airline_iata": "TK",
                        "departure_airport_iata": "SVX",
                        "arrival_airport_iata": "IST",
                        "transfers": 0,
                    }
                ],
            }

            def fake_fetch(url: str, timeout: int) -> bytes:
                del timeout
                return json.dumps(payloads[url]).encode("utf-8")

            result = download_static_catalog(
                cache_dir,
                names=["countries", "routes"],
                fetch_url=fake_fetch,
                now=datetime(2026, 5, 6, tzinfo=timezone.utc),
            )

            self.assertFalse(result["dry_run"])
            self.assertTrue((cache_dir / "countries.json").exists())
            self.assertTrue((cache_dir / "routes.json").exists())
            self.assertFalse((cache_dir / "countries_en.json").exists())
            manifest = json.loads((cache_dir / "catalog_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["entries"]["countries"]["filename"], "countries.json")
            self.assertNotIn("aliases", manifest["entries"]["countries"])
            self.assertEqual(manifest["entries"]["routes"]["count"], 1)

    def test_static_catalog_auto_refresh_updates_missing_or_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            payloads = {
                STATIC_CATALOG_BY_NAME["countries"].url: [{"code": "AE", "name": "United Arab Emirates"}],
                STATIC_CATALOG_BY_NAME["routes"].url: [
                    {
                        "airline_iata": "TK",
                        "departure_airport_iata": "SVX",
                        "arrival_airport_iata": "IST",
                        "transfers": 0,
                    }
                ],
            }

            def fake_fetch(url: str, timeout: int) -> bytes:
                del timeout
                return json.dumps(payloads[url]).encode("utf-8")

            first = refresh_static_catalog_if_needed(
                cache_dir,
                names=["countries", "routes"],
                fetch_url=fake_fetch,
                now=datetime(2026, 5, 6, tzinfo=timezone.utc),
            )
            self.assertTrue(first["refreshed"])
            self.assertEqual(first["checked"]["stale_count"], 2)
            self.assertEqual(first["update"]["updated_count"], 2)

            fresh = refresh_static_catalog_if_needed(
                cache_dir,
                names=["countries", "routes"],
                fetch_url=fake_fetch,
                now=datetime(2026, 5, 7, tzinfo=timezone.utc),
            )
            self.assertFalse(fresh["refreshed"])
            self.assertEqual(fresh["reason"], "fresh")

            stale = catalog_staleness(
                cache_dir,
                names=["countries", "routes"],
                max_age_seconds=24 * 60 * 60,
                now=datetime(2026, 5, 8, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(stale["stale_count"], 2)
            self.assertIn("expired", stale["stale"][0]["reasons"])

    def test_route_plan_auto_hubs_uses_routes_json_topology_prior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            (cache_dir / "airports_en.json").write_text(
                json.dumps(
                    [
                        {
                            "code": "SVX",
                            "city_code": "SVX",
                            "country_code": "RU",
                            "iata_type": "airport",
                            "flightable": True,
                            "coordinates": {"lat": 56.7431, "lon": 60.8027},
                        },
                        {
                            "code": "IST",
                            "city_code": "IST",
                            "country_code": "TR",
                            "iata_type": "airport",
                            "flightable": True,
                            "coordinates": {"lat": 41.2753, "lon": 28.7519},
                        },
                        {
                            "code": "LHR",
                            "city_code": "LON",
                            "country_code": "GB",
                            "iata_type": "airport",
                            "flightable": True,
                            "coordinates": {"lat": 51.47, "lon": -0.4543},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (cache_dir / "airlines_en.json").write_text(
                json.dumps(
                    [
                        {"code": "TK", "name": "Turkish Airlines", "is_lowcost": False},
                        {"code": "BA", "name": "British Airways", "is_lowcost": False},
                    ]
                ),
                encoding="utf-8",
            )
            (cache_dir / "alliances.json").write_text(
                json.dumps([{"name": "Star Alliance", "airlines": ["TK"]}]),
                encoding="utf-8",
            )
            (cache_dir / "routes.json").write_text(
                json.dumps(
                    [
                        {
                            "airline_iata": "TK",
                            "departure_airport_iata": "SVX",
                            "arrival_airport_iata": "IST",
                            "codeshare": False,
                            "transfers": 0,
                        },
                        {
                            "airline_iata": "TK",
                            "departure_airport_iata": "IST",
                            "arrival_airport_iata": "LHR",
                            "codeshare": False,
                            "transfers": 0,
                        },
                        {
                            "airline_iata": "BA",
                            "departure_airport_iata": "SVX",
                            "arrival_airport_iata": "LHR",
                            "codeshare": False,
                            "transfers": 0,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            args = argparse.Namespace(
                origin="SVX",
                destination="LHR",
                depart_date="2026-07-19",
                return_date=None,
                hub=None,
                origin_airport=None,
                destination_airport=None,
                currency="RUB",
                direct_only=False,
                ticketing="separate",
                profile="business",
                min_same_airport_min=120,
                min_cross_airport_min=300,
                max_airports_per_city=6,
                auto_hubs=True,
                max_auto_hubs=5,
            )
            result = build_route_plan(args, Store(cache_dir))

            self.assertEqual(result["hub_source"], "routes_json")
            self.assertEqual(result["hubs"], ["IST"])
            self.assertEqual(result["route_graph"]["direct"][0]["origin"], "SVX")
            self.assertEqual(result["route_graph"]["one_stop_hubs"][0]["hub"], "IST")
            self.assertIn("shared alliance evidence", " ".join(result["route_graph"]["one_stop_hubs"][0]["reasons"]))

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
