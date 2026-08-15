#!/usr/bin/env python3
"""
fetch_travel_news.py — Travel news digest CLI.

Fetches news from RSS, Atom, and Google News RSS sources,
classifies by topic (aviation/hotels/business_travel), deduplicates,
and outputs a Markdown digest.

Usage:
  python fetch_travel_news.py all --days 7 --output markdown
  python fetch_travel_news.py all --days 7 --region ru --priority P1
  python fetch_travel_news.py all --output json
  python fetch_travel_news.py health
  python fetch_travel_news.py clear-cache
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import feedparser
import yaml

# ─── Paths ───────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SOURCES_YAML = SCRIPT_DIR / "sources.yaml"
CACHE_DIR = Path.home() / ".cache" / "travel-news"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_DB = CACHE_DIR / "seen.db"
RAW_JSON = CACHE_DIR / "raw_items.json"

# ─── Constants ───────────────────────────────────────────
USER_AGENT = "Hermes-Travel-News-Digest/1.0"
REQUEST_TIMEOUT_SECONDS = 15
MAX_FEED_BYTES = 2 * 1024 * 1024
MAX_WORKERS = 6
SEEN_DB_RETENTION_DAYS = 30


# ═════════════════════════════════════════════════════════
# CACHE / DEDUP
# ═════════════════════════════════════════════════════════

def init_seen_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SEEN_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            url_hash TEXT PRIMARY KEY,
            url TEXT,
            source TEXT,
            seen_at TEXT,
            title TEXT
        )
    """)
    conn.commit()
    # Purge old entries
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_DB_RETENTION_DAYS)).isoformat()
    conn.execute("DELETE FROM seen WHERE seen_at < ?", (cutoff,))
    conn.commit()
    return conn


def url_hash(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()


def is_seen(conn: sqlite3.Connection, url: str) -> bool:
    h = url_hash(url)
    row = conn.execute("SELECT 1 FROM seen WHERE url_hash = ?", (h,)).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, url: str, source: str, title: str = ""):
    h = url_hash(url)
    conn.execute(
        "INSERT OR IGNORE INTO seen (url_hash, url, source, seen_at, title) VALUES (?, ?, ?, ?, ?)",
        (h, url, source, datetime.now(timezone.utc).isoformat(), title[:200]),
    )
    conn.commit()


def clear_seen_db():
    if SEEN_DB.exists():
        SEEN_DB.unlink()
    print("✅ Cache cleared")


# ═════════════════════════════════════════════════════════
# FETCHERS
# ═════════════════════════════════════════════════════════

def source_feed_url(source: dict) -> str:
    if source["fetch"] == "rss":
        return source.get("rss") or source["url"]
    params = {
        "q": source["query"],
        "hl": source.get("hl", "ru"),
        "gl": source.get("gl", "RU"),
        "ceid": source.get("ceid", "RU:ru"),
    }
    return "https://news.google.com/rss?" + urlencode(params)


def _published_at(entry: dict) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return ""
    return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()


def fetch_feed(source: dict) -> tuple[list[dict], str | None]:
    request = Request(source_feed_url(source), headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_FEED_BYTES + 1)
    except HTTPError as exc:
        return [], f"HTTP {exc.code}"
    except (URLError, TimeoutError) as exc:
        message = exc.reason if isinstance(exc, URLError) else exc
        return [], str(message)[:120]

    if len(payload) > MAX_FEED_BYTES:
        return [], f"feed exceeds {MAX_FEED_BYTES} bytes"

    parsed = feedparser.parse(payload)
    if parsed.bozo and not parsed.entries:
        return [], f"invalid feed: {parsed.bozo_exception}"[:120]

    items = []
    for entry in parsed.entries[:30]:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "published_at": _published_at(entry),
                "summary": str(entry.get("summary", ""))[:500],
                "source": source["name"],
                "region": source.get("region", "ru"),
                "topics": source.get("topics", []),
            }
        )
    return items, None


