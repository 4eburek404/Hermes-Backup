"""Pytest fixtures for fetch_travel_news tests."""
import sys
from pathlib import Path

import pytest

# Add scripts/ dir to path so we can import fetch_travel_news
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_travel_news as fn  # noqa: E402


@pytest.fixture
def tmp_seen_db(tmp_path, monkeypatch):
    """Override SEEN_DB path to tmp_path for test isolation."""
    db = tmp_path / "seen.db"
    monkeypatch.setattr(fn, "SEEN_DB", db)
    return db


@pytest.fixture
def tmp_raw_json(tmp_path, monkeypatch):
    """Override RAW_JSON path."""
    j = tmp_path / "raw.json"
    monkeypatch.setattr(fn, "RAW_JSON", j)
    return j


@pytest.fixture
def tmp_sources_yaml(tmp_path, monkeypatch):
    """Override SOURCES_YAML path to a test config."""
    y = tmp_path / "test_sources.yaml"
    monkeypatch.setattr(fn, "SOURCES_YAML", y)
    return y


@pytest.fixture
def test_keywords():
    """Minimal keyword dict for testing classification."""
    return {
        "aviation": {
            "ru": ["авиа", "рейс", "самолёт", "аэрофлот", "аэропорт"],
            "en": ["airline", "flight", "aircraft", "boeing", "airbus"],
        },
        "hotels": {
            "ru": ["отель", "гостиниц", "проживание", "бронирование"],
            "en": ["hotel", "marriott", "hilton", "hospitality"],
        },
        "business_travel": {
            "ru": ["командир", "деловой", "бизнес-тревел", "корпоративн"],
            "en": ["business travel", "corporate travel", "gbta", "tmc"],
        },
    }


@pytest.fixture
def sample_items():
    """Sample news items for testing filter_and_classify."""
    return [
        {
            "title": "Аэрофлот отменил рейсы в Стамбул",
            "link": "https://example.com/aeroflot-cancelled",
            "description": "Авиакомпания отменила несколько рейсов",
            "date": "Tue, 12 Aug 2026 10:00:00 GMT",
            "source": "Коммерсантъ",
            "region": "ru",
            "topics": ["aviation", "hotels", "business_travel", "general"],
        },
        {
            "title": "Marriott открывает новый отель в Москве",
            "link": "https://example.com/marriott-moscow",
            "description": "Новый отель сети Marriott",
            "date": "Mon, 11 Aug 2026 12:00:00 GMT",
            "source": "BBT",
            "region": "ru",
            "topics": ["business_travel", "aviation", "hotels", "mice"],
        },
        {
            "title": "Трамп подписал указ о налогах",
            "link": "https://example.com/trump-taxes",
            "description": "Новый закон о налогообложении",
            "date": "Mon, 11 Aug 2026 09:00:00 GMT",
            "source": "Lenta.ru",
            "region": "ru",
            "topics": ["aviation", "hotels", "business_travel", "general"],
        },
        {
            "title": "GBTA: командировки выросли на 7%",
            "link": "https://example.com/gbta-growth",
            "description": "Глобальные расходы на business travel достигли $1.7 трлн",
            "date": "Tue, 05 Aug 2026 08:00:00 GMT",
            "source": "BBT",
            "region": "ru",
            "topics": ["business_travel", "aviation", "hotels", "mice"],
        },
        {
            # Duplicate URL of item 1
            "title": "Аэрофлот отменил рейсы в Стамбул (дубликат)",
            "link": "https://example.com/aeroflot-cancelled",
            "description": "",
            "date": "Tue, 12 Aug 2026 10:00:00 GMT",
            "source": "Интерфакс",
            "region": "ru",
            "topics": ["general"],
        },
        {
            # Duplicate normalized title of item 1, different URL
            "title": "Аэрофлот отменил рейсы в Стамбул!!!",
            "link": "https://example.com/aeroflot-cancelled-2",
            "description": "",
            "date": "Tue, 12 Aug 2026 11:00:00 GMT",
            "source": "Интерфакс",
            "region": "ru",
            "topics": ["general"],
        },
        {
            # Very old item — should be filtered by date
            "title": "Старый рейс Аэрофлота",
            "link": "https://example.com/old-flight",
            "description": "Старая новость про авиацию",
            "date": "Mon, 01 Jan 2024 00:00:00 GMT",
            "source": "Коммерсантъ",
            "region": "ru",
            "topics": ["aviation", "general"],
        },
        {
            # No date — should be included
            "title": "Новый авиа-маршрут анонсирован",
            "link": "https://example.com/new-route",
            "description": "Авиакомпания запускает рейс",
            "date": "",
            "source": "Турдом",
            "region": "ru",
            "topics": ["aviation", "general"],
        },
    ]