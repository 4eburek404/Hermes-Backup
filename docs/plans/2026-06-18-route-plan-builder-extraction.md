# RoutePlanBuilder: извлечение планировщика из live_assemble.py

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Структурная декомпозиция `build_live_route_segment_plan` (строки 143–632 файла `live_assemble.py`) в класс `RoutePlanBuilder` с пошаговыми методами, без изменения поведения. Поведение фиксируется golden-тестами до любых перестановок.

**Architecture:** Четыре фазы, как при runner’е: (1) обёртка-класс с `build()` = дословное тело функции, (2) подъём состояния и замыкания в `self.*` / методы, (3) нарезка `build()` на именованные шаги, (4) опциональный перенос в отдельный модуль. Каждая фаза — отдельный коммит, каждый коммит проходит полный suite.

**Tech Stack:** Python 3.11+, pytest, unittest.mock

---

## Provenance / Ownership Gate

| Layer | Path | Status |
|-------|------|--------|
| Source (repo) | `hermes/skills/productivity/flight-search/cli/flights_cli/orchestrators/live_assemble.py` | `Improve/flight_search_skill` branch, HEAD `eae52fb` |
| Runtime | `~/.hermes/skills/productivity/flight-search/cli/flights_cli/orchestrators/live_assemble.py` | Synced from repo |
| Tests | `hermes/skills/productivity/flight-search/cli/tests/test_*.py` (9 файлов импортируют `build_live_route_segment_plan`) | Source of truth |
| Re-exports | `live_assemble.py` строки 44–51: re-export `fetch_kupibilet_search` и 6 хелперов из `live_assembly_runner.py` | Должны остаться |
| Callers | `diagnose.py`, `live_assembly_runner.py:256`, `run_live_route_assembly` (строка 635) | Не ломать |

## Non-Actions

- **Не** объединяем дублирующиеся ветки outbound/return в `_build_direction(direction, strategy)` — это смена логики, не перестановка. Отдельная задача.
- **Не** переименовываем публичный символ `build_live_route_segment_plan` до фазы 4 (и даже там — re-export).
- **Не** меняем `append_unique_route_segment` или другие хелперы из `route_graph.py`.
- **Не** добавляем Protocol/ABC для args/store — текущая сигнатура `argparse.Namespace` остаётся.
- **Не** трогаем тесты, патчащие `flights_cli.orchestrators.live_assemble.build_live_route_segment_plan` — до фазы 4 путь сохраняется.

## Data-Flow Map

| Символ | Где сейчас | Куда на фазе 4 |
|--------|-----------|----------------|
| `build_live_route_segment_plan` | `live_assemble.py:143` | Re-export из `live_assemble.py`, реализация в `route_plan_builder.py` |
| `RoutePlanBuilder` (новый) | — | `orchestrators/route_plan_builder.py` |
| `add_live_segment` (замыкание) | `live_assemble.py:195` | Метод `RoutePlanBuilder._add_segment` |
| `provider_policy_allows_kupibilet` | `live_assemble.py:53` | `route_plan_builder.py` |
| `city_code_first_segment_options` | `live_assemble.py:58` | `route_plan_builder.py` |
| `normalize_day_offsets` | `live_assemble.py:97` | `route_plan_builder.py` |
| `resolve_date_window` | `live_assemble.py:111` | `route_plan_builder.py` |
| `run_live_route_assembly` | `live_assemble.py:635` | Остаётся в `live_assemble.py` |

---

## Task 1: Golden-тесты на 4 стратегии (direct_only, ru_priority, domestic_ru, hub_list) + one-way и round-trip

**Objective:** Зафиксировать текущее поведение `build_live_route_segment_plan` до любых перестановок. Каждая стратегия, each direction (one-way + round-trip) → snapshot segments dict → byte-identical до/после фаз 1–3.

**Files:**
- Create: `tests/test_route_plan_builder_golden.py`

**Step 1: Написать golden-тест**

