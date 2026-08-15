# Travel News Digest Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline plan execution to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not add subagents, libraries, compatibility wrappers, or new design documents.

**Goal:** Reduce `travel-news-digest` from a 3381-line mini-platform to a reliable weekly feed-to-Markdown CLI with one new runtime dependency.

**Architecture:** Keep one synchronous pipeline: load trusted YAML config, fetch RSS/Atom and Google News RSS concurrently with the Python standard library, normalize with `feedparser`, filter and deduplicate in memory, then render Markdown or JSON. Remove HTML scraping, Cloudflare evasion, subprocess delegation, staged raw caches, SQLite state, retries, and browser/subagent instructions.

**Tech Stack:** Python 3.13 standard library, `feedparser==6.0.14`, existing `PyYAML==6.0.3`, pytest, Ruff.

---

## Current Baseline

- Branch: `feat/travel-news-digest-cli` at `80eba56`.
- Scope: 18 files, 3381 inserted lines.
- Fast tests: `33 passed, 2 deselected`.
- Ruff: 14 findings, including two undefined `Path` references in slow tests.
- Runtime imports: `feedparser`, `PyYAML`, `BeautifulSoup`, `curl_cffi`; a dead branch imports absent `httpx`.
- Declared but unused dependencies: `lxml`, `jinja2`.
- No code outside this skill calls `fetch_travel_news.py`; backward-compatible command aliases are unnecessary.

## Execution Record (2026-08-15)

Implemented task-by-task on `feat/travel-news-digest-cli`:

- Task 1: `653b8a4` (`test(travel-news): define minimal digest contract`)
- Task 2: `e857ff6` (`refactor(travel-news): keep feed-backed sources only`)
- Task 3: `045b04d` (`refactor(travel-news): unify feed collection`)
- Task 4: `0c67cc9` (`refactor(travel-news): collapse digest pipeline`)
- Task 5: `48197c2` (`docs(travel-news): reduce skill to runtime contract`)

Two execution corrections were required:

1. **Task 3 sequencing:** state imports, constants, and functions remained until Task 4 while `health_check` and the staged CLI switched to synchronous `fetch_all_sources`. Deleting state in Task 3 as originally written would have left a broken intermediate CLI. Task 4 then removed the state and staged commands completely.
2. **Dual deduplication:** `filter_and_classify` uses separate URL and normalized-title sets. The original `link or normalized_title` sample did not remove the same normalized title when it arrived under a different URL; the offline contract now covers that case.

Final verification: `7 passed`; Ruff clean; belief-map boundaries clean for the target and all 221 modules. The live smoke completed in 16.75 seconds with 196 items, 7 isolated source errors, and all 29 configured sources. Final limits: 8 tracked files, 47-line `SKILL.md`, 298-line CLI, 170-line offline test, and 9-line access notes.

## Research Decisions

1. **Use feeds as the product boundary.** `feedparser` already normalizes RSS and Atom, handles encoding and date variants, resolves links, and sanitizes embedded HTML. Do not own a second HTML parsing stack.
   - https://feedparser.readthedocs.io/en/main/
   - https://feedparser.readthedocs.io/en/latest/html-sanitization/
2. **Use bounded standard-library concurrency.** `ThreadPoolExecutor` is sufficient for blocking feed requests. The source list is small and mostly spans different hosts.
   - https://docs.python.org/3/library/concurrent.futures.html
3. **Use the standard-library HTTP client.** `urllib.request.Request` supports headers, redirects, timeouts, proxies, and response status without another client dependency.
   - https://docs.python.org/3/library/urllib.request.html
4. **Keep source failures isolated.** Miniflux exposes per-feed parsing errors, bounded polling, HTTP timeouts, maximum response size, and per-host limits. For this weekly CLI, keep a global worker limit, a timeout, a response-size ceiling, and an error report; defer per-host scheduling until a real rate-limit failure exists.
   - https://miniflux.app/docs/configuration.html
   - https://miniflux.app/docs/api.html
5. **Defer conditional HTTP state.** Mature readers persist ETag and Last-Modified and send them on later polls. A weekly digest needs the current seven-day feed contents and has only 29 planned requests, so persistent HTTP state is not worth a cache layer yet. Add it only if cadence becomes daily or a publisher requests reduced polling.
   - https://feedparser.readthedocs.io/en/stable/http-etag.html
