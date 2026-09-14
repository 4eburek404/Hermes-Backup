#!/usr/bin/env python3
"""Команда, названная в документации, обязана существовать.

`make что-то`, которое есть в AGENTS.md и нет в Makefile, — самый частый
и самый незаметный дефект документации. Поэтому его ловит скрипт, а не
намерение, и скрипт входит в `make check`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parent.parent

# Только команды, записанные как код — в тройных кавычках или в одинарных.
# Проза называет команды по-своему, и ловить её значит превратить проверку
# в помеху, которую через неделю удалят.
БЛОКИ = re.compile(r"```(?:bash|sh|console)?\n(.*?)```", re.S)
СТРОЧНЫЕ = re.compile(r"`([^`\n]+)`")
КОМАНДА = re.compile(r"\bmake\s+([a-z][a-z0-9:_-]*)")


def документы() -> list[Path]:
    найдено = [КОРЕНЬ / "AGENTS.md", КОРЕНЬ / "SKILL.md", КОРЕНЬ / "README.md"]
    найдено += sorted((КОРЕНЬ / "docs").glob("*.md"))
    найдено += sorted((КОРЕНЬ / "specs").glob("*.md"))
    return [п for п in найдено if п.exists()]


def цели() -> set[str]:
    текст = (КОРЕНЬ / "Makefile").read_text(encoding="utf-8")
    return set(re.findall(r"^([a-z][a-z0-9:_-]*):", текст, re.M))


def команды_в(текст: str) -> list[str]:
    куски = БЛОКИ.findall(текст) + СТРОЧНЫЕ.findall(текст)
    return [м for кусок in куски for м in КОМАНДА.findall(кусок)]


def main() -> int:
    существуют = цели()
    пропажи: list[str] = []

    for документ in документы():
        for команда in команды_в(документ.read_text(encoding="utf-8")):
            if команда not in существуют:
                пропажи.append(f"{документ.relative_to(КОРЕНЬ)}: make {команда}")

    if пропажи:
        print("Эти команды задокументированы и не существуют:", file=sys.stderr)
        for строка in пропажи:
            print(f"  {строка}", file=sys.stderr)
        return 1

    print(f"команды из документации существуют (файлов проверено: {len(документы())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
