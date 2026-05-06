from __future__ import annotations

import argparse
from typing import Any

from ..config import RISK_PROFILES
from ..domain.airports import airport_group
from ..domain.normalize import currency_value, price_value
from ..domain.time import elapsed_minutes, minutes_between
from ..errors import CliError
from ..services.ranking import carrier_policy_from_args, carrier_policy_output, rank_candidate_list
from ..services.validation import connection_risk_points, connection_rule

def collect_segment_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        results: list[dict[str, Any]] = []
        for item in payload:
            results.extend(collect_segment_results(item))
        return results
    if not isinstance(payload, dict):
        return []
    if payload.get("ok") is True and isinstance(payload.get("data"), dict):
        return collect_segment_results(payload["data"])
    if isinstance(payload.get("segment_result"), dict):
        return [payload["segment_result"]]
    if isinstance(payload.get("segment_results"), list):
        return collect_segment_results(payload["segment_results"])
    if isinstance(payload.get("results"), list):
        return collect_segment_results(payload["results"])
    if isinstance(payload.get("offers"), list) and (isinstance(payload.get("query"), dict) or payload.get("leg")):
        return [payload]
    return []


def offer_price(*offers: dict[str, Any]) -> int | None:
    total = 0
    seen = False
    for offer in offers:
        price = price_value(offer)
        if price is not None:
            total += price
            seen = True
    return total if seen else None


def offer_currency(*offers: dict[str, Any]) -> str | None:
    for offer in offers:
        currency = currency_value(offer)
        if currency:
            return currency
    return None


def offer_summary(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": offer.get("id"),
        "origin": offer.get("origin"),
        "destination": offer.get("destination"),
        "departure_airport": offer.get("departure_airport"),
        "arrival_airport": offer.get("arrival_airport"),
        "departure_at": offer.get("departure_at"),
        "arrival_at": offer.get("arrival_at"),
        "price": offer.get("price"),
        "currency": offer.get("currency"),
        "leg": offer.get("leg"),
    }


def rejected_pair(
    first: dict[str, Any],
    second: dict[str, Any],
    direction: str,
    *,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    profile: str,
) -> dict[str, Any] | None:
    first_arrival = str(first.get("arrival_airport") or first.get("destination") or "").upper()
    second_departure = str(second.get("departure_airport") or second.get("origin") or "").upper()
    if not first_arrival or not second_departure or first_arrival == second_departure:
        return None

    actual = minutes_between(str(first.get("arrival_at") or ""), str(second.get("departure_at") or ""))
    rule = connection_rule(first_arrival, second_departure, ticketing, min_same_airport, min_cross_airport, actual)
    arrival_group = airport_group(first_arrival)
    departure_group = airport_group(second_departure)
    same_group = bool(arrival_group and departure_group and arrival_group["key"] == departure_group["key"])
    airport_pair_status = "ground_transfer_required" if same_group else "airport_mismatch"
    first_segments = [seg for seg in (first.get("segments") or []) if isinstance(seg, dict)]
    second_segments = [seg for seg in (second.get("segments") or []) if isinstance(seg, dict)]
    prev_segment = first_segments[-1] if first_segments else {
        "origin": first.get("origin"),
        "destination": first_arrival,
        "arrival_at": first.get("arrival_at"),
    }
    next_segment = second_segments[0] if second_segments else {
        "origin": second_departure,
        "destination": second.get("destination"),
        "departure_at": second.get("departure_at"),
    }
    risk = connection_risk_points(rule, prev_segment, next_segment, profile)
    return {
        "direction": direction,
        "reason": rule["status"],
        "airport_pair_status": airport_pair_status,
        "severity": rule["severity"],
        "arrival_airport": first_arrival,
        "departure_airport": second_departure,
        "same_multi_airport_system": rule["same_multi_airport_system"],
        "airport_group": arrival_group["label"] if same_group and arrival_group else None,
        "actual_min": actual,
        "required_min": rule["required_min"],
        "risk": risk,
        "notes": rule["notes"],
        "first_offer": offer_summary(first),
        "second_offer": offer_summary(second),
        "price": offer_price(first, second),
        "currency": offer_currency(first, second),
    }


def pair_offers(first: dict[str, Any], second: dict[str, Any], direction: str) -> dict[str, Any] | None:
    if first.get("arrival_airport") != second.get("departure_airport"):
        return None
    segments = list(first.get("segments") or []) + list(second.get("segments") or [])
    if len(segments) < 2:
        return None
    return {
        "direction": direction,
        "segments": segments,
        "offers": [
            offer_summary(first),
            offer_summary(second),
        ],
        "price": offer_price(first, second),
        "currency": offer_currency(first, second),
    }


