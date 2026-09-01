from __future__ import annotations

import re
from typing import Any

from ..config import CARRIER_RE


def canonical_flight_number(value: Any) -> str | None:
    """Одно написание номера рейса: SU1400, а не SU-1400.

    Провайдеры расходятся — Tutu ставит дефис, Kupibilet нет, — и один и тот же
    рейс приезжал в ответ в двух видах. Канон совпадает с формой, которую ждёт
    схема .v1: две буквенно-цифровые позиции перевозчика и номер.
    """

    compact = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return compact or None


def carrier_from_flight_number(flight_number: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", str(flight_number or "").upper())
    if (
        len(compact) >= 3
        and compact[:2].isalnum()
        and compact[2].isdigit()
        and any(ch.isalpha() for ch in compact[:2])
    ):
        return compact[:2]
    prefix = "".join(ch for ch in compact if ch.isalpha())
    return prefix if CARRIER_RE.match(prefix) else None