```python
# tests/test_route_plan_builder_golden.py
"""Golden tests for build_live_route_segment_plan — freeze output before refactoring.

Run with: PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v

These tests snapshot the plan dict (segments, route_families, coverage_controls, etc.)
for each strategy × direction combination. Any refactor of the planner must produce
byte-identical output; if these tests break, the refactor changed behaviour.
"""
from __future__ import annotations

import hashlib
import json
import unittest

from flights_cli.orchestrators.live_assemble import build_live_route_segment_plan
from flights_cli.store import Store
from helpers import live_assembly_args


def _plan_snapshot(plan: dict) -> str:
    """Deterministic JSON snapshot: sort keys, serialize dates as strings."""
    return json.dumps(plan, sort_keys=True, default=str)


def _plan_hash(plan: dict) -> str:
    return hashlib.sha256(_plan_snapshot(plan).encode()).hexdigest()


class _GoldenPlanMixin:
    """Subclasses set STRATEGY and DIRECTION overrides."""

    def _make_args(self):
        overrides: dict = {
            "routing_strategy": self.STRATEGY,
            "no_direct_route_intel": True,
            "no_live_cache": True,
        }
        if self.DIRECTION == "one-way":
            overrides["return_date"] = None
        return live_assembly_args(**overrides)

    def test_plan_segment_count(self):
        plan = build_live_route_segment_plan(self._make_args(), Store())
        self.assertGreater(len(plan["segments"]), 0)

    def test_plan_snapshot_hash(self):
        plan = build_live_route_segment_plan(self._make_args(), Store())
        h = _plan_hash(plan)
        # Record expected hash; update only when intentionally changing plan output.
        self.assertEqual(h, self.EXPECTED_HASH, f"Snapshot changed! New hash: {h}\nFirst segment: {plan['segments'][0] if plan['segments'] else 'none'}")

    def test_plan_strategy_matches(self):
        plan = build_live_route_segment_plan(self._make_args(), Store())
        self.assertEqual(plan["routing_strategy"], self.STRATEGY)


class TestDirectOnlyRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "direct_only"
    DIRECTION = "round-trip"
    EXPECTED_HASH = None  # will be set after first run

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            max_connections=0,
            tier2_max_connections=0,
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestDirectOnlyOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "direct_only"
    DIRECTION = "one-way"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date=None,
            max_connections=0,
            tier2_max_connections=0,
            date_window_end="2026-08-20",
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestRuPriorityRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "ru-priority"
    DIRECTION = "round-trip"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestRuPriorityOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "ru-priority"
    DIRECTION = "one-way"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date=None,
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestDomesticRuRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "domestic-ru"
    DIRECTION = "round-trip"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="LED",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestDomesticRuOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "domestic-ru"
    DIRECTION = "one-way"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="LED",
            depart_date="2026-08-15",
            return_date=None,
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestHubListRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "hub-list"
    DIRECTION = "round-trip"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="NCE",
            destination="HND",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            hub=["IST"],
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestHubListOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "hub-list"
    DIRECTION = "one-way"
    EXPECTED_HASH = None

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="NCE",
            destination="HND",
            depart_date="2026-08-15",
            return_date=None,
            hub=["IST"],
            no_direct_route_intel=True,
            no_live_cache=True,
        )
```

**Step 2: Запустить тесты, снять хеши**

Запустить тест, записать хеш для каждого класса. В первый запуск тесты упадут (`EXPECTED_HASH = None` ≠ фактическому хешу). Записать хеши в `EXPECTED_HASH`, перезапустить — должны пройти.

```bash
cd ~/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v
```

Для снятия хешей — временно добавить отладочный вывод:

```python
def test_plan_snapshot_hash(self):
    plan = build_live_route_segment_plan(self._make_args(), Store())
    h = _plan_hash(plan)
    if self.EXPECTED_HASH is None:
        self.skipTest(f"Set EXPECTED_HASH = \"{h}\"")
    self.assertEqual(h, self.EXPECTED_HASH)
```

Запустить, получить хеши → вписать → перезапустить → все 8×3=24 проверки зелёные.

**Step 3: Запустить полный suite**

```bash
PYTHONPATH=. python -m pytest tests/ -x -q --no-header
```

