from __future__ import annotations

from datetime import date
from typing import Any

from ..config import CARRIER_RE, IATA_RE
from ..errors import CliError


def normalize_iata(value: str, field: str = "IATA") -> str:
    code = value.strip().upper()
    if not IATA_RE.match(code):
        raise CliError(
            f"{field} must be a 3-letter IATA code, got {value!r}",
            error_type="validation_error",
        )
    return code


def normalize_carrier_code(value: str, field: str = "carrier") -> str:
    code = str(value or "").strip().upper()
    if not CARRIER_RE.match(code):
        raise CliError(
            f"{field} must be a 2-3 character airline code, got {value!r}",
            error_type="validation_error",
        )
    return code


def _next_future_occurrence(month: int, day: int, today: date) -> date | None:
    for year in range(today.year, today.year + 5):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def parse_iso_date(value: str, field: str, *, today: date | None = None) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CliError(
            f"{field} must be YYYY-MM-DD, got {value!r}", error_type="validation_error"
        ) from exc

    current_date = today or date.today()
    if parsed < current_date:
        suggestion = _next_future_occurrence(parsed.month, parsed.day, current_date)
        message = f"{field} is in the past: {parsed.isoformat()}. Today is {current_date.isoformat()}."
        details = {
            "field": field,
            "reason": "past_date",
            "value": parsed.isoformat(),
            "today": current_date.isoformat(),
        }
        if suggestion is not None:
            message += f" Did you mean {suggestion.isoformat()}?"
            details["suggested_date"] = suggestion.isoformat()
        raise CliError(message, error_type="validation_error", details=details)
    return parsed


def price_value(data: dict[str, Any]) -> int | None:
    raw = data.get("price")
    if raw is None and isinstance(data.get("pricing"), dict):
        raw = data["pricing"].get("price")
    if raw is None:
        return None
    try:
        return max(0, int(float(str(raw).replace(" ", "").replace(",", ""))))
    except (TypeError, ValueError):
        return None


def currency_value(data: dict[str, Any]) -> str | None:
    if isinstance(data.get("currency"), str):
        return data["currency"]
    pricing = data.get("pricing")
    if isinstance(pricing, dict) and isinstance(pricing.get("currency"), str):
        return pricing["currency"]
    return None


def numeric_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return value
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed
