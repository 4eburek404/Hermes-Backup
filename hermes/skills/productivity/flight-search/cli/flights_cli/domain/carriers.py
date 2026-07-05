from __future__ import annotations

import re

from ..config import CARRIER_RE


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
