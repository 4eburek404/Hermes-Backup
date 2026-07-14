from __future__ import annotations

import json
import unittest

from helpers import PROJECT


PROVIDER_FIXTURE_DIR = PROJECT / "tests" / "fixtures" / "providers"
CATALOG_FIXTURE_DIR = PROJECT / "tests" / "fixtures" / "catalog"


class ProviderFixtureTests(unittest.TestCase):
    def test_provider_fixtures_are_json_and_named_by_provider(self) -> None:
        paths = sorted(PROVIDER_FIXTURE_DIR.glob("*.json"))

        self.assertGreaterEqual(len(paths), 3)
        providers = set()
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            provider = payload.get("provider")
            providers.add(provider)
            self.assertEqual(payload.get("fixture_schema"), "provider_raw_fixture.v1")
            self.assertIsInstance(payload.get("query"), dict)
            self.assertIsInstance(payload.get("raw"), dict)
            self.assertIn(str(provider), path.name)

        self.assertGreaterEqual(providers, {"tutu", "kupibilet"})

    def test_catalog_fixture_contains_required_store_files(self) -> None:
        required = {
            "airlines_en.json",
            "airports_en.json",
            "alliances.json",
            "catalog_manifest.json",
            "cities_ru.json",
            "countries.json",
            "planes.json",
        }

        self.assertEqual(
            {path.name for path in CATALOG_FIXTURE_DIR.glob("*.json")},
            required,
        )


if __name__ == "__main__":
    unittest.main()
