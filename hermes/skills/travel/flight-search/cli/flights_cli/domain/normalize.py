from __future__ import annotations

from datetime import date
import math
import re
from typing import Any, Iterable, Mapping

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


def normalize_airport_scope(
    values: list[str] | tuple[str, ...] | None,
    field: str = "airport",
) -> list[str]:
    return sorted(
        {
            normalize_iata(str(value), field)
            for value in (values or [])
            if str(value).strip()
        }
    )


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


def numeric_or_none(value: Any) -> int | float | None:
    """Return a finite non-negative number, or ``None`` for unsafe input.

    Whitespace is accepted as a thousands separator. A dot is a decimal
    separator. A single comma is accepted as a decimal separator unless the
    spelling is ambiguous with a three-digit thousands group (for example,
    ``1,000``).
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            return None
        return int(value) if value.is_integer() else value

    text = "".join(str(value).split())
    if not text:
        return None
    if text.startswith("+"):
        text = text[1:]
    if not text or text.startswith("-"):
        return None
    if "," in text:
        if text.count(",") != 1 or "." in text:
            return None
        whole, fraction = text.split(",")
        if not whole.isdigit() or not fraction.isdigit():
            return None
        if 1 <= len(whole) <= 3 and len(fraction) == 3:
            return None
        text = f"{whole}.{fraction}"
    if re.fullmatch(r"\d+(?:\.\d+)?", text) is None:
        return None
    if "." not in text:
        return int(text)
    try:
        parsed = float(text)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_token(value: Any) -> str:
    return str(value or "").strip()


def ordered_unique(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        value = normalize_token(item)
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def compact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def stable_id(*parts: object, suffix: str | None = None) -> str:
    tokens = [
        normalize_token(part).replace(" ", "_")
        for part in parts
        if normalize_token(part)
    ]
    if suffix:
        tokens.append(normalize_token(suffix).replace(" ", "_"))
    return ":".join(tokens)


def price_amount(*sources: Mapping[str, Any]) -> int | float | None:
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        price = source.get("price")
        if isinstance(price, Mapping):
            amount = numeric_or_none(
                price.get("amount") or price.get("value") or price.get("total")
            )
            if amount is not None:
                return amount
        amount = numeric_or_none(price)
        if amount is not None:
            return amount
        amount = numeric_or_none(
            source.get("amount") or source.get("total_price") or source.get("value")
        )
        if amount is not None:
            return amount
    return None


def currency_value(*sources: Mapping[str, Any]) -> str | None:
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        price = source.get("price")
        if isinstance(price, Mapping):
            currency = normalize_code(price.get("currency"))
            if currency:
                return currency
        currency = normalize_code(source.get("currency"))
        if currency:
            return currency
    return None
