from __future__ import annotations

from datetime import date
from typing import Any

from ..config import CARRIER_RE, IATA_RE, RISK_PROFILES
from ..errors import CliError

def normalize_iata(value: str, field: str = "IATA") -> str:
    code = value.strip().upper()
    if not IATA_RE.match(code):
        raise CliError(f"{field} must be a 3-letter IATA code, got {value!r}", error_type="validation_error")
    return code


def normalize_carrier_code(value: str, field: str = "carrier") -> str:
    code = str(value or "").strip().upper()
    if not CARRIER_RE.match(code):
        raise CliError(f"{field} must be a 2-3 character airline code, got {value!r}", error_type="validation_error")
    return code


def normalize_carrier_codes(values: list[str] | None, field: str) -> set[str]:
    return {normalize_carrier_code(value, field) for value in (values or [])}


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
        raise CliError(f"{field} must be YYYY-MM-DD, got {value!r}", error_type="validation_error") from exc

    current_date = today or date.today()
    if parsed < current_date:
        suggestion = _next_future_occurrence(parsed.month, parsed.day, current_date)
        message = f"{field} is in the past: {parsed.isoformat()}. Today is {current_date.isoformat()}."
        if suggestion is not None:
            message += f" Did you mean {suggestion.isoformat()}?"
        raise CliError(message, error_type="validation_error")
    return parsed


def clamp_score(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def normalize_profile(value: str | None) -> str:
    profile = (value or "balanced").strip().lower()
    if profile not in RISK_PROFILES:
        raise CliError(
            f"profile must be one of {', '.join(sorted(RISK_PROFILES))}, got {value!r}",
            error_type="validation_error",
        )
    return profile


def risk_grade(score: int) -> str:
    if score <= 20:
        return "excellent"
    if score <= 40:
        return "good"
    if score <= 70:
        return "risky"
    return "reject"


def is_reject_score(score: int) -> bool:
    return score > 70


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


def normalize_transfer(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    transfer: dict[str, Any] = {}
    for key in ("at", "to", "country_code"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            transfer[key] = value.strip().upper()
    duration = raw.get("duration_seconds")
    if duration is not None:
        try:
            transfer["duration_seconds"] = max(0, int(float(duration)))
        except (TypeError, ValueError):
            pass
    for key in ("night_transfer", "visa_required"):
        if key in raw:
            transfer[key] = bool(raw.get(key))
    return transfer or None


def normalize_transfers(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    transfers = []
    for item in raw:
        transfer = normalize_transfer(item)
        if transfer is not None:
            transfers.append(transfer)
    return transfers
