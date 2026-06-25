#!/usr/bin/env python3
"""Canonical public entrypoint for the Hermes skill audit helper.

The implementation is stored as data so this file stays small and owns the
single supported skill section contract. Do not add alternate section profiles
here; migrate skills to the canonical compact structure instead.
"""
from __future__ import annotations

import types
from pathlib import Path
from typing import List, Optional

CANONICAL_REQUIRED_SECTIONS = [
    "## Goal",
    "## Steps",
    "## Input",
    "## Output",
    "## Check",
    "## Stop",
    "## References",
]
TOOL_VERSION = "0.2.1"
_IMPL_SOURCE = Path(__file__).with_name("_audit_skill_impl.pydata")
_LEGACY_REQUIRED_SECTIONS_BLOCK = '''REQUIRED_SECTIONS = [
    "## Overview",
    "## When to Use",
    "## Common Pitfalls",
    "## Verification Checklist",
]
'''
_CANONICAL_REQUIRED_SECTIONS_BLOCK = '''REQUIRED_SECTIONS = [
    "## Goal",
    "## Steps",
    "## Input",
    "## Output",
    "## Check",
    "## Stop",
    "## References",
]
'''


def _load_impl() -> types.ModuleType:
    source = _IMPL_SOURCE.read_text(encoding="utf-8")
    if _LEGACY_REQUIRED_SECTIONS_BLOCK not in source:
        raise RuntimeError("audit_skill implementation contract changed; canonical section patch was not applied")
    source = source.replace(_LEGACY_REQUIRED_SECTIONS_BLOCK, _CANONICAL_REQUIRED_SECTIONS_BLOCK, 1)
    module = types.ModuleType("_audit_skill_impl")
    module.__file__ = str(_IMPL_SOURCE)
    module.__package__ = ""
    exec(compile(source, str(_IMPL_SOURCE), "exec"), module.__dict__)
    module.REQUIRED_SECTIONS = list(CANONICAL_REQUIRED_SECTIONS)
    module.TOOL_VERSION = TOOL_VERSION
    return module


_core = _load_impl()

for _name, _value in _core.__dict__.items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value

REQUIRED_SECTIONS = list(CANONICAL_REQUIRED_SECTIONS)
TOOL_VERSION = TOOL_VERSION


def main(argv: Optional[List[str]] = None) -> int:
    _core.REQUIRED_SECTIONS = list(CANONICAL_REQUIRED_SECTIONS)
    _core.TOOL_VERSION = TOOL_VERSION
    return _core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
