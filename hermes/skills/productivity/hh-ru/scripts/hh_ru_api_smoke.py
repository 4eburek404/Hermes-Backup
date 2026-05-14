#!/usr/bin/env python3
"""Small hh.ru API smoke client for the hh-ru skill.

Environment:
  HH_RU_TOKEN  optional bearer token

Examples:
  python3 hh_ru_api_smoke.py /areas/113
  python3 hh_ru_api_smoke.py /vacancies --param text=Python --param area=1 --param per_page=10
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.hh.ru"
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie"}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in SENSITIVE_HEADERS or "api-key" in k.lower() else v) for k, v in headers.items()}


def api_get(endpoint: str, params: dict[str, str], retries: int, backoff_seconds: int) -> dict:
    token = os.getenv("HH_RU_TOKEN")
    headers = {"Accept": "application/json", "User-Agent": "Hermes/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = BASE + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)

    last_error: str | None = None
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed API host
                raw = resp.read().decode("utf-8", errors="replace")
                return {"ok": True, "status": resp.status, "headers": redact_headers(dict(resp.headers)), "data": json.loads(raw)}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {e.code}: {body[:300]}"
            if e.code == 403 and attempt + 1 < retries:
                time.sleep(backoff_seconds * (2 ** attempt))
                continue
            return {"ok": False, "status": e.code, "error": last_error, "headers": redact_headers(dict(e.headers))}
    return {"ok": False, "error": last_error or "request failed"}


def main() -> int:
    p = argparse.ArgumentParser(description="hh.ru API smoke client")
    p.add_argument("endpoint", help="API endpoint, e.g. /areas/113 or /vacancies")
    p.add_argument("--param", action="append", default=[], help="Query param as key=value; repeatable")
    p.add_argument("--retries", type=int, default=1)
    p.add_argument("--backoff-seconds", type=int, default=180)
    args = p.parse_args()
    params: dict[str, str] = {}
    for item in args.param:
        if "=" not in item:
            raise SystemExit(f"Bad --param {item!r}; expected key=value")
        k, v = item.split("=", 1)
        params[k] = v
    result = api_get(args.endpoint, params, args.retries, args.backoff_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
