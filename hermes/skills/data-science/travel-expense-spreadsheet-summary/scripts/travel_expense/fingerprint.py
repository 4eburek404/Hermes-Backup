from __future__ import annotations

import hashlib
from typing import Any

from .text import norm, text_value


def row_fingerprint(date: Any, carrier: Any, details: Any, amount: Any) -> str:
    payload = "|".join([text_value(date), norm(carrier), norm(details), text_value(amount)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
