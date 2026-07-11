from __future__ import annotations

from datetime import date
import math
import re
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
