# formatters.py
"""Human-readable formatting for flight search results.

Produces Telegram-HTML formatted output with Russian-localized dates,
durations, and transfer info (emoji for night transfers and visa requirements).

Adapted from bot/modules/flights/formatters.py — decoupled from bot config/models.
"""
from __future__ import annotations

from datetime import datetime, timezone

MONTH_NAMES_SHORT = [
    "", "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]

MONTH_NAMES_FULL = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _parse_iso(iso_time: str) -> datetime | None:
    """Parse ISO datetime string, tolerating trailing Z."""
    if not iso_time:
        return None
    try:
        return datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def format_time(iso_time: str) -> str:
    """Format ISO datetime as HH:MM, e.g. '06:30'."""
    dt = _parse_iso(iso_time)
    return dt.strftime("%H:%M") if dt else "—"


def format_date(iso_time: str) -> str:
    """Format ISO datetime as '5 май', e.g. '5 май'."""
    dt = _parse_iso(iso_time)
    if not dt:
        return "—"
    return f"{dt.day} {MONTH_NAMES_SHORT[dt.month]}"


def format_date_full(iso_time: str) -> str:
    """Format ISO datetime as '5 мая 2026', e.g. proper Russian genitive."""
    dt = _parse_iso(iso_time)
    if not dt:
        return "—"
    return f"{dt.day} {MONTH_NAMES_FULL[dt.month]} {dt.year}"


def format_duration(minutes: int) -> str:
    """Format duration in minutes as '2ч 35м'."""
    if minutes <= 0:
        return "—"
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}ч {mins}м"
    if hours:
        return f"{hours}ч"
    return f"{mins}м"


def format_transfer(airport_name: str, duration_min: int,
                    night_transfer: bool = False,
                    visa_required: bool = False) -> str:
    """Format transfer info as '🔄 Пересадка в Москва (SVO) · 2ч 35м · 🌙 ночная · ⚠️ виза'."""
    parts = [f"🔄 Пересадка в {airport_name}"]

    # Duration
    if duration_min > 0:
        parts.append(format_duration(duration_min))

    if night_transfer:
        parts.append("🌙 ночная")
    if visa_required:
        parts.append("⚠️ виза")

    return " · ".join(parts)


def format_price(price: int, currency: str = "RUB") -> str:
    """Format price with currency sign. RUB → '12 500 ₽', others → '12 500 USD'."""
    # Thousand separator: space for Russian readability
    formatted = f"{price:,}".replace(",", "\u00A0")  # non-breaking space
    currency_signs = {"RUB": "₽", "USD": "$", "EUR": "€"}
    if currency in currency_signs:
        return f"{formatted} {currency_signs[currency]}"
    return f"{formatted} {currency}"


def format_transfers_count(transfers: int) -> str:
    """Format transfer count: 0 → 'Прямой', 1 → '1 пересадка', 2+ → 'N пересадки/пересадок'."""
    if transfers == 0:
        return "Прямой"
    if transfers == 1:
        return "1 пересадка"
    if 2 <= transfers <= 4:
        return f"{transfers} пересадки"
    return f"{transfers} пересадок"


# --- High-level: build formatted HTML for full flight results ---

def format_flight_results(
    flights: list,  # list of FlightOut dicts
    *,
    origin: str,
    origin_name: str,
    destination: str,
    destination_name: str,
    departure_date: str,
    return_date: str | None = None,
    currency: str = "RUB",
    direct_not_available: bool = False,
    warnings: list[str] | None = None,
) -> str:
    """Build a Telegram-HTML formatted string for flight search results.

    Args:
        flights: List of FlightOut.model_dump() dicts (with formatted fields).
        origin: IATA code, e.g. 'SVX'.
        origin_name: Human name, e.g. 'Екатеринбург (SVX)'.
        destination: IATA code, e.g. 'MOW'.
        destination_name: Human name, e.g. 'Москва (MOW)'.
        departure_date: ISO date string, e.g. '2026-05-01'.
        return_date: Optional ISO date string for round-trip.
        currency: Currency code.
        direct_not_available: True if direct_only was requested but only transfers found.
        warnings: Additional warnings to include.

    Returns:
        Telegram-HTML formatted string.
    """
    warnings = warnings or []

    # Parse date for header
    dep_dt = _parse_iso(departure_date)
    date_str = format_date_full(departure_date) if dep_dt else departure_date

    route = f"{origin_name} → {destination_name}"
    header = f"✈️ <b>{route}</b>\n📅 {date_str}"
    if return_date:
        ret_dt = _parse_iso(return_date)
        ret_str = format_date_full(return_date) if ret_dt else return_date
        header += f" — {ret_str}"

    if not flights:
        lines = [
            header,
            "",
            "Рейсы не найдены.",
            "Попробуйте изменить даты или направление.",
        ]
        return "\n".join(lines)

    lines = [header, f"Найдено вариантов: {len(flights)}"]

    if direct_not_available:
        lines.append("")
        lines.append("⚠️ Прямых рейсов нет, показаны с пересадками")

    lines.append("")

    for i, flight in enumerate(flights, 1):
        lines.append(_format_single_flight(i, flight, currency))

    # Cache/warranty note
    lines.append("")
    lines.append("📌 Цены из кэша, не гарантированы. Перед покупкой проверьте на агрегаторе.")

    return "\n".join(lines)


