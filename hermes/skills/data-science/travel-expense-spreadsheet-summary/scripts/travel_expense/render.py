from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .money import format_money
from .text import text_value


def render_json(result: Mapping[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def render_markdown(result: Mapping[str, Any], *, show_review: bool = False) -> str:
    lines = [
        f"Посчитал по файлу `{result['source_file']}`.",
        "",
        "| Категория | Бронирований | Сумма |",
        "|---|---:|---:|",
    ]
    for row in result["summary"]:
        lines.append(f"| **{row['category']}** | {row['bookings']} | {row['amount_display']} |")

    verification = result["verification"]
    lines.append("")
    if verification["source_total_sum"] is None:
        if verification["source_total_present"]:
            lines.append("Сверка: итоговая строка найдена, но сумма в ней не распознана как число.")
        else:
            lines.append("Сверка: итоговая строка с числовой суммой не найдена; итог рассчитан по строкам бронирований.")
    elif verification["source_total_sum_matches"]:
        lines.append(f"Сверка: сумма по категориям совпадает с итоговой строкой — {format_money(float(verification['source_total_sum']))}.")
    else:
        lines.append(
            "Сверка: сумма по категориям не совпадает с итоговой строкой — "
            f"расчёт {format_money(float(verification['category_sum']))}, "
            f"исходный итог {format_money(float(verification['source_total_sum']))}."
        )

    if verification.get("source_total_count_matches") is False:
        lines.append(
            "Сверка количества: есть расхождение — "
            f"расчёт {verification['booking_rows']}, исходный счетчик {verification['source_total_count']}."
        )

    if result.get("warnings"):
        lines.append("")
        lines.append("Предупреждения:")
        for warning in result["warnings"]:
            lines.append(f"- {warning.get('type')}: {warning.get('message', '')}")

    review_rows = result.get("review_rows", [])
    if show_review and review_rows:
        lines.extend([
            "",
            "Строки для проверки:",
            "",
            "| Строка | Категория | Сумма | Перевозчик | Детали | Причина | Fingerprint |",
            "|---:|---|---:|---|---|---|---|",
        ])
        for item in review_rows:
            carrier = text_value(item.get("carrier"))[:55].replace("|", " ")
            details = text_value(item.get("details"))[:95].replace("|", " ")
            reason = text_value(item.get("reason")).replace("|", " ")
            lines.append(
                f"| {item['row_number']} | {item['category']} | {item['amount_display']} | "
                f"{carrier} | {details} | {reason} | `{item['fingerprint']}` |"
            )
    return "\n".join(lines)


def write_output(path: Path | None, content: str) -> None:
    if path:
        path.write_text(content, encoding="utf-8")
