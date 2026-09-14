"""Чистота ядра: без сети, файлов, часов, случайности и печати.

Проверяется по дереву разбора, а не поиском подстроки: слово `print(` живёт
в докстрингах и комментариях, и подстрочная проверка краснела бы на тексте,
а не на коде. Ловим вызовы и импорты.

Проверь этот тест руками один раз: добавь `print("тут")` в любой модуль ядра
и убедись, что `make arch` покраснел. Тест, который ни разу не падал, ничего
не гарантирует.
"""

from __future__ import annotations

import ast
from pathlib import Path

ЯДРО = Path(__file__).resolve().parents[2] / "src" / "tutu_search_flights" / "core"

ЗАПРЕЩЁННЫЕ_ИМПОРТЫ = {
    "socket", "urllib", "http", "requests", "httpx", "random", "os", "pathlib", "mcp",
}
# Полные имена вызовов, которые делают ответ зависящим от окружения.
ЗАПРЕЩЁННЫЕ_ВЫЗОВЫ = {
    "print", "open", "input",
    "datetime.now", "datetime.utcnow", "date.today", "time.time", "time.monotonic",
    "os.environ", "os.getenv", "random.random", "random.choice", "uuid.uuid4",
}


def имя_вызова(узел: ast.AST) -> str:
    """`datetime.now` из `datetime.datetime.now()` — последние две части пути."""
    части: list[str] = []
    while isinstance(узел, ast.Attribute):
        части.append(узел.attr)
        узел = узел.value
    if isinstance(узел, ast.Name):
        части.append(узел.id)
    return ".".join(reversed(части[-2:])) if len(части) > 1 else (части[0] if части else "")


def нарушения_модуля(модуль: Path) -> list[str]:
    дерево = ast.parse(модуль.read_text(encoding="utf-8"), filename=str(модуль))
    найдено: list[str] = []

    for узел in ast.walk(дерево):
        if isinstance(узел, ast.Import):
            найдено += [
                f"{модуль.name}: import {a.name}"
                for a in узел.names
                if a.name.split(".")[0] in ЗАПРЕЩЁННЫЕ_ИМПОРТЫ
            ]
        elif isinstance(узел, ast.ImportFrom):
            корень = (узел.module or "").split(".")[0]
            if узел.level == 0 and корень in ЗАПРЕЩЁННЫЕ_ИМПОРТЫ:
                найдено.append(f"{модуль.name}: from {узел.module} import …")
        elif isinstance(узел, ast.Call):
            цель = имя_вызова(узел.func)
            if цель in ЗАПРЕЩЁННЫЕ_ВЫЗОВЫ:
                найдено.append(f"{модуль.name}:{узел.lineno}: {цель}()")

    return найдено


def test_ядро_не_знает_про_внешний_мир() -> None:
    нарушения = [n for модуль in sorted(ЯДРО.rglob("*.py")) for n in нарушения_модуля(модуль)]

    assert not нарушения, "ядро тянет наружу — " + "; ".join(нарушения)


def test_ядро_существует_и_проверка_не_вакуумна() -> None:
    """Пустая папка проходит любую проверку. Этот тест ловит исчезновение ядра."""
    assert ЯДРО.is_dir(), f"нет папки ядра: {ЯДРО}"
    assert (ЯДРО / "__init__.py").exists(), "ядро не является пакетом"