def _format_single_flight(index: int, flight: dict, currency: str) -> str:
    """Format one FlightOut dict into an HTML block."""
    price_str = format_price(flight.get("price", 0), currency)
    transfers_str = format_transfers_count(flight.get("transfers", 0))

    parts = [f"<b>{index}. 💰 {price_str}</b> | {transfers_str}"]

    # Duration: show per-segment for round-trip, single for one-way
    dur = flight.get("duration_min")
    has_inbound = bool(flight.get("inbound"))
    dur_str = format_duration(dur) if dur else ""
    if dur_str:
        if has_inbound:
            # Round-trip: outbound and inbound segments each have their own duration
            ob = flight.get("outbound")
            ib = flight.get("inbound")
            ob_dur = ob.get("duration_formatted") if ob else ""
            ib_dur = ib.get("duration_formatted") if ib else ""
            if ob_dur and ib_dur:
                parts.append(f"⏱ туда {ob_dur}, обратно {ib_dur}")
            else:
                parts.append(f"⏱ {dur_str}")
        else:
            parts.append(f"⏱ {dur_str}")

    # Airline
    airline_name = flight.get("airline_name") or flight.get("airline") or ""
    if airline_name:
        parts.append(f"✈️ {airline_name}")

    header_line = " · ".join(parts) if len(parts) > 1 else parts[0]
    lines = [header_line]

    # Outbound segment
    outbound = flight.get("outbound")
    if outbound:
        lines.extend(_format_segment(outbound, label="Туда" if flight.get("inbound") else "Рейс"))

    # Inbound segment
    inbound = flight.get("inbound")
    if inbound:
        lines.extend(_format_segment(inbound, label="Обратно"))

    # Booking URL
    booking_url = flight.get("booking_url")
    if booking_url:
        lines.append(f'🔗 <a href="{booking_url}">Проверить цену / Купить</a>')

    return "\n".join(lines)


def _format_segment(segment: dict, label: str = "") -> list[str]:
    """Format a SegmentOut dict into HTML lines."""
    lines = []

    legs = segment.get("legs", [])
    transfers = segment.get("transfers", [])

    dep_formatted = segment.get("departure_formatted", "")
    arr_formatted = segment.get("arrival_formatted", "")
    dur = segment.get("duration_min")
    dur_str = format_duration(dur) if dur else ""

    # For single-leg direct flights, skip the redundant segment header —
    # the flight header line already has price/transfers/duration.
    # Multi-leg flights get a labeled segment header with time range + duration.
    is_direct = len(legs) == 1 and not transfers

    if label and not is_direct:
        time_info = f"{dep_formatted}" if dep_formatted else ""
        if arr_formatted:
            time_info += f" → {arr_formatted}"
        dur_info = f" · {dur_str}" if dur_str else ""
        lines.append(f"  <b>{label}:</b> {time_info}{dur_info}")

    # Legs and transfers interleaved
    for i, leg in enumerate(legs):
        leg_line = _format_leg(leg)
        lines.append(f"  {leg_line}")

        # Transfer after this leg (if any)
        if i < len(transfers):
            t = transfers[i]
            t_formatted = t.get("formatted", "")
            if t_formatted:
                lines.append(f"    {t_formatted}")

    return lines


def _format_leg(leg: dict) -> str:
    """Format a LegOut dict into a single line."""
    origin_name = leg.get("origin_name") or leg.get("origin", "")
    dest_name = leg.get("destination_name") or leg.get("destination", "")
    dep_time = leg.get("departure_formatted") or format_time(leg.get("departure_at", ""))
    arr_time = leg.get("arrival_formatted") or format_time(leg.get("arrival_at", ""))

    carrier = leg.get("carrier_name") or leg.get("carrier", "")
    flight_num = leg.get("flight_number", "")
    flight_info = f"{carrier} {flight_num}".strip() if carrier else flight_num

    aircraft = leg.get("aircraft_name") or leg.get("aircraft_code", "")
    dur = leg.get("duration_min")
    dur_str = format_duration(dur) if dur else ""

    parts = [f"{origin_name} {dep_time} → {dest_name} {arr_time}"]
    if flight_info:
        parts.append(flight_info)
    if aircraft:
        parts.append(aircraft)
    if dur_str:
        parts.append(dur_str)

    return " · ".join(parts)