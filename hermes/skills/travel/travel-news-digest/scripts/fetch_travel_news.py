#!/usr/bin/env python3
"""Fetch and render a travel-news digest from RSS-backed sources."""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import feedparser
import yaml

SCRIPT_DIR = Path(__file__).parent
SOURCES_YAML = SCRIPT_DIR / "sources.yaml"
USER_AGENT = "Hermes-Travel-News-Digest/1.0"
REQUEST_TIMEOUT_SECONDS = 15
MAX_FEED_BYTES = 2 * 1024 * 1024
MAX_WORKERS = 6


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
    try:
        request = Request(
            source_feed_url(source),
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_FEED_BYTES + 1)
    except HTTPError as exc:
        return [], f"HTTP {exc.code}"
    except (KeyError, TypeError, ValueError) as exc:
        return [], f"invalid source: {exc}"[:120]
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


def classify_item(title: str, summary: str, keywords: dict) -> list[str]:
    text = f"{title} {summary}".casefold()
    matches = []
    for topic, languages in keywords.items():
        words = (word for values in languages.values() for word in values)
        if any(word.casefold() in text for word in words):
            matches.append(topic)
    return matches


def filter_and_classify(
    items: list[dict],
    keywords: dict,
    days: int,
    *,
    now: datetime | None = None,
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=days)
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    result = []

    for item in items:
        published_at = item.get("published_at")
        if published_at:
            try:
                published = datetime.fromisoformat(published_at)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if published < cutoff:
                    continue
            except ValueError:
                pass

        link = item.get("link", "").strip().casefold()
        title_key = re.sub(r"[^\w\s]", "", item["title"].casefold()).strip()
        if (link and link in seen_links) or title_key in seen_titles:
            continue
        if link:
            seen_links.add(link)
        seen_titles.add(title_key)

        matches = classify_item(
            item["title"],
            item.get("summary", ""),
            keywords,
        )
        configured = [
            topic for topic in item.get("topics", []) if topic != "general"
        ]
        if not matches and "general" in item.get("topics", []):
            continue
        item["classified_topics"] = [
            matches[0] if matches else configured[0] if configured else "general"
        ]
        item.pop("summary", None)
        item.pop("topics", None)
        result.append(item)

    result.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    return result


def load_config(
    path: Path = SOURCES_YAML,
    *,
    region: str = "all",
    priority: str = "all",
) -> tuple[list[dict], dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ValueError("sources.yaml must contain a sources list")
    keywords = data.get("keywords", {})
    sources = data["sources"]
    required = {"name", "fetch", "region", "priority", "topics"}
    for index, source in enumerate(sources):
        missing = required - set(source)
        if missing:
            raise ValueError(
                f"source {index} missing: {', '.join(sorted(missing))}"
            )
        if source["fetch"] not in {"rss", "google_news"}:
            raise ValueError(f"unsupported fetch type: {source['fetch']}")
    if region != "all":
        sources = [source for source in sources if source["region"] == region]
    if priority != "all":
        sources = [source for source in sources if source["priority"] == priority]
    return sources, keywords


def render_json(items: list[dict], errors: dict[str, str], *, source_count: int) -> str:
    return json.dumps(
        {
            "items": items,
            "errors": errors,
            "source_count": source_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
        indent=2,
    )


def format_markdown(items: list[dict], errors: dict[str, str], days: int) -> str:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    lines = [
        "# 📰 Дайджест: перелёты, отели, командировки",
        f"**{start:%d.%m.%Y} – {end:%d.%m.%Y}**",
        "",
    ]
    topics = (
        ("aviation", "✈️ Перелёты"),
        ("hotels", "🏨 Отели"),
        ("business_travel", "🎫 Командировки / бизнес-тревел"),
    )
    regions = (("ru", "🇷🇺 Россия"), ("intl", "🌍 Мир"))
    for topic, topic_label in topics:
        topic_items = [item for item in items if topic in item["classified_topics"]]
        if not topic_items:
            continue
        lines.append(f"## {topic_label}")
        for region, region_label in regions:
            section = [item for item in topic_items if item.get("region") == region]
            if not section:
                continue
            lines.extend((f"### {region_label}", ""))
            for item in section[:20]:
                published = item.get("published_at", "")
                date_suffix = f", {published[8:10]}.{published[5:7]}" if published else ""
                lines.append(
                    f"- **{item['title']}** [→]({item['link']}) "
                    f"({item['source']}{date_suffix})"
                )
            lines.append("")
    if not items:
        lines.extend(("_Новостей за выбранный период нет._", ""))
    if errors:
        lines.extend(("## ⚠️ Недоступные источники", ""))
        lines.extend(f"- **{name}**: {error}" for name, error in sorted(errors.items()))
    return "\n".join(lines).rstrip()


def health_check(sources: list[dict]) -> str:
    lines = ["# Health Check", ""]
    for source in sources:
        items, error = fetch_feed(source)
        status = "✅" if not error else "❌"
        result = error or f"{len(items)} items"
        lines.append(f"- {status} **{source['name']}** ({source['fetch']}): {result}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Travel News Digest CLI")
    parser.add_argument(
        "command", nargs="?", choices=["digest", "health"], default="digest"
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--region", choices=["ru", "intl", "all"], default="all")
    parser.add_argument("--priority", choices=["P1", "P2", "P3", "all"], default="all")
    args = parser.parse_args(argv)

    try:
        sources, keywords = load_config(region=args.region, priority=args.priority)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.command == "health":
        print(health_check(sources))
        return 0

    items, errors = fetch_all_sources(sources)
    items = filter_and_classify(items, keywords, args.days)
    output = (
        render_json(items, errors, source_count=len(sources))
        if args.output == "json"
        else format_markdown(items, errors, args.days)
    )
    print(output)
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