Expected: 371 passed, 61 subtests passed (suite вырос на 24 проверки).

**Step 4: Commit**

```bash
git add tests/test_route_plan_builder_golden.py
git commit -m "test: golden tests for build_live_route_segment_plan (4 strategies × 2 directions)"
```

---

## Task 2: Фаза 1 — класс-обёртка RoutePlanBuilder

**Objective:** Создать `RoutePlanBuilder` с методом `build()`, дословно копирующим тело `build_live_route_segment_plan`. Функция `build_live_route_segment_plan` делегирует в класс. Нулевой риск: поведение идентично.

**Files:**
- Modify: `flights_cli/orchestrators/live_assemble.py`

**Step 1: Создать класс RoutePlanBuilder**

В `live_assemble.py`, после строки 141 (после `resolve_date_window`), добавить класс:

```python
class RoutePlanBuilder:
    """Builds a route segment plan from args and store.

    This class is a structural extraction of the former
    ``build_live_route_segment_plan`` function.  It preserves
    behaviour exactly — the ``build`` method body is a copy-paste
    of the original function body.
    """

    def __init__(self, args: argparse.Namespace, store: Store, *, flow: LiveRouteSearchFlow | None = None) -> None:
        self._args = args
        self._store = store
        self._flow = flow

    def build(self) -> dict[str, Any]:
        args = self._args
        store = self._store
        flow = self._flow
        # --- дословное тело бывшей build_live_route_segment_plan ---
        # (весь код со строки 143 по строку 632 переносится сюда без изменений)
        ...
```

**Step 2: Заменить тело build_live_route_segment_plan на делегацию**

```python
def build_live_route_segment_plan(args: argparse.Namespace, store: Store, *, flow: LiveRouteSearchFlow | None = None) -> dict[str, Any]:
    return RoutePlanBuilder(args, store, flow=flow).build()
```

**Step 3: Запустить полный suite + golden-тесты**

```bash
PYTHONPATH=. python -m pytest tests/ -x -q --no-header
PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v
```

Expected: все хеши совпадают, suite зелёный.

**Step 4: Commit**

```bash
git add flights_cli/orchestrators/live_assemble.py
git commit -m "refactor(route-plan): phase 1 — RoutePlanBuilder wrapper class"
```

---

## Task 3: Фаза 2 — подъём состояния и замыкания

**Objective:** Переменные тела `build()` → поля `self.*`; замыкание `add_live_segment` → метод `self._add_segment`. Поведение идентично, доступ через `self` вместо локальных переменных.

**Files:**
- Modify: `flights_cli/orchestrators/live_assemble.py`

**Step 1: Поднять переменные в self.*

В `RoutePlanBuilder.build()` заменить все локальные переменные на `self.*` поля, присваиваемые в `build()` или лениво. Примеры:

- `depart` → `self.depart`
- `ret` → `self.ret`
- `currency` → `self.currency`
- `profile` → `self.routing_profile` (не путать с args.profile)
- `direct_only` → `self.direct_only`
- `window_dates` → `self.window_dates`
- `origin` → `self.origin` (resolved Location)
- `destination` → `self.destination`
- `origin_airports` → `self.origin_airports`
- `destination_airports` → `self.destination_airports`
- `origin_segment_options` → `self.origin_segment_options`
- `destination_segment_options` → `self.destination_segment_options`
- `route_context` → `self.route_context`
- `routing_strategy` → `self.routing_strategy`
- `hubs` → `self.hubs`
- `hub_source` → `self.hub_source`
- `routing_profile` → `self.routing_profile`
- `outbound_second_offsets` → `self.outbound_second_offsets`
- `return_second_offsets` → `self.return_second_offsets`
- `segments` → `self.segments`
- `seen` → `self._seen`
- `route_families` → `self.route_families`
- `include_generic_direct_controls` → `self._include_generic_direct_controls`
- `moscow_gateway_eligible` → `self._moscow_gateway_eligible`
- `gateway_segment_options` → `self._gateway_segment_options`
- `provider_policy` → `self._provider_policy`

**Step 2: Превратить замыкание add_live_segment в метод**

