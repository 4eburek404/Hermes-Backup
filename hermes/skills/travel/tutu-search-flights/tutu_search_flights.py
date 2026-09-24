"""Минимальный разбор успешного ответа search_avia для S1."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


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


def search(
    arguments: dict[str, Any],
    *,
    call_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Вызвать переданный search_avia и спроецировать его ответ в наблюдения S1."""
    envelope = call_tool("search_avia", arguments)
    payload = SearchResponse.model_validate_json(envelope["result"]["content"][0]["text"])

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
