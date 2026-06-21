from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import RISK_PROFILES
from ..domain.carriers import itinerary_carriers, segment_carriers
from ..domain.normalize import clamp_score, currency_value, is_reject_score, normalize_carrier_codes, normalize_profile, risk_grade
from ..domain.stop_policy import (
    StopPolicyOptions,
    decide_stop_policy,
    reportable_max_connections,
    stop_policy_from_options,
    stop_policy_options_from_args,
    stop_policy_payload,
)
from ..services.validation import ItineraryValidationOptions, rank_key, validate_itinerary
from ..errors import CliError

@dataclass(frozen=True, slots=True)
class CarrierPolicyOptions:
    only_carriers: tuple[str, ...] = ()
    exclude_carriers: tuple[str, ...] = ()
    prefer_carriers: tuple[str, ...] = ()
    avoid_carriers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RankingOptions:
    profile: str = "balanced"
    ticketing: str = "separate"
    min_same_airport_min: int = 120
    min_cross_airport_min: int = 300
    max_reasons: int = 5
    include_filtered: int = 20
    carrier_policy: CarrierPolicyOptions = CarrierPolicyOptions()
    stop_policy: StopPolicyOptions = StopPolicyOptions()


def _str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if str(item))
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item))
    return (str(value),) if str(value) else ()


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


def carrier_policy_options_from_args(args: Any) -> CarrierPolicyOptions:
    return CarrierPolicyOptions(
        only_carriers=_str_tuple(getattr(args, "only_carrier", None)),
        exclude_carriers=_str_tuple(getattr(args, "exclude_carrier", None)),
        prefer_carriers=_str_tuple(getattr(args, "prefer_carrier", None)),
        avoid_carriers=_str_tuple(getattr(args, "avoid_carrier", None)),
    )


def ranking_options_from_args(args: Any) -> RankingOptions:
    return RankingOptions(
        profile=str(getattr(args, "profile", "balanced") or "balanced"),
        ticketing=str(getattr(args, "ticketing", "separate") or "separate"),
        min_same_airport_min=int(getattr(args, "min_same_airport_min", 120)),
        min_cross_airport_min=int(getattr(args, "min_cross_airport_min", 300)),
        max_reasons=int(getattr(args, "max_reasons", 5)),
        include_filtered=int(getattr(args, "include_filtered", 20)),
        carrier_policy=carrier_policy_options_from_args(args),
        stop_policy=stop_policy_options_from_args(args),
    )


def carrier_policy_from_options(options: CarrierPolicyOptions) -> dict[str, set[str]]:
    return {
        "only": normalize_carrier_codes(options.only_carriers, "only-carrier"),
        "exclude": normalize_carrier_codes(options.exclude_carriers, "exclude-carrier"),
        "prefer": normalize_carrier_codes(options.prefer_carriers, "prefer-carrier"),
        "avoid": normalize_carrier_codes(options.avoid_carriers, "avoid-carrier"),
    }


def carrier_policy_from_args(args: Any) -> dict[str, set[str]]:
    return carrier_policy_from_options(carrier_policy_options_from_args(args))


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


