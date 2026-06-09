from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

from ..contracts.registry import current_contract
from ..contracts.schema_errors import validation_error_detail

from ..errors import CliError
from .projections.human_answer_mirror import build_human_answer_mirror
from .option_semantics import direction_segments, option_direction, route_requested_round_trip
from .time_utils import display_minutes_between as minutes_between_iso, integer_or_none as int_or_none

_USER_ANSWER_CONTRACT = current_contract("user_answer")
USER_ANSWER_SCHEMA_VERSION = _USER_ANSWER_CONTRACT["schema_version"]
USER_ANSWER_SCHEMA_RESOURCE = _USER_ANSWER_CONTRACT["schema_resource"]
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


def is_provider_aggregate_option(option: dict[str, Any]) -> bool:
    return str(option.get("category") or "") == "provider_aggregate_candidate" or str(option.get("id") or "").startswith("provider-aggregate:")


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
    explicit_max_connections = option.get("max_connections_per_journey")
    if explicit_max_connections is not None:
        max_connections = int(explicit_max_connections)
    else:
        direction_counts = [
            sum(1 for segment in segments if isinstance(segment, dict) and segment.get("direction") == direction)
            for direction in ("outbound", "return")
        ]
        max_direction_segments = max(direction_counts) if any(direction_counts) else len(segments)
        max_connections = max(0, max_direction_segments - 1)
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


