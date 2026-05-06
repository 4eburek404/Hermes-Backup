#!/usr/bin/env python3
"""Verify FTS5 OR fallback and Cyrillic entity extraction are working correctly.

Exit codes: 0 = all checks pass, 1 = one or more checks failed.

Checks:
1. FTS5 AND-then-OR: multi-word queries return results (not 0)
2. FTS5 Cyrillic: Russian-language queries return results
3. Entity extraction: Cyrillic Title-case and single-word entities are extracted
4. Entity links: common entities (e.g. "Konstantin") are linked to multiple facts
5. Entity link coverage: at least 50% of facts have entity links
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".hermes/memory_store.db"
RETRIEVAL_PATH = Path.home() / ".hermes/hermes-agent/plugins/memory/holographic/retrieval.py"
STORE_PATH = Path.home() / ".hermes/hermes-agent/plugins/memory/holographic/store.py"

passed = 0
failed = 0

def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}" + (f" ({detail})" if detail else ""))
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    global passed, failed

    # ---- 0. Prerequisites ----
    print("=== Prerequisites ===")
    if not DB_PATH.exists():
        print("  FATAL  DB not found:", DB_PATH)
        sys.exit(1)
    check("DB exists", True, str(DB_PATH))

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ---- 1. FTS5 OR fallback in code ----
    print("\n=== FTS5 OR fallback (code check) ===")
    if RETRIEVAL_PATH.exists():
        code = RETRIEVAL_PATH.read_text()
        has_or_retry = "OR" in code and "fts_candidates" in code and "retry" in code.lower()
        check("_fts_candidates has OR retry logic", has_or_retry,
               "found OR+retry keywords" if has_or_retry else "missing OR retry in _fts_candidates")
    else:
        check("retrieval.py exists", False, str(RETRIEVAL_PATH))

    # ---- 2. FTS5 live query test ----
    print("\n=== FTS5 live query tests ===")

    # AND query (should work for single-word or tightly matched)
    r = conn.execute("SELECT count(*) FROM facts_fts WHERE facts_fts MATCH ?", ("Konstantin",)).fetchone()[0]
    check("FTS5 single-word 'Konstantin' found", r > 0, f"{r} hits")

    # Multi-word AND vs OR — verify OR >= AND (OR should never be less)
    r_and = conn.execute("SELECT count(*) FROM facts_fts WHERE facts_fts MATCH ?", ("сервер VPS n8n",)).fetchone()[0]
    r_or = conn.execute("SELECT count(*) FROM facts_fts WHERE facts_fts MATCH ?", ("сервер OR VPS OR n8n",)).fetchone()[0]
    check("FTS5 OR >= AND for multi-word RU", r_or >= r_and and r_or > 0,
          f"AND={r_and}, OR={r_or}")

    # Cyrillic single word — use a form that actually appears in the DB
    r_cyr = conn.execute("SELECT count(*) FROM facts_fts WHERE facts_fts MATCH ?", ("провайдер",)).fetchone()[0]
    check("FTS5 Cyrillic token indexed", r_cyr > 0, f"'провайдер' → {r_cyr} hits")

    # ---- 3. Entity extraction in code ----
    print("\n=== Entity extraction (code check) ===")
    if STORE_PATH.exists():
        code = STORE_PATH.read_text()
        has_cyrillic_re = "_RE_CYRILLIC_TITLE" in code
        has_single_title = "_RE_CAPITALIZED_1" in code
        has_backtick = "_RE_BACKTICK" in code
        has_stoplist = "_STOP_ENTITIES" in code
        check("Cyrillic Title-case regex", has_cyrillic_re)
        check("Single Title-case regex", has_single_title)
        check("Backtick-quoted regex", has_backtick)
        check("Stop-list defined", has_stoplist)
    else:
        check("store.py exists", False, str(STORE_PATH))

    # ---- 4. Entity extraction live test ----
    print("\n=== Entity extraction (live test) ===")

    # We can't import the class directly from a running Hermes, so test via patterns
    # Load the actual patterns from store.py
    try:
        sys.path.insert(0, str(Path.home() / ".hermes/hermes-agent"))
        from plugins.memory.holographic.store import MemoryStore, _RE_CYRILLIC_TITLE, _RE_CYRILLIC_MULTI, _RE_CAPITALIZED_1, _STOP_ENTITIES

        test_cases = [
            ("Konstantin prefers flights", ["Konstantin"]),
            ("Константин не терпит overengineering", ["Константин"]),
            ("Ollama Cloud: НЕ использовать", ["Ollama", "Cloud"]),
            ("Для structured output через Ollama Cloud", None),  # just check it doesn't crash
        ]

        store_dummy = MemoryStore.__new__(MemoryStore)
        for text, expected_contains in test_cases:
            entities = MemoryStore._extract_entities(store_dummy, text)
            if expected_contains:
                found = all(e in entities for e in expected_contains)
                check(f"Extract from: '{text[:40]}...'", found,
                      f"got {entities}, expected {expected_contains}")
            else:
                check(f"Extract from: '{text[:40]}...'", len(entities) > 0,
                      f"got {entities}")
    except Exception as e:
        check("Entity extraction import/test", False, str(e))

    # ---- 5. Entity link coverage ----
    print("\n=== Entity link coverage ===")
    total_facts = conn.execute("SELECT count(*) FROM facts").fetchone()[0]
    facts_with_links = conn.execute(
        "SELECT count(DISTINCT fact_id) FROM fact_entities"
    ).fetchone()[0]
    coverage = facts_with_links / total_facts if total_facts else 0
    check("Entity link coverage >= 50%", coverage >= 0.5,
          f"{facts_with_links}/{total_facts} = {coverage:.0%}")

    # Check "Konstantin" entity specifically
    konstantin_eid = conn.execute(
        "SELECT entity_id FROM entities WHERE lower(name) = 'konstantin'"
    ).fetchone()
    if konstantin_eid:
        linked_facts = conn.execute(
            "SELECT count(*) FROM fact_entities WHERE entity_id = ?",
            (konstantin_eid["entity_id"],)
        ).fetchone()[0]
        # Also check Cyrillic variant
        konstantin_ru_eid = conn.execute(
            "SELECT entity_id FROM entities WHERE name = 'Константин'"
        ).fetchone()
        ru_linked = 0
        if konstantin_ru_eid:
            ru_linked = conn.execute(
                "SELECT count(*) FROM fact_entities WHERE entity_id = ?",
                (konstantin_ru_eid["entity_id"],)
            ).fetchone()[0]
        check("'Konstantin' entity links >= 3", linked_facts >= 3,
              f"EN={linked_facts}" + (f", RU={ru_linked}" if konstantin_ru_eid else ", RU=0"))
    else:
        check("'Konstantin' entity exists", False)

    # ---- Summary ----
    conn.close()
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed > 0:
        print("STATUS: DEGRADED — some checks failed")
        sys.exit(1)
    else:
        print("STATUS: HEALTHY")
        sys.exit(0)


if __name__ == "__main__":
    main()