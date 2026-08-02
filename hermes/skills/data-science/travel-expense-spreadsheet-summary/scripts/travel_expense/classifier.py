from __future__ import annotations

import difflib
import re

from .constants import (
    CATEGORY_AIR,
    CATEGORY_HOTEL,
    CATEGORY_RAIL,
    CATEGORY_UNKNOWN,
    EXPLICIT_LODGING_DETAILS,
    GROUND_MARKERS,
    HOTEL_VENDOR_MARKERS,
    KNOWN_AIRLINES,
    MIXED_SERVICE_VENDOR_MARKERS,
    RAIL_CARRIER_MARKERS,
    RAIL_DETAIL_MARKERS,
    SOFT_LODGING_DETAILS,
)
from .text import ORG_AIRLINE_RE, compact, has_any, looks_like_date_range, looks_like_route, norm

try:
    from rapidfuzz import fuzz, process  # type: ignore
except Exception:  # pragma: no cover - rapidfuzz is optional
    fuzz = None
    process = None


def _fuzzy_known_airline(carrier: str) -> tuple[bool, str | None, float | None]:
    """High-threshold fuzzy matching, only for the carrier field.

    It is intentionally not applied to `Детали`: details contain cities,
    company names, routes and hotel names, where fuzzy matching creates false
    positives.
    """
    compact_carrier = compact(carrier)
    if len(compact_carrier) < 5:
        return False, None, None
    choices = {name: compact(name) for name in KNOWN_AIRLINES if len(compact(name)) >= 5}
    if process is not None and fuzz is not None:
        match = process.extractOne(compact_carrier, choices, scorer=fuzz.WRatio, score_cutoff=94)
        if match:
            name, score, _ = match
            return True, str(name), float(score)
    else:
        best_name = None
        best_score = 0.0
        for name, choice in choices.items():
            score = difflib.SequenceMatcher(None, compact_carrier, choice).ratio() * 100
            if score > best_score:
                best_name, best_score = name, score
        if best_score >= 94:
            return True, best_name, best_score
    return False, None, None


def _is_mixed_vendor(carrier: str) -> bool:
    return has_any(carrier, MIXED_SERVICE_VENDOR_MARKERS)


def _is_airline_carrier(carrier: str) -> tuple[bool, str]:
    c = norm(carrier)
    if not c:
        return False, ""
    if has_any(c, KNOWN_AIRLINES):
        return True, "перевозчик совпал с известной авиакомпанией"
    fuzzy_ok, name, score = _fuzzy_known_airline(c)
    if fuzzy_ok:
        return True, f"перевозчик похож на авиакомпанию: {name} ({score:.0f})"
    if ORG_AIRLINE_RE.search(c):
        return True, "перевозчик содержит признак авиакомпании"
    # Limited form for carriers like `Air ...`; not used in details.
    if re.search(r"\bair\s+[a-zа-я]{3,}\b", c, re.IGNORECASE):
        return True, "перевозчик похож на авиаперевозчика Air ..."
    return False, ""


def _has_airline_in_details(details: str) -> bool:
    return has_any(details, KNOWN_AIRLINES) or bool(ORG_AIRLINE_RE.search(norm(details)))


def _has_explicit_lodging(details: str) -> bool:
    return has_any(details, EXPLICIT_LODGING_DETAILS)


def _has_soft_lodging(details: str) -> bool:
    return has_any(details, SOFT_LODGING_DETAILS)


def _looks_like_lodging_by_structure(carrier: str, details: str) -> bool:
    """Conservative structural hotel heuristic.

    Used only when no airline/rail/ground marker has already matched. Typical
    real rows look like: `26.03-27.03.2025 Казань, Амакс Сафар, ФИО`.
    """
    vendor_ok = _is_mixed_vendor(carrier) or has_any(carrier, HOTEL_VENDOR_MARKERS)
    has_range = looks_like_date_range(details)
    not_route = not looks_like_route(details)
    has_object_shape = details.count(",") >= 1 or _has_soft_lodging(details)
    return bool(vendor_ok and has_range and not_route and has_object_shape)


def classify_category(carrier: str, details: str) -> tuple[str, str, bool]:
    """Classify one booking row.

    Return `(category, reason, needs_review)`. The order is deliberately
    conservative and field-aware: carrier-airline checks run before rail checks
    in details, mixed-service vendors are never classified by vendor name alone,
    and soft hotel hints require context.
    """
    c = norm(carrier)
    d = norm(details)
    combined = f"{c} {d}"

    # Explicit lodging service markers are strong enough even for mixed vendors.
    if _has_explicit_lodging(d):
        return CATEGORY_HOTEL, "в деталях есть явный признак проживания", False

    # Carrier field is authoritative for airlines, except generic mixed vendors.
    if not _is_mixed_vendor(c):
        air_ok, air_reason = _is_airline_carrier(c)
        if air_ok:
            return CATEGORY_AIR, air_reason, False

    # Rail carrier comes before details markers.
    if has_any(c, RAIL_CARRIER_MARKERS):
        return CATEGORY_RAIL, "перевозчик содержит ЖД-маркер", False

    # Ground transport is intentionally included in ЖД in this three-category report.
    # Do this before soft lodging so `трансфер до отеля` is not counted as hotel.
    if has_any(combined, GROUND_MARKERS):
        return CATEGORY_RAIL, "наземный транспорт включен в ЖД для совместимости отчета", False

    if has_any(combined, RAIL_DETAIL_MARKERS):
        return CATEGORY_RAIL, "в строке есть ЖД-маркер", False

    # Details can classify aviation when they mention a specific airline.
    # Pure city-city direction without airline/train marker remains Unknown.
    if _has_airline_in_details(d) and looks_like_route(d):
        return CATEGORY_AIR, "в деталях есть авиакомпания и маршрут", True

    if _looks_like_lodging_by_structure(c, d):
        return CATEGORY_HOTEL, "вероятное проживание: поставщик + период + город/объект", True

    # Soft lodging words without vendor/date context are still useful, but require review.
    if _has_soft_lodging(d) and not looks_like_route(d):
        return CATEGORY_HOTEL, "вероятное проживание по гостиничному маркеру в деталях", True

    return CATEGORY_UNKNOWN, "нет надежного положительного признака категории", True
