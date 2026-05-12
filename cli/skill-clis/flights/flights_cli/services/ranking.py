from __future__ import annotations

import argparse
from typing import Any

from ..config import RISK_PROFILES
from ..domain.carriers import itinerary_carriers, segment_carriers
from ..domain.normalize import (
    clamp_score,
    currency_value,
    is_reject_score,
    normalize_carrier_codes,
    normalize_profile,
    price_value,
    risk_grade,
)
from ..services.validation import rank_key, validate_itinerary
from ..errors import CliError
from .stop_policy import apply_stop_policy_frontier, stop_policy_from_args, stop_policy_summary

def extract_candidate_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict) and isinstance(data.get("itineraries"), list):
        candidates = data["itineraries"]
    elif isinstance(data, dict) and isinstance(data.get("candidates"), list):
        candidates = data["candidates"]
    else:
        raise CliError("input must be a list or an object with itineraries/candidates", error_type="validation_error")
    if not all(isinstance(candidate, dict) for candidate in candidates):
        raise CliError("all candidates must be objects", error_type="validation_error")
    return candidates


def carrier_policy_from_args(args: argparse.Namespace) -> dict[str, set[str]]:
    return {
        "only": normalize_carrier_codes(getattr(args, "only_carrier", None), "only-carrier"),
        "exclude": normalize_carrier_codes(getattr(args, "exclude_carrier", None), "exclude-carrier"),
        "prefer": normalize_carrier_codes(getattr(args, "prefer_carrier", None), "prefer-carrier"),
        "avoid": normalize_carrier_codes(getattr(args, "avoid_carrier", None), "avoid-carrier"),
    }


def carrier_policy_output(policy: dict[str, set[str]]) -> dict[str, list[str]]:
    return {key: sorted(value) for key, value in policy.items()}


def carrier_filter_result(segments: list[dict[str, Any]], policy: dict[str, set[str]]) -> dict[str, Any]:
    only = policy["only"]
    exclude = policy["exclude"]
    all_carriers = itinerary_carriers(segments)
    excluded = sorted(all_carriers & exclude)
    if excluded:
        return {
            "ok": False,
            "reason": "excluded_carrier",
            "carriers": sorted(all_carriers),
            "matched_carriers": excluded,
            "message": f"Candidate uses excluded carrier(s): {', '.join(excluded)}.",
        }
    if only:
        missing_segments = []
        for segment in segments:
            carriers = segment_carriers(segment)
            if not carriers or not carriers & only:
                missing_segments.append(
                    {
                        "index": segment.get("index"),
                        "origin": segment.get("origin"),
                        "destination": segment.get("destination"),
                        "carriers": sorted(carriers),
                    }
                )
        if missing_segments:
            return {
                "ok": False,
                "reason": "outside_only_carriers",
                "carriers": sorted(all_carriers),
                "matched_carriers": sorted(all_carriers & only),
                "missing_segments": missing_segments,
                "message": f"Not every segment is operated by selected carrier(s): {', '.join(sorted(only))}.",
            }
    return {
        "ok": True,
        "reason": None,
        "carriers": sorted(all_carriers),
        "matched_carriers": sorted(all_carriers & (only or all_carriers)),
    }


def apply_carrier_preferences(risk: dict[str, Any], segments: list[dict[str, Any]], policy: dict[str, set[str]]) -> dict[str, Any]:
    prefer = policy["prefer"]
    avoid = policy["avoid"]
    if not prefer and not avoid:
        return risk

    carriers = itinerary_carriers(segments)
    score = int(risk["score"])
    components = list(risk["components"])
    preference_components: list[dict[str, Any]] = []

    if prefer:
        matched = sorted(carriers & prefer)
        if matched:
            preference_components.append(
                {
                    "scope": "carrier",
                    "code": "preferred_carrier_match",
                    "points": 0,
                    "message": f"Uses preferred carrier(s): {', '.join(matched)}.",
                }
            )
        else:
            points = 14
            score += points
            preference_components.append(
                {
                    "scope": "carrier",
                    "code": "missing_preferred_carrier",
                    "points": points,
                    "message": f"Does not use preferred carrier(s): {', '.join(sorted(prefer))}.",
                }
            )

    avoided = sorted(carriers & avoid)
    if avoided:
        points = 24
        score += points
        preference_components.append(
            {
                "scope": "carrier",
                "code": "avoided_carrier",
                "points": points,
                "message": f"Uses avoided carrier(s): {', '.join(avoided)}.",
            }
        )

    score = clamp_score(score)
    adjusted = dict(risk)
    adjusted["score"] = score
    adjusted["grade"] = risk_grade(score)
    adjusted["reject"] = is_reject_score(score)
    adjusted["components"] = components + preference_components
    adjusted["carrier_preferences"] = {
        "carriers": sorted(carriers),
        "matched_preferred": sorted(carriers & prefer),
        "matched_avoided": sorted(carriers & avoid),
    }
    adjusted["rank_key"] = rank_key(str(risk["profile"]), score, risk.get("price"), risk.get("elapsed_min"))
    return adjusted


