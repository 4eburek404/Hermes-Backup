"""Покрытие окна дат: что нашлось в каждый день окна.

Сами предложения сюда больше не копируются — они лежат в `options`, и до
`.v1` одно и то же приезжало в ответ дважды. Здесь остался счёт и причина,
по которой день пуст: провайдер не нашёл, проба упала или до дня не дошли.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from ..domain.direct_inventory import DirectInventoryProbe
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
    direct_inventory: Sequence[DirectInventoryProbe],
) -> dict[str, Any] | None:
    """Покрытие окна по дням, или ``None`` для обычного поиска на одну дату.

    Читается только исполненное прямое свидетельство: пустая выдача
    провайдера остаётся пустой выдачей, а не доказательством отсутствия
    маршрута.
    """

    window = _window_dates(depart, window_end)
    if not window:
        return None

    probes_by_date: dict[str, list[DirectInventoryProbe]] = {
        date_text: [] for date_text in window
    }
    for probe in direct_inventory:
        if probe.leg != Leg.DIRECT_OUTBOUND:
            continue
        if probe.date in probes_by_date:
            probes_by_date[probe.date].append(probe)

    dates: list[dict[str, Any]] = []
    for date_text in window:
        probes = probes_by_date[date_text]
        statuses = [probe.status for probe in probes]
        offer_count = sum(probe.offer_count for probe in probes)
        dates.append(
            {
                "date": date_text,
                "status": _date_status(
                    offer_count=offer_count,
                    ok_probe_count=statuses.count("ok"),
                    failed_probe_count=sum(
                        1 for status in statuses if status in {"error", "failed"}
                    ),
                    skipped_probe_count=statuses.count("skipped"),
                ),
                "offer_count": offer_count,
            }
        )
    return {"start": window[0], "end": window[-1], "dates": dates}


__all__ = ["build_date_window"]
