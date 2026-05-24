from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..errors import CliError

USER_ANSWER_SCHEMA_VERSION = "flight_search_user_answer.v1"
USER_ANSWER_SCHEMA_RESOURCE = "flight_search_user_answer.v1.schema.json"
USER_ANSWER_SCHEMA_PACKAGE = "flights_cli.contracts"


@lru_cache(maxsize=1)
def load_user_answer_schema() -> dict[str, Any]:
    text = resources.files(USER_ANSWER_SCHEMA_PACKAGE).joinpath(USER_ANSWER_SCHEMA_RESOURCE).read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def user_answer_validator() -> Draft202012Validator:
    return Draft202012Validator(load_user_answer_schema())


def validation_error_detail(error: ValidationError) -> dict[str, Any]:
    path = "$"
    if error.absolute_path:
        path += "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
    return {"path": path, "message": error.message, "validator": error.validator}


def requested_round_trip(route: dict[str, Any]) -> bool:
    dates = route.get("dates") if isinstance(route.get("dates"), dict) else {}
    return bool(dates.get("return") or dates.get("return_date"))


def is_provider_aggregate_option(option: dict[str, Any]) -> bool:
    return str(option.get("category") or "") == "provider_aggregate_candidate" or str(option.get("id") or "").startswith("provider-aggregate:")


def option_direction(option: dict[str, Any]) -> str | None:
    direction = option.get("direction")
    if direction in ("outbound", "return"):
        return str(direction)
    option_id = str(option.get("id") or "")
    if option_id.startswith("provider-aggregate:outbound:"):
        return "outbound"
    if option_id.startswith("provider-aggregate:return:"):
        return "return"
    segments = option.get("segments") if isinstance(option.get("segments"), list) else []
    segment_directions = {str(segment.get("direction")) for segment in segments if isinstance(segment, dict) and segment.get("direction")}
    if len(segment_directions) == 1:
        only = next(iter(segment_directions))
        if only in ("outbound", "return"):
            return only
    return None


def route_label(option: dict[str, Any]) -> str:
    segments = option.get("segments") if isinstance(option.get("segments"), list) else []
    if segments:
        first = next((segment for segment in segments if isinstance(segment, dict)), None)
        last = next((segment for segment in reversed(segments) if isinstance(segment, dict)), None)
        if first and last and first.get("origin") and last.get("destination"):
            return f" {first.get('origin')}→{last.get('destination')}"
    return ""


def infer_journey_scope(option: dict[str, Any], *, is_round_trip_request: bool) -> str:
    explicit = option.get("journey_scope")
    if explicit == "two_one_way_pair":
        return "two_one_way_pair"
    direction = option_direction(option)
    if is_provider_aggregate_option(option):
        if is_round_trip_request:
            return "return_only" if direction == "return" else "outbound_only"
        return "one_way"
    if is_round_trip_request:
        return "round_trip"
    return "one_way"


def default_label(option: dict[str, Any], *, journey_scope: str, direction: str | None) -> str:
    price = str(option.get("price_text") or "price n/a")
    route = route_label(option)
    if journey_scope == "outbound_only":
        return f"One-way outbound alternative{route}: {price}. Does not cover requested round trip."
    if journey_scope == "return_only":
        return f"One-way return alternative{route}: {price}. Does not cover requested round trip."
    if journey_scope == "two_one_way_pair":
        return f"Two separate one-way offers{route}: {price}."
    if journey_scope == "round_trip":
        return f"Round-trip alternative{route}: {price}."
    if direction == "return":
        return f"One-way return alternative{route}: {price}."
    return f"One-way alternative{route}: {price}."


def default_disclaimer(option: dict[str, Any], *, journey_scope: str) -> str | None:
    if journey_scope == "two_one_way_pair":
        return (
            "Two separate one-way offers; not proven as a single PNR, protected round-trip, "
            "baggage-through itinerary, through fare, or final fare. Sum of displayed one-way prices "
            "is arithmetic only, not booking-screen proof; verify ticketing, baggage, refund, and disruption protection on the booking screen."
        )
    if is_provider_aggregate_option(option):
        return "Provider aggregate offer; ticketing/protection, baggage handling, fare rules, and final fare require booking-screen verification."
    return None


