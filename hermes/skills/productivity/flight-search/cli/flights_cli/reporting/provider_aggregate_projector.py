from __future__ import annotations

from datetime import datetime
from typing import Any

from ..domain.stop_metrics import offer_stop_metrics
from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY, StopPolicy, decide_stop_policy
from .formatting import price_label
from .option_projector import segment_summary


def aggregate_offer_with_stop_metrics(offer: dict[str, Any]) -> dict[str, Any]:
    projected = dict(offer)
    metrics = offer_stop_metrics(projected)
    projected.setdefault("connection_count", metrics["max_connections_per_journey"])
    projected.setdefault("stop_tier", metrics["stop_tier"])
    return projected


def aggregate_control_summary(control: dict[str, Any]) -> dict[str, Any]:
    top_offers = control.get("top_offers") if isinstance(control.get("top_offers"), list) else []
    projected_offers = [aggregate_offer_with_stop_metrics(offer) for offer in top_offers if isinstance(offer, dict)]
    projected_offers.sort(
        key=lambda offer: (
            int(offer.get("connection_count") or 0),
            int(offer.get("airport_mismatch_count") or 0),
            offer.get("price") if offer.get("price") is not None else 10**12,
        )
    )
    return {
        "direction": control.get("direction"),
        "origin": control.get("origin"),
        "destination": control.get("destination"),
        "date": control.get("date"),
        "status": control.get("status"),
        "provider": control.get("provider"),
        "filters": control.get("filters") or {},
        "offer_count": control.get("offer_count"),
        "raw_offer_count": control.get("raw_offer_count"),
        "suppressed_three_plus_count": control.get("suppressed_three_plus_count"),
        "suppressed_airport_change_count": control.get("suppressed_airport_change_count"),
        "raw_variant_count": control.get("raw_variant_count"),
        "cache_status": control.get("cache_status"),
        "top_offers": projected_offers[:3],
        "error": control.get("error"),
    }


def aggregate_journey_scope(direction: str, *, requested_round_trip: bool) -> str:
    if not requested_round_trip:
        return "one_way"
    return "return_only" if direction == "return" else "outbound_only"


def parse_segment_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def positive_minutes(value: Any) -> int | None:
    if value is None:
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    return minutes if minutes >= 0 else None


