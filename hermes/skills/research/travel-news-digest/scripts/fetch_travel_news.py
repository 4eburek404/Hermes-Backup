#!/usr/bin/env python3
"""
fetch_travel_news.py — Travel news digest CLI.

Fetches news from RSS, HTML (curl_cffi), and Google News RSS sources,
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
import asyncio
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import feedparser
import yaml
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

# ─── Paths ───────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SOURCES_YAML = SCRIPT_DIR / "sources.yaml"
CACHE_DIR = Path.home() / ".cache" / "travel-news"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_DB = CACHE_DIR / "seen.db"
RAW_JSON = CACHE_DIR / "raw_items.json"
SKILL_DIR = SCRIPT_DIR.parent
GN_SCRIPT = SKILL_DIR.parent / "web-content-acquisition" / "scripts" / "google_news_rss_titles.py"

# ─── Constants ───────────────────────────────────────────
MAX_CONCURRENT = 10
REQUEST_TIMEOUT = 15
RETRY_DELAYS = [1, 2, 4]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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

def fetch_with_retry(url: str, source_cfg: dict, use_cffi: bool = False) -> str | None:
    """Fetch URL with retry logic. Returns HTML text or None."""
    impersonate = source_cfg.get("impersonate", "safari")
    retries = source_cfg.get("retry", 1)

    for attempt in range(retries):
        try:
            if use_cffi:
                r = cffi_requests.get(url, impersonate=impersonate, timeout=REQUEST_TIMEOUT)
            else:
                import httpx
                r = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                return r.text
            elif attempt < retries - 1:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                time.sleep(delay)
        except Exception:
            if attempt < retries - 1:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                time.sleep(delay)
    return None


def parse_rss(source: dict) -> tuple[list[dict], str | None]:
    """Parse RSS feed. Returns (items, error)."""
    rss_url = source.get("rss", source["url"])
    try:
        # Use curl_cffi for TLS-fingerprinted fetch, then feedparser for parsing
        r = cffi_requests.get(rss_url, impersonate="safari", timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        parsed = feedparser.parse(r.text)
        items = []
        for entry in parsed.entries[:30]:  # last 30 items
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            desc = entry.get("description", "").strip()
            # Strip HTML from description
            if desc:
                desc = BeautifulSoup(desc, "html.parser").get_text(strip=True)[:300]
            date = entry.get("published", entry.get("updated", ""))
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "date": date,
                    "source": source["name"],
                    "region": source.get("region", "ru"),
                })
        return items, None
    except Exception as e:
        return [], str(e)[:100]


def parse_html(source: dict) -> tuple[list[dict], str | None]:
    """Parse HTML page with curl_cffi + BeautifulSoup. Returns (items, error)."""
    url = source["url"]
    selector = source.get("selector", "a")
    min_len = source.get("text_min_length", 20)

    html = fetch_with_retry(url, source, use_cffi=True)
    if html is None:
        return [], "fetch failed (timeout/403)"

    try:
        soup = BeautifulSoup(html, "html.parser")
        items = []
        seen_titles = set()
        for a in soup.select(selector):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if len(title) >= min_len and title not in seen_titles:
                seen_titles.add(title)
                full_url = urljoin(url, href) if href else url
                items.append({
                    "title": title,
                    "link": full_url,
                    "description": "",  # HTML listing usually no description
                    "date": "",  # will be empty for HTML sources
                    "source": source["name"],
                    "region": source.get("region", "intl"),
                })
        return items[:30], None
    except Exception as e:
        return [], str(e)[:100]


def parse_google_news(source: dict) -> tuple[list[dict], str | None]:
    """Run google_news_rss_titles.py as subprocess."""
    query = source["query"]
    hl = source.get("hl", "ru")
    gl = source.get("gl", "RU")
    ceid = source.get("ceid", "")

    cmd = [sys.executable, str(GN_SCRIPT), "--query", query, "--hl", hl, "--gl", gl, "--limit", "20"]
    if ceid:
        cmd.extend(["--ceid", ceid])

    try:
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
        if result.returncode != 0:
            return [], f"script exit {result.returncode}"

        items = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split(" | ", 1)
            if len(parts) == 2:
                date_str, title = parts
                # Extract source from title (format: "Title - SourceName")
                source_name = source["name"]
                if " - " in title:
                    title, orig_source = title.rsplit(" - ", 1)
                    source_name = orig_source.strip()
                items.append({
                    "title": title.strip(),
                    "link": "",
                    "description": "",
                    "date": date_str.strip(),
                    "source": source_name,
                    "region": source.get("region", "ru"),
                })
        return items, None
    except Exception as e:
        return [], str(e)[:100]


# ═════════════════════════════════════════════════════════
# ORCHESTRATION
# ═════════════════════════════════════════════════════════

async def fetch_all_sources(sources: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Fetch all sources concurrently. Returns (all_items, errors)."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    all_items = []
    errors = {}

    async def fetch_one(source: dict):
        async with semaphore:
            loop = asyncio.get_event_loop()
            fetch_type = source["fetch"]

            if fetch_type == "rss":
                items, err = await loop.run_in_executor(None, parse_rss, source)
            elif fetch_type == "curl_cffi":
                items, err = await loop.run_in_executor(None, parse_html, source)
            elif fetch_type == "google_news":
                items, err = await loop.run_in_executor(None, parse_google_news, source)
            else:
                items, err = [], f"unknown fetch type: {fetch_type}"

            if err:
                errors[source["name"]] = err
            else:
                # Attach topics from source config
                for item in items:
                    item["topics"] = source.get("topics", [])
                    item["priority"] = source.get("priority", "P3")
                all_items.extend(items)

    tasks = [fetch_one(s) for s in sources]
    await asyncio.gather(*tasks)
    return all_items, errors


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
    lines.append(f"# 📰 Дайджест: перелёты, отели, командировки")
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
        if fetch_type == "rss":
            items, err = parse_rss(source)
        elif fetch_type == "curl_cffi":
            items, err = parse_html(source)
        elif fetch_type == "google_news":
            items, err = parse_google_news(source)
        else:
            items, err = [], "unknown type"

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
        items, errors = asyncio.run(fetch_all_sources(sources))
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