6. **Declare dependencies explicitly.** This is a standalone script, so a two-line `requirements.txt` is smaller than packaging it as a project. Do not rely on comments claiming packages are already in the shared venv.
   - https://packaging.python.org/en/latest/specifications/pyproject-toml/
7. **Reuse `web-content-acquisition` as a follow-up boundary, not as a runtime dependency.** Preserve its tested Google News edition parameters (`hl`, `gl`, `ceid`) and its evidence rule: a Google News wrapper is not proof that the publisher article was read. Keep the digest at feed-entry level. Only when the user explicitly asks for details, hand the selected item to `../web-content-acquisition/SKILL.md` to resolve and extract the direct publisher page. Do not import or spawn its CLI: the documented `md` and `article` commands are unavailable in the canonical environment, and SearXNG/browser/artifact workflows would turn this small scheduled digest into a research platform.
   - `hermes/skills/research/web-content-acquisition/scripts/google_news_rss_titles.py`
   - `hermes/skills/research/web-content-acquisition/references/news-and-rss-followup.md`

## Product Boundary

### Keep

- `digest` command with `--days`, `--output`, `--region`, and `--priority`.
- `health` command for manual source diagnosis.
- 23 direct RSS/Atom sources.
- 6 Google News RSS queries converted to feed URLs in-process with explicit `hl`, `gl`, and `ceid` editions.
- Per-run URL/title deduplication.
- Three deterministic topics: aviation, hotels, business travel.
- Markdown and JSON output.
- Partial success: one broken source never discards successful sources.

### Delete

- Four `curl_cffi` HTML sources: Турпром, Travel Weekly, BTN, PhocusWire.
- `BeautifulSoup`, `soupsieve`, `lxml`, `jinja2`, digest-local `curl_cffi`, and dead `httpx` use.
- `asyncio`, retry/backoff code, CSS selectors, and browser impersonation.
- `fetch`, `process`, `all`, and `clear-cache` commands.
- `raw_items.json`, SQLite `seen.db`, URL hashing, retention cleanup, and cross-run state.
- Google News subprocess dependency on `web-content-acquisition`.
- Live network tests.
- Duplicate source template, completed design plans, subagent transcripts, provider/model notes, and redundant source catalogs.

### Explicitly Deferred

- Article-body extraction.
- LLM summarization.
- Browser fallbacks.
- Per-host throttling.
- ETag/Last-Modified persistence.
- Persistent read/unread or delivered-item state.
- Automated retries.
- Automated full-article follow-up; use the sibling `web-content-acquisition` skill manually when the user requests details.

Add one only after a measured failure in the weekly digest requires it.

## Target File Tree

```text
travel-news-digest/
├── .gitignore
├── PLAN.md                         # remove after the refactor is accepted
├── SKILL.md                        # 60-90 lines
├── requirements.txt               # feedparser + PyYAML
├── references/
│   └── sources-and-access-notes.md # short operator notes only
├── scripts/
│   ├── fetch_travel_news.py        # target: <=300 lines
│   └── sources.yaml                # 29 feed-backed sources
└── tests/
    └── test_fetch_travel_news.py   # offline tests only, target: <=220 lines
```

## Stable CLI Contract

```bash
python scripts/fetch_travel_news.py digest --days 7 --output markdown
python scripts/fetch_travel_news.py digest --days 7 --output json
python scripts/fetch_travel_news.py health --region all --priority all
```

- Exit `0`: digest produced; individual source failures are reported in output.
- Exit `2`: invalid arguments or invalid local config.
- Exit `1`: no source returned any item or an unexpected local failure occurred.
- JSON output keys: `items`, `errors`, `source_count`, `generated_at`.
- Each item keys: `title`, `link`, `published_at`, `source`, `region`, `classified_topics`.

---

### Task 1: Replace the Test Suite with the Minimal Offline Contract

**Files:**
- Modify: `hermes/skills/research/travel-news-digest/tests/test_fetch_travel_news.py`
- Delete: `hermes/skills/research/travel-news-digest/tests/conftest.py`
- Delete: `hermes/skills/research/travel-news-digest/tests/test_sources.yaml`
- Delete: `hermes/skills/research/travel-news-digest/pytest.ini`

- [ ] **Step 1: Replace shared fixtures and 35 characterization tests with local offline data**

