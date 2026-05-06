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
    pairs.sort(key=lambda pair: (pair["price"] if pair["price"] is not None else 10**12, elapsed_minutes(pair["segments"]) or 10**9))
    severity_order = {"error": 0, "warn": 1, "ok": 2}
    rejected.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity")), 9),
            -int((item.get("risk") or {}).get("score") or 0),
            item["price"] if item.get("price") is not None else 10**12,
        )
    )
    return pairs, rejected


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
            "outbound_pair_count": 0,
            "return_pair_count": 0,
            "rejected_pair_count": 0,
            "rejected_pair_sample_count": 0,
            "candidate_count": 0,
            "limit_per_pair": args.limit_per_pair,
            "max_candidates": args.max_candidates,
        },
        "candidates": [],
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
    rejected_pairs = outbound_rejected + return_rejected

    candidates: list[dict[str, Any]] = []
    if outbound_pairs and return_pairs:
        for outbound in outbound_pairs:
            for inbound in return_pairs:
                candidates.append(candidate_from_pairs(outbound, inbound, len(candidates) + 1))
                if len(candidates) >= args.max_candidates:
                    break
            if len(candidates) >= args.max_candidates:
                break
    else:
        for outbound in outbound_pairs:
            candidates.append(candidate_from_pairs(outbound, None, len(candidates) + 1))
            if len(candidates) >= args.max_candidates:
                break
        for inbound in return_pairs:
            candidates.append(candidate_from_pairs(None, inbound, len(candidates) + 1))
            if len(candidates) >= args.max_candidates:
                break

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
    ranked["assembly"] = {
        "segment_result_count": len(segment_results),
        "outbound_pair_count": len(outbound_pairs),
        "return_pair_count": len(return_pairs),
        "rejected_pair_count": len(rejected_pairs),
        "rejected_pair_sample_count": min(len(rejected_pairs), args.include_rejected_pairs),
        "candidate_count": len(candidates),
        "limit_per_pair": args.limit_per_pair,
        "max_candidates": args.max_candidates,
    }
    ranked["candidates"] = candidates[: args.include_candidates]
    ranked["rejected_pairs"] = rejected_pairs[: args.include_rejected_pairs]
    return ranked
