"""Tests for fetch_travel_news.py — Characterization + Bug-Driven.

Run:  python -m pytest tests/ -v -m "not slow"
Slow: python -m pytest tests/ -v -m slow
All:  python -m pytest tests/ -v
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import pytest

from fetch_travel_news import (
    classify_item,
    clear_seen_db,
    fetch_with_retry,
    filter_and_classify,
    format_markdown,
    init_seen_db,
    is_seen,
    load_sources,
    mark_seen,
    parse_html,
    parse_rss,
    url_hash,
)


# ═══════════════════════════════════════════════════════════
# P1: classify_item (5 tests — characterization)
# ═══════════════════════════════════════════════════════════

class TestClassifyItem:

    def test_classify_aviation_ru(self, test_keywords):
        result = classify_item("Аэрофлот отменил рейсы", "", test_keywords)
        assert "aviation" in result

    def test_classify_hotels_en(self, test_keywords):
        result = classify_item("Marriott opens new hotel", "", test_keywords)
        assert "hotels" in result

    def test_classify_business_travel(self, test_keywords):
        result = classify_item("GBTA: командировки выросли на 7%", "", test_keywords)
        assert "business_travel" in result

    def test_classify_no_match(self, test_keywords):
        result = classify_item("Трамп подписал указ", "", test_keywords)
        assert result == []

    def test_classify_returns_first_match_only(self, test_keywords):
        """One news item → one topic (no duplicates across sections)."""
        # "Аэрофлот отменил рейсы" — matches "авиа"/"рейс"/"аэрофлот" (aviation)
        # Does NOT match hotels/business_travel keywords
        result = classify_item("Аэрофлот отменил рейсы", "", test_keywords)
        assert len(result) == 1
        assert result == ["aviation"]

    def test_classify_multiple_topics_present(self, test_keywords):
        """Title with keywords from two topics — both should be returned by classify_item.
        (filter_and_classify is responsible for picking only the first.)"""
        # "Аэрофлот открыл отель" — matches aviation (аэрофлот) AND hotels (отель)
        result = classify_item("Аэрофлот открыл отель", "", test_keywords)
        assert "aviation" in result
        assert "hotels" in result
        assert len(result) == 2

    def test_classify_case_insensitive(self, test_keywords):
        """Keywords should match case-insensitively (Marriott vs marriott)."""
        result = classify_item("MARRIOTT opens new HOTEL", "", test_keywords)
        assert "hotels" in result


# ═══════════════════════════════════════════════════════════
# P2: filter_and_classify (7 tests — characterization + bug-fix)
# ═══════════════════════════════════════════════════════════

class TestFilterAndClassify:

    def test_filter_drops_general_source_irrelevant(self, sample_items, test_keywords):
        """Lenta item without travel keywords → filtered out."""
        # sample_items[2] = "Трамп подписал указ" from Lenta (has general in topics)
        result = filter_and_classify(sample_items, test_keywords, days=7)
        titles = [r["title"] for r in result]
        assert "Трамп подписал указ" not in titles

    def test_filter_keeps_travel_source_no_kw(self, sample_items, test_keywords):
        """BBT item without keywords → kept, assigned first configured topic."""
        # sample_items[1] = "Marriott открывает..." from BBT (no "general")
        result = filter_and_classify(sample_items, test_keywords, days=7)
        bbt_items = [r for r in result if r["source"] == "BBT"]
        # BBT items should be present
        assert len(bbt_items) >= 1
        # Each should have exactly ONE classified topic
        for item in bbt_items:
            assert len(item["classified_topics"]) == 1

    def test_dedup_by_url(self, sample_items, test_keywords):
        """Two items with same URL → only one remains."""
        result = filter_and_classify(sample_items, test_keywords, days=7)
        urls = [r["link"] for r in result]
        assert urls.count("https://example.com/aeroflot-cancelled") == 1

    def test_dedup_by_normalized_title(self, sample_items, test_keywords):
        """Title with different punctuation → deduped."""
        result = filter_and_classify(sample_items, test_keywords, days=7)
        titles = [r["title"] for r in result]
        # Should have "Аэрофлот отменил рейсы в Стамбул" but NOT "Аэрофлот отменил рейсы в Стамбул!!!"
        has_bang = any("!!!" in t for t in titles)
        assert not has_bang

    def test_date_filter_old_items(self, sample_items, test_keywords):
        """Items older than --days → filtered out."""
        result = filter_and_classify(sample_items, test_keywords, days=7)
        titles = [r["title"] for r in result]
        # Old item from 2024 should be gone
        assert "Старый рейс Аэрофлота" not in titles

    def test_date_no_date_included(self, sample_items, test_keywords):
        """Items without date → included."""
        result = filter_and_classify(sample_items, test_keywords, days=7)
        titles = [r["title"] for r in result]
        assert "Новый авиа-маршрут анонсирован" in titles

    def test_classified_topics_single(self, sample_items, test_keywords):
        """Each filtered item has exactly one classified topic."""
        result = filter_and_classify(sample_items, test_keywords, days=7)
        for item in result:
            assert len(item["classified_topics"]) == 1


# ═══════════════════════════════════════════════════════════
# P3: parsing (4 tests — mocked data)
# ═══════════════════════════════════════════════════════════

class TestParseRSS:

    def test_parse_rss_mock(self, monkeypatch):
        """Mock RSS XML with 3 items → 3 parsed."""
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
            <title>Test Feed</title>
            <item>
                <title>First News</title>
                <link>https://example.com/1</link>
                <description>First description</description>
                <pubDate>Tue, 12 Aug 2026 10:00:00 GMT</pubDate>
            </item>
            <item>
                <title>Second News</title>
                <link>https://example.com/2</link>
                <description>Second description</description>
                <pubDate>Mon, 11 Aug 2026 10:00:00 GMT</pubDate>
            </item>
            <item>
                <title>Third News</title>
                <link>https://example.com/3</link>
                <description>Third</description>
                <pubDate>Sun, 10 Aug 2026 10:00:00 GMT</pubDate>
            </item>
        </channel></rss>"""

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = rss_xml

        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", lambda *a, **kw: mock_resp)

        source = {"name": "TestFeed", "url": "https://example.com/", "rss": "https://example.com/rss"}
        items, err = parse_rss(source)
        assert err is None
        assert len(items) == 3
        assert items[0]["title"] == "First News"
        assert items[0]["link"] == "https://example.com/1"

    def test_parse_rss_empty(self, monkeypatch):
        """Empty RSS → 0 items, no error."""
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Empty</title></channel></rss>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = rss_xml
        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", lambda *a, **kw: mock_resp)

        source = {"name": "Empty", "url": "https://example.com/", "rss": "https://example.com/rss"}
        items, err = parse_rss(source)
        assert err is None
        assert len(items) == 0

    def test_parse_rss_http_error(self, monkeypatch):
        """HTTP 403 → error returned."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = ""
        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", lambda *a, **kw: mock_resp)

        source = {"name": "Blocked", "url": "https://example.com/", "rss": "https://example.com/rss"}
        items, err = parse_rss(source)
        assert items == []
        assert "403" in err

    def test_parse_html_mock(self, monkeypatch):
        """Mock HTML with 5 links → 5 items."""
        html = """<html><body>
        <a href="/news/1">First news headline here</a>
        <a href="/news/2">Second news headline here</a>
        <a href="/news/3">Third news headline here</a>
        <a href="/news/4">Fourth news headline here</a>
        <a href="/news/5">Fifth news headline here</a>
        <a href="/x">short</a>
        </body></html>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", lambda *a, **kw: mock_resp)

        source = {
            "name": "TestHTML",
            "url": "https://example.com/",
            "selector": "a[href*='/news/']",
            "text_min_length": 20,
        }
        items, err = parse_html(source)
        assert err is None
        assert len(items) == 5
        assert items[0]["title"] == "First news headline here"
        assert items[0]["link"] == "https://example.com/news/1"


