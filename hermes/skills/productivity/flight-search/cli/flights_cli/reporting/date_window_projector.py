from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..domain.vocabulary import Leg

_COMPACT_OFFER_FIELDS = (
    "carrier",
    "flight_number",
    "origin",
    "destination",
    "departure_at",
    "arrival_at",
    "duration_min",
    "price",
    "currency",
    "provider",
)

_DEFAULT_MAX_OFFERS_PER_DATE = 20


def _window_dates(plan: dict[str, Any]) -> list[str]:
    dates_meta = plan.get("dates") if isinstance(plan.get("dates"), dict) else {}
    window_end_text = dates_meta.get("window_end")
    depart_text = dates_meta.get("depart")
    if not window_end_text or not depart_text:
        return []
    try:
        depart = date.fromisoformat(str(depart_text))
        window_end = date.fromisoformat(str(window_end_text))
    except ValueError:
        return []
    if window_end < depart:
        return []
    return [
        (depart + timedelta(days=offset)).isoformat()
        for offset in range((window_end - depart).days + 1)
    ]


def _compact_offer(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        field: offer[field]
        for field in _COMPACT_OFFER_FIELDS
        if offer.get(field) is not None
    }


def _date_status(
    *,
    offer_count: int,
    ok_probe_count: int,
    failed_probe_count: int,
    skipped_probe_count: int,
) -> str:
    if offer_count > 0:
        return "direct_offers"
    if ok_probe_count > 0:
        return (
            "no_direct_offers_with_failures"
            if failed_probe_count > 0
            else "no_direct_offers"
        )
    if failed_probe_count > 0:
        return "probe_failed"
    if skipped_probe_count > 0:
        return "not_probed"
    return "not_probed"


def build_date_window_inventory(
    plan: dict[str, Any],
    segment_searches: list[dict[str, Any]],
    segment_results: list[dict[str, Any]],
    *,
    max_offers_per_date: int = _DEFAULT_MAX_OFFERS_PER_DATE,
) -> dict[str, Any] | None:
    """Project per-date direct inventory evidence for a bounded date window.

    Returns ``None`` for ordinary single-date searches. The projection reads only
    executed direct-leg evidence; empty provider output stays provider-empty
    evidence, not structural route absence.
    """

    window = _window_dates(plan)
    if not window:
        return None

    summaries_by_date: dict[str, list[dict[str, Any]]] = {
        date_text: [] for date_text in window
    }
    for item in segment_searches or []:
        if not isinstance(item, dict) or item.get("leg") != Leg.DIRECT_OUTBOUND:
            continue
        date_text = str(item.get("date") or "")
        if date_text in summaries_by_date:
            summaries_by_date[date_text].append(item)

    offers_by_date: dict[str, list[dict[str, Any]]] = {
        date_text: [] for date_text in window
    }
    for result in segment_results or []:
        if not isinstance(result, dict) or result.get("leg") != Leg.DIRECT_OUTBOUND:
            continue
        date_text = str(result.get("date") or "")
        if date_text not in offers_by_date:
            continue
        for offer in result.get("offers") or []:
            if isinstance(offer, dict):
                offers_by_date[date_text].append(_compact_offer(offer))

    entries: list[dict[str, Any]] = []
    for date_text in window:
        summaries = summaries_by_date[date_text]
        ok_probes = [item for item in summaries if str(item.get("status")) == "ok"]
        failed_probes = [
            item for item in summaries if str(item.get("status")) in {"error", "failed"}
        ]
        skipped_probes = [
            item for item in summaries if str(item.get("status")) == "skipped"
        ]
        offers = sorted(
            offers_by_date[date_text],
            key=lambda offer: str(offer.get("departure_at") or ""),
        )
        omitted = max(0, len(offers) - max_offers_per_date)
        entry: dict[str, Any] = {
            "date": date_text,
            "status": _date_status(
                offer_count=len(offers),
                ok_probe_count=len(ok_probes),
                failed_probe_count=len(failed_probes),
                skipped_probe_count=len(skipped_probes),
            ),
            "offer_count": len(offers),
            "probe_count": len(summaries),
            "failed_probe_count": len(failed_probes),
            "offers": offers[:max_offers_per_date],
        }
        if omitted:
            entry["omitted_offer_count"] = omitted
        if skipped_probes:
            entry["skip_reasons"] = sorted(
                {
                    str(item.get("reason"))
                    for item in skipped_probes
                    if item.get("reason")
                }
            )
        entries.append(entry)

    return {
        "boundary": "provider_live_only",
        "negative_evidence": "provider_empty_only_not_route_absence",
        "window": {"start": window[0], "end": window[-1], "days": len(window)},
        "dates": entries,
    }
