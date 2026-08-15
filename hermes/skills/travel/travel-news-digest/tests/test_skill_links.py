from __future__ import annotations

import re
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_cross_skill_markdown_references_resolve() -> None:
    documents = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "sources-and-access-notes.md",
    ]

    for document in documents:
        text = document.read_text(encoding="utf-8")
        references = re.findall(r"`([^`]+/SKILL\.md)`", text)
        assert references, f"no SKILL.md references found in {document}"
        for reference in references:
            target = (document.parent / reference).resolve()
            assert target.is_file(), f"broken reference in {document}: {reference}"
