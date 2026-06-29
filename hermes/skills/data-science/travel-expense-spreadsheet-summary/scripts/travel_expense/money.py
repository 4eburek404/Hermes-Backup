from __future__ import annotations

import math
import re
from typing import Any

from .text import FORMULA_ERROR_VALUES, text_value


def parse_amount(value: Any) -> float | None:
    """Parse Excel/Russian-style money. Return None for non-numeric cells."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return round(float(value), 2)
    original = text_value(value)
    if not original or original.upper() in FORMULA_ERROR_VALUES:
        return None
    s = original.replace("\u00a0", " ").replace("₽", "")
    s = re.sub(r"(?i)руб\.?,?", "", s)
    s = re.sub(r"[^0-9,\.\- ]", "", s).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def format_money(amount: float) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " ₽"
