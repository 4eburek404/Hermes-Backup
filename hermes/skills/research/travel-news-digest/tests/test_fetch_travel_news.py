from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_travel_news as news  # noqa: E402

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Airline opens route</title><link>https://example.com/1</link>
<description>New international flight</description>
<pubDate>Fri, 15 Aug 2099 10:00:00 GMT</pubDate></item>
</channel></rss>"""

SOURCES = [
    {
        "name": "Test Feed",
        "fetch": "rss",
        "rss": "https://example.com/feed.xml",
        "region": "intl",
        "priority": "P1",
        "topics": ["aviation"],
    }
]

KEYWORDS = {
    "aviation": {"en": ["airline", "flight"], "ru": ["авиа", "рейс"]},
    "hotels": {"en": ["hotel"], "ru": ["отель"]},
    "business_travel": {
        "en": ["business travel"],
        "ru": ["командир"],
    },
}


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return RSS


def test_fetch_feed_normalizes_rss(monkeypatch):
    monkeypatch.setattr(news, "urlopen", lambda *_args, **_kwargs: Response())
    items, error = news.fetch_feed(SOURCES[0])
    assert error is None
    assert items == [
        {
            "title": "Airline opens route",
            "link": "https://example.com/1",
            "published_at": "2099-08-15T10:00:00+00:00",
            "summary": "New international flight",
            "source": "Test Feed",
            "region": "intl",
            "topics": ["aviation"],
        }
    ]


def test_google_news_url_preserves_query_and_edition():
    url = news.source_feed_url(
        {
            "fetch": "google_news",
            "query": "business travel",
            "hl": "en",
            "gl": "GB",
            "ceid": "GB:en",
        }
    )
    assert url.startswith("https://news.google.com/rss?")
    assert "q=business+travel" in url
    assert "hl=en" in url
    assert "gl=GB" in url
    assert "ceid=GB%3Aen" in url


def test_fetch_all_sources_keeps_successes(monkeypatch):
    def fake_fetch(source):
        if source["name"] == "Broken":
            return [], "HTTP 503"
        return [{"title": "ok", "source": source["name"]}], None

    monkeypatch.setattr(news, "fetch_feed", fake_fetch)
    items, errors = news.fetch_all_sources(
        [SOURCES[0], {**SOURCES[0], "name": "Broken"}], max_workers=2
    )
    assert items == [{"title": "ok", "source": "Test Feed"}]
    assert errors == {"Broken": "HTTP 503"}


def test_load_config_filters_region_and_priority(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        "keywords: {}\nsources:\n"
        "  - {name: A, fetch: rss, rss: 'https://a.test/feed', "
        "region: ru, priority: P1, topics: [aviation]}\n"
        "  - {name: B, fetch: rss, rss: 'https://b.test/feed', "
        "region: intl, priority: P2, topics: [hotels]}\n",
        encoding="utf-8",
    )
    sources, keywords = news.load_config(path, region="ru", priority="P1")
    assert [source["name"] for source in sources] == ["A"]
    assert keywords == {}


def test_filter_deduplicates_and_classifies():
    items = [
        {
            "title": "Airline opens route",
            "link": "https://e/1",
            "summary": "",
            "published_at": "2099-08-15T10:00:00+00:00",
            "topics": ["aviation"],
        },
        {
            "title": "Airline opens route!",
            "link": "https://e/1",
            "summary": "",
            "published_at": "2099-08-15T10:00:00+00:00",
            "topics": ["aviation"],
        },
    ]
    result = news.filter_and_classify(
        items,
        KEYWORDS,
        days=7,
        now=datetime(2099, 8, 16, tzinfo=timezone.utc),
    )
    assert len(result) == 1
    assert result[0]["classified_topics"] == ["aviation"]


def test_render_json_has_stable_envelope():
    payload = json.loads(
        news.render_json([], {"Broken": "timeout"}, source_count=2)
    )
    assert set(payload) == {"items", "errors", "source_count", "generated_at"}
    assert payload["errors"] == {"Broken": "timeout"}


def test_main_returns_one_when_every_source_fails(monkeypatch):
    monkeypatch.setattr(
        news,
        "load_config",
        lambda *_args, **_kwargs: (SOURCES, KEYWORDS),
    )
    monkeypatch.setattr(
        news,
        "fetch_all_sources",
        lambda *_args, **_kwargs: ([], {"Test Feed": "timeout"}),
    )
    assert news.main(["digest", "--output", "json"]) == 1
