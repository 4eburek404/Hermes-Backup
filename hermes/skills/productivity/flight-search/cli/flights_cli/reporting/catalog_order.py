from __future__ import annotations

import re
from typing import Any

from .option_semantics import direction_segments, option_direction
from .time_utils import display_minutes_between, integer_or_none


def option_is_user_visible(option: dict[str, Any]) -> bool:
    if option.get("ok") is False:
        return False
    risk = option.get("risk") if isinstance(option.get("risk"), dict) else {}
    if risk.get("reject") is True:
        return False
    return True


def option_max_connections_per_journey(option: dict[str, Any]) -> int:
    explicit = integer_or_none(option.get("max_connections_per_journey"))
    if explicit is None:
        summary = option.get("validation_summary") if isinstance(option.get("validation_summary"), dict) else {}
        explicit = integer_or_none(summary.get("max_connections_per_journey"))
    if explicit is not None:
        return max(0, explicit)

    counts: list[int] = []
    for direction in ("outbound", "return"):
        segments = direction_segments(option, direction)
        if segments:
            counts.append(max(0, len(segments) - 1))
    if counts:
        return max(counts)

    segments = option.get("segments") if isinstance(option.get("segments"), list) else []
    return max(0, len(segments) - 1) if segments else 10**6


def option_price_amount(option: dict[str, Any]) -> int | float:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    amount = integer_or_none(price.get("amount"))
    if amount is not None:
        return amount
    text = str(option.get("price_text") or "")
    digits = re.sub(r"[^\d]", "", text)
    if digits:
        return int(digits)
    return 10**12


def _elapsed_text_minutes(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)\s*h\s*(\d{1,2})", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.fullmatch(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", text)
    if match and (match.group(1) or match.group(2)):
        return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
    match = re.fullmatch(r"(\d+):(\d{2})", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    return None


def option_elapsed_minutes(option: dict[str, Any]) -> int:
    for key in ("itinerary_elapsed_min", "elapsed_min"):
        value = integer_or_none(option.get(key))
        if value is not None:
            return value

    spans: list[int] = []
    for direction in ("outbound", "return"):
        segments = direction_segments(option, direction)
        if segments:
            elapsed = display_minutes_between(segments[0].get("departure_at"), segments[-1].get("arrival_at"))
            if elapsed is not None:
                spans.append(elapsed)
    if spans:
        return max(spans)

    elapsed_text = _elapsed_text_minutes(option.get("elapsed"))
    return elapsed_text if elapsed_text is not None else 10**9


def option_rank(option: dict[str, Any]) -> int:
    rank = integer_or_none(option.get("rank"))
    return rank if rank is not None else 10**6


def option_covers_requested_trip(option: dict[str, Any], *, is_round_trip_request: bool) -> bool:
    explicit = option.get("covers_requested_trip")
    if isinstance(explicit, bool):
        return explicit
    scope = str(option.get("journey_scope") or "")
    if scope in ("one_way", "round_trip", "two_one_way_pair"):
        return True
    if scope in ("outbound_only", "return_only"):
        return not is_round_trip_request
    return option_direction(option) is None or not is_round_trip_request


def catalog_order_key(option: dict[str, Any], *, is_round_trip_request: bool = False) -> tuple[int, int, int, int, int, int | float]:
    return (
        0 if option_is_user_visible(option) else 1,
        0 if option_covers_requested_trip(option, is_round_trip_request=is_round_trip_request) else 1,
        option_max_connections_per_journey(option),
        option_rank(option),
        option_elapsed_minutes(option),
        option_price_amount(option),
    )


def canonical_option_id(option: dict[str, Any]) -> str:
    option_id = str(option.get("id") or "")
    if option_id.startswith("ru-priority-") and ":" in option_id:
        return option_id.split(":", 1)[1]
    return option_id


def itinerary_signature(option: dict[str, Any]) -> tuple[tuple[str, str, str, str, str, str], ...]:
    segments = option.get("segments") if isinstance(option.get("segments"), list) else []
    return tuple(
        (
            str(segment.get("direction") or ""),
            str(segment.get("flight_number") or ""),
            str(segment.get("origin") or ""),
            str(segment.get("destination") or ""),
            str(segment.get("departure_at") or ""),
            str(segment.get("arrival_at") or ""),
        )
        for segment in segments
        if isinstance(segment, dict)
    )


def ordered_user_options(
    recommended: list[Any],
    priority: list[Any],
    *,
    limit: int,
    is_round_trip_request: bool = False,
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for source_bucket, source_options in enumerate((recommended or [], priority)):
        for option in source_options:
            if not isinstance(option, dict) or not option_is_user_visible(option):
                continue
            candidates.append((source_bucket, option))
    candidates.sort(
        key=lambda item: (
            *catalog_order_key(item[1], is_round_trip_request=is_round_trip_request)[:3],
            item[0],
            *catalog_order_key(item[1], is_round_trip_request=is_round_trip_request)[3:],
        )
    )

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_signatures: set[tuple[tuple[tuple[str, str, str, str, str, str], ...], int | float]] = set()
    for _, option in candidates:
        option_id = canonical_option_id(option)
        signature = itinerary_signature(option)
        priced_signature = (signature, option_price_amount(option))
        if option_id and option_id in seen_ids:
            continue
        if signature and priced_signature in seen_signatures:
            continue
        if option_id:
            seen_ids.add(option_id)
        if signature:
            seen_signatures.add(priced_signature)
        selected.append(option)
        if len(selected) >= max(0, limit):
            break
    return selected
