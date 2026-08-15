# Plan v2.0: Update travel-news-digest SKILL + Tests for fetch_travel_news.py

**Reviewed by:** deepseek-v4-flash:0731 (6/10), gemma4:31b (6/10)

## Review Findings (incorporated)

### From deepseek:
1. **TDD-фрейминг неверен для brownfield** → переименовать в Characterization Testing. RED — только для реальных багов.
2. **Флейки-тесты на сеть** → интеграционные тесты не ассертить "0 errors", только "items > 0"
3. **SQLite изоляция** → `conftest.py` с `tmp_path` фикстурой, тестовый `seen.db` в tmp
4. **Нет тестов для**: `parse_google_news`, `fetch_with_retry`, `load_sources`, CLI-флагов
5. **SKILL.md уже имеет CLI-раздел** → обновить существующий, не создавать новый

### From gemma4:
1. **Нет валидации конфига** → тест на битый YAML
2. **Нет теста на таймаут** → мок зависшего источника
3. **Поверхностная проверка markdown** → проверка URL, дат, структуры
4. **Согласен с deepseek** по TDD → Characterization Testing

## Part 1: Tests (Characterization + Bug-Driven)

### Принцип: characterization testing, не TDD
- Закрепить текущее поведение скрипта (550 строк, уже работает)
- RED — только для известных багов (retry, фильтрация, edge cases)
- GREEN — фикс багов
- REFACTOR — последняя стадия

### Структура:
```
travel-news-digest/
  scripts/
    fetch_travel_news.py
    sources.yaml
  tests/
    test_fetch_travel_news.py
    test_sources.yaml          # 3 тестовых источника
    conftest.py                # fixtures: tmp_path for seen.db, mock config
```

### conftest.py:
```python
import pytest
from pathlib import Path

@pytest.fixture
def tmp_seen_db(tmp_path, monkeypatch):
    """Override SEEN_DB path to tmp_path for test isolation."""
    db = tmp_path / "seen.db"
    monkeypatch.setattr("fetch_travel_news.SEEN_DB", db)
    return db

@pytest.fixture
def tmp_raw_json(tmp_path, monkeypatch):
    """Override RAW_JSON path."""
    j = tmp_path / "raw.json"
    monkeypatch.setattr("fetch_travel_news.RAW_JSON", j)
    return j

@pytest.fixture
def test_keywords():
    return {
        "aviation": {"ru": ["авиа", "рейс", "самолёт"], "en": ["airline", "flight"]},
        "hotels": {"ru": ["отель", "гостиниц"], "en": ["hotel", "Marriott"]},
        "business_travel": {"ru": ["командир", "деловой"], "en": ["business travel"]},
    }
```

### Тест-кейсы (24 шт):

#### P1 — Unit: classify_item (5 тестов, characterization):

| # | Test | Input | Expected | Type |
|---|------|-------|----------|------|
| 1 | `test_classify_aviation_ru` | "Аэрофлот отменил рейсы" | ["aviation"] | char |
| 2 | `test_classify_hotels_en` | "Marriott opens new hotel" | ["hotels"] | char |
| 3 | `test_classify_business_travel` | "GBTA: командировки выросли" | ["business_travel"] | char |
| 4 | `test_classify_no_match` | "Трамп подписал указ" | [] | char |
| 5 | `test_classify_returns_first_match_only` | "Аэрофлот открыл отель-курорт" | ["aviation"] | char |

#### P2 — Unit: filter_and_classify (6 тестов):

| # | Test | Description | Type |
|---|------|-------------|------|
| 6 | `test_filter_drops_general_irrelevant` | Lenta без travel-kw → отфильтрован | char |
| 7 | `test_filter_keeps_travel_source_no_kw` | BBT без kw → kept, first configured topic | char |
| 8 | `test_dedup_by_url` | 2 item, один URL → 1 остаётся | char |
| 9 | `test_dedup_by_normalized_title` | "Рейсы!!!" и "Рейсы" → 1 остаётся | char |
| 10 | `test_date_filter_7days` | item 30 дней назад → отфильтрован | char |
| 11 | `test_date_filter_boundary` | item ровно 7 дней назад → проходит (boundary) | bug-fix (RED) |

