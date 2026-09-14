"""Границы: кто имеет право завершать процесс, печатать и держать сырой словарь.

Правила проекта: библиотечный код не вызывает `sys.exit` и не печатает в stdout —
завершение процесса только в `cli`. `dict[str, Any]` допустим ровно в двух точках,
и обе живут в `mcp`: сразу после разбора ответа и перед сериализацией.
"""

from __future__ import annotations

import ast
from pathlib import Path

ПАКЕТ = Path(__file__).resolve().parents[2] / "src" / "tutu_search_flights"


def модули(слой: str) -> list[Path]:
    return sorted((ПАКЕТ / слой).rglob("*.py"))


def вызовы(модуль: Path) -> list[tuple[int, str]]:
    дерево = ast.parse(модуль.read_text(encoding="utf-8"), filename=str(модуль))
    найдено: list[tuple[int, str]] = []
    for узел in ast.walk(дерево):
        if isinstance(узел, ast.Call):
            цель = узел.func
            if isinstance(цель, ast.Name):
                найдено.append((узел.lineno, цель.id))
            elif isinstance(цель, ast.Attribute) and isinstance(цель.value, ast.Name):
                найдено.append((узел.lineno, f"{цель.value.id}.{цель.attr}"))
    return найдено


def test_процесс_завершает_только_cli() -> None:
    нарушения: list[str] = []
    for слой in ("core", "mcp"):
        for модуль in модули(слой):
            нарушения += [
                f"{слой}/{модуль.name}:{строка}: {имя}()"
                for строка, имя in вызовы(модуль)
                if имя in ("sys.exit", "exit", "quit")
            ]

    assert not нарушения, "завершение процесса вне cli — " + "; ".join(нарушения)


def test_печатает_только_cli() -> None:
    нарушения: list[str] = []
    for слой in ("core", "mcp"):
        for модуль in модули(слой):
            нарушения += [
                f"{слой}/{модуль.name}:{строка}"
                for строка, имя in вызовы(модуль)
                if имя == "print"
            ]

    assert not нарушения, "печать вне cli — " + "; ".join(нарушения)


def test_сырой_словарь_живёт_только_в_mcp() -> None:
    """`dict[str, Any]` выше границы разбора означает, что типизация протекла."""
    нарушения: list[str] = []
    for слой in ("core", "cli"):
        for модуль in модули(слой):
            текст = модуль.read_text(encoding="utf-8")
            for номер, строка in enumerate(текст.splitlines(), start=1):
                без_комментария = строка.split("#", 1)[0]
                if "dict[str, Any]" in без_комментария or "Dict[str, Any]" in без_комментария:
                    нарушения.append(f"{слой}/{модуль.name}:{номер}")

    assert not нарушения, "сырой словарь вне mcp — " + "; ".join(нарушения)