```python
def _add_segment(self, direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str, **extra: Any) -> None:
    append_unique_route_segment(
        self.segments,
        self._seen,
        direction=direction,
        leg=leg,
        dep_date=dep_date,
        origin_code=origin_code,
        dest_code=dest_code,
        include_date=True,
        extra=extra,
    )
```

Заменить все вызовы `add_live_segment(...)` на `self._add_segment(...)`.

**Step 3: Запустить полный suite + golden-тесты**

```bash
PYTHONPATH=. python -m pytest tests/ -x -q --no-header
PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v
```

Expected: хеши совпадают, suite зелёный.

**Step 4: Commit**

```bash
git add flights_cli/orchestrators/live_assemble.py
git commit -m "refactor(route-plan): phase 2 — lift state to self.* and closure to _add_segment"
```

---

## Task 4: Фаза 3 — нарезка build() на шаги

**Objective:** `build()` сжимается до ~5 строк делегации в именованные методы:

```python
def build(self) -> dict[str, Any]:
    self._resolve_context()
    self._build_outbound()
    self._build_return()
    self._coverage_and_warnings()
    return self._assemble_result()
```

Ветки стратегий внутри outbound/return разбиваются на приватные методы:
`_outbound_direct_only()`, `_outbound_ru_priority()`, `_outbound_domestic_ru()`, `_outbound_hub_list()`,
и аналогично `_return_*`.

**Files:**
- Modify: `flights_cli/orchestrators/live_assemble.py`

**Step 1: Выделить _resolve_context()**

Всё от начала `build()` до `segments: list[dict] = []` → метод `_resolve_context()`. Устанавливает `self.*` поля. Возвращает `None` (мутация через `self`).

**Step 2: Выделить _build_outbound()**

Строки outbound-сегментов (строки 223–388 оригинала) → `_build_outbound()`. Внутри — диспетчеризация по `self.routing_strategy` / `self.direct_only`:

```python
def _build_outbound(self) -> None:
    if self.direct_only:
        self._outbound_direct_only()
    elif self.routing_strategy == RoutingStrategy.RU_PRIORITY:
        self._outbound_ru_priority()
    elif self.routing_strategy == RoutingStrategy.DOMESTIC_RU:
        self._outbound_domestic_ru()
    else:
        self._outbound_hub_list()
```

Каждый `_outbound_*` метод — прямой перенос соответствующего блока, вызовы `self._add_segment(...)` вместо `add_live_segment(...)`.

**Step 3: Выделить _build_return()**

Аналогично outbound, для блока `if ret:` (строки 390–546).

**Step 4: Выделить _coverage_and_warnings()**

Строки 548–567 (warnings) + 569–583 (coverage_controls) + 584–591 (route_graph).

**Step 5: Выделить _assemble_result()**

Финальный `return {...}` (строки 593–632).

**Step 6: Запустить полный suite + golden-тесты**

```bash
PYTHONPATH=. python -m pytest tests/ -x -q --no-header
PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v
```

Expected: хеши совпадают, suite зелёный.

**Step 7: Commit**

```bash
git add flights_cli/orchestrators/live_assemble.py
git commit -m "refactor(route-plan): phase 3 — slice build() into step methods by strategy"
```

---

## Task 5: Фаза 4 — перенос в отдельный модуль (опционально)

**Objective:** Вынести `RoutePlanBuilder` и планировщик-онли хелперы (`city_code_first_segment_options`, `normalize_day_offsets`, `resolve_date_window`, `provider_policy_allows_kupibilet`) в `orchestrators/route_plan_builder.py`. `live_assemble.py` сжимается до обёртки `run_live_route_assembly` + ре-экспортов.

**⚠️ Патч-путь:** Тесты, патчащие `flights_cli.orchestrators.live_assemble.build_live_route_segment_plan`, нужно обновить на `flights_cli.orchestrators.route_plan_builder.RoutePlanBuilder.build` или `flights_cli.orchestrators.route_plan_builder.build_live_route_segment_plan`. Это 2 файла: `test_live_route_pipeline.py`, `test_live_assemble_probe_ledger.py`.

