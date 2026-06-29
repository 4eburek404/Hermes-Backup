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
    HOTEL_NAME_HINTS,
    HOTEL_VENDOR_MARKERS,
    KNOWN_AIRLINES,
    MIXED_SERVICE_VENDOR_MARKERS,
    RAIL_MARKERS,
)
from .text import ORG_AIRLINE_RE, has_any, looks_like_date_range, looks_like_route, norm, compact

try:
    from rapidfuzz import fuzz, process  # type: ignore
except Exception:  # pragma: no cover
    fuzz = None
    process = None


def _fuzzy_known_airline(carrier: str) -> tuple[bool, str | None, float | None]:
    compact_carrier = compact(carrier)
    if len(compact_carrier) < 5:
        return False, None, None
    choices = {name: compact(name) for name in KNOWN_AIRLINES if len(compact(name)) >= 5}
    if process is not None and fuzz is not None:
        match = process.extractOne(compact_carrier, choices, scorer=fuzz.WRatio, score_cutoff=92)
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
        if best_score >= 92:
            return True, best_name, best_score
    return False, None, None


def _is_airline_carrier(carrier: str, details: str) -> tuple[bool, str]:
    c = norm(carrier)
    if has_any(c, KNOWN_AIRLINES):
        return True, "перевозчик совпал с известной авиакомпанией"
    fuzzy_ok, name, score = _fuzzy_known_airline(c)
    if fuzzy_ok:
        return True, f"перевозчик похож на авиакомпанию: {name} ({score:.0f})"
    if ORG_AIRLINE_RE.search(c):
        return True, "перевозчик содержит признак авиакомпании"
    if re.search(r"\bair\s+[a-zа-я]{3,}\b", c, re.IGNORECASE) and looks_like_route(details):
        return True, "перевозчик похож на авиаперевозчика Air ... и детали похожи на маршрут"
    return False, ""


def _looks_like_lodging_by_structure(carrier: str, details: str) -> bool:
    vendor_ok = has_any(carrier, MIXED_SERVICE_VENDOR_MARKERS) or has_any(carrier, HOTEL_VENDOR_MARKERS)
    has_range = looks_like_date_range(details)
    comma_structure = details.count(",") >= 1
    not_route = not looks_like_route(details)
    hotel_name_hint = has_any(details, HOTEL_NAME_HINTS)
    return bool(vendor_ok and has_range and not_route and (comma_structure or hotel_name_hint))


def classify_category(carrier: str, details: str) -> tuple[str, str, bool]:
    c = norm(carrier)
    d = norm(details)
    combined = f"{c} {d}"

    if has_any(d, EXPLICIT_LODGING_DETAILS):
        return CATEGORY_HOTEL, "в деталях есть явный признак проживания", False

    air_ok, air_reason = _is_airline_carrier(c, d)
    if air_ok:
        return CATEGORY_AIR, air_reason, False

    if has_any(c, RAIL_MARKERS):
        return CATEGORY_RAIL, "перевозчик содержит ЖД-маркер", False

    if has_any(combined, GROUND_MARKERS):
        return CATEGORY_RAIL, "наземный транспорт включен в ЖД для совместимости отчета", True

    if has_any(combined, RAIL_MARKERS):
        return CATEGORY_RAIL, "в строке есть ЖД-маркер", False

    if has_any(d, KNOWN_AIRLINES) and looks_like_route(d):
        return CATEGORY_AIR, "в деталях есть авиакомпания и маршрут", True

    if _looks_like_lodging_by_structure(c, d):
        return CATEGORY_HOTEL, "вероятное проживание: поставщик + период + город/объект", True

    return CATEGORY_UNKNOWN, "нет надежного положительного признака категории", True