def rank_candidate_list(candidates: list[dict[str, Any]], options: RankingOptions) -> dict[str, Any]:
    profile = normalize_profile(options.profile)
    policy = carrier_policy_from_options(options.carrier_policy)
    stop_policy = stop_policy_from_options(options.stop_policy)
    evaluated: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    include_filtered = max(0, int(options.include_filtered))
    for index, candidate in enumerate(candidates):
        validation_options = ItineraryValidationOptions(
            ticketing=str(candidate.get("ticketing") or options.ticketing),
            min_same_airport_min=options.min_same_airport_min,
            min_cross_airport_min=options.min_cross_airport_min,
            profile=profile,
        )
        validation = validate_itinerary(candidate, validation_options)
        carrier_filter = carrier_filter_result(validation["segments"], policy)
        candidate_id = candidate.get("id") or candidate.get("name") or f"candidate-{index + 1}"
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
        evaluated.append(
            {
                "candidate_id": candidate_id,
                "candidate": candidate,
                "validation": validation,
                "carrier_filter": carrier_filter,
            }
        )

    preferred_available = any(
        bool(item["validation"].get("ok"))
        and int((item["validation"].get("summary") or {}).get("max_connections_per_journey") or 0) <= stop_policy.preferred_max_connections
        for item in evaluated
    )
    allowed_max_connections = reportable_max_connections(stop_policy, preferred_available)
    ranked: list[dict[str, Any]] = []
    stop_filtered_count = 0
    suppressed_three_plus_count = 0
    suppressed_two_stop_count = 0
    preferred_candidate_count = 0
    two_stop_candidate_count = 0
    for item in evaluated:
        validation = item["validation"]
        summary = validation.get("summary") or {}
        max_connections = int(summary.get("max_connections_per_journey") or 0)
        stop_tier = str(summary.get("stop_tier") or "")
        if max_connections <= stop_policy.preferred_max_connections:
            preferred_candidate_count += 1
        if max_connections == 2:
            two_stop_candidate_count += 1
        decision = decide_stop_policy(summary, stop_policy, preferred_available=preferred_available)
        if not decision.reportable_by_stop_policy:
            stop_filtered_count += 1
            if max_connections >= 3:
                suppressed_three_plus_count += 1
            elif max_connections == 2 and preferred_available:
                suppressed_two_stop_count += 1
            if len(filtered) < include_filtered:
                filtered.append(
                    {
                        "id": item["candidate_id"],
                        "reason": "stop_policy",
                        "message": f"Candidate suppressed by stop policy: {stop_tier} ({decision.reason}).",
                        "max_connections_per_journey": max_connections,
                        "stop_tier": stop_tier,
                        "stop_policy_decision": decision.to_dict(),
                    }
                )
            continue
        carrier_filter = item["carrier_filter"]
        risk = apply_carrier_preferences(validation["risk"], validation["segments"], policy)
        ranked.append(
            {
                "id": item["candidate_id"],
                "ok": validation["ok"],
                "price": risk["price"],
                "currency": currency_value(item["candidate"]),
                "elapsed_min": risk["elapsed_min"],
                "carriers": carrier_filter["carriers"],
                "journeys": validation.get("journeys"),
                "risk": {
                    "profile": risk["profile"],
                    "score": risk["score"],
                    "grade": risk["grade"],
                    "reject": risk["reject"],
                    "rank_key": risk["rank_key"],
                    "top_reasons": risk["components"][: options.max_reasons],
                },
                "validation_summary": validation["summary"],
                "connections": validation["connections"],
            }
        )

    ranked.sort(key=lambda item: item["risk"]["rank_key"])
    for position, item in enumerate(ranked, 1):
        item["rank"] = position

    return {
        "profile": profile,
        "profile_description": RISK_PROFILES[profile]["description"],
        "rank_order": RISK_PROFILES[profile]["rank_order"],
        "count": len(ranked),
        "carrier_policy": {
            **carrier_policy_output(policy),
            "filtered_count": len(candidates) - len(ranked),
            "filtered": filtered,
        },
        "stop_policy": stop_policy_payload(stop_policy),
        "stop_policy_diagnostics": {
            "policy": stop_policy.name,
            "preferred_max_connections": stop_policy.preferred_max_connections,
            "tier2_max_connections": stop_policy.tier2_max_connections,
            "hard_max_connections": stop_policy.hard_max_connections,
            "preferred_candidate_count": preferred_candidate_count,
            "two_stop_candidate_count": two_stop_candidate_count,
            "eligible_preferred_count": preferred_candidate_count,
            "eligible_tier2_count": two_stop_candidate_count,
            "used_two_stop_tier": not preferred_available and two_stop_candidate_count > 0,
            "used_tier2_two_stop": not preferred_available and two_stop_candidate_count > 0,
            "three_plus_suppressed_count": suppressed_three_plus_count,
            "suppressed_three_plus_count": suppressed_three_plus_count,
            "two_stop_suppressed_because_preferred_exists": suppressed_two_stop_count,
            "suppressed_two_stop_because_preferred_exists": suppressed_two_stop_count,
            "stop_policy_filtered_count": stop_filtered_count,
            "garbage_options_hidden_from_answer": suppressed_three_plus_count > 0,
            "allowed_max_connections": allowed_max_connections,
        },
        "ranked": ranked,
    }
