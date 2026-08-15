#!/usr/bin/env python3
"""Parse an airport direct-destination inventory from extracted web content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


def content_from_input(raw: str) -> str:
    """Return article text from an article-CLI JSON envelope or plain text."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("markdown", "text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    raise ValueError("input JSON does not contain article markdown or text")


def parse_inventory(content: str) -> tuple[list[tuple[str, str, int]], dict[str, Any]]:
    """Extract sorted route frequencies and page metadata."""

    metadata: dict[str, Any] = {}
    match = re.search(
        r"has non-stop passenger flights scheduled to (\d+) destinations in (\d+) countries",
        content,
    )
    if match:
        metadata["total_destinations"] = int(match.group(1))
        metadata["countries"] = int(match.group(2))
    match = re.search(r"(\d+) domestic flights?", content)
    if match:
        metadata["domestic"] = int(match.group(1))
    match = re.search(r"Last updated on: ([\d-]+)", content)
    if match:
        metadata["last_updated"] = match.group(1)

    pattern = re.compile(
        r"(?m)^\s*([^\n()]+?)\s*\(([A-Z]{3})\)(?:\\n|\n)\s*(\d+) flights? / month"
    )
    seen: dict[str, tuple[str, int]] = {}
    for match in pattern.finditer(content):
        city = match.group(1).strip()
        iata = match.group(2)
        frequency = int(match.group(3))
        if iata not in seen or frequency > seen[iata][1]:
            seen[iata] = (city, frequency)
    if not seen:
        raise ValueError("no direct destinations found in extracted content")
    routes = sorted(seen.items(), key=lambda item: (-item[1][1], item[0]))
    return [(iata, city, frequency) for iata, (city, frequency) in routes], metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iata", required=True, help="Origin airport IATA code")
    parser.add_argument("--input", default="-", help="article JSON/text file, or -")
    parser.add_argument("--source-url", default="", help="Source URL for JSON output")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    args = parser.parse_args()

    raw = (
        sys.stdin.read()
        if args.input == "-"
        else Path(args.input).read_text(encoding="utf-8")
    )
    try:
        content = content_from_input(raw)
        routes, metadata = parse_inventory(content)
    except ValueError as exc:
        parser.error(str(exc))
    iata = args.iata.strip().upper()
    if args.json:
        print(
            json.dumps(
                {
                    "iata": iata,
                    "source_url": args.source_url or None,
                    "metadata": metadata,
                    "routes": [
                        {"iata": code, "city": city, "flights_per_month": frequency}
                        for code, city, frequency in routes
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"=== {iata}")
    print(f"last updated: {metadata.get('last_updated', '?')}")
    print(f"destinations: {len(routes)}")
    for code, city, frequency in routes:
        print(f"{code:4} {city:40} {frequency}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
