from __future__ import annotations

# Compatibility shim: diagnostic summary lines moved under reporting.projections.
from .projections.summary_lines import build_answer_lines, build_summary_lines

__all__ = ["build_answer_lines", "build_summary_lines"]