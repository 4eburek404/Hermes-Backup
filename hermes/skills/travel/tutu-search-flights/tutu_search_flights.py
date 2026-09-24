"""Разбор ответа Tutu search_avia и живой поиск через MCP SDK."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

TUTU_MCP_URL = "https://mcp.tutu.ru/mcp"


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Price(SourceModel):
    amount: Decimal
    currency: str


class Baggage(SourceModel):
    kg: int | None = None
    pieces: int | None = None
    dimensions: str | None = None


class Exchange(SourceModel):
    available: bool
    deadline_hours: int | None = None


class Conditions(SourceModel):
    fare_family: str | None = None
    baggage: Baggage | None = None
    cabin_baggage: Baggage | None = None
    refundable: bool | None = None
    changeable: bool | None = None
    exchange: Exchange | None = None


class Variant(SourceModel):
    price: Price
    conditions: Conditions


class Segment(SourceModel):
    carrier: str
    voyage_no: str
    from_: str = Field(alias="from")
    to: str
    departure_at: AwareDatetime
    arrival_at: AwareDatetime
    duration_min: int

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Leg(SourceModel):
    segments: list[Segment]


class Offer(SourceModel):
    duration_min: int
    segments_count: int
    departure_at: AwareDatetime
    arrival_at: AwareDatetime
    legs: list[Leg]
    variants: list[Variant]


class Pricing(SourceModel):
    basis: str
    passengers: dict[str, int]


class Meta(SourceModel):
    pricing: Pricing
    has_more: bool


class SearchResponse(SourceModel):
    offers: list[Offer]
    meta: Meta


def _project_text(text: str) -> dict[str, Any]:
    payload = SearchResponse.model_validate_json(text)

    offers = []
    for offer in payload.offers:
        segments = [segment for leg in offer.legs for segment in leg.segments]
        segment = segments[0]
        fares = []
        for variant in offer.variants:
            conditions = variant.conditions
            fares.append(
                {
                    "name": conditions.fare_family,
                    "amount": format(variant.price.amount, ".2f"),
                    "currency": variant.price.currency,
                    "baggage": (
                        conditions.baggage.model_dump(exclude_unset=True)
                        if conditions.baggage
                        else None
                    ),
                    "cabin_baggage": (
                        conditions.cabin_baggage.model_dump(exclude_unset=True)
                        if conditions.cabin_baggage
                        else None
                    ),
                    "refundable": conditions.refundable,
                    "changeable": conditions.changeable,
                    "exchange": (
                        conditions.exchange.model_dump(exclude_unset=True)
                        if conditions.exchange
                        else None
                    ),
                }
            )
        offers.append(
            {
                "flight_number": segment.voyage_no,
                "carrier": segment.carrier,
                "origin": segment.from_,
                "destination": segments[-1].to,
                "departure_at": offer.departure_at.isoformat(),
                "arrival_at": offer.arrival_at.isoformat(),
                "duration_min": offer.duration_min,
                "segments_count": offer.segments_count,
                "fares": fares,
            }
        )

    return {
        "pricing_basis": payload.meta.pricing.basis,
        "passengers": payload.meta.pricing.passengers,
        "has_more": payload.meta.has_more,
        "offers": offers,
    }


def search(
    arguments: dict[str, Any],
    *,
    call_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Вызвать переданный search_avia и спроецировать его ответ в наблюдения S1."""
    envelope = call_tool("search_avia", arguments)
    return _project_text(envelope["result"]["content"][0]["text"])


async def search_live(
    arguments: dict[str, Any],
    *,
    url: str = TUTU_MCP_URL,
) -> dict[str, Any]:
    """Выполнить живой search_avia через официальный MCP Python SDK."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("search_avia", arguments=arguments)

    text = next(
        (
            block.text
            for block in result.content
            if isinstance(getattr(block, "text", None), str)
        ),
        None,
    )
    if text is None:
        raise ValueError("Tutu MCP search_avia returned no text result")
    return _project_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Живой поиск авиабилетов через Tutu MCP")
    parser.add_argument("arguments", help="JSON-объект аргументов search_avia")
    parsed = parser.parse_args(argv)

    try:
        arguments = json.loads(parsed.arguments)
    except json.JSONDecodeError as exc:
        parser.error(f"arguments must be valid JSON: {exc.msg}")
    if not isinstance(arguments, dict):
        parser.error("arguments must be a JSON object")

    result = asyncio.run(search_live(arguments))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
