"""Проверки целостности research-записей и их manifest.

Изначально эта обвязка была единственной исполняемой проверкой до появления
продуктового кода. Сейчас она по-прежнему ловит потерю записей, расхождения
manifest и отсутствие опорной даты до запуска продуктовых спецификаций.
"""

from __future__ import annotations

import json
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[1]
ФИКСТУРЫ = КОРЕНЬ / "fixtures"
ОБЯЗАТЕЛЬНЫЕ_ПОЛЯ = ("recorded_at", "source", "method", "arguments", "note", "response")


def манифест() -> dict:
    return json.loads((ФИКСТУРЫ / "manifest.json").read_text(encoding="utf-8"))


def test_манифест_читается_и_не_пуст() -> None:
    записи = манифест()["entries"]

    assert len(записи) >= 19, f"записей в манифесте: {len(записи)}"


def test_каждая_запись_манифеста_указывает_на_существующий_файл() -> None:
    пропажи = [з["file"] for з in манифест()["entries"] if not (ФИКСТУРЫ / з["file"]).exists()]

    assert not пропажи, "манифест ссылается на несуществующие файлы — " + "; ".join(пропажи)


def test_каждая_фикстура_на_диске_есть_в_манифесте() -> None:
    объявлены = {з["file"] for з in манифест()["entries"]}
    на_диске = {
        str(ф.relative_to(ФИКСТУРЫ)) for ф in ФИКСТУРЫ.rglob("*.json") if ф.name != "manifest.json"
    }

    assert not (на_диске - объявлены), "не объявлены в манифесте — " + "; ".join(
        sorted(на_диске - объявлены)
    )


def test_у_каждого_конверта_есть_опорная_дата_и_обязательные_поля() -> None:
    дефекты: list[str] = []

    for запись in манифест()["entries"]:
        конверт = json.loads((ФИКСТУРЫ / запись["file"]).read_text(encoding="utf-8"))
        нет = [поле for поле in ОБЯЗАТЕЛЬНЫЕ_ПОЛЯ if поле not in конверт]
        if нет:
            дефекты.append(f"{запись['file']}: нет {', '.join(нет)}")

    assert not дефекты, "конверт неполон — " + "; ".join(дефекты)


def test_записаны_и_отказы_тоже() -> None:
    """Набор из одних успешных ответов не проверяет разбор ошибок ничем."""
    роли = {Path(з["file"]).stem for з in манифест()["entries"]}
    отказы = {"empty-route", "past-date", "bad-input", "unknown-carrier"}

    assert отказы <= роли, "нет записей отказов: " + ", ".join(sorted(отказы - роли))