def option_summary(option: dict[str, Any] | None, *, is_round_trip_request: bool = False) -> dict[str, Any] | None:
    if not isinstance(option, dict):
        return None
    risk = option.get("risk") if isinstance(option.get("risk"), dict) else {}
    segments = option.get("segments") if isinstance(option.get("segments"), list) else []
    max_connections = int(option.get("max_connections_per_journey") if option.get("max_connections_per_journey") is not None else max(0, len(segments) - 1))
    journey_scope = infer_journey_scope(option, is_round_trip_request=is_round_trip_request)
    direction = option_direction(option)
    provider_aggregate = is_provider_aggregate_option(option)
    covers_requested_trip = option.get("covers_requested_trip")
    if not isinstance(covers_requested_trip, bool):
        covers_requested_trip = journey_scope in ("one_way", "round_trip", "two_one_way_pair")
    directional_only = option.get("directional_only")
    if not isinstance(directional_only, bool):
        directional_only = provider_aggregate and journey_scope in ("one_way", "outbound_only", "return_only")
    composed_of_directional_offers = bool(option.get("composed_of_directional_offers"))
    ticketing_model = str(option.get("ticketing_model") or ("provider_aggregate" if provider_aggregate else "separate_segments"))
    user_facing_label = str(option.get("user_facing_label") or option.get("label") or default_label(option, journey_scope=journey_scope, direction=direction))
    disclaimer = option.get("disclaimer") or default_disclaimer(option, journey_scope=journey_scope)
    summary = {
        "id": option.get("id"),
        "category": option.get("category"),
        "price_text": str(option.get("price_text") or "price n/a"),
        "elapsed": option.get("elapsed"),
        "risk_grade": risk.get("grade"),
        "segment_count": len(segments),
        "stop_tier": option.get("stop_tier"),
        "max_connections_per_journey": max_connections,
        "journey_scope": journey_scope,
        "covers_requested_trip": covers_requested_trip,
        "direction": direction,
        "directional_only": directional_only,
        "composed_of_directional_offers": composed_of_directional_offers,
        "ticketing_model": ticketing_model,
        "user_facing_label": user_facing_label,
    }
    for key in ("itinerary_elapsed_min", "flight_time_min", "layover_total_min"):
        if key in option:
            summary[key] = option.get(key)
    for key in ("outbound_time", "return_time"):
        value = option.get(key)
        if isinstance(value, dict):
            summary[key] = {
                "itinerary_elapsed_min": value.get("itinerary_elapsed_min"),
                "flight_time_min": value.get("flight_time_min"),
                "layover_total_min": value.get("layover_total_min"),
            }
    if disclaimer:
        summary["disclaimer"] = str(disclaimer)
    return summary


def is_two_one_way_pair_option(option: dict[str, Any]) -> bool:
    return option.get("journey_scope") == "two_one_way_pair" or option.get("composed_of_directional_offers") is True


def priority_options_for_user_contract(priority: list[Any], *, limit: int = 5) -> list[dict[str, Any]]:
    dict_priority = [item for item in priority if isinstance(item, dict)]
    selected = dict_priority[: max(0, limit)]
    pair = next((item for item in dict_priority if is_two_one_way_pair_option(item)), None)
    if pair is not None and all(item.get("id") != pair.get("id") for item in selected):
        selected.append(pair)
    return selected


