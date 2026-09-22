#!/usr/bin/env python3
"""Run the skill CLI with recorded carrier HTTP instead of live network."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("expected target Python script")

    target = Path(sys.argv[1]).resolve()
    fixture = Path(os.environ["FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE"])
    fixture_text = fixture.read_text(encoding="utf-8")

    sys.path.insert(0, str(target.parent))
    from flight_calendar import carrier_http

    def request_raw(
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 45,
        label: str = "HTTP request",
        sleep: object = None,
    ) -> tuple[int, str, str]:
        del url, method, headers, body, timeout, label, sleep
        return 200, "application/json; charset=utf-8", fixture_text

    carrier_http.request_raw = request_raw
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
