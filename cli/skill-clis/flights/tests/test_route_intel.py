from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flights_cli.config import SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL, SVX_OFFICIAL_SCHEDULE_URL
from flights_cli.providers.route_intel import (
    build_svx_route_index,
    load_or_refresh_svx_route_index,
    parse_svx_schedule_airport_codes,
)


class RouteIntelTests(unittest.TestCase):
    def test_svx_schedule_parser_reads_airport_cells_only(self) -> None:
        html = """
        <tr><td>U6-875</td><td>A-319</td><td>PKX</td></tr>
        <tr><td>SU-630</td><td>A-320 SH</td><td>IST</td></tr>
        <tr><td>RED WINGS</td><td>RRJ-95B</td><td>ABA</td></tr>
        """

        codes = parse_svx_schedule_airport_codes(html, known_airports={"PKX", "IST", "MUC"})

        self.assertEqual(codes, ["IST", "PKX"])

    def test_svx_route_index_contains_directional_routes(self) -> None:
        index = build_svx_route_index(
            outbound_html="<td>IST</td><td>PKX</td>",
            return_html="<td>IST</td><td>DXB</td>",
            known_airports={"IST", "PKX", "DXB"},
            fetched_at=datetime(2026, 5, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(index["airport"], "SVX")
        self.assertEqual(index["routes"]["outbound"], ["IST", "PKX"])
        self.assertEqual(index["routes"]["return"], ["DXB", "IST"])

    def test_svx_route_index_cache_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            calls: list[str] = []

            def fake_fetch(url: str, timeout: int) -> str:
                del timeout
                calls.append(url)
                if url == SVX_OFFICIAL_SCHEDULE_URL:
                    return "<td>IST</td><td>PKX</td>"
                if url == SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL:
                    return "<td>IST</td>"
                raise AssertionError(url)

            first_index, first_cache = load_or_refresh_svx_route_index(
                ttl_seconds=60,
                timeout=5,
                known_airports={"IST", "PKX"},
                cache_dir=cache_dir,
                fetch_text=fake_fetch,
                now=datetime(2026, 5, 7, tzinfo=timezone.utc),
            )
            second_index, second_cache = load_or_refresh_svx_route_index(
                ttl_seconds=60,
                timeout=5,
                known_airports={"IST", "PKX"},
                cache_dir=cache_dir,
                fetch_text=fake_fetch,
            )

            self.assertEqual(calls, [SVX_OFFICIAL_SCHEDULE_URL, SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL])
            self.assertFalse(first_cache["hit"])
            self.assertTrue(second_cache["hit"])
            self.assertEqual(first_index["routes"], second_index["routes"])


if __name__ == "__main__":
    unittest.main()
