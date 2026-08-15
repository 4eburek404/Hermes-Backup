---
name: travel-news-digest
description: Build a weekly aviation, hotel, and business-travel news digest from configured RSS and Google News feeds.
metadata:
  hermes:
    category: travel
    tags: [travel, news, aviation, hotels, business-travel]
---

# Travel News Digest

Use the CLI first. It fetches, filters, deduplicates, and renders the digest without an LLM.

Treat the directory containing this `SKILL.md` as `<skill-root>` and resolve
every bundled path relative to it.
Use `"${HERMES_SKILLS_PYTHON:-python3}"` as the Python interpreter for bundled
commands. When `HERMES_SKILLS_PYTHON` is set, use that exact executable;
otherwise use `python3`.

## Run

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/fetch_travel_news.py" digest --days 7 --output markdown
```

Optional filters: `--region ru|intl|all`, `--priority P1|P2|P3|all`.
Use `health` only to diagnose sources:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/fetch_travel_news.py" health
```

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

If the user asks for details beyond a feed entry, use `../../research/web-content-acquisition/SKILL.md` to resolve the direct publisher URL and extract that article. Keep article extraction, search services, browser automation, and research artifacts out of this CLI.

## Maintenance

```bash
"${HERMES_SKILLS_PYTHON:-python3}" -m pytest -q -p no:cacheprovider
RUFF_CACHE_DIR=/tmp/travel-news-digest-ruff "${HERMES_SKILLS_PYTHON:-python3}" -m ruff check scripts tests
```

Keep feed access notes in `references/sources-and-access-notes.md`.
