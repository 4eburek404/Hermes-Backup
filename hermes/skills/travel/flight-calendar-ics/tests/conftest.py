from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture(autouse=True, scope="session")
def isolate_runtime_timezone_refresh():
    """Keep the ordinary offline suite away from the live upstream endpoint."""
    patch = pytest.MonkeyPatch()
    with TemporaryDirectory(prefix="flight-calendar-test-cache.") as tmp:
        cache_dir = Path(tmp)
        (cache_dir / "refresh-state.json").write_text(
            json.dumps({"last_attempt": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )
        patch.setenv("FLIGHT_CALENDAR_CACHE_DIR", str(cache_dir))
        yield
    patch.undo()
