#!/usr/bin/env python3
"""Fetch Google News RSS titles for the news-search skill.

Examples:
  python3 google_news_rss_titles.py --limit 20
  python3 google_news_rss_titles.py --query 'Иран США' --hl ru --gl RU --limit 10
  python3 google_news_rss_titles.py --query 'Middle East' --hl en --gl US --ceid US:en
"""
from __future__ import annotations

import argparse
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def build_url(hl: str, gl: str, ceid: str, query: str | None) -> str:
    params = {"hl": hl, "gl": gl, "ceid": ceid}
    if query:
        params["q"] = query
    return "https://news.google.com/rss?" + urllib.parse.urlencode(params)


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch Google News RSS titles")
    p.add_argument("--hl", default="ru", help="Interface language, e.g. ru or en")
    p.add_argument("--gl", default="RU", help="Geo edition, e.g. RU, US, GB")
    p.add_argument("--ceid", default="RU:ru", help="Country edition, e.g. RU:ru or US:en")
    p.add_argument("--query", "-q", default=None, help="Optional news search query")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--show-links", action="store_true")
    args = p.parse_args()

    url = build_url(args.hl, args.gl, args.ceid, args.query)
    req = urllib.request.Request(url, headers={"User-Agent": "HermesNewsRSS/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - news source URL is fixed
        tree = ET.parse(resp)

    for item in tree.getroot().findall(".//item")[: max(0, args.limit)]:
        title = (item.findtext("title") or "").strip()
        pubdate = (item.findtext("pubDate") or "").strip()
        link = (item.findtext("link") or "").strip()
        print(f"{pubdate} | {title}")
        if args.show_links and link:
            print(f"  {link}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
