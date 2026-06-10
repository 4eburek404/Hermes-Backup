#!/usr/bin/env python3
"""Public executable wrapper for the flight-calendar-ics CLI."""
from __future__ import annotations

from flight_calendar import parser

main = parser.main
build_parser = parser.build_parser
run_command = parser.run_command
infer_command = parser.infer_command
PUBLIC_ENTRYPOINT = parser.PUBLIC_ENTRYPOINT


if __name__ == "__main__":
    raise SystemExit(main())
