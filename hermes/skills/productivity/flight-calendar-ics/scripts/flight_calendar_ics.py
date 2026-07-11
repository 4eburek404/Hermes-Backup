#!/usr/bin/env python3
"""Public executable wrapper for the flight-calendar-ics CLI.

Command parsing and behavior live in ``flight_calendar.parser``; this wrapper
exposes the public CLI hooks and forwards execution.
"""

from __future__ import annotations

from flight_calendar import parser as _parser

build_parser = _parser.build_parser
main = _parser.main

__all__ = ["build_parser", "main"]
if __name__ == "__main__":
    raise SystemExit(main())
