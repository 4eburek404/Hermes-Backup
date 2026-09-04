"""Покрытие окна дат: что нашлось в каждый день окна.

Сами предложения сюда больше не копируются — они лежат в `options`, и до
`.v1` одно и то же приезжало в ответ дважды. Здесь остался счёт и причина,
по которой день пуст: провайдер не нашёл, проба упала или до дня не дошли.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..domain.vocabulary import Leg


def _window_dates(depart_text: str | None, window_end_text: str | None) -> list[str]:
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


def build_date_window(
    depart: str | None,
    window_end: str | None,
    direct_inventory_searches: list[dict[str, Any]],
    direct_inventory_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Покрытие окна по дням, или ``None`` для обычного поиска на одну дату.

    Читается только исполненное прямое свидетельство: пустая выдача
    провайдера остаётся пустой выдачей, а не доказательством отсутствия
    маршрута.
    """

    window = _window_dates(depart, window_end)
    if not window:
        return None

    probes_by_date: dict[str, list[dict[str, Any]]] = {
        date_text: [] for date_text in window
    }
    for item in direct_inventory_searches or []:
        if not isinstance(item, dict) or item.get("leg") != Leg.DIRECT_OUTBOUND:
            continue
        date_text = str(item.get("date") or "")
        if date_text in probes_by_date:
            probes_by_date[date_text].append(item)

    offer_counts: dict[str, int] = {date_text: 0 for date_text in window}
    for result in direct_inventory_results or []:
        if not isinstance(result, dict) or result.get("leg") != Leg.DIRECT_OUTBOUND:
            continue
        date_text = str(result.get("date") or "")
        if date_text not in offer_counts:
            continue
        offer_counts[date_text] += sum(
            1 for offer in result.get("offers") or [] if isinstance(offer, dict)
        )

    dates: list[dict[str, Any]] = []
    for date_text in window:
        probes = probes_by_date[date_text]
        statuses = [str(item.get("status")) for item in probes]
        dates.append(
            {
                "date": date_text,
                "status": _date_status(
                    offer_count=offer_counts[date_text],
                    ok_probe_count=statuses.count("ok"),
                    failed_probe_count=sum(
                        1 for status in statuses if status in {"error", "failed"}
                    ),
                    skipped_probe_count=statuses.count("skipped"),
                ),
                "offer_count": offer_counts[date_text],
            }
        )
    return {"start": window[0], "end": window[-1], "dates": dates}


__all__ = ["build_date_window"]
