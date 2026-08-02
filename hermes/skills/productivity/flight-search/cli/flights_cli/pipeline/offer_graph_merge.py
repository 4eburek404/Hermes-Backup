from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain.normalize import (
    currency_value as _currency,
    normalize_code as _normalize_code,
    normalize_token as _normalize_token,
    numeric_or_none,
    ordered_unique as _ordered_unique,
    price_amount as _price_amount,
)
from ..domain.offer_paths import normalize_direction as _normalize_direction


def dedupe_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    deduped: list[dict[str, Any]] = []
    signature_index: dict[tuple[tuple[str, ...], ...], int] = {}
    deduped_count = 0
    for candidate in candidates:
        signature = _candidate_signature(candidate)
        if signature is None:
            deduped.append(candidate)
            continue
        existing_index = signature_index.get(signature)
        if existing_index is None:
            signature_index[signature] = len(deduped)
            deduped.append(candidate)
            continue
        deduped[existing_index] = _merge_duplicate_candidates(
            deduped[existing_index],
            candidate,
        )
        deduped_count += 1
    return deduped, deduped_count


def _candidate_signature(
    candidate: dict[str, Any],
) -> tuple[tuple[str, ...], ...] | None:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return None
    signature: list[tuple[str, ...]] = []
    for journey in journeys:
        if not isinstance(journey, dict):
            return None
        direction = _normalize_direction(journey.get("direction")) or ""
        segments = journey.get("segments")
        if not isinstance(segments, list) or not segments:
            return None
        for segment in segments:
            if not isinstance(segment, dict):
                return None
            part = (
                direction,
                _normalize_code(segment.get("origin")),
                _normalize_code(segment.get("destination")),
                _normalize_token(segment.get("departure_at")),
                _normalize_token(segment.get("arrival_at")),
            )
            if not all(part):
                return None
            signature.append(part)
    return tuple(signature) if signature else None


def _merge_duplicate_candidates(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    if _prefer_incoming_duplicate(existing, incoming):
        primary = deepcopy(incoming)
        alternate = existing
    else:
        primary = deepcopy(existing)
        alternate = incoming

    alternate_sources = [
        *[
            dict(source)
            for source in primary.get("alternate_sources") or []
            if isinstance(source, dict)
        ],
        _candidate_source_summary(alternate),
        *[
            dict(source)
            for source in alternate.get("alternate_sources") or []
            if isinstance(source, dict)
        ],
    ]
    primary["alternate_sources"] = _dedupe_source_summaries(alternate_sources)
    primary["source_providers"] = _ordered_unique(
        [
            *(primary.get("source_providers") or []),
            *(alternate.get("source_providers") or []),
        ]
    )
    primary["offer_ids"] = _ordered_unique(
        [*(primary.get("offer_ids") or []), *(alternate.get("offer_ids") or [])]
    )
    primary["edge_ids"] = _ordered_unique(
        [*(primary.get("edge_ids") or []), *(alternate.get("edge_ids") or [])]
    )
    primary["warnings"] = _ordered_unique(
        [*(primary.get("warnings") or []), *(alternate.get("warnings") or [])]
    )
    primary["covers_requested_trip"] = bool(
        primary.get("covers_requested_trip") or alternate.get("covers_requested_trip")
    )
    _attach_price_comparison(primary)
    return primary


def _candidate_preference(candidate: dict[str, Any]) -> tuple[int, int, int]:
    return (
        1 if candidate.get("source_type") == "provider_full_route" else 0,
        1 if candidate.get("price_basis") == "provider_offer_price" else 0,
        1 if candidate.get("price") is not None else 0,
    )


def _prefer_incoming_duplicate(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> bool:
    existing_preference = _candidate_preference(existing)
    incoming_preference = _candidate_preference(incoming)
    if incoming_preference != existing_preference:
        return incoming_preference > existing_preference
    if (
        existing.get("price_basis") != incoming.get("price_basis")
        or str(existing.get("currency") or "").upper()
        != str(incoming.get("currency") or "").upper()
    ):
        return False
    existing_price = numeric_or_none(existing.get("price"))
    incoming_price = numeric_or_none(incoming.get("price"))
    return (
        existing_price is not None
        and incoming_price is not None
        and incoming_price < existing_price
    )


def _candidate_source_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "source_type",
        "provider",
        "source_providers",
        "gateway",
        "gateways",
        "price",
        "currency",
        "price_basis",
        "ticketing_model",
        "ticketing_boundaries",
        "detail_status",
        "journey_scope",
        "covers_requested_trip",
        "offer_ids",
        "edge_ids",
        "path_offer_count",
        "warnings",
    )
    return {key: deepcopy(candidate.get(key)) for key in keys if key in candidate}


def _dedupe_source_summaries(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for source in sources:
        key = (
            str(source.get("source_type") or ""),
            "|".join(str(item) for item in source.get("offer_ids") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _attach_price_comparison(candidate: dict[str, Any]) -> None:
    provider_price = _candidate_price_for_basis(candidate, "provider_offer_price")
    summed_price = _candidate_price_for_basis(candidate, "summed_live_leg_prices")
    if provider_price is None or summed_price is None:
        candidate.pop("price_comparison", None)
        return
    provider_amount, provider_currency = provider_price
    summed_amount, summed_currency = summed_price
    if provider_currency != summed_currency or provider_amount == summed_amount:
        candidate.pop("price_comparison", None)
        return
    candidate["price_comparison"] = {
        "provider_offer_price": {
            "amount": provider_amount,
            "currency": provider_currency,
        },
        "summed_live_leg_prices": {
            "amount": summed_amount,
            "currency": summed_currency,
        },
        "difference": summed_amount - provider_amount,
        "currency": provider_currency,
    }


def _candidate_price_for_basis(
    candidate: dict[str, Any],
    basis: str,
) -> tuple[int | float, str] | None:
    sources = [
        candidate,
        *[
            source
            for source in candidate.get("alternate_sources") or []
            if isinstance(source, dict)
        ],
    ]
    for source in sources:
        if source.get("price_basis") != basis:
            continue
        amount = _price_amount(source)
        currency = _currency(source)
        if amount is not None and currency:
            return amount, currency
    return None


__all__ = ["dedupe_candidates"]