def numeric_or_none(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def compact_price_text(option: dict[str, Any]) -> str:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    amount = numeric_or_none(price.get("amount"))
    currency = str(price.get("currency") or "").upper()
    if amount is not None:
        rendered = f"{int(amount):,}".replace(",", " ") if float(amount).is_integer() else str(amount)
        if currency == "RUB":
            return f"{rendered} ₽"
        if currency:
            return f"{rendered} {currency}"
        return rendered
    raw = str(option.get("price_text") or "").strip()
    return re.sub(r"\bRUB\b", "₽", raw, flags=re.IGNORECASE) if raw else "цена н/д"


def price_contract(option: dict[str, Any]) -> dict[str, Any]:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    source = "provider_aggregate" if is_provider_aggregate_option(option) else "live_provider"
    confidence = "medium" if is_provider_aggregate_option(option) else "high"
    return {
        "amount": numeric_or_none(price.get("amount")),
        "currency": str(price.get("currency") or "").upper() or None,
        "display": compact_price_text(option),
        "source": source,
        "confidence": confidence,
    }


def baggage_piece_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    if value.get("count") is not None:
        parts.append(f"{value.get('count')}pc")
    if value.get("weight") is not None:
        parts.append(f"{value.get('weight')}kg")
    if value.get("text"):
        parts.append(str(value.get("text")))
    return "/".join(parts) if parts else None


def baggage_contract(option: dict[str, Any]) -> dict[str, str]:
    checked = baggage_piece_text(option.get("baggage"))
    cabin = baggage_piece_text(option.get("hand_luggage") or option.get("cabin_baggage"))
    source = "provider_offer" if checked or cabin else "unknown"
    confidence = "medium" if checked or cabin else "unknown"
    return {
        "checked": checked or "unknown",
        "cabin": cabin or "unknown",
        "source": source,
        "confidence": confidence,
    }


def protection_contract(option: dict[str, Any]) -> dict[str, Any]:
    ticketing_model = str(option.get("ticketing_model") or ("provider_aggregate" if is_provider_aggregate_option(option) else "separate_segments"))
    if ticketing_model == "single_ticket_proven":
        return {
            "single_pnr_status": "proven",
            "through_baggage_status": "proven",
            "self_transfer": False,
            "purchase_screen_verification_required": False,
        }
    if ticketing_model in ("separate_segments", "separate_one_way_offers"):
        return {
            "single_pnr_status": "unproven",
            "through_baggage_status": "unproven",
            "self_transfer": True,
            "purchase_screen_verification_required": True,
        }
    return {
        "single_pnr_status": "unknown",
        "through_baggage_status": "unknown",
        "self_transfer": None,
        "purchase_screen_verification_required": True,
    }


def catalog_segment(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": str(segment.get("flight_number") or segment.get("carrier") or "") or None,
        "carrier": str(segment.get("carrier") or segment.get("marketing_carrier") or "") or None,
        "origin": str(segment.get("origin") or "") or None,
        "destination": str(segment.get("destination") or "") or None,
        "departure_at": str(segment.get("departure_at") or "") or None,
        "arrival_at": str(segment.get("arrival_at") or "") or None,
        "duration_min": int_or_none(segment.get("duration_min")),
    }


def direction_layovers(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layovers: list[dict[str, Any]] = []
    for previous, current in zip(segments, segments[1:]):
        layovers.append(
            {
                "airport": previous.get("destination") or current.get("origin"),
                "duration_min": minutes_between_iso(previous.get("arrival_at"), current.get("departure_at")),
            }
        )
    return layovers


def direction_elapsed(option: dict[str, Any], direction: str, segments: list[dict[str, Any]]) -> int | None:
    key = "outbound_time" if direction == "outbound" else "return_time"
    value = option.get(key)
    if isinstance(value, dict):
        known = int_or_none(value.get("itinerary_elapsed_min"))
        if known is not None:
            return known
    if segments:
        return minutes_between_iso(segments[0].get("departure_at"), segments[-1].get("arrival_at"))
    return int_or_none(option.get("itinerary_elapsed_min") or option.get("elapsed_min"))


def direction_contract(option: dict[str, Any], direction: str) -> dict[str, Any] | None:
    segments = direction_segments(option, direction)
    if not segments and option_direction(option) not in (direction, None):
        return None
    if not segments and option.get("journey_scope") == "round_trip":
        return None
    detail_status = str(option.get("detail_status") or ("full" if segments else "summary_only"))
    if detail_status not in ("full", "summary_only", "missing"):
        detail_status = "summary_only"
    catalog_segments = [catalog_segment(segment) for segment in segments]
    return {
        "detail_status": detail_status if catalog_segments else "summary_only",
        "segments": catalog_segments,
        "layovers": direction_layovers(catalog_segments),
        "elapsed_min": direction_elapsed(option, direction, catalog_segments),
        "render_line": render_direction_for_catalog(catalog_segments, direction),
    }


def iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return value[:10]


def catalog_display_date(value: Any) -> str:
    date = iso_date(value)
    if not date:
        return "дата н/д"
    parts = date.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    return date


def catalog_display_time(value: Any) -> str:
    if not isinstance(value, str) or "T" not in value:
        return "??:??"
    return value.split("T", 1)[1][:5]


def render_direction_for_catalog(segments: list[dict[str, Any]], direction: str) -> str | None:
    if not segments:
        return None
    date = catalog_display_date(segments[0].get("departure_at"))
    flights = []
    for segment in segments:
        number = segment.get("flight_number") or segment.get("carrier") or "рейс"
        origin = segment.get("origin") or "???"
        destination = segment.get("destination") or "???"
        flights.append(f"{number} {origin}-{destination} {catalog_display_time(segment.get('departure_at'))}-{catalog_display_time(segment.get('arrival_at'))}")
    label = "туда" if direction == "outbound" else "обратно"
    return f"{date} {label}: " + " -> ".join(flights)


def risk_badges(option: dict[str, Any], *, ticketing_model: str, baggage: dict[str, str], protection: dict[str, Any]) -> list[str]:
    badges: list[str] = []
    if ticketing_model == "provider_aggregate":
        badges.append("provider_aggregate")
    if ticketing_model == "separate_one_way_offers":
        badges.append("separate_one_way_offers")
    if ticketing_model == "separate_segments":
        badges.append("separate_segments")
    if protection.get("single_pnr_status") != "proven":
        badges.append("single_pnr_unproven")
    if protection.get("through_baggage_status") != "proven":
        badges.append("through_baggage_unproven")
    if baggage.get("checked") == "unknown":
        badges.append("baggage_unknown")
    if option.get("directional_only") is True:
        badges.append("directional_only")
    if option.get("max_connections_per_journey") is not None and int(option.get("max_connections_per_journey") or 0) >= 2:
        badges.append("two_stop_or_more")
    return list(dict.fromkeys(badges))


def catalog_caveats(option: dict[str, Any], *, badges: list[str]) -> list[str]:
    caveats: list[str] = []
    disclaimer = option.get("disclaimer") or option.get("ticketing_note")
    if disclaimer:
        caveats.append(str(disclaimer))
    if "single_pnr_unproven" in badges:
        caveats.append("single PNR/protection not proven; verify on booking screen")
    if "baggage_unknown" in badges:
        caveats.append("baggage unknown until fare/package verification")
    return list(dict.fromkeys(caveats))


def catalog_item(option: dict[str, Any], *, number: int, is_round_trip_request: bool) -> dict[str, Any]:
    journey_scope = infer_journey_scope(option, is_round_trip_request=is_round_trip_request)
    ticketing_model = str(option.get("ticketing_model") or ("provider_aggregate" if is_provider_aggregate_option(option) else "separate_segments"))
    if ticketing_model not in ("single_ticket_proven", "provider_aggregate", "separate_one_way_offers", "separate_segments", "unknown"):
        ticketing_model = "unknown"
    baggage = baggage_contract(option)
    protection = protection_contract({**option, "ticketing_model": ticketing_model})
    badges = risk_badges(option, ticketing_model=ticketing_model, baggage=baggage, protection=protection)
    outbound = direction_contract(option, "outbound")
    inbound = direction_contract(option, "return")
    item: dict[str, Any] = {
        "number": number,
        "option_id": str(option.get("id") or f"option-{number}"),
        "covers_requested_trip": bool(option.get("covers_requested_trip") if isinstance(option.get("covers_requested_trip"), bool) else journey_scope in ("one_way", "round_trip", "two_one_way_pair")),
        "journey_scope": journey_scope,
        "ticketing_model": ticketing_model,
        "detail_status": str(option.get("detail_status") or ("full" if option.get("segments") else "summary_only")),
        "total_price": price_contract(option),
        "directions": {"outbound": outbound, "return": inbound},
        "baggage": baggage,
        "protection": protection,
        "risk": option.get("risk") if isinstance(option.get("risk"), dict) else {},
        "badges": badges,
        "caveats": catalog_caveats(option, badges=badges),
        "render_line": "",
        "evidence_refs": [],
    }
    item["render_line"] = render_catalog_item(item)
    return item


def catalog_options(recommended: list[Any], priority: list[Any], *, limit: int = 10) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for option in [*(recommended or []), *priority_options_for_user_contract(priority or [], limit=limit)]:
        if not isinstance(option, dict):
            continue
        option_id = str(option.get("id") or "")
        key = option_id or str(id(option))
        if key in seen:
            continue
        seen.add(key)
        selected.append(option)
        if len(selected) >= limit:
            break
    return selected


def infer_answer_mode(*, is_round_trip_request: bool, options: list[dict[str, Any]]) -> str:
    if not options:
        return "no_viable_options"
    if is_round_trip_request or len(options) > 1:
        return "catalog"
    return "recommendation"


def build_catalog_contract(recommended: list[Any], priority: list[Any], *, is_round_trip_request: bool) -> dict[str, Any]:
    options = catalog_options(recommended, priority, limit=10)
    return {
        "presentation": {"style": "numbered_compact", "language": "ru", "max_items": 10},
        "items": [catalog_item(option, number=index, is_round_trip_request=is_round_trip_request) for index, option in enumerate(options, start=1)],
    }


def render_catalog_item(item: dict[str, Any]) -> str:
    parts = [f"{item.get('number')}. {item['total_price']['display']}"]
    outbound = item.get("directions", {}).get("outbound") if isinstance(item.get("directions"), dict) else None
    inbound = item.get("directions", {}).get("return") if isinstance(item.get("directions"), dict) else None
    if isinstance(outbound, dict) and outbound.get("render_line"):
        parts.append(str(outbound["render_line"]))
    if isinstance(inbound, dict) and inbound.get("render_line"):
        parts.append(str(inbound["render_line"]))
    if item.get("badges"):
        parts.append("риски: " + ", ".join(str(value) for value in item["badges"][:4]))
    return " — ".join(parts)


def render_catalog_answer(route: dict[str, Any], catalog: dict[str, Any], *, caveat_context: dict[str, Any]) -> str:
    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    lines = [f"Нашёл варианты {origin}→{destination}."]
    lines.extend(str(item.get("render_line") or "") for item in catalog.get("items") or [] if isinstance(item, dict))
    negative_wording = str(caveat_context.get("negative_wording") or "").strip()
    checks: list[str] = [
        "Проверить перед покупкой: single PNR/багаж/through fare не доказаны; финальную цену, тариф, багаж и правила проверить на booking screen.",
        "Текущий live/provider результат не доказывает отсутствие through fare, прямого рейса или защищённого билета.",
    ]
    if negative_wording and negative_wording not in checks:
        checks.append(negative_wording)
    if caveat_context.get("not_executed"):
        checks.append("Coverage неполное: не все live-проверки выполнены.")
    if caveat_context.get("provider_failures"):
        checks.append("часть live-проверок упала — повторить, если это влияет на выбор.")
    lines.extend(checks)
    return "\n".join(line for line in lines if line)


def is_two_one_way_pair_option(option: dict[str, Any]) -> bool:
    return option.get("journey_scope") == "two_one_way_pair" or option.get("composed_of_directional_offers") is True


def priority_options_for_user_contract(priority: list[Any], *, limit: int = 5) -> list[dict[str, Any]]:
    dict_priority = [item for item in priority if isinstance(item, dict)]
    selected = dict_priority[: max(0, limit)]
    pair = next((item for item in dict_priority if is_two_one_way_pair_option(item)), None)
    if pair is not None and all(item.get("id") != pair.get("id") for item in selected):
        selected.append(pair)
    return selected


def rendered_answer_lines(rendered_text: str) -> list[str]:
    return [line.strip() for line in rendered_text.splitlines() if line.strip()]


def canonical_user_answer_text(agent_report: dict[str, Any], rendered_text: str | None = None) -> str:
    if rendered_text is not None and rendered_text.strip():
        return rendered_text.strip()
    generated: dict[str, Any] = build_human_answer_mirror(agent_report)
    generated_text = str(generated.get("text") or "").strip()
    if generated_text:
        return generated_text
    return "Нет пользовательского ответа."


def has_any_signal(text: str, signals: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in signals)


def build_user_answer(agent_report: dict[str, Any], *, rendered_text: str | None = None) -> dict[str, Any]:
    diagnostics_raw = agent_report.get("coverage_diagnostics")
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
    completeness = diagnostics.get("completeness") if isinstance(diagnostics.get("completeness"), dict) else {}
    not_executed_raw = diagnostics.get("not_executed_controls")
    not_executed = not_executed_raw if isinstance(not_executed_raw, list) else []
    not_supported_raw = diagnostics.get("not_supported_controls")
    not_supported = not_supported_raw if isinstance(not_supported_raw, list) else []
    provider_failures = agent_report.get("provider_failures") if isinstance(agent_report.get("provider_failures"), list) else []
    through_fare_checks = agent_report.get("through_fare_checks") if isinstance(agent_report.get("through_fare_checks"), list) else []
    recommended = agent_report.get("recommended_options") if isinstance(agent_report.get("recommended_options"), list) else []
    priority = agent_report.get("priority_options") if isinstance(agent_report.get("priority_options"), list) else []
    route = agent_report.get("route") if isinstance(agent_report.get("route"), dict) else {}
    stop_policy = agent_report.get("stop_policy") if isinstance(agent_report.get("stop_policy"), dict) else {}
    stop_diagnostics = agent_report.get("stop_policy_diagnostics") if isinstance(agent_report.get("stop_policy_diagnostics"), dict) else {}
    offer_graph_raw = agent_report.get("offer_graph")
    offer_graph: dict[str, Any] = offer_graph_raw if isinstance(offer_graph_raw, dict) else {}
    truth_language_raw = offer_graph.get("truth_language")
    truth_language: dict[str, Any] = truth_language_raw if isinstance(truth_language_raw, dict) else {}
    two_stop_fallback_used = bool(stop_diagnostics.get("used_two_stop_fallback"))

    is_round_trip_request = route_requested_round_trip(route)
    catalog = build_catalog_contract(recommended, priority, is_round_trip_request=is_round_trip_request)
    answer_mode = infer_answer_mode(is_round_trip_request=is_round_trip_request, options=catalog.get("items") or [])
    route_contract = {
        "origin": route.get("origin"),
        "destination": route.get("destination"),
        "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
    }
    if answer_mode == "catalog":
        answer_text = render_catalog_answer(
            route_contract,
            catalog,
            caveat_context={
                "not_executed": not_executed,
                "provider_failures": provider_failures,
                "negative_wording": truth_language.get("negative_wording"),
            },
        )
    else:
        answer_text = canonical_user_answer_text(agent_report, rendered_text)
    answer_lines = rendered_answer_lines(answer_text)
    answer_text_lower = answer_text.lower()

    return {
        "schema_version": USER_ANSWER_SCHEMA_VERSION,
        "answer_mode": answer_mode,
        "route": route_contract,
        "catalog": catalog,
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
            "not_supported_control_count": len(not_supported),
            "provider_failure_count": len(provider_failures),
            "through_fare_check_count": len(through_fare_checks),
        },
        "required_caveats": {
            "source_boundaries_included": not bool(agent_report.get("source_boundaries")) or has_any_signal(
                answer_text_lower,
                ("do not treat", "не доказывает", "не доказывают", "не доказательство", "not proof", "does not prove"),
            ),
            "coverage_incompleteness_acknowledged": not bool(not_executed) or has_any_signal(
                answer_text_lower,
                ("coverage is incomplete", "coverage непол", "not_executed", "не все live-проверки", "неполное"),
            ),
            "provider_failures_acknowledged": not bool(provider_failures) or has_any_signal(
                answer_text_lower,
                ("provider failure", "failed", "live-проверок упала", "live-проверки упали"),
            ),
            "through_fare_verification_required": not bool(through_fare_checks) or has_any_signal(
                answer_text_lower,
                ("through-fare", "through fare", "сквозн", "единый тариф"),
            ),
            "purchase_screen_verification_required": has_any_signal(
                answer_text_lower,
                ("booking screen", "purchase-screen", "purchase screen", "final fare", "финальн"),
            ),
        },
        "rendered_text": answer_text,
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


def user_answer_contract_semantic_errors(answer: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    evidence = answer.get("evidence_status") if isinstance(answer.get("evidence_status"), dict) else {}
    caveats = answer.get("required_caveats") if isinstance(answer.get("required_caveats"), dict) else {}
    stop_status = answer.get("stop_policy_status") if isinstance(answer.get("stop_policy_status"), dict) else {}
    route = answer.get("route") if isinstance(answer.get("route"), dict) else {}
    is_round_trip_request = route_requested_round_trip(route)
    summary_entries: list[tuple[str, dict[str, Any]]] = []
    primary = answer.get("primary_recommendation")
    if isinstance(primary, dict):
        summary_entries.append(("$.primary_recommendation", primary))
    for index, item in enumerate(answer.get("alternatives") or []):
        if isinstance(item, dict):
            summary_entries.append((f"$.alternatives[{index}]", item))
    summaries = [item for _, item in summary_entries]

    answer_mode = answer.get("answer_mode")
    catalog = answer.get("catalog") if isinstance(answer.get("catalog"), dict) else {}
    catalog_items = [item for item in catalog.get("items") or [] if isinstance(item, dict)]
    rendered_text = str(answer.get("rendered_text") or "")
    if answer_mode == "catalog":
        expected_numbers = list(range(1, len(catalog_items) + 1))
        actual_numbers = [int(item.get("number") or 0) for item in catalog_items]
        if not catalog_items:
            errors.append({"path": "$.catalog.items", "message": "catalog mode requires at least one catalog item", "validator": "semantic"})
        if actual_numbers != expected_numbers:
            errors.append({"path": "$.catalog.items", "message": "catalog item numbering must be contiguous starting at 1", "validator": "semantic"})
        for number in expected_numbers:
            if len(re.findall(rf"(?m)^\s*{number}\.", rendered_text)) != 1:
                errors.append({"path": "$.rendered_text", "message": "rendered_text must contain one numbered catalog line for each catalog item", "validator": "semantic"})
                break
        for index, item in enumerate(catalog_items):
            path = f"$.catalog.items[{index}]"
            directions = item.get("directions") if isinstance(item.get("directions"), dict) else {}
            if is_round_trip_request and item.get("covers_requested_trip") is True:
                if not isinstance(directions.get("outbound"), dict) or not isinstance(directions.get("return"), dict):
                    errors.append({"path": f"{path}.directions", "message": "round-trip catalog items that cover the request must include outbound and return directions", "validator": "semantic"})
            if item.get("ticketing_model") != "single_ticket_proven":
                protection = item.get("protection") if isinstance(item.get("protection"), dict) else {}
                if protection.get("purchase_screen_verification_required") is not True:
                    errors.append({"path": f"{path}.protection.purchase_screen_verification_required", "message": "unproven ticketing models must require purchase-screen verification", "validator": "semantic"})
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
def validate_user_answer(answer: dict[str, Any]) -> None:
    errors = sorted(user_answer_validator().iter_errors(answer), key=lambda item: list(item.absolute_path))
    details = [validation_error_detail(error) for error in errors]
    details.extend(user_answer_contract_semantic_errors(answer))
    if details:
        raise CliError(
            "flight_search_user_answer failed contract validation",
            error_type="contract_error",
            details={"schema_version": answer.get("schema_version"), "errors": details},
        )
