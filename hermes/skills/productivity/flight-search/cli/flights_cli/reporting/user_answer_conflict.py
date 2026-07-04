from __future__ import annotations

from typing import Any

from .user_answer_catalog import (
    catalog_item,
    render_catalog_answer,
    render_catalog_item,
)


def _unique_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _constraint_records(direction: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in direction.get("constraints") or []
        if isinstance(item, dict)
    ]


def _first_constraint_value(
    constraints: list[dict[str, Any]], key: str
) -> Any | None:
    for item in constraints:
        if item.get("type") == key:
            return item.get("value")
    return None


def _schedule_departure_hours(direction: dict[str, Any]) -> list[int]:
    hours: list[int] = []
    schedule = (
        direction.get("direct_schedule")
        if isinstance(direction.get("direct_schedule"), dict)
        else {}
    )
    for item in schedule.get("items") or []:
        if not isinstance(item, dict):
            continue
        directions = item.get("directions") if isinstance(item.get("directions"), dict) else {}
        for detail in directions.values():
            if not isinstance(detail, dict):
                continue
            segments = detail.get("segments")
            if not isinstance(segments, list) or not segments:
                continue
            departure = str(segments[0].get("departure_at") or "")
            if len(departure) >= 13 and departure[11:13].isdigit():
                hours.append(int(departure[11:13]))
    return hours


def _time_found_phrase(direction: dict[str, Any]) -> str:
    hours = _schedule_departure_hours(direction)
    if hours and max(hours) < 12:
        return "утром"
    return "раньше"


def _carrier_text(value: Any) -> str:
    if isinstance(value, list):
        carriers = [str(item).strip().upper() for item in value if str(item).strip()]
    else:
        carriers = [str(value).strip().upper()] if str(value).strip() else []
    return "/".join(carriers)


def _conflict_caveat(direction: dict[str, Any]) -> str:
    constraints = _constraint_records(direction)
    first_departure_after = _first_constraint_value(
        constraints, "first_departure_after"
    )
    if first_departure_after:
        found = _time_found_phrase(direction)
        return (
            f"прямых рейсов после {first_departure_after} нет; "
            f"прямые есть {found} — показаны ниже."
        )
    only_carriers = _first_constraint_value(constraints, "only_carriers")
    if only_carriers:
        carrier_text = _carrier_text(only_carriers)
        if carrier_text:
            return (
                f"прямых рейсов {carrier_text} нет; "
                "прямые есть у других перевозчиков — показаны ниже."
            )
    return (
        "прямые рейсы есть, но они нарушают явное ограничение запроса — "
        "показаны ниже."
    )


def _absence_line(direction: dict[str, Any]) -> str:
    constraints = _constraint_records(direction)
    first_departure_after = _first_constraint_value(
        constraints, "first_departure_after"
    )
    if first_departure_after:
        return f"и с одной пересадкой после {first_departure_after} вариантов нет."
    only_carriers = _first_constraint_value(constraints, "only_carriers")
    carrier_text = _carrier_text(only_carriers)
    if carrier_text:
        return f"и с одной пересадкой у {carrier_text} вариантов нет."
    return "и с одной пересадкой вариантов под ограничение не нашлось."


def build_constraint_conflict_payload(
    raw_conflict: dict[str, Any] | None,
    *,
    is_round_trip_request: bool,
) -> dict[str, Any] | None:
    if not isinstance(raw_conflict, dict) or raw_conflict.get("present") is not True:
        return None
    directions: list[dict[str, Any]] = []
    for raw_direction in raw_conflict.get("directions") or []:
        if not isinstance(raw_direction, dict):
            continue
        schedule_options = [
            item
            for item in raw_direction.get("direct_schedule") or []
            if isinstance(item, dict)
        ]
        schedule_items = [
            catalog_item(option, number=index, is_round_trip_request=False)
            for index, option in enumerate(schedule_options, start=1)
        ]
        direction = {
            "direction": raw_direction.get("direction"),
            "constraints": _constraint_records(raw_direction),
            "fallback": raw_direction.get("fallback")
            if isinstance(raw_direction.get("fallback"), dict)
            else {},
            "direct_schedule": {
                "presentation": {
                    "style": "numbered_inline_itinerary_v1",
                    "language": "ru",
                    "max_items": max(1, len(schedule_items)),
                },
                "items": schedule_items,
            },
        }
        direction["caveat"] = _conflict_caveat(direction)
        direction["absence_line"] = _absence_line(direction)
        directions.append(direction)
    if not directions:
        return None
    return {
        "schema_version": "flight_constraint_conflict.v1",
        "present": True,
        "directions": directions,
        "fallback": raw_conflict.get("fallback")
        if isinstance(raw_conflict.get("fallback"), dict)
        else {},
    }


def _conflict_checks(caveat_context: dict[str, Any]) -> list[str]:
    checks = [
        str(caveat_context.get("negative_wording") or "").strip()
        or "не нашёл в выполненных live/probe источниках; это не доказательство отсутствия вне границ источника",
        "финальную цену, тариф, багаж и правила проверить на booking screen.",
    ]
    if caveat_context.get("not_executed"):
        checks.append("coverage неполное: не все live-проверки выполнены.")
    if caveat_context.get("provider_failures"):
        checks.append(
            "часть live-проверок упала — если это влияет на выбор, повторить поиск перед покупкой."
        )
    return _unique_text(checks)


def _render_schedule_item(item: dict[str, Any]) -> str:
    lines = render_catalog_item(item).splitlines()
    if not lines:
        return ""
    number = int(item.get("number") or 0)
    prefix = f"{number}. "
    if number > 0 and lines[0].startswith(prefix):
        lines[0] = f"прямой {number}: {lines[0][len(prefix):]}"
    return "\n".join(lines)


def render_constraint_conflict_answer(
    route: dict[str, Any],
    catalog: dict[str, Any],
    constraint_conflict: dict[str, Any],
    *,
    caveat_context: dict[str, Any],
    gateway_summary: str | None = None,
) -> str:
    lines: list[str] = []
    directions = [
        item
        for item in constraint_conflict.get("directions") or []
        if isinstance(item, dict)
    ]
    for caveat in _unique_text([str(item.get("caveat") or "") for item in directions]):
        lines.append(caveat)

    for direction in directions:
        schedule = (
            direction.get("direct_schedule")
            if isinstance(direction.get("direct_schedule"), dict)
            else {}
        )
        items = [item for item in schedule.get("items") or [] if isinstance(item, dict)]
        if not items:
            continue
        if lines:
            lines.append("")
        lines.append("Прямые рейсы, которые не проходят ограничение:")
        lines.extend(_render_schedule_item(item) for item in items)

    if catalog.get("items"):
        if lines:
            lines.append("")
        lines.append(
            render_catalog_answer(
                route,
                catalog,
                caveat_context=caveat_context,
                gateway_summary=gateway_summary,
            )
        )
    else:
        absence_lines = _unique_text(
            [str(item.get("absence_line") or "") for item in directions]
        )
        if absence_lines:
            if lines:
                lines.append("")
            lines.extend(absence_lines)
        if gateway_summary:
            lines.append("")
            lines.append(gateway_summary)
        checks = _conflict_checks(caveat_context)
        if checks:
            lines.append("")
            lines.append("**Проверить перед покупкой**")
            lines.extend(f"- {line}" for line in checks)
    return "\n".join(lines).strip()
