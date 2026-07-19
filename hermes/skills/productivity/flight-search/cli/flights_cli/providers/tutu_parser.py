"""Pure normalization of Tutu carrier, segment, journey, and offer payloads."""

from __future__ import annotations

import re
from typing import Any

from ..config import TUTU_MCP_DEFAULT_URL
from ..domain.connection_policy import (
    airport_mismatch_violations,
    chronology_violations,
    missing_segment_time_violations,
)
from ..domain.normalize import normalize_airport_scope, price_value
from ..domain.offer_order import provider_offer_business_key
from ..domain.stop_policy import candidate_connection_counts
from ..errors import CliError
from ..store import Store

TUTU_NORMALIZER_VERSION = "tutu-avia-v5"

# Matches a 3-letter IATA code in parentheses at end of string:
# "Тулуза — Тулуза-Бланьяк (TLS)" -> TLS
_IATA_RE = re.compile(r"\(([A-Z]{3})\)\s*(?:,\s*терм\.\s*\S+)?\s*$")


# --- IATA extraction from Tutu airport strings ---


def extract_iata_from_airport_string(text: str) -> str | None:
    """Extract IATA code from a Tutu airport string like 'Тулуза — Тулуза-Бланьяк (TLS)'."""
    if not text:
        return None
    match = _IATA_RE.search(text.strip())
    if match:
        return match.group(1)
    # Fallback: bare IATA at end
    match2 = re.search(r"\b([A-Z]{3})\b\s*$", text.strip())
    if match2:
        return match2.group(1)
    return None


# --- Carrier name → IATA code resolution ---


def _carrier_name_key(value: str) -> str:
    text = str(value or "").replace("\u00a0", " ").strip().casefold()
    text = text.replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def _carrier_match_key(value: str) -> str:
    return "".join(
        character for character in _carrier_name_key(value) if character.isalnum()
    )


def _valid_carrier_code(value: str) -> str | None:
    code = str(value or "").strip().upper()
    return code if re.fullmatch(r"[A-Z0-9]{2,3}", code) else None


def _carrier_catalog_rows(store: Store) -> list[dict[str, Any]]:
    return store.airline_rows()


def _build_carrier_name_index(store: Store | None) -> dict[str, str]:
    if store is None:
        return {}
    index: dict[str, str] = {}
    for airline in _carrier_catalog_rows(store):
        code = _valid_carrier_code(str(airline.get("code") or ""))
        if not code:
            continue
        name = _carrier_name_key(str(airline.get("name") or ""))
        if name:
            index.setdefault(name, code)
        translations = airline.get("name_translations")
        if isinstance(translations, dict):
            for tr_name in translations.values():
                tr = _carrier_name_key(str(tr_name or ""))
                if tr:
                    index.setdefault(tr, code)
    return index


def _carrier_display_names_by_code(store: Store | None) -> dict[str, list[str]]:
    if store is None:
        return {}
    names_by_code: dict[str, list[str]] = {}
    seen_by_code: dict[str, set[str]] = {}

    def add_name(code: str, name: str) -> None:
        display_name = str(name or "").strip()
        if not display_name:
            return
        key = _carrier_name_key(display_name)
        seen = seen_by_code.setdefault(code, set())
        if key in seen:
            return
        seen.add(key)
        names_by_code.setdefault(code, []).append(display_name)

    # Tutu currently exposes Russian display names for many carriers, so prefer
    # the RU catalog row while still sending EN aliases as fallbacks.
    for airline in store.airline_rows(localized_first=True):
        code = _valid_carrier_code(str(airline.get("code") or ""))
        if not code:
            continue
        add_name(code, str(airline.get("name") or ""))
        translations = airline.get("name_translations")
        if isinstance(translations, dict):
            for tr_name in translations.values():
                add_name(code, str(tr_name or ""))
    return names_by_code


