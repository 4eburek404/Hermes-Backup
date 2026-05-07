"""Hermes user plugin: Travelpayouts flight search.

Self-contained extraction/adaptation from the abandoned Telegram bot flights
module. Do not import the bot package: it has unrelated Telegram/WebApp config
requirements that can break Hermes startup.
"""
from __future__ import annotations

from .schemas import TRAVELPAYOUTS_FLIGHT_SEARCH_SCHEMA
from .tools import check_travelpayouts_available, travelpayouts_flight_search


def register(ctx) -> None:
    """Register Travelpayouts tools. Called once by Hermes plugin loader."""
    ctx.register_tool(
        name="travelpayouts_flight_search",
        toolset="travelpayouts",
        schema=TRAVELPAYOUTS_FLIGHT_SEARCH_SCHEMA,
        handler=travelpayouts_flight_search,
        check_fn=check_travelpayouts_available,
        requires_env=["TRAVELPAYOUTS_TOKEN"],
        is_async=True,
        description="Search cached Travelpayouts/Aviasales flight prices. Advisory only; no booking.",
        emoji="✈️",
    )
