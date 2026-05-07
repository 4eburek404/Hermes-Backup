#!/usr/bin/env python3
"""Read-only SQLite metrics for Hermes holographic memory."""
from __future__ import annotations

import json
import sqlite3
import statistics
from pathlib import Path

path = Path.home() / ".hermes/memory_store.db"
print("db_exists", path.exists())
print("db_size_bytes", path.stat().st_size if path.exists() else 0)
if not path.exists():
    raise SystemExit(0)

con = sqlite3.connect(path)
con.row_factory = sqlite3.Row
cur = con.cursor()
print("tables", [r[0] for r in cur.execute("select name from sqlite_master where type='table' order by name")])
print("indexes", [r[0] for r in cur.execute("select name from sqlite_master where type='index' order by name")])

for table in ["facts", "facts_fts", "entities", "fact_entities", "memory_banks"]:
    try:
        print(table, cur.execute(f"select count(*) from {table}").fetchone()[0])
    except Exception as e:  # noqa: BLE001 - diagnostic script
        print(table, "missing_or_error", str(e))

sql = (
    "select fact_id, category, tags, trust_score, retrieval_count, "
    "helpful_count, created_at, updated_at, length(content) as len "
    "from facts"
)
rows = [dict(r) for r in cur.execute(sql)]
if rows:
    def stat(xs):
        return {"min": min(xs), "max": max(xs), "avg": sum(xs)/len(xs), "median": statistics.median(xs)}
    cats = {}
    by_day = {}
    tagged = 0
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
        by_day[(r["created_at"] or "")[:10]] = by_day.get((r["created_at"] or "")[:10], 0) + 1
        tagged += bool(r["tags"])
    print(json.dumps({
        "facts": len(rows),
        "categories": cats,
        "created_by_day": by_day,
        "tagged": tagged,
        "trust": stat([r["trust_score"] for r in rows]),
        "helpful": stat([r["helpful_count"] for r in rows]),
        "retrieval": stat([r["retrieval_count"] for r in rows]),
        "content_len": stat([r["len"] for r in rows]),
        "top_helpful": sorted(
            [(r["fact_id"], r["helpful_count"], r["trust_score"], r["category"]) for r in rows],
            key=lambda x: (-x[1], -x[2])
        )[:10],
        "low_trust": sorted(
            [(r["fact_id"], r["trust_score"], r["category"], r["len"]) for r in rows],
            key=lambda x: x[1]
        )[:10],
    }, ensure_ascii=False, indent=2))
con.close()
