#!/usr/bin/env python3
"""Разведка Tutu MCP: вызвать, записать сырой ответ конвертом.

Живая сеть разрешена только этому файлу. Он говорит с сервером сырым JSON-RPC
через curl, а не через клиент проекта, потому что клиента ещё нет — фикстуры
должны существовать раньше кода, который их разбирает.

    python3 probe.py meta      # самоописание сервера
    python3 probe.py avia      # пробы search_avia
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

URL = "https://mcp.tutu.ru/mcp"
КОРЕНЬ = Path(__file__).resolve().parent
ФИКСТУРЫ = КОРЕНЬ / "fixtures"


def вызвать(метод: str, параметры: dict, таймаут: int = 90) -> dict:
    тело = {"jsonrpc": "2.0", "id": 1, "method": метод, "params": параметры}
    готово = subprocess.run(
        [
            "curl", "-sS", "-X", "POST", URL,
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json, text/event-stream",
            "-d", json.dumps(тело, ensure_ascii=False),
            "--max-time", str(таймаут),
        ],
        capture_output=True, text=True, timeout=таймаут + 15,
    )
    сырое = готово.stdout.strip()
    if not сырое:
        return {"_transport_error": готово.stderr.strip() or "пустой ответ"}
    try:
        return json.loads(сырое)
    except json.JSONDecodeError:
        # streamable-http может ответить SSE-кадрами: data: {...}
        строки = [s[6:] for s in сырое.splitlines() if s.startswith("data: ")]
        if строки:
            return json.loads(строки[-1])
        return {"_unparsed": сырое[:4000]}


def полезная_нагрузка(ответ: dict):
    """Туту прячет JSON строкой внутри текстового блока. Разворачиваем для чтения."""
    содержимое = (ответ.get("result") or {}).get("content")
    if not isinstance(содержимое, list) or not содержимое:
        return None
    текст = содержимое[0].get("text")
    if not isinstance(текст, str):
        return None
    try:
        return json.loads(текст)
    except json.JSONDecodeError:
        return {"_text": текст}


def записать(роль: str, группа: str, метод: str, аргументы: dict,
             ответ: dict, заметка: str, протухает: list[str] | None = None) -> dict:
    папка = ФИКСТУРЫ / группа
    папка.mkdir(parents=True, exist_ok=True)
    конверт = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "tutu",
        "method": метод,
        "tool": аргументы.get("name") if метод == "tools/call" else метод,
        "arguments": аргументы.get("arguments", аргументы),
        "note": заметка,
        "volatile": протухает or [],
        "response": {"envelope": ответ, "payload": полезная_нагрузка(ответ)},
    }
    файл = папка / f"{роль}.json"
    файл.write_text(json.dumps(конверт, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"file": f"{группа}/{роль}.json", **{k: конверт[k] for k in
            ("recorded_at", "method", "tool", "arguments", "note", "volatile")}}


def тул(роль: str, группа: str, имя: str, аргументы: dict, заметка: str,
        протухает: list[str] | None = None, таймаут: int = 90) -> dict:
    параметры = {"name": имя, "arguments": аргументы}
    ответ = вызвать("tools/call", параметры, таймаут)
    запись = записать(роль, группа, "tools/call", параметры, ответ, заметка, протухает)
    нагрузка = полезная_нагрузка(ответ)
    признак = "ошибка" if "error" in ответ else ("пусто" if нагрузка is None else "ок")
    размер = len(json.dumps(ответ, ensure_ascii=False))
    print(f"  {признак:6} {роль:34} {размер:>8} байт")
    return запись


ЛЕТИМ = {"origin": "Москва", "destination": "Сочи", "departure_date": "2026-10-15"}


def разведать_мета() -> list[dict]:
    print("\nСамоописание сервера")
    записи: list[dict] = []

    ответ = вызвать("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "tutu-flight-recon", "version": "0.1.0"},
    })
    записи.append(записать("initialize", "meta", "initialize", {}, ответ,
                           "serverInfo, capabilities и блок instructions — как Туту сами видят флоу"))
    print(f"  {'ок':6} {'initialize':34} {len(json.dumps(ответ, ensure_ascii=False)):>8} байт")

    ответ = вызвать("tools/list", {})
    записи.append(записать("tools-list", "meta", "tools/list", {}, ответ,
                           "фактическая спецификация инструментов: имена, описания, inputSchema"))
    print(f"  {'ок':6} {'tools-list':34} {len(json.dumps(ответ, ensure_ascii=False)):>8} байт")

    записи.append(тул("avia-instructions", "meta", "get_avia_instructions", {},
                      "плейбук по авиа от самих Туту — читать до написания первой строки"))
    for uri, роль, заметка in (
        ("tutu://help/overview", "resource-help", "общая справка сервера"),
        ("tutu://status", "resource-status", "здоровье апстримов: источник факта «не смогли узнать»"),
        ("tutu://geo", "resource-geo", "справочник городов — вместо своего хардкода"),
    ):
        записи.append(тул(роль, "meta", "fetch_resource", {"uri": uri}, заметка))
    return записи


def разведать_авиа() -> list[dict]:
    print("\nПробы search_avia")
    п = lambda **kw: {**ЛЕТИМ, **kw}  # noqa: E731
    протухает = ["offers[].price", "offers[].checkout_ref", "meta.search_id"]
    записи = [
        тул("baseline", "avia", "search_avia", п(page_size=3),
            "базовая форма ответа: что приходит всегда", протухает),
        тул("view-full", "avia", "search_avia", п(page_size=2, view="full"),
            "что скрыто в компактном виде и стоит ли оно лишних байтов", протухает),
        тул("direct-only", "avia", "search_avia", п(page_size=3, direct_only=True),
            "post_filter_dropped_not_direct: сервер сам отдаёт свидетельство отбора", протухает),
        тул("round-trip", "avia", "search_avia", п(page_size=2, return_date="2026-10-22"),
            "форма round-trip: одно предложение на оба плеча или два", протухает),
        тул("party-2a-1c", "avia", "search_avia", п(page_size=2, adults=2, children=1),
            "за кого цена: basis типа Price. Сравнивать с baseline", протухает),
        тул("connections", "avia", "search_avia",
            {"origin": "Калининград", "destination": "Владивосток",
             "departure_date": "2026-10-15", "page_size": 2},
            "пересадки: форма legs[].segments[], номер рейса, аэропорт и терминал", протухает),
        тул("overnight", "avia", "search_avia",
            п(page_size=5, sort="duration_asc"),
            "рейсы через полночь: как записан прилёт следующего дня и пояс", протухает),
        тул("page-2", "avia", "search_avia", п(page_size=2, page=2),
            "пагинация: has_more, total_matched, total_matched_exact", протухает),
        тул("iata-airport", "avia", "search_avia",
            {"origin": "SVO", "destination": "AER", "departure_date": "2026-10-15", "page_size": 2},
            "IATA сужает до аэропорта: post_filter_dropped_wrong_airport, airport_note", протухает),
        тул("empty-route", "avia", "search_avia",
            {"origin": "Урюпинск", "destination": "Певек",
             "departure_date": "2026-10-15", "page_size": 3},
            "пустая выдача: что в meta, объясняет ли сервер причину"),
        тул("past-date", "avia", "search_avia",
            п(departure_date="2020-01-01", page_size=2),
            "дата в прошлом: форма отказа"),
        тул("bad-input", "avia", "search_avia",
            {"origin": "Москва", "destination": "Сочи", "departure_date": "вчера"},
            "невалидный ввод: форма ошибки, которую придётся разбирать"),
        тул("unknown-carrier", "avia", "search_avia",
            п(page_size=3, carriers=["aeroflot"]),
            "фильтр по имени латиницей: молча ли отбрасывает всё"),
    ]
    return записи


def обновить_манифест(группа: str, записи: list[dict]) -> Path:
    """Заменить в манифесте записи этой группы, остальные оставить как есть.

    Манифест один на весь набор: `tests/test_harness.py` сверяет его с файлами
    на диске, и отдельные `manifest-<группа>.json` оставили бы общий манифест
    протухшим после каждой пересъёмки.
    """
    путь = ФИКСТУРЫ / "manifest.json"
    прежние = json.loads(путь.read_text(encoding="utf-8"))["entries"] if путь.exists() else []
    чужие = [з for з in прежние if группа_записи(з) != группа]
    все = sorted(чужие + записи, key=lambda з: з["file"])
    путь.write_text(
        json.dumps(
            {
                "recorded_at": max(з["recorded_at"] for з in все),
                "source": "tutu",
                "url": URL,
                "entries": все,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return путь


def группа_записи(запись: dict) -> str:
    return запись["file"].split("/", 1)[0]


if __name__ == "__main__":
    что = sys.argv[1] if len(sys.argv) > 1 else "meta"
    записи = разведать_мета() if что == "meta" else разведать_авиа()
    путь = обновить_манифест(что, записи)
    print(f"\nзаписей в группе {что}: {len(записи)} → {путь.relative_to(КОРЕНЬ)}")