def fetch_all_sources(
    sources: list[dict], *, max_workers: int = MAX_WORKERS
) -> tuple[list[dict], dict[str, str]]:
    items: list[dict] = []
    errors: dict[str, str] = {}
    workers = max(1, min(max_workers, len(sources) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_feed, source): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                batch, error = future.result()
            except Exception as exc:
                batch, error = [], str(exc)[:120]
            if error:
                errors[source["name"]] = error
            else:
                items.extend(batch)
    return items, errors


# ═════════════════════════════════════════════════════════
# PROCESSING
# ═════════════════════════════════════════════════════════

def classify_item(title: str, description: str, keywords: dict) -> list[str]:
    """Classify item by keywords. Returns list of topics."""
    text = (title + " " + description).lower()
    topics = []
    for topic, lang_keywords in keywords.items():
        for lang, words in lang_keywords.items():
            for kw in words:
                if kw.lower() in text:
                    topics.append(topic)
                    break
            if topic in topics:
                break
    return list(set(topics))


def filter_and_classify(items: list[dict], keywords: dict, days: int) -> list[dict]:
    """Filter by date, classify, deduplicate."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    seen_urls = set()
    seen_titles = set()
    result = []

    for item in items:
        # Date filter (skip if no date — include anyway)
        if item.get("date"):
            try:
                # Try parsing various date formats
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(item["date"])
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt and dt < cutoff:
                    continue
            except Exception:
                pass  # If can't parse date, include the item

        # Dedup by URL
        url = item.get("link", "").strip().lower()
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # Dedup by normalized title
        norm_title = re.sub(r"[^\w\s]", "", item["title"].lower()).strip()
        if norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)

        # Classify — keyword match required for general news sources
        topics = classify_item(item["title"], item.get("description", ""), keywords)

        # For sources that include "general" in their topics (Коммерсантъ, Интерфакс,
        # Ведомости, Lenta, Sostav — general news media), DROP items that don't match
        # any travel keywords — they're irrelevant (politics, war, celebrity gossip)
        source_topics = item.get("topics", [])
        has_general = "general" in source_topics

        if not topics:
            if has_general:
                continue  # Skip irrelevant news from general sources
            # For travel-specific sources, assign to FIRST configured topic only
            configured = [t for t in source_topics if t != "general"]
            item["classified_topics"] = [configured[0]] if configured else ["general"]
        else:
            # Assign to FIRST matching topic only (avoid duplicates across sections)
            item["classified_topics"] = [topics[0]]

        result.append(item)

    # Sort by date (newest first), items without date go last
    result.sort(key=lambda x: x.get("date", ""), reverse=True)
    return result


# ═════════════════════════════════════════════════════════
# DIGEST FORMATTING
# ═════════════════════════════════════════════════════════

def format_markdown(items: list[dict], errors: dict[str, str], days: int) -> str:
    """Format items into Markdown digest."""
    today = datetime.now().strftime("%d.%m.%Y")
    week_ago = (datetime.now() - timedelta(days=days)).strftime("%d.%m.%Y")

    # Group by topic and region
    topics_map = {
        "aviation": "✈️ ПЕРЕЛЁТЫ",
        "hotels": "🏨 ОТЕЛИ",
        "business_travel": "🎫 КОМАНДИРОВКИ / БИЗНЕС-ТРЕВЕЛ",
        "mice": "🎫 КОМАНДИРОВКИ / БИЗНЕС-ТРЕВЕЛ",
        "general": "📋 ОБЩЕЕ",
    }

    sections = {"ru": {}, "intl": {}}
    for region in ["ru", "intl"]:
        for topic_key in topics_map:
            sections[region][topic_key] = []

    for item in items:
        region = item.get("region", "ru")
        if region not in ("ru", "intl"):
            region = "intl"
        for topic in item.get("classified_topics", ["general"]):
            if topic in topics_map:
                sections[region][topic].append(item)

    # Build markdown
    lines = []
    lines.append("# 📰 Дайджест: перелёты, отели, командировки")
    lines.append(f"**Неделя {week_ago} – {today} · Источников: {len(items)}**\n")

    source_names = sorted(set(item["source"] for item in items))
    lines.append(f"**Источники:** {', '.join(source_names)}\n")
    lines.append("---\n")

    for region, region_label in [("ru", "🇷🇺 Россия"), ("intl", "🌍 Мир")]:
        for topic_key, topic_label in topics_map.items():
            section_items = sections[region][topic_key]
            if not section_items:
                continue
            # Always print topic header + region subheader
            lines.append(f"## {topic_label}")
            lines.append(f"### {region_label}\n")

            # Avoid duplicate items across topics — track printed
            printed = set()
            for item in section_items[:20]:  # max 20 per section
                item_id = item.get("link") or item["title"]
                if item_id in printed:
                    continue
                printed.add(item_id)

                desc = item.get("description", "")
                date_str = ""
                if item.get("date"):
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(item["date"])
                        if dt:
                            date_str = dt.strftime("%d.%m")
                    except Exception:
                        pass

                source = item["source"]
                suffix = f"({source}, {date_str})" if date_str else f"({source})"
                desc_part = f" — {desc}" if desc and len(desc) > 10 else ""
                link = item.get("link", "")
                link_part = f" [→]({link})" if link else ""
                lines.append(f"- **{item['title']}**{desc_part}{link_part} {suffix}")

            lines.append("")

    # Failed sources
    if errors:
        lines.append("---\n")
        lines.append("## ⚠️ Failed Sources\n")
        for name, err in sorted(errors.items()):
            lines.append(f"- **{name}**: {err}")
        lines.append("")

    lines.append("---\n")
    lines.append("### 📌 Источники")
    lines.append(f"Собрано из {len(source_names)} источников. Ошибок: {len(errors)}.\n")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════
# HEALTH CHECK
# ═════════════════════════════════════════════════════════

def health_check(sources: list[dict]) -> str:
    """Check health of all sources."""
    lines = ["# Health Check\n"]
    lines.append("| # | Source | Type | Status | Items | Error |")
    lines.append("|---|--------|------|--------|-------|-------|")

    for i, source in enumerate(sources, 1):
        fetch_type = source["fetch"]
        items, err = fetch_feed(source)

        status = "✅" if not err else "❌"
        lines.append(f"| {i} | {source['name']} | {fetch_type} | {status} | {len(items)} | {err or ''} |")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════

def load_sources(region: str | None, priority: str | None) -> list[dict]:
    with open(SOURCES_YAML, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = config["sources"]
    if region and region != "all":
        sources = [s for s in sources if s.get("region") == region]
    if priority and priority != "all":
        sources = [s for s in sources if s.get("priority") == priority]
    return sources


def main():
    parser = argparse.ArgumentParser(description="Travel News Digest CLI")
    parser.add_argument("command", choices=["all", "fetch", "process", "digest", "health", "clear-cache"])
    parser.add_argument("--days", type=int, default=7, help="News from last N days")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--region", choices=["ru", "intl", "all"], default="all")
    parser.add_argument("--priority", choices=["P1", "P2", "P3", "all"], default="all")

    args = parser.parse_args()

    if args.command == "clear-cache":
        clear_seen_db()
        return

    sources = load_sources(args.region, args.priority)

    if args.command == "health":
        print(health_check(sources))
        return

    with open(SOURCES_YAML, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    keywords = config.get("keywords", {})

    conn = init_seen_db()

    # ─── FETCH ─────────────────────────────────────────
    if args.command in ("all", "fetch"):
        print(f"Fetching from {len(sources)} sources...", file=sys.stderr)
        items, errors = fetch_all_sources(sources)
        print(f"  → {len(items)} items, {len(errors)} errors", file=sys.stderr)

        if args.command == "fetch" and args.output == "json":
            print(json.dumps({"items": items, "errors": errors}, ensure_ascii=False, indent=2))
            return

        # Save raw for reuse
        with open(RAW_JSON, "w", encoding="utf-8") as f:
            json.dump({"items": items, "errors": errors}, f, ensure_ascii=False)
    else:
        # Load from cache
        if not RAW_JSON.exists():
            print("No cached data. Run 'fetch' first.", file=sys.stderr)
            sys.exit(1)
        with open(RAW_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            items = data["items"]
            errors = data.get("errors", {})

    # ─── PROCESS ──────────────────────────────────────
    if args.command in ("all", "process"):
        items = filter_and_classify(items, keywords, args.days)
        # Mark seen
        for item in items:
            if item.get("link"):
                mark_seen(conn, item["link"], item["source"], item["title"])
        print(f"  → {len(items)} items after filtering", file=sys.stderr)

    # ─── DIGEST ───────────────────────────────────────
    if args.command in ("all", "digest"):
        if args.output == "json":
            print(json.dumps({"items": items, "errors": errors}, ensure_ascii=False, indent=2))
        else:
            print(format_markdown(items, errors, args.days))

    conn.close()


if __name__ == "__main__":
    main()
