#!/usr/bin/env python3
"""Print built-in USER.md/MEMORY.md size pressure."""
from __future__ import annotations

from pathlib import Path

for name in ["USER.md", "MEMORY.md"]:
    p = Path.home() / ".hermes/memories" / name
    text = p.read_text() if p.exists() else ""
    print(name, "exists=", p.exists(), "chars=", len(text), "bytes=", p.stat().st_size if p.exists() else 0, "lines=", text.count("\n") + bool(text))