def pair_connection_quality(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    profile: str,
) -> dict[str, Any]:
    first_arrival = str(first.get("arrival_airport") or first.get("destination") or "").upper()
    second_departure = str(second.get("departure_airport") or second.get("origin") or "").upper()
    actual = minutes_between(str(first.get("arrival_at") or ""), str(second.get("departure_at") or ""))
    rule = connection_rule(first_arrival, second_departure, ticketing, min_same_airport, min_cross_airport, actual)
    first_segments = [seg for seg in (first.get("segments") or []) if isinstance(seg, dict)]
    second_segments = [seg for seg in (second.get("segments") or []) if isinstance(seg, dict)]
    prev_segment = first_segments[-1] if first_segments else {
        "origin": first.get("origin"),
        "destination": first_arrival,
        "arrival_at": first.get("arrival_at"),
    }
    next_segment = second_segments[0] if second_segments else {
        "origin": second_departure,
        "destination": second.get("destination"),
        "departure_at": second.get("departure_at"),
    }
    risk = connection_risk_points(rule, prev_segment, next_segment, profile)
    return {
        "status": rule["status"],
        "severity": rule["severity"],
        "actual_min": actual,
        "required_min": rule["required_min"],
        "risk": risk,
    }


def pair_sort_key(pair: dict[str, Any]) -> tuple[int, int, int, int]:
    quality = pair.get("connection_quality") or {}
    risk = quality.get("risk") or {}
    price = pair["price"] if pair.get("price") is not None else 10**12
    elapsed = elapsed_minutes(pair["segments"]) or 10**9
    return (
        1 if int(risk.get("score") or 0) >= 100 else 0,
        int(risk.get("score") or 0),
        price,
        elapsed,
    )


def assemble_direction(
    segment_results: list[dict[str, Any]],
    first_leg: str,
    second_leg: str,
    direction: str,
    limit_per_pair: int,
    *,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    profile: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    first_results = [result for result in segment_results if result.get("direction") == direction and result.get("leg") == first_leg]
    second_results = [result for result in segment_results if result.get("direction") == direction and result.get("leg") == second_leg]
    pairs = []
    rejected = []
    for first_result in first_results:
        for first_offer in list(first_result.get("offers") or [])[:limit_per_pair]:
            if not isinstance(first_offer, dict):
                continue
            for second_result in second_results:
                for second_offer in list(second_result.get("offers") or [])[:limit_per_pair]:
                    if not isinstance(second_offer, dict):
                        continue
                    pair = pair_offers(first_offer, second_offer, direction)
                    if pair is not None:
                        pair["connection_quality"] = pair_connection_quality(
                            first_offer,
                            second_offer,
                            ticketing=ticketing,
                            min_same_airport=min_same_airport,
                            min_cross_airport=min_cross_airport,
                            profile=profile,
                        )
                        pairs.append(pair)
                    else:
                        rejection = rejected_pair(
                            first_offer,
                            second_offer,
                            direction,
                            ticketing=ticketing,
                            min_same_airport=min_same_airport,
                            min_cross_airport=min_cross_airport,
                            profile=profile,
                        )
                        if rejection is not None:
                            rejected.append(rejection)
    pairs.sort(key=pair_sort_key)
    severity_order = {"error": 0, "warn": 1, "ok": 2}
    rejected.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity")), 9),
            -int((item.get("risk") or {}).get("score") or 0),
            item["price"] if item.get("price") is not None else 10**12,
        )
    )
    return pairs, rejected


def direct_journeys(
    segment_results: list[dict[str, Any]],
    leg: str,
    direction: str,
    limit_per_result: int,
) -> list[dict[str, Any]]:
    journeys: list[dict[str, Any]] = []
    direct_results = [result for result in segment_results if result.get("direction") == direction and result.get("leg") == leg]
    for result in direct_results:
        for offer in list(result.get("offers") or [])[:limit_per_result]:
            if not isinstance(offer, dict):
                continue
            segments = [segment for segment in (offer.get("segments") or []) if isinstance(segment, dict)]
            if not segments:
                continue
            journeys.append(
                {
                    "direction": direction,
                    "segments": segments,
                    "offers": [offer_summary(offer)],
                    "price": offer_price(offer),
                    "currency": offer_currency(offer),
                    "direct": True,
                }
            )
    journeys.sort(key=pair_sort_key)
    return journeys


