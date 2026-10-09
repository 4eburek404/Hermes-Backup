"""Force standalone executable specs onto an isolated offline runtime."""

from __future__ import annotations

import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

_RUNTIME_DIR = tempfile.TemporaryDirectory(prefix="flight-calendar-standalone.")
_CACHE_DIR = Path(_RUNTIME_DIR.name)
_BUNDLED_CATALOG = Path(__file__).resolve().parents[1] / "data" / "airport-timezones.json"
(_CACHE_DIR / "airport-timezones.json").write_bytes(_BUNDLED_CATALOG.read_bytes())
(_CACHE_DIR / "refresh-state.json").write_text(
    json.dumps({"last_success": datetime.now(timezone.utc).isoformat()}),
    encoding="utf-8",
)
os.environ["FLIGHT_CALENDAR_CACHE_DIR"] = str(_CACHE_DIR)


def _blocked(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise SystemExit("live network is forbidden in standalone executable specs")


request.urlopen = _blocked  # type: ignore[assignment]
socket.socket.connect = _blocked  # type: ignore[method-assign]