def _carrier_facets(raw: dict[str, Any]) -> list[str]:
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    facets = meta.get("carriers_available") if isinstance(meta, dict) else None
    names: list[str] = []
    for item in facets or []:
        value = item.get("name") if isinstance(item, dict) else item
        name = str(value or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _match_carrier_facet(candidates: list[str], facets: list[str]) -> str | None:
    candidate_keys = [_carrier_match_key(item) for item in candidates]
    for facet in facets:
        facet_key = _carrier_match_key(facet)
        if facet_key and facet_key in candidate_keys:
            return facet
    for facet in facets:
        facet_key = _carrier_match_key(facet)
        for candidate_key in candidate_keys:
            if len(candidate_key) >= 4 and facet_key.startswith(candidate_key):
                return facet
    return None


def resolve_tutu_carrier_facets(
    only_carriers: list[str] | None,
    *,
    facets: list[str],
    store: Store | None,
) -> tuple[list[str], dict[str, str], list[str]]:
    name_index = _build_carrier_name_index(store)
    display_names_by_code = _carrier_display_names_by_code(store)
    resolved: list[str] = []
    overrides: dict[str, str] = {}
    unmatched: list[str] = []

    for facet in facets:
        code = resolve_carrier_code(facet, name_index=name_index)
        if code:
            overrides[_carrier_name_key(facet)] = code
            continue
        for candidate_code, candidates in display_names_by_code.items():
            if _match_carrier_facet(candidates, [facet]):
                overrides[_carrier_name_key(facet)] = candidate_code
                break

    for raw_value in only_carriers or []:
        value = str(raw_value or "").strip()
        if not value:
            continue
        code = resolve_carrier_code(value, name_index=name_index)
        candidates = display_names_by_code.get(code or "", []) or [value]
        matched = _match_carrier_facet(candidates, facets)
        if matched:
            if matched not in resolved:
                resolved.append(matched)
            if code:
                overrides[_carrier_name_key(matched)] = code
            continue
        if code:
            unmatched.append(value)
            continue
        raise CliError(
            f"Tutu carrier filter could not be resolved: {value}",
            error_type="carrier_filter_unresolved",
            details={"carrier": value, "carriers_available": facets},
        )
    return resolved, overrides, unmatched


def resolve_carrier_code(
    carrier_name: str | None,
    *,
    name_index: dict[str, str] | None = None,
) -> str | None:
    if not carrier_name:
        return None
    text = carrier_name.strip()
    # Already a 2-letter IATA code
    if re.fullmatch(r"[A-Z0-9]{2,3}", text.upper()):
        return text.upper()
    if name_index:
        key = _carrier_name_key(text)
        if key in name_index:
            return name_index[key]
    return None


# --- Planner-owned airport scope → Tutu location resolution ---


def _iata_to_city_name(iata_code: str, store: Store | None) -> str | None:
    if store is None:
        return None
    code = iata_code.upper()
    # Check city catalog first
    city = store.city_by_code.get(code)
    if city and city.get("name"):
        return str(city["name"])
    # Check airport catalog → city_code → city
    airport = store.airport_by_code.get(code)
    if airport:
        city_code = str(airport.get("city_code") or "").upper()
        if city_code:
            city = store.city_by_code.get(city_code)
            if city and city.get("name"):
                return str(city["name"])
    return None


def _normalized_airport_scope(
    location_code: str,
    airport_scope: list[str] | None,
    store: Store | None,
) -> list[str]:
    explicit = normalize_airport_scope(airport_scope, "airport-scope")
    if explicit:
        return explicit
    if store is not None:
        try:
            location = store.resolve_location(location_code.upper())
        except CliError:
            pass
        else:
            resolved = sorted(
                {str(code).upper() for code in (location.airports or []) if code}
            )
            if resolved:
                return resolved
    return [location_code.upper()]


def _tutu_location_input(
    location_code: str,
    airport_scope: list[str],
    store: Store | None,
) -> tuple[str, str]:
    if len(airport_scope) == 1:
        return airport_scope[0], "airport"
    city_name = _iata_to_city_name(location_code, store)
    if city_name is None and airport_scope:
        city_name = _iata_to_city_name(airport_scope[0], store)
    return city_name or location_code, "city"


# --- Normalization ---


def normalize_tutu_segment(
    segment: dict[str, Any],
    *,
    carrier_name_index: dict[str, str],
    expected_origin: str | None = None,
    expected_destination: str | None = None,
) -> dict[str, Any] | None:
    from_text = str(segment.get("from") or "")
    to_text = str(segment.get("to") or "")
    origin = extract_iata_from_airport_string(from_text) or expected_origin or ""
    destination = (
        extract_iata_from_airport_string(to_text) or expected_destination or ""
    )
    if not origin or not destination:
        return None

    carrier_name = str(segment.get("carrier") or "")
    carrier_code = resolve_carrier_code(carrier_name, name_index=carrier_name_index)
    voyage_no = str(segment.get("voyage_no") or "").strip()
    flight_number = voyage_no or None
    if (
        carrier_code
        and flight_number
        and not flight_number.upper().startswith(carrier_code)
    ):
        flight_number = f"{carrier_code}{flight_number}"

    # Extract terminal info if present
    departure_terminal = None
    arrival_terminal = None
    term_match = re.search(r"терм\.\s*(\S+)", from_text)
    if term_match:
        departure_terminal = term_match.group(1).rstrip(",")
    term_match2 = re.search(r"терм\.\s*(\S+)", to_text)
    if term_match2:
        arrival_terminal = term_match2.group(1).rstrip(",")

    return {
        "flight_number": flight_number or None,
        "marketing_carrier": carrier_code or "",
        "operating_carrier": carrier_code or "",
        "carrier_name": carrier_name or None,
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_terminal": departure_terminal,
        "arrival_terminal": arrival_terminal,
        "departure_at": str(segment.get("departure_at") or ""),
        "arrival_at": str(segment.get("arrival_at") or ""),
        "duration": segment.get("duration_min"),
    }


def tutu_offer_key(flights: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        ":".join(
            [
                str(flight.get("flight_number") or ""),
                str(flight.get("origin") or ""),
                str(flight.get("destination") or ""),
                str(flight.get("departure_at") or ""),
                str(flight.get("arrival_at") or ""),
            ]
        )
        for flight in flights
    )


def _increment(counter: dict[str, int], key: str, amount: int = 1) -> None:
    counter[key] = counter.get(key, 0) + amount


def _journey_segments(journey: dict[str, Any]) -> list[dict[str, Any]]:
    segments = journey.get("segments")
    return [segment for segment in (segments or []) if isinstance(segment, dict)]


def _all_journey_segments(journeys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for journey in journeys:
        result.extend(_journey_segments(journey))
    return result


def _tutu_journey_key(journeys: list[dict[str, Any]]) -> tuple[str, ...]:
    parts: list[str] = []
    for index, journey in enumerate(journeys):
        direction = str(journey.get("direction") or f"journey_{index}")
        for segment_key in tutu_offer_key(_journey_segments(journey)):
            parts.append(f"{direction}:{segment_key}")
    return tuple(parts)


def _journey_endpoint_codes(
    journey: dict[str, Any],
) -> tuple[str | None, str | None]:
    segments = _journey_segments(journey)
    if not segments:
        return None, None
    origin = str(segments[0].get("origin") or "").upper() or None
    destination = str(segments[-1].get("destination") or "").upper() or None
    return origin, destination


def _matches_allowed_airport_scope(
    journeys: list[dict[str, Any]],
    *,
    origin_airports: list[str],
    destination_airports: list[str],
    skipped: dict[str, int],
) -> bool:
    origin_codes = set(origin_airports)
    destination_codes = set(destination_airports)
    expected = [(origin_codes, destination_codes, "outbound")]
    if len(journeys) > 1:
        expected.append((destination_codes, origin_codes, "return"))

    for journey, (allowed_origins, allowed_destinations, direction) in zip(
        journeys, expected
    ):
        journey_origin, journey_destination = _journey_endpoint_codes(journey)
        if (
            journey_origin not in allowed_origins
            or journey_destination not in allowed_destinations
        ):
            _increment(skipped, "outside_airport_scope")
            debug = journey.setdefault("debug", {})
            debug["airport_scope_mismatch"] = {
                "direction": direction,
                "allowed_origins": sorted(allowed_origins),
                "allowed_destinations": sorted(allowed_destinations),
                "actual_origin": journey_origin,
                "actual_destination": journey_destination,
            }
            return False
    return True


def _normalize_tutu_journeys(
    offer: dict[str, Any],
    *,
    origin: str,
    destination: str,
    carrier_name_index: dict[str, str],
    skipped: dict[str, int],
) -> list[dict[str, Any]]:
    legs = offer.get("legs")
    if not isinstance(legs, list) or not legs:
        _increment(skipped, "no_legs")
        return []

    journeys: list[dict[str, Any]] = []
    for leg_index, leg in enumerate(legs):
        if not isinstance(leg, dict):
            continue
        raw_segments = [
            segment
            for segment in (leg.get("segments") or [])
            if isinstance(segment, dict)
        ]
        if not raw_segments:
            continue

        direction = (
            "outbound"
            if leg_index == 0
            else "return"
            if leg_index == 1
            else f"journey_{leg_index + 1}"
        )
        expected_start = (
            origin if leg_index == 0 else destination if leg_index == 1 else None
        )
        expected_end = (
            destination if leg_index == 0 else origin if leg_index == 1 else None
        )
        normalized_segments: list[dict[str, Any]] = []
        for segment_index, segment in enumerate(raw_segments):
            normalized = normalize_tutu_segment(
                segment,
                carrier_name_index=carrier_name_index,
                expected_origin=expected_start if segment_index == 0 else None,
                expected_destination=(
                    expected_end if segment_index == len(raw_segments) - 1 else None
                ),
            )
            if normalized is not None:
                normalized_segments.append(normalized)
        if normalized_segments:
            journeys.append({"direction": direction, "segments": normalized_segments})

    if not journeys:
        _increment(skipped, "no_segments")
    return journeys


def parse_tutu_avia_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    return_date: str | None = None,
    limit: int = 20,
    store: Store | None = None,
    source_url: str | None = None,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
    carrier_name_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    offers_raw = raw.get("offers")
    if not isinstance(offers_raw, list):
        raise CliError(
            "Tutu MCP response does not contain an offers list",
            error_type="upstream_error",
        )

    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
    carrier_name_index = _build_carrier_name_index(store)
    carrier_name_index.update(carrier_name_overrides or {})
    requested_carriers = {
        str(code).strip().upper() for code in (only_carriers or []) if str(code).strip()
    }
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped: dict[str, int] = {}

    for index, offer in enumerate(offers_raw):
        if not isinstance(offer, dict):
            _increment(skipped, "bad_offer")
            continue

        journeys = _normalize_tutu_journeys(
            offer,
            origin=origin,
            destination=destination,
            carrier_name_index=carrier_name_index,
            skipped=skipped,
        )
        if not journeys:
            continue
        if len(journeys) > 2:
            _increment(skipped, "unsupported_journey_count")
            continue
        normalized_candidate = {"journeys": journeys}
        missing_times = missing_segment_time_violations(normalized_candidate)
        if missing_times:
            _increment(skipped, str(missing_times[0]["reason"]))
            continue
        reversed_segments = [
            violation
            for violation in chronology_violations(normalized_candidate)
            if violation.get("reason") == "segment_arrival_before_departure"
        ]
        if reversed_segments:
            _increment(skipped, str(reversed_segments[0]["reason"]))
            continue
        if airport_mismatch_violations(normalized_candidate):
            _increment(skipped, "airport_change")
            continue
        if not _matches_allowed_airport_scope(
            journeys,
            origin_airports=allowed_origins,
            destination_airports=allowed_destinations,
            skipped=skipped,
        ):
            continue
        price_data = offer.get("price")
        if isinstance(price_data, dict):
            amount = price_value({"price": price_data.get("amount")})
            offer_currency = str(price_data.get("currency") or currency).upper()
        else:
            amount = price_value({"price": price_data})
            offer_currency = currency

        outbound_segments = _journey_segments(journeys[0])
        if not outbound_segments:
            _increment(skipped, "bad_segments")
            continue
        all_segments = _all_journey_segments(journeys)
        key = _tutu_journey_key(journeys)
        has_self_transfer_field = any(
            key in offer for key in ("is_multi_pnr", "has_self_transfer")
        )
        self_transfer = (
            bool(offer.get("is_multi_pnr") or offer.get("has_self_transfer"))
            if has_self_transfer_field
            else None
        )
        offer_obj = {
            "id": str(offer.get("offer_id") or f"tutu:{index}"),
            "price": amount,
            "currency": offer_currency,
            "number_of_changes": max(
                candidate_connection_counts({"journeys": journeys}), default=0
            ),
            "duration": offer.get("duration_min"),
            "departure_at": outbound_segments[0]["departure_at"],
            "arrival_at": outbound_segments[-1]["arrival_at"],
            "origin": outbound_segments[0]["origin"],
            "destination": outbound_segments[-1]["destination"],
            "flight_numbers": [
                f["flight_number"] for f in all_segments if f.get("flight_number")
            ],
            "marketing_carriers": sorted(
                {
                    f["marketing_carrier"]
                    for f in all_segments
                    if f.get("marketing_carrier")
                }
            ),
            "operating_carriers": sorted(
                {
                    f["operating_carrier"]
                    for f in all_segments
                    if f.get("operating_carrier")
                }
            ),
            "segments": outbound_segments,
            "journeys": journeys,
            "journey_scope": "round_trip" if len(journeys) == 2 else "one_way",
            "ticketing_model": "provider_order_unverified",
            "self_transfer": self_transfer,
            "self_transfer_note": offer.get("multi_pnr_note"),
            "self_transfer_source": "tutu" if has_self_transfer_field else None,
        }
        if len(journeys) == 2:
            return_segments = _journey_segments(journeys[1])
            if return_segments:
                offer_obj["return_departure_at"] = return_segments[0]["departure_at"]
                offer_obj["return_arrival_at"] = return_segments[-1]["arrival_at"]
        previous = deduped.get(key)
        previous_price = previous.get("price") if previous else None
        if previous is None or (
            amount is not None and (previous_price is None or amount < previous_price)
        ):
            deduped[key] = offer_obj

    normalized_offers = list(deduped.values())
    sorted_offers = sorted(normalized_offers, key=provider_offer_business_key)
    normalized_limit = max(0, int(limit))
    offers = sorted_offers[:normalized_limit] if normalized_limit else sorted_offers
    omitted_offer_count = max(0, len(sorted_offers) - len(offers))
    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": currency,
        "source": "Tutu MCP search_avia (tutu.ru)",
        "source_url": source_url or TUTU_MCP_DEFAULT_URL,
        "note": "Tutu.ru aggregate source; recheck final fare and seat availability before ticketing.",
        "filters": {
            "direct_only": bool(direct_only),
            "only_carriers": sorted(requested_carriers),
            "origin_airports": allowed_origins,
            "destination_airports": allowed_destinations,
        },
        "return_date": return_date,
        "pagination": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
        "raw_count": len(offers_raw),
        "skipped": skipped,
        "offer_count": len(offers),
        "unique_flight_count": len(normalized_offers),
        "omitted_offer_count": omitted_offer_count,
        "offers": offers,
    }