def candidate_from_pairs(outbound: dict[str, Any] | None, inbound: dict[str, Any] | None, index: int) -> dict[str, Any]:
    journeys = []
    offers = []
    price_parts = []
    if outbound:
        journeys.append({"direction": "outbound", "segments": outbound["segments"]})
        offers.extend(outbound["offers"])
        price_parts.append(outbound)
    if inbound:
        journeys.append({"direction": "return", "segments": inbound["segments"]})
        offers.extend(inbound["offers"])
        price_parts.append(inbound)
    first = journeys[0]["segments"][0]
    last = journeys[-1]["segments"][-1]
    return {
        "id": f"assembled-{index}:{first['origin']}-{last['destination']}",
        "price": offer_price(*price_parts),
        "currency": offer_currency(*price_parts),
        "journeys": journeys,
        "source_offers": offers,
    }


def candidate_signature(candidate: dict[str, Any]) -> tuple[tuple[str, str, str, str, str, str], ...]:
    parts: list[tuple[str, str, str, str, str, str]] = []
    for journey in candidate.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        direction = str(journey.get("direction") or "")
        for segment in journey.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            parts.append(
                (
                    direction,
                    str(segment.get("flight_number") or ""),
                    str(segment.get("origin") or ""),
                    str(segment.get("destination") or ""),
                    str(segment.get("departure_at") or ""),
                    str(segment.get("arrival_at") or ""),
                )
            )
    return tuple(parts)


