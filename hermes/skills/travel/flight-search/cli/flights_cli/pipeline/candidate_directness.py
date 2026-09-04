"""Признаки прямоты кандидата и запрошенные аэропорты.

Модуль остался от `direct_gate` — того, что решал, стоит ли открывать
шлюзовое плечо, по сырым ответам провайдера. Шлюзов больше нет, решения
тоже; уцелели три предиката, которые читают уже собранного кандидата.
Имя приведено к тому, что здесь на самом деле лежит.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.vocabulary import normalize_direction


def _airport_set(*values: Any) -> set[str]:
    return {str(value).strip().upper() for value in values if str(value or "").strip()}


def requested_airport_codes(
    value: str | None, airport_scope: list[str] | None = None
) -> set[str]:
    scoped = _airport_set(*(airport_scope or []))
    return scoped or _airport_set(value)


def candidate_is_direct(candidate: Mapping[str, Any]) -> bool:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return False
    return all(
        isinstance(journey, Mapping)
        and isinstance(journey.get("segments"), list)
        and len(journey["segments"]) == 1
        and isinstance(journey["segments"][0], Mapping)
        for journey in journeys
    )


def candidate_direct_mode_violation(
    candidate: Mapping[str, Any], direct_mode: Mapping[str, bool]
) -> str | None:
    active = {
        normalize_direction(direction)
        for direction, enabled in direct_mode.items()
        if enabled
    }
    if not active:
        return None
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return next(iter(active))
    for journey in journeys:
        if not isinstance(journey, Mapping):
            continue
        direction = normalize_direction(journey.get("direction"))
        if direction not in active:
            continue
        segments = [
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, Mapping)
        ]
        if len(segments) != 1:
            return direction
    return None


__all__ = [
    "candidate_direct_mode_violation",
    "candidate_is_direct",
    "requested_airport_codes",
]
