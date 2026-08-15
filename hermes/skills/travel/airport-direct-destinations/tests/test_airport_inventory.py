import json
from pathlib import Path
import runpy

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "airport_inventory.py"


def test_parse_inventory_extracts_metadata_and_deduplicates_routes() -> None:
    module = runpy.run_path(str(SCRIPT), run_name="airport_inventory")
    markdown = """
    has non-stop passenger flights scheduled to 3 destinations in 2 countries
    1 domestic flight
    Last updated on: 2026-08-15
    Montréal (YUL)
    8 flights / month
    St. John's (YYT)
    1 flight / month
    Montréal (YUL)
    12 flights / month
    """

    payload = json.dumps({"ok": True, "data": {"markdown": markdown}})
    content = module["content_from_input"](payload)
    routes, metadata = module["parse_inventory"](content)

    assert routes == [("YUL", "Montréal", 12), ("YYT", "St. John's", 1)]
    assert metadata == {
        "total_destinations": 3,
        "countries": 2,
        "domestic": 1,
        "last_updated": "2026-08-15",
    }


def test_parse_inventory_rejects_empty_route_content() -> None:
    module = runpy.run_path(str(SCRIPT), run_name="airport_inventory")

    with pytest.raises(ValueError, match="no direct destinations"):
        module["parse_inventory"]("Access denied")