#### P3 — Unit: parsing (4 теста, мокированные):

| # | Test | Description | Type |
|---|------|-------------|------|
| 12 | `test_parse_rss_mock` | Мок RSS XML (3 items) → 3 parsed | char |
| 13 | `test_parse_rss_empty` | Пустой RSS → [], no error | char |
| 14 | `test_parse_rss_malformed` | Битый XML → [], error message | char |
| 15 | `test_parse_html_mock` | Мок HTML (5 ссылок) → 5 items | char |

#### P4 — Unit: fetch_with_retry + load_sources (4 теста, NEW from review):

| # | Test | Description | Type |
|---|------|-------------|------|
| 16 | `test_fetch_retry_3_attempts` | Мок 3x timeout → returns None, 3 retries | bug-fix (RED) |
| 17 | `test_load_sources_filter_region` | --region ru → только RU источники | char |
| 18 | `test_load_sources_filter_priority` | --priority P1 → только P1 | char |
| 19 | `test_load_sources_invalid_yaml` | Битый YAML → чистая ошибка, не traceback | bug-fix (RED) |

#### P5 — Unit: seen_db (2 теста):

| # | Test | Description | Type |
|---|------|-------------|------|
| 20 | `test_seen_db_dedup` | mark_seen → is_seen = True | char |
| 21 | `test_seen_db_retention_30days` | entry 31 день назад → удалён | char |

#### P6 — Unit: format_markdown (3 теста):

| # | Test | Description | Type |
|---|------|-------------|------|
| 22 | `test_markdown_has_sections` | "✈️ ПЕРЕЛЁТЫ", "🏨 ОТЕЛИ", "🎫" | char |
| 23 | `test_markdown_failed_sources` | "⚠️ Failed Sources" при errors | char |
| 24 | `test_markdown_url_integrity` | URL присутствуют, не обрезаны | char |

#### P7 — Integration (2 теста, @pytest.mark.slow, не ассертить "0 errors"):

| # | Test | Description | Type |
|---|------|-------------|------|
| 25 | `test_health_check_3_sources` | 3 тестовых источника → статус ✅/❌ | slow |
| 26 | `test_fetch_all_returns_items` | 3 тестовых источника → items > 0 | slow |

### Порядок реализации:

1. Создать `tests/` структуру + `conftest.py` + `test_sources.yaml`
2. Написать P1-P6 (22 unit-теста) — запустить (characterization)
3. Баги найденные → RED → фикс → GREEN
4. Написать P7 (2 integration) — `@pytest.mark.slow`, запускать с `-m "not slow"`
5. Refactor: вынести общее, упростить

## Part 2: SKILL.md Update

### Принцип: обновить существующий SKILL.md, не переписывать

1. **Раздел "CLI Script"** (строка 256+) — обновить:
   - Добавить `fetch_travel_news.py` как PRIMARY метод
   - Команды: `all`, `health`, `clear-cache`
   - Флаги: `--days`, `--output`, `--region`, `--priority`
   - Примеры

2. **Раздел "Workflow"** — обновить:
   - Шаг 1: "Запустить `python scripts/fetch_travel_news.py all --days 7`"
   - Шаг 2: "Просмотреть вывод, при необходимости --summarize через LLM"
   - Шаг 3: "Fallback: ручной сбор через agent (для browser-only источников)"

3. **Раздел "Pitfalls"** — добавить:
   - bs4/feedparser/lxml в Hermes venv (pip install в venv, не system)
   - curl_cffi+safari нестабилен (retry 3x)
   - Общие СМИ (Коммерсантъ, Lenta) фильтруются по keywords — нерелевантные отбрасываются
   - SQLite кеш в ~/.cache/travel-news/seen.db — очистка через `clear-cache`
   - Источники с `general` в topics требуют keyword match, иначе items дропаются

4. **Reference files** — обновить:
   - `scripts/fetch_travel_news.py` — основной скрипт
   - `scripts/sources.yaml` — конфиг источников
   - `tests/test_fetch_travel_news.py` — тесты

5. **Убрать дублирующиеся Pitfalls** (нумерация 9, 10, 11... — проверить и исправить)