def minutes_between(start_value: Any, end_value: Any) -> int | None:
    start = parse_segment_datetime(start_value)
    end = parse_segment_datetime(end_value)
    if start is None or end is None:
        return None
    if (start.tzinfo is None) != (end.tzinfo is None):
        return None
    delta_min = int((end - start).total_seconds() // 60)
    return delta_min if delta_min >= 0 else None


def segment_duration_min(segment: dict[str, Any]) -> int | None:
    explicit = positive_minutes(segment.get("duration_min"))
    if explicit is not None:
        return explicit
    explicit = positive_minutes(segment.get("duration"))
    if explicit is not None:
        return explicit
    return minutes_between(segment.get("departure_at"), segment.get("arrival_at"))


def flight_time_from_segments(segments: list[dict[str, Any]]) -> int | None:
    if not segments:
        return None
    durations = [segment_duration_min(segment) for segment in segments]
    if any(duration is None for duration in durations):
        return None
    return sum(int(duration) for duration in durations if duration is not None)


def layover_time_from_segments(segments: list[dict[str, Any]]) -> int | None:
    if len(segments) <= 1:
        return 0 if segments else None
    layovers: list[int] = []
    for previous, current in zip(segments, segments[1:]):
        gap = minutes_between(previous.get("arrival_at"), current.get("departure_at"))
        if gap is None:
            return None
        layovers.append(gap)
    return sum(layovers)


def aggregate_time_fields(offer: dict[str, Any]) -> dict[str, int | None]:
    segments = [segment for segment in offer.get("segments") or [] if isinstance(segment, dict)]
    itinerary_elapsed_min: int | None = None
    if segments:
        itinerary_elapsed_min = minutes_between(segments[0].get("departure_at"), segments[-1].get("arrival_at"))

    flight_time_min = flight_time_from_segments(segments)
    if flight_time_min is None:
        flight_time_min = positive_minutes(offer.get("duration_min"))
    if flight_time_min is None:
        flight_time_min = positive_minutes(offer.get("duration"))

    layover_total_min: int | None = None
    if itinerary_elapsed_min is not None and flight_time_min is not None:
        computed = itinerary_elapsed_min - flight_time_min
        if computed >= 0:
            layover_total_min = computed
    if layover_total_min is None:
        layover_total_min = layover_time_from_segments(segments)
        if layover_total_min is not None and itinerary_elapsed_min is None:
            layover_total_min = None

    return {
        "itinerary_elapsed_min": itinerary_elapsed_min,
        "flight_time_min": flight_time_min,
        "layover_total_min": layover_total_min,
    }


def duration_label(value: Any) -> str | None:
    minutes = positive_minutes(value)
    if minutes is None:
        return None
    hours, mins = divmod(minutes, 60)
    return f"{hours}h{mins:02d}"


def aggregate_time_text(time_fields: dict[str, Any]) -> str | None:
    itinerary = time_fields.get("itinerary_elapsed_min")
    flight = time_fields.get("flight_time_min")
    layover = time_fields.get("layover_total_min")
    if itinerary is not None:
        itinerary_text = duration_label(itinerary)
        layover_text = duration_label(layover)
        if itinerary_text and layover_text and positive_minutes(layover) not in (None, 0):
            return f"Travel time: {itinerary_text}, including layover time: {layover_text}"
        if itinerary_text:
            return f"Travel time: {itinerary_text}"
    flight_text = duration_label(flight)
    if flight_text:
        return f"Flight time, not including layover time: {flight_text}"
    return None


def aggregate_user_facing_label(
    control: dict[str, Any],
    offer: dict[str, Any],
    *,
    direction: str,
    journey_scope: str,
    time_fields: dict[str, Any],
) -> str:
    route = f"{control.get('origin')}→{control.get('destination')}"
    price = price_label(offer.get("price"), offer.get("currency"))
    base = f"{route}, {price}"
    time_text = aggregate_time_text(time_fields)
    if time_text:
        base = f"{base}. {time_text}"
    if journey_scope == "outbound_only":
        return f"One-way outbound alternative: {base}. Does not cover requested round trip."
    if journey_scope == "return_only":
        return f"One-way return alternative: {base}. Does not cover requested round trip."
    direction_text = "return" if direction == "return" else "outbound"
    return f"One-way {direction_text} provider aggregate alternative: {base}."


TWO_ONE_WAY_PAIR_DISCLAIMER = (
    "Not proven as a single PNR, protected round-trip, baggage-through itinerary, through fare, or final fare. "
    "Verify ticketing, baggage, refund, and disruption protection on the booking screen."
)


def option_price_amount_and_currency(option: dict[str, Any]) -> tuple[Any, Any]:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    return price.get("amount"), price.get("currency")


def numeric_price_amount(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def option_price_text(option: dict[str, Any]) -> str:
    amount, currency = option_price_amount_and_currency(option)
    return str(option.get("price_text") or price_label(amount, currency))


def option_route_label(option: dict[str, Any], fallback: str) -> str:
    segments = [segment for segment in option.get("segments") or [] if isinstance(segment, dict)]
    if segments:
        first = segments[0]
        last = segments[-1]
        if first.get("origin") and last.get("destination"):
            return f"{first.get('origin')}→{last.get('destination')}"
    return fallback


def option_time_fields(option: dict[str, Any]) -> dict[str, int | None]:
    return {
        "itinerary_elapsed_min": positive_minutes(option.get("itinerary_elapsed_min")),
        "flight_time_min": positive_minutes(option.get("flight_time_min")),
        "layover_total_min": positive_minutes(option.get("layover_total_min")),
    }


def option_time_label(direction: str, option: dict[str, Any]) -> str | None:
    time_text = aggregate_time_text(option_time_fields(option))
    if not time_text:
        return None
    return f"{direction} — {time_text}"


def option_max_connections(option: dict[str, Any]) -> int:
    try:
        return int(option.get("max_connections_per_journey") or 0)
    except (TypeError, ValueError):
        return 0


def worst_stop_tier(outbound: dict[str, Any], inbound: dict[str, Any]) -> str | None:
    tier_order = {"T0_DIRECT": 0, "T1_ONE_STOP": 1, "T2_TWO_STOP": 2}
    tiers = [tier for tier in (outbound.get("stop_tier"), inbound.get("stop_tier")) if tier in tier_order]
    if not tiers:
        return None
    return max(tiers, key=lambda tier: tier_order[str(tier)])


def two_one_way_pair_price(outbound: dict[str, Any], inbound: dict[str, Any]) -> tuple[dict[str, Any], str]:
    outbound_amount, outbound_currency = option_price_amount_and_currency(outbound)
    inbound_amount, inbound_currency = option_price_amount_and_currency(inbound)
    outbound_number = numeric_price_amount(outbound_amount)
    inbound_number = numeric_price_amount(inbound_amount)
    if (
        outbound_number is not None
        and inbound_number is not None
        and outbound_currency
        and inbound_currency
        and str(outbound_currency) == str(inbound_currency)
    ):
        total = outbound_number + inbound_number
        return {"amount": total, "currency": outbound_currency}, f"Sum of displayed one-way prices: {price_label(total, outbound_currency)}"
    return (
        {"amount": None, "currency": None},
        f"Displayed one-way prices: outbound {option_price_text(outbound)} + return {option_price_text(inbound)}",
    )


def two_one_way_pair_option(outbound: dict[str, Any], inbound: dict[str, Any]) -> dict[str, Any]:
    price, price_text = two_one_way_pair_price(outbound, inbound)
    outbound_route = option_route_label(outbound, "outbound offer")
    inbound_route = option_route_label(inbound, "return offer")
    outbound_component = f"outbound {outbound_route} {option_price_text(outbound)}"
    inbound_component = f"return {inbound_route} {option_price_text(inbound)}"
    outbound_time_label = option_time_label("outbound", outbound)
    inbound_time_label = option_time_label("return", inbound)
    if outbound_time_label:
        outbound_component = f"{outbound_component} ({outbound_time_label})"
    if inbound_time_label:
        inbound_component = f"{inbound_component} ({inbound_time_label})"
    component_label = f"{outbound_component} + {inbound_component}"
    carriers: list[str] = []
    for option in (outbound, inbound):
        for code in option.get("carriers") or []:
            carrier = str(code).upper()
            if carrier and carrier not in carriers:
                carriers.append(carrier)
    max_connections = max(option_max_connections(outbound), option_max_connections(inbound))
    pair = {
        "rank": None,
        "id": f"provider-aggregate:two-one-way-pair:{outbound.get('id')}+{inbound.get('id')}",
        "category": "provider_aggregate_candidate",
        "reason": "Two separate directional provider aggregate one-way offers are available for the requested round trip; treat as linked alternatives, not as protected round-trip ticketing.",
        "detail_status": "summary_only",
        "ok": True,
        "price": price,
        "price_text": price_text,
        "elapsed_min": None,
        "elapsed": None,
        "carriers": carriers,
        "risk": {
            "score": None,
            "grade": None,
            "reject": None,
            "top_reasons": [
                {
                    "code": "separate_one_way_offers",
                    "message": "Outbound and return are separate one-way provider aggregate offers; protection is not proven.",
                }
            ],
        },
        "validation_summary": {
            "candidate_type": "two_one_way_pair",
            "components": [
                {"id": outbound.get("id"), "journey_scope": outbound.get("journey_scope"), "price_text": option_price_text(outbound), **option_time_fields(outbound)},
                {"id": inbound.get("id"), "journey_scope": inbound.get("journey_scope"), "price_text": option_price_text(inbound), **option_time_fields(inbound)},
            ],
        },
        "stop_tier": worst_stop_tier(outbound, inbound),
        "max_connections_per_journey": max_connections,
        "journey_scope": "two_one_way_pair",
        "covers_requested_trip": True,
        "direction": None,
        "directional_only": False,
        "composed_of_directional_offers": True,
        "ticketing_model": "separate_one_way_offers",
        "user_facing_label": f"Two separate one-way offers: {component_label}. {price_text}.",
        "disclaimer": TWO_ONE_WAY_PAIR_DISCLAIMER,
        "connections": [],
        "segments": [],
        "ticketing_note": f"Two separate one-way provider aggregate offers. {TWO_ONE_WAY_PAIR_DISCLAIMER}",
    }
    outbound_time = option_time_fields(outbound)
    inbound_time = option_time_fields(inbound)
    if any(value is not None for value in outbound_time.values()):
        pair["outbound_time"] = outbound_time
    if any(value is not None for value in inbound_time.values()):
        pair["return_time"] = inbound_time
    return pair


def add_two_one_way_pair_if_available(options: list[dict[str, Any]], *, requested_round_trip: bool) -> list[dict[str, Any]]:
    if not requested_round_trip:
        return options
    outbound = next((item for item in options if item.get("journey_scope") == "outbound_only"), None)
    inbound = next((item for item in options if item.get("journey_scope") == "return_only"), None)
    if not outbound or not inbound:
        return options
    if any(item.get("journey_scope") == "two_one_way_pair" for item in options):
        return options
    return [*options, two_one_way_pair_option(outbound, inbound)]


def provider_aggregate_candidate_options(
    controls: list[dict[str, Any]],
    limit: int = 5,
    *,
    stop_policy: StopPolicy = BUSINESS_DEFAULT_STOP_POLICY,
    preferred_available: bool = False,
    requested_round_trip: bool = False,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    aggregate_preferred_available = any(
        offer_stop_metrics(offer)["max_connections_per_journey"] <= stop_policy.preferred_max_connections
        for control in controls
        for offer in (control.get("top_offers") or [])
        if isinstance(control, dict) and control.get("status") == "ok" and isinstance(offer, dict)
    )
    effective_preferred_available = preferred_available or aggregate_preferred_available
    for control in controls:
        if control.get("status") != "ok":
            continue
        direction = str(control.get("direction") or "outbound")
        for offer in control.get("top_offers") or []:
            if not isinstance(offer, dict):
                continue
            metrics = offer_stop_metrics(offer)
            decision = decide_stop_policy(metrics, stop_policy, preferred_available=effective_preferred_available)
            if not decision.reportable_by_stop_policy:
                continue
            segments = [segment_summary(segment, direction) for segment in offer.get("segments") or [] if isinstance(segment, dict)]
            time_fields = aggregate_time_fields({**offer, "segments": segments})
            detail_status = "full" if segments else "summary_only"
            offer_id = offer.get("id") or f"{control.get('origin')}-{control.get('destination')}-{len(options) + 1}"
            provider_note = str(offer.get("ticketing_note") or "Provider-assembled route offer.")
            journey_scope = aggregate_journey_scope(direction, requested_round_trip=requested_round_trip)
            covers_requested_trip = journey_scope == "one_way"
            user_facing_label = aggregate_user_facing_label(control, offer, direction=direction, journey_scope=journey_scope, time_fields=time_fields)
            ticketing_note = (
                f"Provider aggregate one-way {direction} candidate; ticketing_protection=unknown. {provider_note} "
                "Verify single-PNR/protection, baggage, fare rules, and final fare on the booking screen."
            )
            options.append(
                {
                    "rank": None,
                    "id": f"provider-aggregate:{direction}:{offer_id}",
                    "category": "provider_aggregate_candidate",
                    "reason": "Provider returned a directional one-way aggregate offer; treat as a candidate for purchase-screen verification, not as proof of protected through-ticketing.",
                    "detail_status": detail_status,
                    "ok": True,
                    "price": {"amount": offer.get("price"), "currency": offer.get("currency")},
                    "price_text": price_label(offer.get("price"), offer.get("currency")),
                    "elapsed_min": None,
                    "elapsed": None,
                    **time_fields,
                    "carriers": [str(code).upper() for code in offer.get("carriers") or [] if code],
                    "risk": {
                        "score": None,
                        "grade": None,
                        "reject": None,
                        "top_reasons": [
                            {
                                "code": "provider_aggregate_candidate",
                                "message": "Ticketing protection is unknown until verified on the booking screen.",
                            }
                        ],
                    },
                    "validation_summary": {
                        "candidate_type": "provider_aggregate",
                        "provider": control.get("provider"),
                        "filters": control.get("filters") or {},
                        "stop_policy_decision": decision.to_dict(),
                        **metrics,
                    },
                    "stop_tier": metrics["stop_tier"],
                    "max_connections_per_journey": metrics["max_connections_per_journey"],
                    "journey_scope": journey_scope,
                    "covers_requested_trip": covers_requested_trip,
                    "direction": direction,
                    "directional_only": True,
                    "composed_of_directional_offers": False,
                    "ticketing_model": "provider_aggregate",
                    "user_facing_label": user_facing_label,
                    "disclaimer": "Provider aggregate one-way offer; ticketing/protection, baggage handling, fare rules, and final fare require booking-screen verification.",
                    "connections": [],
                    "segments": segments,
                    "ticketing_note": ticketing_note,
                }
            )
            if len(options) >= max(0, limit):
                return add_two_one_way_pair_if_available(options, requested_round_trip=requested_round_trip)
    return add_two_one_way_pair_if_available(options, requested_round_trip=requested_round_trip)
