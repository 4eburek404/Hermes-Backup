from __future__ import annotations

import math
import re
from typing import Any, Iterable

FORMULA_ERROR_VALUES = {"#NAME?", "#VALUE!", "#REF!", "#DIV/0!", "#N/A", "#NULL!", "#NUM!"}

SINGLE_DATE_RE = re.compile(r"\b\d{1,2}[.]\d{1,2}[.]\d{2,4}\b")
DATE_RANGE_RE = re.compile(r"\b\d{1,2}[.]\d{1,2}(?:[.]\d{2,4})?\s*[-–—]\s*\d{1,2}[.]\d{1,2}(?:[.]\d{2,4})?\b")
ROUTE_DASH_RE = re.compile(r"[А-ЯA-ZЁ][А-ЯA-Zа-яa-zё .'-]{1,35}\s*[-–—]\s*[А-ЯA-ZЁ][А-ЯA-Zа-яa-zё .'-]{1,35}")
TOTAL_LABEL_RE = re.compile(r"\b(итог|итого|total|grand total)\b", re.IGNORECASE)
ORG_AIRLINE_RE = re.compile(r"\b(авиакомпан\w*|авиалини\w*|airlines?|airways)\b", re.IGNORECASE)


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def norm(value: Any) -> str:
    s = text_value(value).lower().replace("ё", "е")
    s = re.sub(r"[«»\"'`]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compact(value: Any) -> str:
    return re.sub(r"[^0-9a-zа-я]+", "", norm(value))


def has_any(text: str, markers: Iterable[str]) -> bool:
    source = norm(text)
    source_compact = compact(text)
    for marker in markers:
        marker_norm = norm(marker)
        marker_compact = compact(marker)
        if not marker_norm:
            continue
        if marker_norm in source or marker_compact in source_compact:
            return True
    return False


def is_formula_error(value: Any) -> bool:
    return text_value(value).upper() in FORMULA_ERROR_VALUES


def row_text(values: Iterable[Any]) -> str:
    return " ".join(text_value(value) for value in values if text_value(value))


def looks_like_date(value: Any) -> bool:
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return 35000 <= float(value) <= 60000
    return bool(SINGLE_DATE_RE.search(text_value(value)))


def looks_like_route(details: str) -> bool:
    raw = text_value(details)
    if not raw:
        return False
    has_dash_route = bool(ROUTE_DASH_RE.search(raw))
    has_date = bool(SINGLE_DATE_RE.search(raw) or re.search(r"\b\d{1,2}[.]\d{1,2}[.]?\d{0,4}\b", raw))
    return has_dash_route and has_date


def looks_like_date_range(text: str) -> bool:
    raw = text_value(text)
    if DATE_RANGE_RE.search(raw):
        return True
    return bool(re.search(r"\bс\s*\d{1,2}[.]\d{1,2}.*?[-–—].*?\d{1,2}[.]\d{1,2}", norm(raw), re.IGNORECASE))
