#!/usr/bin/env python3
"""Fallback HTML extractor for the web-article-reader skill.

Use only when the primary `article` CLI is unavailable. This is deliberately
small and dependency-free; it extracts <article>, then <main>, then <body> and
prints plain-ish text. For JS-heavy pages, use browser rendering instead.
"""
from __future__ import annotations

import argparse
import html
import re
import urllib.request


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HermesArticleFallback/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - user-provided URL by design
        raw = resp.read()
        ctype = resp.headers.get("content-type", "")
    m = re.search(r"charset=([^;]+)", ctype, re.I)
    encoding = (m.group(1).strip() if m else "utf-8") or "utf-8"
    return raw.decode(encoding, errors="replace")


def extract_text(text: str) -> str:
    for tag in ("article", "main", "body"):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.I | re.S)
        if m:
            content = m.group(1)
            break
    else:
        raise SystemExit("Could not extract article/main/body content")

    content = re.sub(r"<script[^>]*>.*?</script>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<style[^>]*>.*?</style>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<h([1-3])[^>]*>(.*?)</h\1>", r"\n## \2\n", content, flags=re.I | re.S)
    content = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n", content, flags=re.I | re.S)
    content = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", content, flags=re.I | re.S)
    content = re.sub(r"<img[^>]*alt=[\"']([^\"']*)[\"'][^>]*>", r"[Image: \1]", content, flags=re.I)
    content = re.sub(r"<[^>]+>", " ", content)
    content = html.unescape(content)
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n[ \t]+", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dependency-free fallback article extractor")
    parser.add_argument("url")
    args = parser.parse_args()
    print(extract_text(fetch(args.url)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