def dedupe_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[tuple[str, str, str, str, str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    duplicates = 0
    for candidate in candidates:
        signature = candidate_signature(candidate)
        if signature and signature in seen:
            duplicates += 1
            continue
        if signature:
            seen.add(signature)
        first = (candidate.get("journeys") or [{}])[0].get("segments", [{}])[0]
        last = (candidate.get("journeys") or [{}])[-1].get("segments", [{}])[-1]
        normalized = dict(candidate)
        normalized["id"] = f"assembled-{len(deduped) + 1}:{first.get('origin')}-{last.get('destination')}"
        deduped.append(normalized)
    return deduped, duplicates


def ranked_candidate_details(ranked_items: list[dict[str, Any]], candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_id = {str(candidate.get("id")): candidate for candidate in candidates}
    details = []
    for item in ranked_items[: max(0, limit)]:
        candidate = by_id.get(str(item.get("id")))
        if candidate is not None:
            details.append({"rank": item.get("rank"), "ranked": item, "candidate": candidate})
    return details


def recommendation_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.get("id"),
        "rank": item.get("rank"),
        "price": item.get("price"),
        "currency": item.get("currency"),
        "elapsed_min": item.get("elapsed_min"),
        "carriers": item.get("carriers") or [],
        "ok": item.get("ok"),
        "risk": item.get("risk"),
    }


def recommendation_summary(ranked_items: list[dict[str, Any]]) -> dict[str, Any]:
    ok_items = [item for item in ranked_items if item.get("ok") is True]
    source = ok_items or ranked_items
    cheapest = min(source, key=lambda item: item["price"] if item.get("price") is not None else 10**12, default=None)
    fastest = min(source, key=lambda item: item["elapsed_min"] if item.get("elapsed_min") is not None else 10**12, default=None)
    return {
        "best_ranked": recommendation_item(ranked_items[0] if ranked_items else None),
        "cheapest_acceptable": recommendation_item(cheapest),
        "fastest_acceptable": recommendation_item(fastest),
    }


def empty_assembled_result(args: argparse.Namespace) -> dict[str, Any]:
    policy = carrier_policy_from_args(args)
    return {
        "profile": args.profile,
        "profile_description": RISK_PROFILES[args.profile]["description"],
        "rank_order": RISK_PROFILES[args.profile]["rank_order"],
        "count": 0,
        "carrier_policy": {**carrier_policy_output(policy), "filtered_count": 0, "filtered": []},
        "ranked": [],
        "assembly": {
            "segment_result_count": 0,
            "outbound_direct_count": 0,
            "outbound_pair_count": 0,
            "return_direct_count": 0,
            "return_pair_count": 0,
            "rejected_pair_count": 0,
            "rejected_pair_sample_count": 0,
            "raw_candidate_count": 0,
            "candidate_duplicate_count": 0,
            "candidate_count": 0,
            "ranked_total_count": 0,
            "ranked_output_count": 0,
            "candidate_pool_limit": args.candidate_pool_limit,
            "candidate_pool_truncated": False,
            "limit_per_pair": args.limit_per_pair,
            "max_candidates": args.max_candidates,
        },
        "candidates": [],
        "ranked_candidates": [],
        "recommendations": {"best_ranked": None, "cheapest_acceptable": None, "fastest_acceptable": None},
        "rejected_pairs": [],
    }


def assemble_segment_results(segment_results: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    if not segment_results:
        raise CliError("no parsed segment results found; run `flights results parse` first", error_type="validation_error")

    outbound_pairs, outbound_rejected = assemble_direction(
        segment_results,
        "origin_to_hub",
        "hub_to_destination",
        "outbound",
        args.limit_per_pair,
        ticketing=args.ticketing,
        min_same_airport=args.min_same_airport_min,
        min_cross_airport=args.min_cross_airport_min,
        profile=args.profile,
    )
    return_pairs, return_rejected = assemble_direction(
        segment_results,
        "destination_to_hub",
        "hub_to_origin",
        "return",
        args.limit_per_pair,
        ticketing=args.ticketing,
        min_same_airport=args.min_same_airport_min,
        min_cross_airport=args.min_cross_airport_min,
        profile=args.profile,
    )
    outbound_direct = direct_journeys(segment_results, "direct_outbound", "outbound", args.limit_per_pair)
    return_direct = direct_journeys(segment_results, "direct_return", "return", args.limit_per_pair)
    outbound_journeys = outbound_direct + outbound_pairs
    return_journeys = return_direct + return_pairs
    rejected_pairs = outbound_rejected + return_rejected

    candidates: list[dict[str, Any]] = []
    candidate_pool_limit = max(max(1, int(args.max_candidates)), int(getattr(args, "candidate_pool_limit", 5000)))
    candidate_pool_truncated = False
    if outbound_journeys and return_journeys:
        for outbound in outbound_journeys:
            for inbound in return_journeys:
                candidates.append(candidate_from_pairs(outbound, inbound, len(candidates) + 1))
                if len(candidates) >= candidate_pool_limit:
                    candidate_pool_truncated = True
                    break
            if candidate_pool_truncated:
                break
    else:
        for outbound in outbound_journeys:
            candidates.append(candidate_from_pairs(outbound, None, len(candidates) + 1))
            if len(candidates) >= candidate_pool_limit:
                candidate_pool_truncated = True
                break
        if not candidate_pool_truncated:
            for inbound in return_journeys:
                candidates.append(candidate_from_pairs(None, inbound, len(candidates) + 1))
                if len(candidates) >= candidate_pool_limit:
                    candidate_pool_truncated = True
                    break
    raw_candidate_count = len(candidates)
    candidates, duplicate_count = dedupe_candidates(candidates)

    rank_args = argparse.Namespace(
        profile=args.profile,
        ticketing=args.ticketing,
        min_same_airport_min=args.min_same_airport_min,
        min_cross_airport_min=args.min_cross_airport_min,
        max_reasons=args.max_reasons,
        only_carrier=getattr(args, "only_carrier", None),
        exclude_carrier=getattr(args, "exclude_carrier", None),
        prefer_carrier=getattr(args, "prefer_carrier", None),
        avoid_carrier=getattr(args, "avoid_carrier", None),
        include_filtered=getattr(args, "include_filtered", 20),
    )
    policy = carrier_policy_from_args(rank_args)
    ranked = rank_candidate_list(candidates, rank_args) if candidates else {
        "profile": args.profile,
        "profile_description": RISK_PROFILES[args.profile]["description"],
        "rank_order": RISK_PROFILES[args.profile]["rank_order"],
        "count": 0,
        "carrier_policy": {**carrier_policy_output(policy), "filtered_count": 0, "filtered": []},
        "ranked": [],
    }
    ranked_total_count = len(ranked["ranked"])
    max_ranked = max(0, int(args.max_candidates))
    ranked["ranked"] = ranked["ranked"][:max_ranked]
    ranked["count"] = len(ranked["ranked"])
    ranked["ranked_total_count"] = ranked_total_count
    ranked["assembly"] = {
        "segment_result_count": len(segment_results),
        "outbound_direct_count": len(outbound_direct),
        "outbound_pair_count": len(outbound_pairs),
        "return_direct_count": len(return_direct),
        "return_pair_count": len(return_pairs),
        "rejected_pair_count": len(rejected_pairs),
        "rejected_pair_sample_count": min(len(rejected_pairs), args.include_rejected_pairs),
        "raw_candidate_count": raw_candidate_count,
        "candidate_duplicate_count": duplicate_count,
        "candidate_count": len(candidates),
        "ranked_total_count": ranked_total_count,
        "ranked_output_count": len(ranked["ranked"]),
        "candidate_pool_limit": candidate_pool_limit,
        "candidate_pool_truncated": candidate_pool_truncated,
        "limit_per_pair": args.limit_per_pair,
        "max_candidates": args.max_candidates,
    }
    ranked["candidates"] = candidates[: args.include_candidates]
    ranked["ranked_candidates"] = ranked_candidate_details(
        ranked["ranked"],
        candidates,
        int(getattr(args, "include_ranked_candidates", 5)),
    )
    ranked["recommendations"] = recommendation_summary(ranked["ranked"])
    ranked["rejected_pairs"] = rejected_pairs[: args.include_rejected_pairs]
    return ranked
