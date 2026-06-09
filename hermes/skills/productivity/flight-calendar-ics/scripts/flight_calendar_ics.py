#!/usr/bin/env python3
"""Public executable wrapper for the flight-calendar-ics CLI.

Keep this file small: command parsing and behavior live in
``flight_calendar.parser`` so the script-level entrypoint stays stable while the
implementation is testable as a package.
"""
from __future__ import annotations

from typing import Any

from flight_calendar import parser as _parser
from flight_calendar.parser import *  # noqa: F401,F403 - legacy import surface

PUBLIC_ENTRYPOINT = _parser.PUBLIC_ENTRYPOINT

_CARRIER_HANDLER_NAMES = ("command_aeroflot", "command_ural", "command_utair", "command_redwings")
_CANONICAL_CARRIER_HANDLERS = {name: getattr(_parser, name) for name in _CARRIER_HANDLER_NAMES}


def command_build(args: Any, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    """Compatibility shim for legacy tests that monkeypatch wrapper handlers."""
    for name in _CARRIER_HANDLER_NAMES:
        setattr(_parser, name, globals()[name])
    try:
        return _parser.command_build(args, process)
    finally:
        for name, handler in _CANONICAL_CARRIER_HANDLERS.items():
            setattr(_parser, name, handler)


main = _parser.main
build_parser = _parser.build_parser
run_command = _parser.run_command
infer_command = _parser.infer_command


if __name__ == "__main__":
    raise SystemExit(main())