def build_user_answer_contract(agent_report: dict[str, Any]) -> dict[str, Any]:
    diagnostics = agent_report.get("coverage_diagnostics") if isinstance(agent_report.get("coverage_diagnostics"), dict) else {}
    completeness = diagnostics.get("completeness") if isinstance(diagnostics.get("completeness"), dict) else {}
    not_executed = diagnostics.get("not_executed_controls") if isinstance(diagnostics.get("not_executed_controls"), list) else []
    provider_failures = agent_report.get("provider_failures") if isinstance(agent_report.get("provider_failures"), list) else []
    through_fare_checks = agent_report.get("through_fare_checks") if isinstance(agent_report.get("through_fare_checks"), list) else []
    answer_lines = [str(line) for line in agent_report.get("answer_lines") or [] if str(line)]
    answer_text = "\n".join(answer_lines).lower()
    recommended = agent_report.get("recommended_options") if isinstance(agent_report.get("recommended_options"), list) else []
    priority = agent_report.get("priority_options") if isinstance(agent_report.get("priority_options"), list) else []
    route = agent_report.get("route") if isinstance(agent_report.get("route"), dict) else {}
    stop_policy = agent_report.get("stop_policy") if isinstance(agent_report.get("stop_policy"), dict) else {}
    stop_diagnostics = agent_report.get("stop_policy_diagnostics") if isinstance(agent_report.get("stop_policy_diagnostics"), dict) else {}
    two_stop_fallback_used = bool(stop_diagnostics.get("used_two_stop_fallback"))

    is_round_trip_request = requested_round_trip(route)

    return {
        "schema_version": USER_ANSWER_SCHEMA_VERSION,
        "route": {
            "origin": route.get("origin"),
            "destination": route.get("destination"),
            "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
        },
        "primary_recommendation": option_summary(recommended[0] if recommended else None, is_round_trip_request=is_round_trip_request),
        "alternatives": [
            summary
            for summary in (
                option_summary(item, is_round_trip_request=is_round_trip_request)
                for item in priority_options_for_user_contract(priority, limit=5)
            )
            if summary is not None
        ],
        "stop_policy_status": {
            "policy": str(stop_policy.get("name") or stop_diagnostics.get("policy") or "business_default"),
            "max_reported_connections": 2 if two_stop_fallback_used else int(stop_policy.get("preferred_max_connections") or 1),
            "two_stop_fallback_used": two_stop_fallback_used,
            "three_plus_suppressed_count": int(stop_diagnostics.get("three_plus_suppressed_count") or 0),
            "garbage_options_suppressed": bool(stop_diagnostics.get("garbage_options_hidden_from_answer")),
        },
        "evidence_status": {
            "coverage_complete": bool(completeness.get("all_planned_controls_have_terminal_state")),
            "planned_control_count": int(completeness.get("planned_count") or 0),
            "terminal_control_count": int(completeness.get("terminal_count") or 0),
            "not_executed_control_count": len(not_executed),
            "provider_failure_count": len(provider_failures),
            "through_fare_check_count": len(through_fare_checks),
        },
        "required_caveats": {
            "source_boundaries_included": bool(agent_report.get("source_boundaries")) and "do not treat" in answer_text,
            "coverage_incompleteness_acknowledged": not bool(not_executed) or "coverage is incomplete" in answer_text or "not_executed" in answer_text,
            "provider_failures_acknowledged": not bool(provider_failures) or "provider failure" in answer_text or "failed" in answer_text,
            "through_fare_verification_required": not bool(through_fare_checks) or "through-fare" in answer_text or "through fare" in answer_text,
            "purchase_screen_verification_required": "booking screen" in answer_text or "purchase-screen" in answer_text or "final fare" in answer_text,
        },
        "answer_lines": answer_lines,
    }


def summary_label_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("user_facing_label", "label", "disclaimer", "ticketing_note")
    ).lower()


def has_two_one_way_phrase(text: str) -> bool:
    return "two separate one-way offers" in text or "2 separate one-way offers" in text


def normalized_ticketing_claim_text(text: str) -> str:
    normalized = text.lower().replace("single-pnr", "single pnr").replace("through-fare", "through fare")
    return re.sub(r"\s+", " ", normalized)


def has_unproven_ticketing_claim(text: str) -> bool:
    normalized = normalized_ticketing_claim_text(text)
    claim_terms = (
        "single pnr",
        "protected round-trip",
        "protected round trip",
        "baggage-through",
        "baggage through",
        "through fare",
    )
    allowed_markers = (
        "not proven",
        "not a ",
        "not an ",
        "not proof",
        "no proof",
        "does not prove",
        "do not treat",
        "verify",
        "unknown",
    )
    for sentence in re.split(r"[.;\n]+", normalized):
        if not any(term in sentence for term in claim_terms):
            continue
        if any(marker in sentence for marker in allowed_markers):
            continue
        return True
    return False


def label_text(item: dict[str, Any]) -> str:
    return str(item.get("user_facing_label") or item.get("label") or "")


