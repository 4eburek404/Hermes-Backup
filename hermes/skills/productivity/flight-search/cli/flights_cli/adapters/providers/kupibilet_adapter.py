from __future__ import annotations

from collections import Counter
from typing import Any

from ...config import KUPIBILET_CITY_CODE_FIRST_AIRPORTS
from ...domain.carriers import carrier_from_flight_number
from ...domain.normalize import parse_iso_date
from ...domain.provider_offer_filter import (
    MAX_MODEL_CONNECTIONS,
    filter_provider_offers,
)
from ...domain.stop_metrics import offer_stop_metrics
from ...ports.providers import (
    CacheStatus,
    ProviderCapabilities,
    ProviderName,
    ProviderProbeResult,
)
from ...providers.kupibilet import (
    cached_kupibilet_search,
    kupibilet_result_to_segment_result,
    kupibilet_segment_search_summary,
)
from ...store import Store
from ...execution.cache_status import cache_status_from_result
from .common import evidence_type_for_offer_count, segment_probe_type_from_query


KUPIBILET_CAPABILITIES = ProviderCapabilities(
    supports_ru_touching=True,
    supports_global=True,
    supports_city_code=True,
    supports_direct_only=True,
    supports_carrier_filter=True,
    supports_full_route_aggregate=True,
    supports_round_trip=False,
    supports_cache=True,
    probe_types=frozenset(
        {
            "segment_direct",
            "segment_hub_leg",
            "full_route_aggregate",
            "carrier_aggregate",
            "city_pair_direct",
        }
    ),
)


def _raw_offer_actual_airports(offer: dict[str, Any]) -> tuple[str, str]:
    segments = offer.get("segments") if isinstance(offer.get("segments"), list) else []
    if not segments:
        origin = str(
            offer.get("origin") or offer.get("departure_airport") or ""
        ).upper()
        destination = str(
            offer.get("destination") or offer.get("arrival_airport") or ""
        ).upper()
        return origin, destination
    first = segments[0] if isinstance(segments[0], dict) else {}
    last = segments[-1] if isinstance(segments[-1], dict) else {}
    origin = str(first.get("origin") or first.get("departure_airport") or "").upper()
    destination = str(
        last.get("destination") or last.get("arrival_airport") or ""
    ).upper()
    return origin, destination


def _city_code_offer_rejection_reason(
    *,
    actual_origin: str,
    actual_destination: str,
    origin_scope: set[str],
    destination_scope: set[str],
) -> str | None:
    if not actual_origin or not actual_destination:
        return "missing_actual_airport_fields"
    if origin_scope and actual_origin not in origin_scope:
        return "origin_out_of_scope"
    if destination_scope and actual_destination not in destination_scope:
        return "destination_out_of_scope"
    return None


def validate_kupibilet_city_code_scope(
    spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]
) -> dict[str, Any] | None:
    query_origin = str(spec.get("origin") or "").upper()
    query_destination = str(spec.get("destination") or "").upper()
    origin_scope = {
        str(code).upper()
        for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(query_origin, [])
    }
    destination_scope = {
        str(code).upper()
        for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(query_destination, [])
    }
    if not origin_scope and not destination_scope:
        return None

    rejected_reasons: Counter[str] = Counter()
    raw_offers = [
        offer for offer in (result.get("offers") or []) if isinstance(offer, dict)
    ]
    for raw_offer in raw_offers:
        actual_origin, actual_destination = _raw_offer_actual_airports(raw_offer)
        reason = _city_code_offer_rejection_reason(
            actual_origin=actual_origin,
            actual_destination=actual_destination,
            origin_scope=origin_scope,
            destination_scope=destination_scope,
        )
        if reason:
            rejected_reasons[reason] += 1

    accepted_offers: list[dict[str, Any]] = []
    for offer in segment_result.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        actual_origin = str(
            offer.get("departure_airport") or offer.get("origin") or ""
        ).upper()
        actual_destination = str(
            offer.get("arrival_airport") or offer.get("destination") or ""
        ).upper()
        reason = _city_code_offer_rejection_reason(
            actual_origin=actual_origin,
            actual_destination=actual_destination,
            origin_scope=origin_scope,
            destination_scope=destination_scope,
        )
        if reason:
            continue
        accepted_offers.append(offer)

    segment_result["offers"] = accepted_offers
    return {
        "query_origin": query_origin,
        "query_destination": query_destination,
        "origin_scope_airports": sorted(origin_scope),
        "destination_scope_airports": sorted(destination_scope),
        "accepted_offer_count": len(accepted_offers),
        "rejected_offer_count": sum(rejected_reasons.values()),
        "rejected_reasons": dict(rejected_reasons),
    }


