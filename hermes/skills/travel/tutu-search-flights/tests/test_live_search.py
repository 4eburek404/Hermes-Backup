"""Opt-in интеграционная проверка живого поиска Tutu через MCP SDK."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
import tutu_search_flights

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("TUTU_LIVE") != "1", reason="set TUTU_LIVE=1"),
]


def test_live_search_returns_current_tutu_offer():
    departure_date = (datetime.now(UTC).date() + timedelta(days=21)).isoformat()
    result = asyncio.run(
        tutu_search_flights.search_live(
            {
                "origin": "Москва",
                "destination": "Сочи",
                "departure_date": departure_date,
                "page_size": 1,
            }
        )
    )

    assert result["pricing_basis"] == "party_total"
    assert result["passengers"] == {"full": 1}
    assert result["offers"]
    assert result["offers"][0]["fares"]
