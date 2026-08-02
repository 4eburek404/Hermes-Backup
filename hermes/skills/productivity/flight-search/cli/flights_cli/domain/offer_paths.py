from __future__ import annotations

from typing import Any


def provider_result_offers(result: dict[str, Any]) -> list[Any] | None:
    for key in ("offers", "top_offers"):
        offers = result.get(key)
        if isinstance(offers, list):
            return offers
    return None


def segment_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [segment for segment in value if isinstance(segment, dict)]


def segment_origin(segment: dict[str, Any]) -> str:
    return (
        str(
            segment.get("origin")
            or segment.get("departure")
            or segment.get("from")
            or segment.get("departure_airport")
            or ""
        )
        .strip()
        .upper()
    )


def segment_destination(segment: dict[str, Any]) -> str:
    return (
        str(
            segment.get("destination")
            or segment.get("arrival")
            or segment.get("to")
            or segment.get("arrival_airport")
            or ""
        )
        .strip()
        .upper()
    )


def normalize_direction(value: Any) -> str | None:
    direction = str(value or "").strip().lower()
    return direction or None


def offer_segment_paths(
    offer: dict[str, Any], *, fallback_direction: str | None
) -> list[dict[str, Any]]:
    journeys = offer.get("journeys")
    paths: list[dict[str, Any]] = []
    if isinstance(journeys, list):
        for journey_index, journey in enumerate(journeys):
            if not isinstance(journey, dict):
                continue
            segments = segment_dicts(journey.get("segments"))
            if not segments:
                continue
            paths.append(
                {
                    "segments": segments,
                    "direction": normalize_direction(journey.get("direction"))
                    or fallback_direction,
                    "debug": {
                        "source_path": "journeys",
                        "journey_index": journey_index,
                    },
                }
            )
    if paths:
        return paths
    segments = segment_dicts(offer.get("segments"))
    if not segments:
        return []
    return [
        {
            "segments": segments,
            "direction": normalize_direction(offer.get("direction"))
            or fallback_direction,
            "debug": {"source_path": "segments"},
        }
    ]
