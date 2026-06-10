"""Contract test for WP-1 (timezone catalog rename/de-brand/flatten) and
WP-2 (removal of manual airport->city/timezone maps).

These assertions are filesystem/string based so they flip cleanly from RED
(before the refactor) to GREEN (after), independent of import state.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
DATA_CATALOG = SKILL_ROOT / "data" / "airport-timezones.json"
OLD_CATALOG = SKILL_ROOT / "assets" / "travelpayouts" / "airport_timezones.json"

# Union of the two former DEFAULT_AIRPORT_CITY maps in ural/utair.
FORMER_MAP_CODES = [
    "DME", "SVO", "VKO", "ZIA", "LED", "SVX", "AER",
    "KUF", "KZN", "OVB", "TJM", "UFA", "SGC", "HMA",
]


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


class CatalogDeBrandContract(unittest.TestCase):
    def test_no_travelpayouts_token_in_scripts(self) -> None:
        offenders = []
        for path in _py_files(SCRIPTS):
            if re.search(r"travelpayouts", path.read_text(encoding="utf-8"), re.IGNORECASE):
                offenders.append(path.relative_to(SKILL_ROOT).as_posix())
        self.assertEqual(offenders, [], f"'travelpayouts' brand still present in: {offenders}")

    def test_catalog_lives_in_flat_data_dir(self) -> None:
        self.assertTrue(DATA_CATALOG.exists(), "expected catalog at data/airport-timezones.json")
        self.assertFalse(OLD_CATALOG.exists(), "old assets/travelpayouts/ path must be gone")
        self.assertFalse(
            (SKILL_ROOT / "assets").exists(),
            "assets/ nesting should be removed once the catalog is the only asset",
        )

    def test_catalog_schema_version_is_debranded(self) -> None:
        doc = json.loads(DATA_CATALOG.read_text(encoding="utf-8"))
        self.assertNotIn("travelpayouts", json.dumps(doc).lower())
        self.assertEqual(doc.get("schema_version"), "airport-timezones.v1")

    def test_former_map_airports_are_resolvable_by_catalog(self) -> None:
        # Proves WP-2 removal is safe: every airport the static maps covered
        # still resolves through the bundled catalog.
        timezones = json.loads(DATA_CATALOG.read_text(encoding="utf-8"))["timezones"]
        missing = [code for code in FORMER_MAP_CODES if code not in timezones]
        self.assertEqual(missing, [], f"catalog missing former-map airports: {missing}")


class ManualTimezoneMapRemovalContract(unittest.TestCase):
    def test_no_default_airport_city_map_in_providers(self) -> None:
        offenders = []
        for path in _py_files(SCRIPTS):
            if "DEFAULT_AIRPORT_CITY" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(SKILL_ROOT).as_posix())
        self.assertEqual(offenders, [], f"manual DEFAULT_AIRPORT_CITY map still present in: {offenders}")


if __name__ == "__main__":
    unittest.main()
