#!/usr/bin/env python3
"""Public executable wrapper for the flight-calendar-ics CLI.

Command parsing and behavior live in ``flight_calendar.parser``; this wrapper
only re-exports that surface and forwards execution.
"""
from __future__ import annotations

from flight_calendar.parser import *  # noqa: F401,F403 - public re-export surface
from flight_calendar.parser import main

if __name__ == "__main__":
    raise SystemExit(main())