def normalized_time_label(item: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", label_text(item).lower().replace("wall-clock", "wall clock"))


def has_ambiguous_provider_time_wording(item: dict[str, Any]) -> bool:
    text = normalized_time_label(item)
    if re.search(r"\b(duration|elapsed)\b", text):
        return True
    forbidden_phrases = ("total journey time", "total time", "wall clock", "без пересадок", "nonstop")
    if any(phrase in text for phrase in forbidden_phrases):
        return True
    if re.search(r"\bdirect\b", text):
        return True
    return False


def has_travel_time_without_itinerary_elapsed(item: dict[str, Any]) -> bool:
    return "travel time" in normalized_time_label(item) and item.get("itinerary_elapsed_min") is None


def has_combined_pair_time_fields(item: dict[str, Any]) -> bool:
    return any(item.get(key) is not None for key in ("itinerary_elapsed_min", "flight_time_min", "layover_total_min"))


def semantic_errors(answer: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    evidence = answer.get("evidence_status") if isinstance(answer.get("evidence_status"), dict) else {}
    caveats = answer.get("required_caveats") if isinstance(answer.get("required_caveats"), dict) else {}
    stop_status = answer.get("stop_policy_status") if isinstance(answer.get("stop_policy_status"), dict) else {}
    route = answer.get("route") if isinstance(answer.get("route"), dict) else {}
    is_round_trip_request = requested_round_trip(route)
    summary_entries: list[tuple[str, dict[str, Any]]] = []
    primary = answer.get("primary_recommendation")
    if isinstance(primary, dict):
        summary_entries.append(("$.primary_recommendation", primary))
    for index, item in enumerate(answer.get("alternatives") or []):
        if isinstance(item, dict):
            summary_entries.append((f"$.alternatives[{index}]", item))
    summaries = [item for _, item in summary_entries]

    for path, item in summary_entries:
        provider_aggregate = is_provider_aggregate_option(item)
        if not provider_aggregate:
            continue
        scope = item.get("journey_scope")
        if has_ambiguous_provider_time_wording(item):
            errors.append(
                {
                    "path": f"{path}.user_facing_label",
                    "message": "provider aggregate user-facing time wording must not use ambiguous duration/elapsed/total time/wall-clock/direct claims",
                    "validator": "semantic",
                }
            )
        if scope == "two_one_way_pair":
            if has_combined_pair_time_fields(item):
                errors.append(
                    {
                        "path": f"{path}.itinerary_elapsed_min",
                        "message": "two_one_way_pair must not set combined itinerary_elapsed_min/flight_time_min/layover_total_min fields",
                        "validator": "semantic",
                    }
                )
        elif has_travel_time_without_itinerary_elapsed(item):
            errors.append(
                {
                    "path": f"{path}.user_facing_label",
                    "message": "provider aggregate label may say Travel time only when itinerary_elapsed_min is known; use Flight time, not including layover time otherwise",
                    "validator": "semantic",
                }
            )

    if evidence.get("planned_control_count") != evidence.get("terminal_control_count") and evidence.get("coverage_complete"):
        errors.append({"path": "$.evidence_status.coverage_complete", "message": "coverage_complete cannot be true when planned and terminal counts differ", "validator": "semantic"})
    if int(evidence.get("not_executed_control_count") or 0) > 0 and caveats.get("coverage_incompleteness_acknowledged") is not True:
        errors.append({"path": "$.required_caveats.coverage_incompleteness_acknowledged", "message": "final answer must acknowledge incomplete coverage when controls are not_executed", "validator": "semantic"})
    if int(evidence.get("provider_failure_count") or 0) > 0 and caveats.get("provider_failures_acknowledged") is not True:
        errors.append({"path": "$.required_caveats.provider_failures_acknowledged", "message": "final answer must acknowledge provider failures", "validator": "semantic"})
    if int(evidence.get("through_fare_check_count") or 0) > 0 and caveats.get("through_fare_verification_required") is not True:
        errors.append({"path": "$.required_caveats.through_fare_verification_required", "message": "final answer must require through-fare verification", "validator": "semantic"})
    if caveats.get("source_boundaries_included") is not True:
        errors.append({"path": "$.required_caveats.source_boundaries_included", "message": "final answer must include source-boundary caveats", "validator": "semantic"})
    if caveats.get("purchase_screen_verification_required") is not True:
        errors.append({"path": "$.required_caveats.purchase_screen_verification_required", "message": "final answer must require booking or purchase-screen verification", "validator": "semantic"})
    if any(item.get("stop_tier") == "T3_THREE_PLUS" or int(item.get("max_connections_per_journey") or 0) >= 3 for item in summaries):
        errors.append({"path": "$.primary_recommendation", "message": "final answer must not report three-plus-connection options", "validator": "semantic"})
    if any(item.get("stop_tier") == "T2_TWO_STOP" or int(item.get("max_connections_per_journey") or 0) == 2 for item in summaries):
        if stop_status.get("two_stop_fallback_used") is not True:
            errors.append({"path": "$.alternatives", "message": "two-stop options require explicit two-stop fallback status", "validator": "semantic"})
    if is_round_trip_request:
        for path, item in summary_entries:
            item_id = str(item.get("id") or "")
            scope = item.get("journey_scope")
            direction = option_direction(item)
            text = summary_label_text(item)
            provider_aggregate = is_provider_aggregate_option(item)
            if provider_aggregate and direction in ("outbound", "return"):
                expected_scope = "return_only" if direction == "return" else "outbound_only"
                expected_label = "one-way return" if direction == "return" else "one-way outbound"
                if scope != expected_scope:
                    errors.append(
                        {
                            "path": f"{path}.journey_scope",
                            "message": f"round-trip {direction} provider aggregate alternative must use journey_scope={expected_scope}, not {scope!r}",
                            "validator": "semantic",
                        }
                    )
                if item.get("covers_requested_trip") is not False:
                    errors.append(
                        {
                            "path": f"{path}.covers_requested_trip",
                            "message": f"round-trip {direction} provider aggregate alternative must set covers_requested_trip=false",
                            "validator": "semantic",
                        }
                    )
                if item.get("directional_only") is not True:
                    errors.append(
                        {
                            "path": f"{path}.directional_only",
                            "message": f"round-trip {direction} provider aggregate alternative must set directional_only=true",
                            "validator": "semantic",
                        }
                    )
                if expected_label not in text:
                    errors.append(
                        {
                            "path": f"{path}.user_facing_label",
                            "message": f"round-trip {direction} provider aggregate alternative must include an explicit {expected_label} label",
                            "validator": "semantic",
                        }
                    )
                if item_id.startswith("provider-aggregate:") and scope == "round_trip":
                    errors.append(
                        {
                            "path": f"{path}.journey_scope",
                            "message": f"provider aggregate {direction} one-way offer cannot be labeled as journey_scope=round_trip",
                            "validator": "semantic",
                        }
                    )
            if scope == "two_one_way_pair" or item.get("composed_of_directional_offers") is True:
                if scope != "two_one_way_pair":
                    errors.append(
                        {
                            "path": f"{path}.journey_scope",
                            "message": "two separate one-way offers pair must use journey_scope=two_one_way_pair",
                            "validator": "semantic",
                        }
                    )
                if item.get("covers_requested_trip") is not True:
                    errors.append(
                        {
                            "path": f"{path}.covers_requested_trip",
                            "message": "two separate one-way offers pair must set covers_requested_trip=true",
                            "validator": "semantic",
                        }
                    )
                if item.get("direction") is not None:
                    errors.append(
                        {
                            "path": f"{path}.direction",
                            "message": "two separate one-way offers pair must set direction=null",
                            "validator": "semantic",
                        }
                    )
                if item.get("directional_only") is not False:
                    errors.append(
                        {
                            "path": f"{path}.directional_only",
                            "message": "two separate one-way offers pair must set directional_only=false",
                            "validator": "semantic",
                        }
                    )
                if item.get("composed_of_directional_offers") is not True:
                    errors.append(
                        {
                            "path": f"{path}.composed_of_directional_offers",
                            "message": "two separate one-way offers pair must set composed_of_directional_offers=true",
                            "validator": "semantic",
                        }
                    )
                if item.get("ticketing_model") != "separate_one_way_offers":
                    errors.append(
                        {
                            "path": f"{path}.ticketing_model",
                            "message": "two separate one-way offers pair must set ticketing_model=separate_one_way_offers",
                            "validator": "semantic",
                        }
                    )
                if not has_two_one_way_phrase(text):
                    errors.append(
                        {
                            "path": f"{path}.disclaimer",
                            "message": "two_one_way_pair alternatives must label/disclaim that they are two separate one-way offers",
                            "validator": "semantic",
                        }
                    )
                if has_unproven_ticketing_claim(text):
                    errors.append(
                        {
                            "path": f"{path}.disclaimer",
                            "message": "two_one_way_pair must not claim single PNR, protected round-trip, baggage-through, or through fare without proof",
                            "validator": "semantic",
                        }
                    )
    return errors


def validate_user_answer_contract(answer: dict[str, Any]) -> None:
    errors = sorted(user_answer_validator().iter_errors(answer), key=lambda item: list(item.absolute_path))
    details = [validation_error_detail(error) for error in errors]
    details.extend(semantic_errors(answer))
    if details:
        raise CliError(
            "flight_search_user_answer failed contract validation",
            error_type="contract_error",
            details={"schema_version": answer.get("schema_version"), "errors": details},
        )
