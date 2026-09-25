"""Разбор ответа Tutu search_avia и живой поиск через MCP SDK."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
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
    label: str
    from_: str = Field(alias="from")
    to: str
    departure_at: AwareDatetime
    arrival_at: AwareDatetime
    duration_min: int
    segments: list[Segment]

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Offer(SourceModel):
    duration_min: int
    segments_count: int
    departure_at: AwareDatetime
    arrival_at: AwareDatetime
    legs: list[Leg]
    variants: list[Variant]
    is_round_trip: bool | None = None
    return_departure_at: AwareDatetime | None = None
    return_arrival_at: AwareDatetime | None = None
    has_self_transfer: bool | None = None
    is_multi_pnr: bool | None = None
    multi_pnr_note: str | None = None


class Pricing(SourceModel):
    basis: str
    passengers: dict[str, int]


class Meta(SourceModel):
    pricing: Pricing
    has_more: bool
    total_matched_exact: bool
    upstream_note: str | None = None
    post_filter_dropped_over_cap: int = 0
    post_filter_dropped_not_direct: int = 0
    post_filter_dropped_wrong_carrier: int = 0
    post_filter_dropped_wrong_flight_number: int = 0
    post_filter_dropped_wrong_airport: int = 0


class SearchResponse(SourceModel):
    offers: list[Offer]
    meta: Meta


def _project_text(text: str) -> dict[str, Any]:
    payload = SearchResponse.model_validate_json(text)

    offers = []
    for offer in payload.offers:
        segments = [segment for leg in offer.legs for segment in leg.segments]
        first_segment = segments[0]
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

        legs = []
        for leg in offer.legs:
            legs.append(
                {
                    "label": leg.label,
                    "from": leg.from_,
                    "to": leg.to,
                    "departure_at": leg.departure_at.isoformat(),
                    "arrival_at": leg.arrival_at.isoformat(),
                    "duration_min": leg.duration_min,
                    "segments": [
                        {
                            "flight_number": segment.voyage_no,
                            "carrier": segment.carrier,
                            "origin": segment.from_,
                            "destination": segment.to,
                            "departure_at": segment.departure_at.isoformat(),
                            "arrival_at": segment.arrival_at.isoformat(),
                            "duration_min": segment.duration_min,
                        }
                        for segment in leg.segments
                    ],
                }
            )

        single_segment = offer.segments_count == 1
        offers.append(
            {
                "flight_number": first_segment.voyage_no if single_segment else None,
                "carrier": first_segment.carrier if single_segment else None,
                "origin": offer.legs[0].from_,
                "destination": offer.legs[0].to,
                "departure_at": offer.departure_at.isoformat(),
                "arrival_at": offer.arrival_at.isoformat(),
                "return_departure_at": (
                    offer.return_departure_at.isoformat() if offer.return_departure_at else None
                ),
                "return_arrival_at": (
                    offer.return_arrival_at.isoformat() if offer.return_arrival_at else None
                ),
                "duration_min": offer.duration_min,
                "segments_count": offer.segments_count,
                "is_round_trip": offer.is_round_trip,
                "has_self_transfer": offer.has_self_transfer,
                "is_multi_pnr": offer.is_multi_pnr,
                "multi_pnr_note": offer.multi_pnr_note,
                "legs": legs,
                "fares": fares,
            }
        )

    dropped = {
        name: value
        for name, value in {
            "over_cap": payload.meta.post_filter_dropped_over_cap,
            "not_direct": payload.meta.post_filter_dropped_not_direct,
            "wrong_carrier": payload.meta.post_filter_dropped_wrong_carrier,
            "wrong_flight_number": payload.meta.post_filter_dropped_wrong_flight_number,
            "wrong_airport": payload.meta.post_filter_dropped_wrong_airport,
        }.items()
        if value
    }

    return {
        "pricing_basis": payload.meta.pricing.basis,
        "passengers": payload.meta.pricing.passengers,
        "has_more": payload.meta.has_more,
        "total_matched_exact": payload.meta.total_matched_exact,
        "upstream_note": payload.meta.upstream_note,
        "post_filter_dropped": dropped,
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
    from mcp import Client

    async with Client(url) as client:
        result = await client.call_tool("search_avia", arguments)

    text = next(
        (block.text for block in result.content if isinstance(getattr(block, "text", None), str)),
        None,
    )
    if result.is_error:
        raise RuntimeError(text or "Tutu MCP search_avia failed")
    if text is None:
        raise ValueError("Tutu MCP search_avia returned no text result")
    return _project_text(text)


def _exception_message(error: Exception) -> str:
    if isinstance(error, ExceptionGroup):
        message = "; ".join(_exception_message(child) for child in error.exceptions)
        return message or str(error) or type(error).__name__
    return str(error) or type(error).__name__


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

    try:
        result = asyncio.run(search_live(arguments))
    except Exception as exc:
        print(_exception_message(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