**Files:**
- Create: `flights_cli/orchestrators/route_plan_builder.py`
- Modify: `flights_cli/orchestrators/live_assemble.py` (оставить ре-экспорты + `run_live_route_assembly`)
- Modify: `flights_cli/orchestrators/__init__.py` (если нужно)
- Modify: `tests/test_live_route_pipeline.py` (patch-путь)
- Modify: `tests/test_live_assemble_probe_ledger.py` (patch-путь)
- Modify: `flights_cli/apps/diagnose.py` (импорт не меняется — ре-экспорт)

**Step 1: Создать route_plan_builder.py**

Перенести: `RoutePlanBuilder`, `provider_policy_allows_kupibilet`, `city_code_first_segment_options`, `normalize_day_offsets`, `resolve_date_window`, `build_live_route_segment_plan` (делегация).

Импорты: всё, что нужно из `..config`, `..domain`, `..pipeline`, `..store`, `.route_graph`.

**Step 2: Обновить live_assemble.py**

Оставить:
```python
from .route_plan_builder import (  # noqa: F401 — re-export
    build_live_route_segment_plan,
    city_code_first_segment_options,
    normalize_day_offsets,
    provider_policy_allows_kupibilet,
    resolve_date_window,
)
```

Плюс `run_live_route_assembly` и ре-экспорты из `live_assembly_runner`.

Удалить: всё тело планировщика, хелперы, класс `RoutePlanBuilder`.

**Step 3: Обновить patch-пути в тестах**

`test_live_route_pipeline.py:94` и `test_live_assemble_probe_ledger.py:60`: заменить `flights_cli.orchestrators.live_assemble.build_live_route_segment_plan` → `flights_cli.orchestrators.route_plan_builder.build_live_route_segment_plan`.

**Step 4: Запустить полный suite + golden-тесты**

```bash
PYTHONPATH=. python -m pytest tests/ -x -q --no-header
PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v
```

Expected: все тесты зелёные, хеши golden совпадают.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(route-plan): phase 4 — extract RoutePlanBuilder into route_plan_builder.py"
```

---

## Pitfalls

1. **Порядок сегментов критичен.** `append_unique_route_segment` с `seen`-дедупликацией зависит от порядка вызовов. Golden-тесты фиксируют итоговый `segments` список. Любая перестановка вызовов `_add_segment` внутри стратегии — это смена поведения, не рефакторинг.
2. **Инъекция flow.** `LiveAssemblyRunner` передаёт `flow=self.flow` (строка 256 runner’а). Конструктор `RoutePlanBuilder(args, store, flow=flow)` сохраняет инъекцию. Если `flow is None` — `_resolve_context()` должен вызывать `build_live_route_search_flow(args, store)` (как сейчас).
3. **Re-exports.** `live_assemble.py` ре-экспортирует `fetch_kupibilet_search` и 6 хелперов из `live_assembly_runner.py` (строки 44–51). Не удалять — внешние импорты (включая патчи в тестах) завязаны на этот путь.
4. **Patching tests.** На фазах 1–3 `build_live_route_segment_plan` остаётся в `live_assemble.py` — патчи живут. Только фаза 4 требует обновления patch-пути.
5. **`provider_policy` vs `args.provider_policy`.** В теле функции используется `provider_policy` (локальная из `getattr(args, ...)`), не `args.provider_policy`. При подъёме в `self._provider_policy` — та же переменная, но явнее.

## Verification Checklist

- [ ] Golden-тесты: хеши всех 8 сценариев совпадают до/после каждой фазы
- [ ] Полный suite: 371+ тестов, 0 failures
- [ ] `build_live_route_segment_plan` — публичный API, поведение идентично
- [ ] `LiveAssemblyRunner` передаёт `flow=self.flow` корректно
- [ ] Импорты из `live_assemble` (`build_live_route_segment_plan`, `run_live_route_assembly`, хелперы) работают
- [ ] Фаза 4: patch-путь в `test_live_route_pipeline.py` и `test_live_assemble_probe_ledger.py` обновлён