def aggregate_offer_summary(offer: dict[str, Any]) -> dict[str, Any]:
    raw_segments = [
        flight for flight in (offer.get("segments") or []) if isinstance(flight, dict)
    ]
    carriers: set[str] = set()
    segments = []
    for flight in raw_segments:
        flight_number = str(flight.get("flight_number") or "")
        marketing = str(flight.get("marketing_carrier") or "").upper()
        operating = str(flight.get("operating_carrier") or "").upper()
        carrier = operating or marketing or carrier_from_flight_number(flight_number)
        if carrier:
            carriers.add(carrier)
        segments.append(
            {
                "flight_number": flight_number or None,
                "carrier": carrier or None,
                "marketing_carrier": marketing or None,
                "operating_carrier": operating or None,
                "carrier_name": flight.get("carrier_name"),
                "origin": flight.get("origin"),
                "destination": flight.get("destination"),
                "departure_terminal": flight.get("departure_terminal"),
                "arrival_terminal": flight.get("arrival_terminal"),
                "departure_at": flight.get("departure_at"),
                "arrival_at": flight.get("arrival_at"),
            }
        )
    airport_mismatches = []
    for previous, current in zip(segments, segments[1:]):
        previous_arrival = str(previous.get("destination") or "").upper()
        current_departure = str(current.get("origin") or "").upper()
        if (
            previous_arrival
            and current_departure
            and previous_arrival != current_departure
        ):
            airport_mismatches.append(
                {
                    "arrival_airport": previous_arrival,
                    "departure_airport": current_departure,
                    "warning": "provider aggregate offer changes airport between consecutive flights; verify ground transfer and ticket protection",
                }
            )
    stop_metrics = offer_stop_metrics(offer)
    return {
        "id": offer.get("id"),
        "price": offer.get("price"),
        "currency": offer.get("currency"),
        "change_count": offer.get("number_of_changes"),
        "connection_count": stop_metrics["max_connections_per_journey"],
        "stop_tier": stop_metrics["stop_tier"],
        "reportable_by_stop_policy": stop_metrics["max_connections_per_journey"]
        <= MAX_MODEL_CONNECTIONS,
        "duration_min": offer.get("duration"),
        "flight_numbers": offer.get("flight_numbers")
        or [
            segment.get("flight_number")
            for segment in segments
            if segment.get("flight_number")
        ],
        "carriers": sorted(carriers),
        "segments": segments,
        "airport_mismatch_count": len(airport_mismatches),
        "airport_mismatches": airport_mismatches,
        "ticketing_note": "Provider-assembled route offer; verify single-PNR/protection, baggage, and final fare on the booking screen.",
        **{
            key: offer.get(key)
            for key in (
                "ticketing_model",
                "self_transfer",
                "self_transfer_note",
                "self_transfer_source",
            )
            if key in offer
        },
    }


def kupibilet_aggregate_control_summary(
    *,
    direction: str,
    origin: str,
    destination: str,
    depart_date: str,
    carriers: list[str],
    result: dict[str, Any],
) -> dict[str, Any]:
    offers = [
        offer for offer in (result.get("offers") or []) if isinstance(offer, dict)
    ]
    filtered_offers, filter_stats = filter_provider_offers(offers)
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "date": depart_date,
        "status": "ok",
        "provider": "kupibilet",
        "source": result.get("source"),
        "filters": {"direct_only": False, "only_carriers": carriers},
        "offer_count": len(filtered_offers),
        "raw_offer_count": result.get(
            "raw_offer_count", filter_stats["raw_offer_count"]
        ),
        "suppressed_three_plus_count": int(
            result.get("suppressed_three_plus_count") or 0
        )
        + filter_stats["suppressed_three_plus_count"],
        "suppressed_airport_change_count": int(
            result.get("suppressed_airport_change_count") or 0
        )
        + filter_stats["suppressed_airport_change_count"],
        "raw_variant_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "cache": result.get("cache", {"hit": False}),
        "cache_status": cache_status_from_result(result),
        "top_offers": [aggregate_offer_summary(offer) for offer in filtered_offers],
    }