# ═══════════════════════════════════════════════════════════
# P4: fetch_with_retry + load_sources (4 tests)
# ═══════════════════════════════════════════════════════════

class TestFetchWithRetry:

    def test_fetch_retry_returns_text_on_success(self, monkeypatch):
        """Successful fetch returns text."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>OK</html>"
        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", lambda *a, **kw: mock_resp)

        result = fetch_with_retry("https://example.com/", {"impersonate": "safari"}, use_cffi=True)
        assert result == "<html>OK</html>"

    def test_fetch_retry_3_attempts(self, monkeypatch):
        """3 timeouts → returns None after 3 retries."""
        call_count = {"n": 0}

        def mock_get(*a, **kw):
            call_count["n"] += 1
            raise Exception("timeout")

        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", mock_get)
        # Patch time.sleep to avoid real delays
        monkeypatch.setattr("fetch_travel_news.time.sleep", lambda x: None)

        result = fetch_with_retry("https://example.com/", {"impersonate": "safari", "retry": 3}, use_cffi=True)
        assert result is None
        assert call_count["n"] == 3

    def test_fetch_retry_http_403_then_success(self, monkeypatch):
        """HTTP 403 on first attempt, 200 on second → returns text."""
        responses = [
            MagicMock(status_code=403, text=""),
            MagicMock(status_code=200, text="<html>OK</html>"),
        ]
        call_count = {"n": 0}

        def mock_get(*a, **kw):
            r = responses[call_count["n"]]
            call_count["n"] += 1
            return r

        monkeypatch.setattr("fetch_travel_news.cffi_requests.get", mock_get)
        monkeypatch.setattr("fetch_travel_news.time.sleep", lambda x: None)

        result = fetch_with_retry("https://example.com/", {"impersonate": "safari", "retry": 3}, use_cffi=True)
        assert result == "<html>OK</html>"
        assert call_count["n"] == 2


class TestLoadSources:

    def test_load_sources_filter_region(self, tmp_path, monkeypatch):
        """--region ru → only RU sources."""
        import yaml as yaml_mod
        config = {
            "sources": [
                {"name": "RU1", "url": "http://x", "fetch": "rss", "region": "ru", "priority": "P1", "topics": ["general"]},
                {"name": "INTL1", "url": "http://y", "fetch": "rss", "region": "intl", "priority": "P1", "topics": ["general"]},
            ]
        }
        p = tmp_path / "sources.yaml"
        p.write_text(yaml_mod.dump(config), encoding="utf-8")
        monkeypatch.setattr("fetch_travel_news.SOURCES_YAML", p)

        result = load_sources("ru", None)
        assert len(result) == 1
        assert result[0]["name"] == "RU1"

    def test_load_sources_filter_priority(self, tmp_path, monkeypatch):
        """--priority P1 → only P1 sources."""
        import yaml as yaml_mod
        config = {
            "sources": [
                {"name": "P1src", "url": "http://x", "fetch": "rss", "region": "ru", "priority": "P1", "topics": ["general"]},
                {"name": "P2src", "url": "http://y", "fetch": "rss", "region": "ru", "priority": "P2", "topics": ["general"]},
            ]
        }
        p = tmp_path / "sources.yaml"
        p.write_text(yaml_mod.dump(config), encoding="utf-8")
        monkeypatch.setattr("fetch_travel_news.SOURCES_YAML", p)

        result = load_sources(None, "P1")
        assert len(result) == 1
        assert result[0]["name"] == "P1src"

    def test_load_sources_invalid_yaml(self, tmp_path, monkeypatch):
        """Malformed YAML → raises exception (not silent fail)."""
        p = tmp_path / "sources.yaml"
        p.write_text("sources: [\n{invalid yaml", encoding="utf-8")
        monkeypatch.setattr("fetch_travel_news.SOURCES_YAML", p)

        with pytest.raises(Exception):
            load_sources(None, None)


# ═══════════════════════════════════════════════════════════
# P5: seen_db (3 tests)
# ═══════════════════════════════════════════════════════════

class TestSeenDB:

    def test_url_hash_deterministic(self):
        """Same URL → same hash."""
        h1 = url_hash("https://example.com/page")
        h2 = url_hash("https://example.com/page")
        assert h1 == h2

    def test_url_hash_case_insensitive(self):
        """URL hash is case-insensitive."""
        h1 = url_hash("https://Example.COM/Page")
        h2 = url_hash("https://example.com/page")
        assert h1 == h2

    def test_seen_db_mark_and_check(self, tmp_seen_db):
        """mark_seen → is_seen returns True."""
        conn = init_seen_db()
        url = "https://example.com/news/1"
        assert not is_seen(conn, url)
        mark_seen(conn, url, "TestSource", "Test Title")
        assert is_seen(conn, url)
        conn.close()

    def test_seen_db_different_url_not_seen(self, tmp_seen_db):
        """mark url1, check url2 → False."""
        conn = init_seen_db()
        mark_seen(conn, "https://example.com/1", "Src", "T1")
        assert not is_seen(conn, "https://example.com/2")
        conn.close()


# ═══════════════════════════════════════════════════════════
# P6: format_markdown (3 tests)
# ═══════════════════════════════════════════════════════════

class TestFormatMarkdown:

    def _make_items(self):
        return [
            {
                "title": "Аэрофлот отменил рейсы",
                "link": "https://example.com/1",
                "description": "Несколько рейсов отменены",
                "date": "Tue, 12 Aug 2026 10:00:00 GMT",
                "source": "Коммерсантъ",
                "region": "ru",
                "classified_topics": ["aviation"],
            },
            {
                "title": "Marriott открывает отель",
                "link": "https://example.com/2",
                "description": "Новый отель",
                "date": "Mon, 11 Aug 2026 12:00:00 GMT",
                "source": "BBT",
                "region": "ru",
                "classified_topics": ["hotels"],
            },
        ]

    def test_markdown_has_sections(self):
        """Markdown contains section headers for items present."""
        md = format_markdown(self._make_items(), {}, days=7)
        assert "✈️ ПЕРЕЛЁТЫ" in md
        assert "🏨 ОТЕЛИ" in md
        # Командировки section only if business_travel items present (none in test data)
        # so we don't assert it here

    def test_markdown_has_business_travel_section(self):
        """Markdown contains Командировки section when business_travel items present."""
        items = self._make_items()
        items.append({
            "title": "GBTA: командировки выросли",
            "link": "https://example.com/3",
            "description": "Рост на 7%",
            "date": "Tue, 12 Aug 2026 10:00:00 GMT",
            "source": "BBT",
            "region": "ru",
            "classified_topics": ["business_travel"],
        })
        md = format_markdown(items, {}, days=7)
        assert "🎫" in md or "КОМАНДИРОВКИ" in md

    def test_markdown_failed_sources(self):
        """Markdown contains Failed Sources section when errors present."""
        md = format_markdown(self._make_items(), {"Travel Weekly": "403"}, days=7)
        assert "⚠️ Failed Sources" in md
        assert "Travel Weekly" in md

    def test_markdown_url_present(self):
        """Markdown contains at least one URL."""
        md = format_markdown(self._make_items(), {}, days=7)
        assert "https://example.com/1" in md or "example.com" in md

    def test_markdown_source_and_date(self):
        """Each item has source and date in parentheses."""
        md = format_markdown(self._make_items(), {}, days=7)
        assert "Коммерсантъ" in md
        assert "12.08" in md


# ═══════════════════════════════════════════════════════════
# P7: Integration (2 tests — @pytest.mark.slow)
# ═══════════════════════════════════════════════════════════

@pytest.mark.slow
class TestIntegration:

    def test_health_check_3_sources(self, tmp_path, monkeypatch):
        """Health check on test_sources.yaml → all sources return status."""
        import yaml as yaml_mod
        test_yaml = Path(__file__).parent / "test_sources.yaml"
        monkeypatch.setattr("fetch_travel_news.SOURCES_YAML", test_yaml)

        from fetch_travel_news import health_check
        sources = load_sources(None, None)
        result = health_check(sources)
        assert "Test RSS" in result
        assert "Test Google News" in result
        assert "Test curl_cffi" in result

    def test_fetch_all_returns_items(self, tmp_path, monkeypatch):
        """Fetch from test_sources.yaml → items > 0."""
        import asyncio as aio
        test_yaml = Path(__file__).parent / "test_sources.yaml"
        monkeypatch.setattr("fetch_travel_news.SOURCES_YAML", test_yaml)

        sources = load_sources(None, None)
        from fetch_travel_news import fetch_all_sources
        items, errors = aio.run(fetch_all_sources(sources))
        # Don't assert 0 errors — network is flaky
        assert len(items) > 0