#!/usr/bin/env python3
"""Compact public CLI for flight-calendar-ics."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from flight_calendar import ics_render, itinerary_contract, timezone_catalog
from flight_calendar.carriers import aeroflot, redwings, s7, ural, utair
from flight_calendar.common import parse_tz_overrides, secure_write_text
from flight_calendar.errors import CliFailure
from flight_calendar.redirect_resolution import resolve_known_booking_redirect
from flight_calendar.route_detection import first_url_from_args, infer_build_route


PUBLIC_USAGE = "use --json build with exactly one source: --url-file or --input"
BLOCKED_OPTIONS = {
    "--url": "--url is not supported; use --url-file",
    "--output-dir": "--output-dir was removed; use --output for the .ics path",
    "--full-envelope": "--full-envelope was removed",
    "--pnr": "explicit carrier credential flags were removed; use --url-file",
    "--rloc": "explicit carrier credential flags were removed; use --url-file",
    "--pnr-locator": "explicit carrier credential flags were removed; use --url-file",
    "--pnr-key": "explicit carrier credential flags were removed; use --url-file",
    "--last-name": "explicit carrier credential flags were removed; use --url-file",
    "--first-name": "explicit carrier credential flags were removed; use --url-file",
    "--access-key": "explicit carrier credential flags were removed; use --url-file",
    "--frontend-base": "diagnostic carrier overrides were removed",
    "--graphql-endpoint": "diagnostic carrier overrides were removed",
}


class CompactArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 - argparse override
        raise CliFailure(PUBLIC_USAGE, code="usage_error")


def _reject_removed_options(argv: list[str]) -> None:
    for token in argv:
        for option, message in BLOCKED_OPTIONS.items():
            if token == option or token.startswith(f"{option}="):
                raise CliFailure(message, code="usage_error")


def _fail_usage(message: str) -> None:
    raise CliFailure(message, code="usage_error")


def parse_cli_tz_overrides(items: list[str]) -> dict[str, str]:
    return parse_tz_overrides(items, fail=_fail_usage)


def build_timezone_map(overrides: dict[str, str] | None = None) -> dict[str, str]:
    return timezone_catalog.build_timezone_map(overrides)


def validate_itinerary_contract(itinerary: dict[str, Any]) -> dict[str, Any]:
    normalized = itinerary_contract.normalize_legacy_itinerary(itinerary)
    itinerary_contract.validate_itinerary_schema(normalized)
    itinerary_contract.validate_itinerary_semantics(normalized)
    return normalized


def _load_input_itinerary(input_path: Path) -> dict[str, Any]:
    data = ics_render.load_input(input_path)
    return validate_itinerary_contract(data)


def _source_args_for_url_file(url_file: Path) -> argparse.Namespace:
    return argparse.Namespace(
        input=None,
        url=None,
        url_file=url_file,
        pnr_locator=None,
        pnr_key=None,
        pnr=None,
        rloc=None,
        last_name=None,
        first_name=None,
        access_code=None,
    )


def _build_itinerary_from_url_file(
    url_file: Path, tz_items: list[str]
) -> dict[str, Any]:
    source_args = _source_args_for_url_file(url_file)
    raw_url = first_url_from_args(source_args)
    if not raw_url:
        raise CliFailure("url file is empty", code="usage_error")
    booking_url = resolve_known_booking_redirect(raw_url)
    route = str(infer_build_route(source_args, url_override=booking_url)["route"])

    tz_map = build_timezone_map(parse_cli_tz_overrides(tz_items))
    if route == "aeroflot":
        locator, key, normalized_url = aeroflot.parse_pnr_source(
            booking_url, None, None
        )
        itinerary = aeroflot.convert_to_itinerary(
            aeroflot.fetch_aeroflot_pnr(locator, key),
            tz_map,
            booking_url=normalized_url,
        )
    elif route == "ural":
        locator, last_name, normalized_url = ural.parse_ural_source(
            booking_url, None, None
        )
        itinerary = ural.convert_to_itinerary(
            ural.fetch_ural_reservation(locator, last_name, booking_url=normalized_url),
            tz_map,
            booking_url=normalized_url,
        )
    elif route == "utair":
        locator, last_name, normalized_url = utair.parse_utair_source(
            booking_url, None, None
        )
        token = utair.fetch_utair_token()
        itinerary = utair.convert_to_itinerary(
            utair.fetch_utair_orders(locator, last_name, token=token),
            tz_map,
            booking_url=normalized_url,
        )
    elif route == "redwings":
        locator, access_code, normalized_url = redwings.parse_redwings_source(
            booking_url, None, None
        )
        itinerary = redwings.convert_to_itinerary(
            redwings.fetch_redwings_order(locator, access_code),
            tz_map,
            booking_url=normalized_url,
        )
    elif route == "s7":
        _booking_id, _passenger_id, normalized_url = s7.parse_s7_source(
            booking_url, None, None
        )
        itinerary = s7.convert_to_itinerary(
            s7.fetch_s7_order(normalized_url),
            tz_map,
            booking_url=normalized_url,
        )
    else:
        raise CliFailure("unsupported booking URL route", code="route_unknown")
    return validate_itinerary_contract(itinerary)


def _default_output_path() -> Path:
    return Path(tempfile.mkdtemp(prefix="flight-ics.")) / "flights.ics"


def command_build(args: argparse.Namespace) -> dict[str, Any]:
    if args.input is not None and args.tz:
        raise CliFailure("--tz is only supported with --url-file", code="usage_error")

    if args.input is not None:
        itinerary = _load_input_itinerary(args.input)
    else:
        itinerary = _build_itinerary_from_url_file(args.url_file, args.tz)

    ics_text, summaries = ics_render.build_calendar(itinerary, no_alarms=args.no_alarms)
    ics_render.validate_ics_text(ics_text, len(summaries))
    output_path = args.output or _default_output_path()
    secure_write_text(output_path, ics_text)
    return {
        "ok": True,
        "media": f"MEDIA:{output_path}",
        "segments_count": len(summaries),
        "no_further_action_needed": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = CompactArgumentParser(
        description="Create a compact flight .ics calendar file.", allow_abbrev=False
    )
    parser.add_argument(
        "--json",
        action="store_true",
        required=True,
        help="Emit short machine-readable JSON",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser(
        "build",
        help="Create one .ics file from a booking URL file or itinerary JSON",
        allow_abbrev=False,
    )
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--url-file", type=Path, help="Private file containing one carrier booking URL"
    )
    source.add_argument("--input", "-i", type=Path, help="Minimal itinerary JSON")
    build.add_argument(
        "--output",
        type=Path,
        help="Output .ics path; defaults to a temporary flights.ics",
    )
    build.add_argument(
        "--no-alarms", action="store_true", help="Do not add VALARM reminders"
    )
    build.add_argument(
        "--tz",
        action="append",
        default=[],
        help="Carrier URL path timezone override CODE=Area/City",
    )
    return parser


def _emit_json(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _emit_human_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv_list
    stderr_buffer = io.StringIO()
    try:
        _reject_removed_options(argv_list)
        parser = build_parser()
        args = parser.parse_args(argv_list)
        if args.command != "build":
            raise CliFailure(PUBLIC_USAGE, code="usage_error")
        with contextlib.redirect_stderr(stderr_buffer):
            payload = command_build(args)
        _emit_json(payload)
        return 0
    except CliFailure as exc:
        payload = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        if json_mode:
            _emit_json(payload)
        else:
            _emit_human_error(str(exc))
        return exc.exit_code
    except ValueError as exc:
        payload = {
            "ok": False,
            "error": {"code": "validation_error", "message": str(exc)},
        }
        if json_mode:
            _emit_json(payload)
        else:
            _emit_human_error(str(exc))
        return 2
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if code == 0:
            return 0
        message = stderr_buffer.getvalue().strip() or PUBLIC_USAGE
        payload = {
            "ok": False,
            "error": {
                "code": "validation_error",
                "message": message.replace("ERROR: ", ""),
            },
        }
        if json_mode:
            _emit_json(payload)
        else:
            _emit_human_error(payload["error"]["message"])
        return code
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        payload = {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": f"{type(exc).__name__}: {exc}",
            },
        }
        if json_mode:
            _emit_json(payload)
        else:
            _emit_human_error(payload["error"]["message"])
        return 1