class KupibiletProviderAdapter:
    name: ProviderName = "kupibilet"
    capabilities = KUPIBILET_CAPABILITIES

    def __init__(
        self, *, store: Store | None = None, fetcher: Any | None = None
    ) -> None:
        self.store = store
        self.fetcher = fetcher

    def search_segment(self, query: dict[str, Any]) -> ProviderProbeResult:
        origin = str(query["origin"]).upper()
        destination = str(query["destination"]).upper()
        depart_date_text = str(query["date"])
        depart_date = parse_iso_date(depart_date_text, "segment-date")
        direction = str(query["direction"])
        leg = str(query["leg"])
        result = cached_kupibilet_search(
            origin,
            destination,
            depart_date,
            currency=str(query["currency"]).upper(),
            only_carriers=list(query.get("only_carriers") or []),
            direct_only=bool(query.get("direct_only", True)),
            limit=int(query["limit"]),
            timeout=int(query.get("timeout") or 60),
            cache_ttl_seconds=int(query.get("cache_ttl_seconds") or 0),
            use_cache=bool(query.get("use_cache", True)),
            fetcher=self.fetcher,
        )
        spec = {
            "direction": direction,
            "leg": leg,
            "origin": origin,
            "destination": destination,
            "date": depart_date_text,
        }
        segment_result = kupibilet_result_to_segment_result(
            result, direction=direction, leg=leg
        )
        city_code_validation = validate_kupibilet_city_code_scope(
            spec, result, segment_result
        )
        summary = {
            **kupibilet_segment_search_summary(spec, result, segment_result),
            "provider": "kupibilet",
        }
        if city_code_validation is not None:
            summary["city_code_validation"] = city_code_validation
            if (
                city_code_validation["rejected_offer_count"]
                and not city_code_validation["accepted_offer_count"]
            ):
                summary["status"] = "invalid"
                summary["reason"] = "city_code_scope_validation_failed"
        cache_status: CacheStatus = cache_status_from_result(result)  # type: ignore[assignment]
        offer_count = len(segment_result.get("offers") or [])
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or ""),
            probe_type=segment_probe_type_from_query(query, self.capabilities),
            provider="kupibilet",
            query={
                "origin": origin,
                "destination": destination,
                "date": depart_date_text,
                "currency": str(query["currency"]).upper(),
                "only_carriers": list(query.get("only_carriers") or []),
                "direct_only": bool(query.get("direct_only", True)),
            },
            execution_state="searched",
            cache_status=cache_status,
            evidence_type=evidence_type_for_offer_count(
                offer_count=offer_count, cache_status=cache_status
            ),
            result_summary=summary,
            offers=tuple(segment_result.get("offers") or []),
            source_boundary={
                "provider": "kupibilet",
                "source_key": segment_result.get("source_key"),
                "source": segment_result.get("source") or result.get("source"),
                "scope": "provider live/cached segment search",
                "warning": "availability and price require final booking-screen recheck",
            },
        )

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        origin = str(query["origin"]).upper()
        destination = str(query["destination"]).upper()
        depart_date_text = str(query["date"])
        depart_date = parse_iso_date(depart_date_text, "aggregate-control-date")
        carriers = list(query.get("only_carriers") or [])
        result = cached_kupibilet_search(
            origin,
            destination,
            depart_date,
            currency=str(query["currency"]).upper(),
            only_carriers=carriers,
            direct_only=False,
            limit=int(query["limit"]),
            timeout=int(query.get("timeout") or 60),
            cache_ttl_seconds=int(query.get("cache_ttl_seconds") or 0),
            use_cache=bool(query.get("use_cache", True)),
            fetcher=self.fetcher,
        )
        summary = kupibilet_aggregate_control_summary(
            direction=str(query["direction"]),
            origin=origin,
            destination=destination,
            depart_date=depart_date_text,
            carriers=carriers,
            result=result,
        )
        cache_status: CacheStatus = cache_status_from_result(result)  # type: ignore[assignment]
        offer_count = int(summary.get("offer_count") or 0)
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or ""),
            probe_type="carrier_aggregate" if carriers else "full_route_aggregate",
            provider="kupibilet",
            query={
                "origin": origin,
                "destination": destination,
                "date": depart_date_text,
                "currency": str(query["currency"]).upper(),
                "only_carriers": carriers,
                "direct_only": False,
            },
            execution_state="searched",
            cache_status=cache_status,
            evidence_type=evidence_type_for_offer_count(
                offer_count=offer_count, cache_status=cache_status
            ),
            result_summary=summary,
            offers=tuple(summary.get("top_offers") or []),
            source_boundary={
                "provider": "kupibilet",
                "source": result.get("source"),
                "scope": "provider aggregate full-route search",
                "warning": "aggregate route offers are provider-returned candidates, not verified protected fares",
            },
        )
