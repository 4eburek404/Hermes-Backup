# FTS5 OR fallback and Cyrillic entity extraction fixes

Date: 2026-05-05
Files modified: `plugins/memory/holographic/retrieval.py`, `plugins/memory/holographic/store.py`

## Problem 1: FTS5 AND default breaks multi-word search

**Root cause:** FTS5 `MATCH` uses AND by default. A query like `"сервер VPS n8n backup"` requires a single row to contain ALL four words. When no fact has all four, `_fts_candidates()` returns an empty list, and Jaccard reranking has nothing to rerank.

**Observed:** 8 different Russian-language search queries all returned 0 results despite relevant facts existing in the DB. ~60 of 86 facts were effectively invisible to `fact_store search`.

**Fix in `retrieval.py`, `_fts_candidates()`:**
1. Try standard AND query first.
2. If 0 results and query has multiple tokens, retry with OR: split query into tokens, join with `OR`, try `MATCH` again.
3. Return whichever set is non-empty.

**Before (0 results):** `"overengineering simplicity"`, `"сервер VPS n8n backup"`, `"Ural Airlines Kupibilet"`, `"preference communication формат"`, `"memory MEMORY architecture rules"`, `"cron model language email"`

**After (2–3 results each):** All above queries return relevant facts with Jaccard reranking working correctly.

**Re-verification after Hermes updates:** If `fact_store search` with multi-word queries starts returning 0 again, check `_fts_candidates` for the OR retry block. The fix is in the Hermes codebase under `~/.hermes/hermes-agent/` and may be overwritten by `git pull`.

## Problem 2: Entity extraction misses Cyrillic and single Title-case

**Root cause:** Original `_extract_entities()` used one regex `_RE_CAPITALIZED = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'` which only matched multi-word Latin Title-case phrases (2+ words). Single words like "Konstantin", all Cyrillic like "Константин", and backtick-quoted terms were never extracted as entities.

**Impact:** `probe('Konstantin')` found only facts where "Konstantin" appeared in a multi-word phrase. Most preference facts (#42, #43, #77, #105, #107) were not linked to the entity. `reason()` cross-entity queries missed these facts entirely.

**Fix in `store.py`:**

Added regex patterns:
- `_RE_CAPITALIZED_1 = r'\b([A-Z][a-z]{2,})\b'` — single Title-case English words (≥3 chars)
- `_RE_CYRILLIC_TITLE = r'\b([А-ЯЁ][а-яё]{2,})\b'` — single Cyrillic Title-case (≥3 chars)
- `_RE_CYRILLIC_MULTI = r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)+)\b'` — multi-word Cyrillic Title-case
- `_RE_BACKTICK = r'`([^`]+)`'` — backtick-quoted terms (code names, CLI tools)

Added stop list `_STOP_ENTITIES` filtering generic words:
- English: the, for, and, not, with, via, may, ...
- Russian: Когда, Перед, После, Если, Для, Это, Сервер, Сайт, Файл, Папка, Почта, ...

Updated `_extract_entities()` to apply all patterns in priority order (multi-word → single → quoted → AKA) with dedup and stop-list filtering.

**Reindexing required:** After patching, existing facts keep their old entity links. Run `MemoryStore.rebuild_all_vectors()` to re-extract entities and recompute HRR vectors. This was done for the 86 existing facts on 2026-05-05.

**Verification:**
```python
from plugins.memory.holographic.store import MemoryStore
store = MemoryStore.__new__(MemoryStore)
# Should now extract: ['Konstantin']
print(MemoryStore._extract_entities(store, 'Konstantin prefers flight search'))
# Should now extract: ['Константин']
print(MemoryStore._extract_entities(store, 'Константин не терпит overengineering'))
# Should now extract: ['Ollama Cloud', 'Ollama', 'Cloud']
print(MemoryStore._extract_entities(store, 'Для structured output через Ollama Cloud'))
```

## Residual known issues

- `_RE_CYRILLIC_TITLE` catches random capitalized common nouns (e.g., "Предпочитает", "Показатель"). `_STOP_ENTITIES` mitigates the worst cases but cannot cover all Russian nouns. This is acceptable noise — entity links get added but trust scoring and Jaccard reranking keep the signal high.
- `_RE_CAPITALIZED_1` may extract "For", "After", "All" etc. from English text. The stop list covers the most common, but some will slip through.
- Entity extraction is regex-based, not NER — it produces candidates for HRR binding, not authoritative entity resolution. Imperfect extraction is better than zero extraction.