def rank_candidate_list(candidates: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    profile = normalize_profile(args.profile)
    policy = carrier_policy_from_args(args)
    ranked: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    stop_policy = stop_policy_from_args(args)
    include_filtered = max(0, int(getattr(args, "include_filtered", 20)))
    stop_policy_diagnostics_requested = bool(getattr(args, "include_stop_policy_diagnostics", False))
    validated_items: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        candidate_args = argparse.Namespace(
            ticketing=str(candidate.get("ticketing") or args.ticketing),
            min_same_airport_min=args.min_same_airport_min,
            min_cross_airport_min=args.min_cross_airport_min,
            profile=profile,
        )
        validation = validate_itinerary(candidate, candidate_args)
        candidate_id = candidate.get("id") or candidate.get("name") or f"candidate-{index + 1}"
        validated_items.append(
            {
                "id": candidate_id,
                "ok": validation["ok"],
                "price": price_value(candidate),
                "journeys": validation.get("journeys"),
                "validation": validation,
                "validation_summary": validation["summary"],
                "connections": validation["connections"],
                "segments": validation["segments"],
                "source_candidate": candidate,
                "index": index,
            }
        )

    validated_items, stop_diagnostics = apply_stop_policy_frontier(validated_items, stop_policy)
    for item in validated_items:
        validation = item["validation"]
        segments = validation["segments"]
        raw_candidate = item.get("source_candidate")
        carrier_filter = carrier_filter_result(segments, policy)
        candidate_id = item["id"]
        if not carrier_filter["ok"]:
            if len(filtered) < include_filtered:
                filtered.append(
                    {
                        "id": candidate_id,
                        "reason": carrier_filter["reason"],
                        "message": carrier_filter["message"],
                        "carriers": carrier_filter["carriers"],
                        "matched_carriers": carrier_filter.get("matched_carriers", []),
                        "missing_segments": carrier_filter.get("missing_segments", []),
                    }
                )
            continue
        risk = apply_carrier_preferences(validation["risk"], segments, policy)
        ranked.append(
            {
                "id": candidate_id,
                "ok": validation["ok"],
                "price": item["price"],
                "currency": currency_value(raw_candidate),
                "elapsed_min": risk["elapsed_min"],
                "carriers": carrier_filter["carriers"],
                "journeys": validation.get("journeys"),
                "risk": {
                    "profile": risk["profile"],
                    "score": risk["score"],
                    "grade": risk["grade"],
                    "reject": risk["reject"],
                    "rank_key": risk["rank_key"],
                    "top_reasons": risk["components"][: args.max_reasons],
                },
                "validation_summary": validation["summary"],
                "connections": validation["connections"],
            }
        )

    ranked.sort(key=lambda item: item["risk"]["rank_key"])
    for position, item in enumerate(ranked, 1):
        item["rank"] = position

    stop_policy_summary_payload = stop_policy_summary(stop_policy, stop_diagnostics if stop_policy_diagnostics_requested else None)
    if not stop_policy_diagnostics_requested:
        stop_diagnostics["garbage_options_hidden_from_answer"] = bool(not stop_policy.suppress_three_plus)

    return {
        "profile": profile,
        "profile_description": RISK_PROFILES[profile]["description"],
        "rank_order": RISK_PROFILES[profile]["rank_order"],
        "stop_policy": stop_policy_summary_payload,
        "stop_policy_diagnostics": stop_diagnostics,
        "count": len(ranked),
        "carrier_policy": {
            **carrier_policy_output(policy),
            "filtered_count": len(candidates) - len(ranked),
            "filtered": filtered,
        },
        "ranked": ranked,
    }