Use one test module with these imports and constants:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import fetch_travel_news as news

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
    "business_travel": {"en": ["business travel"], "ru": ["командир"]},
}
```

- [ ] **Step 2: Add the feed-normalization test**

```python
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
```

- [ ] **Step 2a: Add the Google News edition contract**

```python
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
```

- [ ] **Step 3: Add the partial-success test**

```python
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
```

- [ ] **Step 4: Add tests for configuration, filtering, output, and exit codes**

```python
def test_load_config_filters_region_and_priority(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        "keywords: {}\nsources:\n"
        "  - {name: A, fetch: rss, rss: 'https://a.test/feed', region: ru, priority: P1, topics: [aviation]}\n"
        "  - {name: B, fetch: rss, rss: 'https://b.test/feed', region: intl, priority: P2, topics: [hotels]}\n",
        encoding="utf-8",
    )
    sources, keywords = news.load_config(path, region="ru", priority="P1")
    assert [source["name"] for source in sources] == ["A"]
    assert keywords == {}


def test_filter_deduplicates_and_classifies():
    items = [
        {"title": "Airline opens route", "link": "https://e/1", "summary": "", "published_at": "2099-08-15T10:00:00+00:00", "topics": ["aviation"]},
        {"title": "Airline opens route!", "link": "https://e/1", "summary": "", "published_at": "2099-08-15T10:00:00+00:00", "topics": ["aviation"]},
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
    payload = json.loads(news.render_json([], {"Broken": "timeout"}, source_count=2))
    assert set(payload) == {"items", "errors", "source_count", "generated_at"}
    assert payload["errors"] == {"Broken": "timeout"}


def test_main_returns_one_when_every_source_fails(monkeypatch):
    monkeypatch.setattr(news, "load_config", lambda *_args, **_kwargs: (SOURCES, KEYWORDS))
    monkeypatch.setattr(news, "fetch_all_sources", lambda *_args, **_kwargs: ([], {"Test Feed": "timeout"}))
    assert news.main(["digest", "--output", "json"]) == 1
```

- [ ] **Step 5: Run the new tests and confirm they fail against the current implementation**

Run:

```bash
cd /Users/home/Documents/01_repo/Hermes-Backup/hermes/skills/research/travel-news-digest
PYTHONDONTWRITEBYTECODE=1 /Users/home/.venvs/hermes-backup/bin/python -m pytest -q -p no:cacheprovider
```

Expected: failures for missing `fetch_feed`, synchronous `fetch_all_sources`, `load_config`, `render_json`, and `main(argv)`.

- [ ] **Step 6: Commit the contract tests**

```bash
git add hermes/skills/research/travel-news-digest/tests hermes/skills/research/travel-news-digest/pytest.ini
git commit -m "test(travel-news): define minimal digest contract"
```

---

### Task 2: Reduce Sources to Feed-Backed Inputs and Declare Dependencies

**Files:**
- Modify: `hermes/skills/research/travel-news-digest/scripts/sources.yaml`
- Create: `hermes/skills/research/travel-news-digest/requirements.txt`
- Delete: `hermes/skills/research/travel-news-digest/templates/sources.yaml`

- [ ] **Step 1: Remove the four `fetch: curl_cffi` source blocks**

Delete the source blocks named exactly:

```text
Турпром
Travel Weekly
BTN
PhocusWire
```

Keep all 23 `fetch: rss` blocks and all 6 `fetch: google_news` blocks. Expected source total: 29.

- [ ] **Step 2: Remove HTML-only configuration keys**

Verify that `scripts/sources.yaml` contains none of these keys or values:

```text
curl_cffi
selector:
text_min_length:
impersonate:
retry:
```

Run:

```bash
rg -n 'curl_cffi|selector:|text_min_length:|impersonate:|retry:' hermes/skills/research/travel-news-digest/scripts/sources.yaml
```

Expected: no output, exit code `1`.

- [ ] **Step 3: Add the explicit runtime dependency file**

Create `requirements.txt` with exactly:

```text
feedparser==6.0.14
PyYAML==6.0.3
```

- [ ] **Step 4: Validate the source count and supported types**

Run:

```bash
/Users/home/.venvs/hermes-backup/bin/python - <<'PY'
from pathlib import Path
import yaml

data = yaml.safe_load(Path("hermes/skills/research/travel-news-digest/scripts/sources.yaml").read_text())
assert len(data["sources"]) == 29
assert {source["fetch"] for source in data["sources"]} == {"rss", "google_news"}
print("29 feed-backed sources")
PY
```

Expected: `29 feed-backed sources`.

- [ ] **Step 5: Commit the dependency and source reduction**

```bash
git add hermes/skills/research/travel-news-digest/scripts/sources.yaml hermes/skills/research/travel-news-digest/requirements.txt hermes/skills/research/travel-news-digest/templates/sources.yaml
git commit -m "refactor(travel-news): keep feed-backed sources only"
```

---

### Task 3: Replace Three Fetchers with One Feed Fetcher

**Files:**
- Modify: `hermes/skills/research/travel-news-digest/scripts/fetch_travel_news.py`
- Test: `hermes/skills/research/travel-news-digest/tests/test_fetch_travel_news.py`

- [ ] **Step 1: Replace the import block and constants**

Use this dependency surface:

```python
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
```

Remove imports of `asyncio`, `hashlib`, `os`, `sqlite3`, `time`, `Any`, `urljoin`, `BeautifulSoup`, and `curl_cffi`.

- [ ] **Step 2: Normalize RSS and Google News to one URL function**

```python
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
```

This intentionally keeps the sibling skill's seven-line Google News URL behavior local. Importing a script across two standalone skill directories or calling it as a subprocess would create more coupling than this duplication removes.

- [ ] **Step 3: Add the single bounded feed fetcher**

```python
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
        return [], str(exc.reason if isinstance(exc, URLError) else exc)[:120]

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
```

- [ ] **Step 4: Replace asyncio orchestration with a bounded thread pool**

```python
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
```

- [ ] **Step 5: Delete obsolete fetch code**

Delete these functions completely:

```text
fetch_with_retry
parse_rss
parse_html
parse_google_news
```

Delete constants `RETRY_DELAYS`, `CACHE_DIR`, `SEEN_DB`, `RAW_JSON`, `SKILL_DIR`, and `GN_SCRIPT`.

- [ ] **Step 6: Run the fetch contract tests**

Run:

```bash
cd /Users/home/Documents/01_repo/Hermes-Backup/hermes/skills/research/travel-news-digest
PYTHONDONTWRITEBYTECODE=1 /Users/home/.venvs/hermes-backup/bin/python -m pytest -q -p no:cacheprovider tests/test_fetch_travel_news.py -k 'fetch_feed or fetch_all'
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the unified fetcher**

```bash
git add hermes/skills/research/travel-news-digest/scripts/fetch_travel_news.py hermes/skills/research/travel-news-digest/tests/test_fetch_travel_news.py
git commit -m "refactor(travel-news): unify feed collection"
```

---

### Task 4: Collapse State, Filtering, Rendering, and CLI

**Files:**
- Modify: `hermes/skills/research/travel-news-digest/scripts/fetch_travel_news.py`
- Test: `hermes/skills/research/travel-news-digest/tests/test_fetch_travel_news.py`

- [ ] **Step 1: Delete persistent state**

Delete these functions and every call to them:

```text
init_seen_db
url_hash
is_seen
mark_seen
clear_seen_db
```

Per-run deduplication in `filter_and_classify` remains the only deduplication mechanism.

- [ ] **Step 2: Make time deterministic and use normalized dates**

Use this signature and cutoff logic:

```python
def filter_and_classify(
    items: list[dict],
    keywords: dict,
    days: int,
    *,
    now: datetime | None = None,
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=days)
```

For each item:

```python
published_at = item.get("published_at")
if published_at and datetime.fromisoformat(published_at) < cutoff:
    continue

key = item.get("link") or re.sub(r"[^\w\s]", "", item["title"].casefold()).strip()
if key in seen:
    continue
seen.add(key)

matches = classify_item(item["title"], item.get("summary", ""), keywords)
configured = [topic for topic in item.get("topics", []) if topic != "general"]
if not matches and "general" in item.get("topics", []):
    continue
item["classified_topics"] = [matches[0] if matches else configured[0] if configured else "general"]
result.append(item)
```

Sort with:

```python
result.sort(key=lambda item: item.get("published_at", ""), reverse=True)
```

- [ ] **Step 3: Replace duplicate YAML reads with one validated loader**

```python
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
            raise ValueError(f"source {index} missing: {', '.join(sorted(missing))}")
        if source["fetch"] not in {"rss", "google_news"}:
            raise ValueError(f"unsupported fetch type: {source['fetch']}")
    if region != "all":
        sources = [source for source in sources if source["region"] == region]
    if priority != "all":
        sources = [source for source in sources if source["priority"] == priority]
    return sources, keywords
```

- [ ] **Step 4: Add a stable JSON renderer**

```python
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
```

Keep `format_markdown`, but remove rendered descriptions. Each item line becomes exactly:

```python
lines.append(f"- **{item['title']}** [→]({item['link']}) ({item['source']}{date_suffix})")
```

- [ ] **Step 5: Replace six commands with two**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Travel News Digest CLI")
    parser.add_argument("command", nargs="?", choices=["digest", "health"], default="digest")
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
```

- [ ] **Step 6: Run the full offline suite and Ruff**

```bash
cd /Users/home/Documents/01_repo/Hermes-Backup/hermes/skills/research/travel-news-digest
PYTHONDONTWRITEBYTECODE=1 /Users/home/.venvs/hermes-backup/bin/python -m pytest -q -p no:cacheprovider
RUFF_CACHE_DIR=/tmp/travel-news-digest-ruff /Users/home/.venvs/hermes-backup/bin/python -m ruff check scripts tests
```

Expected: all tests pass; Ruff prints `All checks passed!`.

- [ ] **Step 7: Commit the single-pass CLI**

```bash
git add hermes/skills/research/travel-news-digest/scripts/fetch_travel_news.py hermes/skills/research/travel-news-digest/tests/test_fetch_travel_news.py
git commit -m "refactor(travel-news): collapse digest pipeline"
```

---

### Task 5: Delete Documentation Debris and Rewrite the Skill Contract

**Files:**
- Modify: `hermes/skills/research/travel-news-digest/SKILL.md`
- Modify: `hermes/skills/research/travel-news-digest/references/sources-and-access-notes.md`
- Delete: `hermes/skills/research/travel-news-digest/references/cli-automation-plan.md`
- Delete: `hermes/skills/research/travel-news-digest/references/curl-cffi-cloudflare-bypass.md`
- Delete: `hermes/skills/research/travel-news-digest/references/expanded-source-catalog.md`
- Delete: `hermes/skills/research/travel-news-digest/references/source-catalog-87.md`
- Delete: `hermes/skills/research/travel-news-digest/references/source-catalog-extended.md`
- Delete: `hermes/skills/research/travel-news-digest/references/subagent-model-config.md`
- Delete: `hermes/skills/research/travel-news-digest/references/subagent-review-results.md`

- [ ] **Step 1: Replace `SKILL.md` with the runtime contract**

Use this structure and no additional sections:

```markdown
---
name: travel-news-digest
description: Build a weekly aviation, hotel, and business-travel news digest from configured RSS and Google News feeds.
---

# Travel News Digest

Use the CLI first. It fetches, filters, deduplicates, and renders the digest without an LLM.

## Run

\`\`\`bash
python scripts/fetch_travel_news.py digest --days 7 --output markdown
\`\`\`

Optional filters: `--region ru|intl|all`, `--priority P1|P2|P3|all`.
Use `health` only to diagnose sources:

\`\`\`bash
python scripts/fetch_travel_news.py health
\`\`\`

## Output Contract

- Preserve source title, link, publication date, and source name.
- Group by aviation, hotels, and business travel; then Russia and international.
- Show successful items even when some sources fail.
- List failed sources at the end.
- Do not claim an article was read when only its feed entry was fetched.

## Configuration

Edit `scripts/sources.yaml`. Supported fetch types are `rss` and `google_news`.
Runtime dependencies are pinned in `requirements.txt`.

## Follow-up

If the user asks for details beyond a feed entry, use `../web-content-acquisition/SKILL.md` to resolve the direct publisher URL and extract that article. Keep article extraction, search services, browser automation, and research artifacts out of this CLI.

## Maintenance

\`\`\`bash
python -m pytest -q -p no:cacheprovider
RUFF_CACHE_DIR=/tmp/travel-news-digest-ruff python -m ruff check scripts tests
\`\`\`

Keep feed access notes in `references/sources-and-access-notes.md`.
```

- [ ] **Step 2: Reduce access notes to current operational facts**

Keep only:

```markdown
# Source Access Notes

- Runtime catalog: `scripts/sources.yaml`.
- Direct RSS/Atom is preferred.
- Google News RSS covers publishers without a stable public feed.
- Preserve each query's `hl`, `gl`, and `ceid` edition settings.
- A failed source is reported and does not fail the whole digest.
- For requested article details, hand the selected link to `../web-content-acquisition/SKILL.md`; do not add extraction to this CLI.
- Reintroduce HTML fetching only after a named required publisher cannot be covered by RSS or Google News.
```

- [ ] **Step 3: Delete the seven archival reference files**

After deletion, `references/` must contain only `sources-and-access-notes.md`.

- [ ] **Step 4: Verify documentation contains no deleted concepts**

Run:

```bash
rg -n 'curl_cffi|BeautifulSoup|lxml|jinja2|httpx|SQLite|seen\.db|delegate_task|Ollama|browser_' hermes/skills/research/travel-news-digest
```

Expected: no output except this `PLAN.md` while the plan remains in the branch.

- [ ] **Step 5: Commit the documentation reduction**

```bash
git add hermes/skills/research/travel-news-digest/SKILL.md hermes/skills/research/travel-news-digest/references
git commit -m "docs(travel-news): reduce skill to runtime contract"
```

---

### Task 6: Verify the Product and Measure the Deletion

**Files:**
- Modify only if verification exposes a defect: files already listed in Tasks 1-5.

- [ ] **Step 1: Run offline verification**

```bash
cd /Users/home/Documents/01_repo/Hermes-Backup/hermes/skills/research/travel-news-digest
PYTHONDONTWRITEBYTECODE=1 /Users/home/.venvs/hermes-backup/bin/python -m pytest -q -p no:cacheprovider
RUFF_CACHE_DIR=/tmp/travel-news-digest-ruff /Users/home/.venvs/hermes-backup/bin/python -m ruff check scripts tests
```

Expected: exit `0` from both commands.

- [ ] **Step 2: Run one live JSON smoke test**

```bash
cd /Users/home/Documents/01_repo/Hermes-Backup/hermes/skills/research/travel-news-digest
python scripts/fetch_travel_news.py digest --days 7 --output json > /tmp/travel-news-digest.json
/Users/home/.venvs/hermes-backup/bin/python - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/travel-news-digest.json").read_text())
assert set(data) == {"items", "errors", "source_count", "generated_at"}
assert data["source_count"] == 29
assert data["items"], data["errors"]
print(len(data["items"]), "items", len(data["errors"]), "source errors")
PY
```

Expected: at least one item; source failures are allowed and counted.

- [ ] **Step 3: Prove the dependency boundary**

```bash
rg -n '^(import|from) ' hermes/skills/research/travel-news-digest/scripts/fetch_travel_news.py
```

Expected third-party imports only:

```text
import feedparser
import yaml
```

Do not uninstall `curl_cffi` from the shared Hermes venv; `flight-calendar-ics` and `flight-status` still import it. Environment cleanup for `beautifulsoup4`, `lxml`, and `jinja2` requires a separate shared-venv dependency audit.

- [ ] **Step 4: Prove the size reduction**

```bash
find hermes/skills/research/travel-news-digest -type f | sort
wc -l \
  hermes/skills/research/travel-news-digest/SKILL.md \
  hermes/skills/research/travel-news-digest/scripts/fetch_travel_news.py \
  hermes/skills/research/travel-news-digest/tests/test_fetch_travel_news.py \
  hermes/skills/research/travel-news-digest/references/sources-and-access-notes.md
```

Acceptance limits:

```text
SKILL.md <= 90 lines
fetch_travel_news.py <= 300 lines
test_fetch_travel_news.py <= 220 lines
sources-and-access-notes.md <= 40 lines
tracked files <= 8 while PLAN.md exists
```

- [ ] **Step 5: Check the final diff and branch state**

```bash
git diff --check
git status -sb
git diff --stat origin/feat/travel-news-digest-cli...HEAD
```

Expected: no whitespace errors; only intentional digest files changed or deleted.

- [ ] **Step 6: Commit verification-only fixes if any were required**

If Step 1 or Step 2 required a correction, stage only the corrected digest files and commit:

```bash
git commit -m "fix(travel-news): pass refactor verification"
```

If no correction was required, do not create an empty commit.

## Self-Review

- Spec coverage: dependency reduction, source strategy, fetching, filtering, error isolation, output, tests, docs, and deletion metrics each have an implementation task.
- Placeholder scan: no TBD, TODO, unnamed implementation step, or deferred implementation hidden inside an active task.
- Type consistency: `fetch_feed`, `fetch_all_sources`, `load_config`, `filter_and_classify`, `render_json`, and `main(argv)` signatures match across tests and implementation steps.
- Ponytail check: no new runtime abstraction, service, database, cache, parser, HTTP client, browser path, or compatibility layer.
- Web acquisition check: reuse Google News edition semantics and the manual direct-article follow-up contract, but add no cross-skill import, subprocess, search service, extractor, or artifact directory to the digest runtime.
