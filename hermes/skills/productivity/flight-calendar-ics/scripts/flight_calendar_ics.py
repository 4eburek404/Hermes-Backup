#!/usr/bin/env python3
"""Single agent-facing CLI for flight-calendar-ics.

The CLI is intentionally a thin orchestrator around the skill's stdlib helper
modules. Its contract surface is the JSON envelope emitted with ``--json``:
future agents should parse that envelope instead of scraping human stdout.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

import aeroflot_pnr_to_itinerary as aeroflot
import itinerary_contract
import make_flight_ics
import ural_airlines_to_itinerary as ural
import utair_to_itinerary as utair
import redwings_to_itinerary as redwings

SCHEMA_VERSION = "flight-calendar-ics-cli.v1"
COMMANDS = ["doctor", "validate", "make", "aeroflot", "ural", "utair", "redwings"]


class CliFailure(Exception):
    """Expected CLI failure that should become a machine-readable error."""

    def __init__(self, message: str, *, code: str = "validation_error", exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def add_step(process: list[dict[str, Any]], step: str, status: str = "ok", **data: Any) -> None:
    item: dict[str, Any] = {"step": step, "status": status}
    if data:
        item.update(data)
    process.append(item)


def redact(text: str) -> str:
    """Redact known booking credentials without trying to identify names."""
    patterns = [
        (r"(?i)(pnrKey=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(pnr_key[\"'\s:=]+)[0-9a-f]{16,256}", r"\1[REDACTED]"),
        (r"(?i)(pnrLocator=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(pnr_locator[\"'\s:=]+)[A-Z0-9]{5,8}", r"\1[REDACTED]"),
        (r"(?i)(pnr=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(pnrNumber=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(lastName=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(rloc=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(last_name=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(filters(?:%5B|\[)locator(?:%5D|\])=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(filters(?:%5B|\[)passenger_lastname(?:%5D|\])=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(Authorization:\s*Bearer\s+)[^\s&]+", r"\1[REDACTED]"),
        (r"(?i)(#/find/)[^/\s]+/[^/\s]+(/Submit)", r"\1[REDACTED]/[REDACTED]\2"),
        (r"(?i)((?:access[-_ ]?key|access_code|finder_code)[\"'\s:=]+)[^\s&\"']+", r"\1[REDACTED]"),
        (r"(?i)([\"']secret[\"']\s*:\s*[\"'])[^\"']+([\"'])", r"\1[REDACTED]\2"),
        (r"(?i)(ticket=)\d{6,}", r"\1[REDACTED]"),
        (r"(?i)(ticket[_ -]?number[\"'\s:=]+)\d{6,}", r"\1[REDACTED]"),
        (r"\b\d{13}\b", "[REDACTED]"),
    ]
    out = text
    for pattern, repl in patterns:
        out = re.sub(pattern, repl, out)
    return out


def envelope(
    *,
    ok: bool,
    command: str,
    process: list[dict[str, Any]],
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "command": command,
        "process": process,
    }
    if ok:
        obj["data"] = data or {}
    else:
        obj["error"] = error or {"code": "unknown_error", "message": "unknown error"}
    return obj


def emit_json(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def emit_human(obj: dict[str, Any]) -> None:
    if obj["ok"]:
        data = obj.get("data") or {}
        print(f"OK: {obj['command']}")
        if "segments_count" in data:
            print(f"segments: {data['segments_count']}")
        if data.get("ics_path"):
            print(f"ics: {data['ics_path']}")
        if data.get("json_path"):
            print(f"json: {data['json_path']}")
    else:
        err = obj.get("error") or {}
        print(f"ERROR: {err.get('message', 'unknown error')}", file=sys.stderr)


def secure_write_text(path: Path, text: str) -> None:
    """Write sensitive itinerary artifacts as owner-only files."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    finally:
        try:
            os.chmod(path, 0o600)
        except FileNotFoundError:
            pass


def safe_segment_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": summary.get("flight_number"),
        "route": summary.get("route"),
        "dtstart_utc": summary.get("dtstart_utc"),
        "dtend_utc": summary.get("dtend_utc"),
    }


def validate_itinerary_contract(itinerary: dict[str, Any], process: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = itinerary_contract.normalize_legacy_itinerary(itinerary)
    try:
        itinerary_contract.validate_itinerary_schema(normalized)
    except ValueError:
        add_step(process, "validate_itinerary_schema", "error")
        raise
    add_step(process, "validate_itinerary_schema", schema_version=itinerary_contract.SCHEMA_VERSION)
    try:
        itinerary_contract.validate_itinerary_semantics(normalized)
    except ValueError:
        add_step(process, "validate_itinerary_semantics", "error")
        raise
    add_step(process, "validate_itinerary_semantics")
    return normalized


def build_and_validate(input_path: Path, *, no_alarms: bool, process: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    data = make_flight_ics.load_input(input_path)
    add_step(process, "load_input")
    data = validate_itinerary_contract(data, process)
    ics_text, summaries = make_flight_ics.build_calendar(data, no_alarms=no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    return ics_text, summaries


def command_doctor(_args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    add_step(process, "load_input", "skipped", reason="doctor has no itinerary input")
    data = {
        "entrypoint": str(Path(__file__).resolve()),
        "entrypoint_kind": "single-python-executable",
        "schema_version": SCHEMA_VERSION,
        "commands": COMMANDS,
        "legacy_scripts": [
            "scripts/make_flight_ics.py",
            "scripts/aeroflot_pnr_to_itinerary.py",
            "scripts/ural_airlines_to_itinerary.py",
            "scripts/utair_to_itinerary.py",
            "scripts/redwings_to_itinerary.py",
        ],
        "json_contract": {
            "ok": "boolean",
            "command": "string",
            "process": "ordered list of step/status objects",
            "data": "object when ok=true",
            "error": "object when ok=false",
        },
        "input_contract": {
            "schema_version": itinerary_contract.SCHEMA_VERSION,
            "schema_path": str(itinerary_contract.SCHEMA_PATH),
        },
        "sensitive_stdout_policy": "route/timestamp summaries only; no PNR keys, passenger names, ticket numbers, or full booking URLs",
    }
    return 0, data


def command_validate(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    _ics_text, summaries = build_and_validate(args.input, no_alarms=args.no_alarms, process=process)
    add_step(process, "no_write")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "write_performed": False,
    }


def command_make(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    ics_text, summaries = build_and_validate(args.input, no_alarms=args.no_alarms, process=process)
    output = args.output or args.input.with_suffix(".ics")
    secure_write_text(output, ics_text)
    add_step(process, "write_output", artifact="ics", mode="0600")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "ics_path": str(output),
        "write_performed": True,
    }


def aeroflot_segments(itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "flight_number": f.get("flight_number"),
            "route": f"{(f.get('departure') or {}).get('airport')}->{(f.get('arrival') or {}).get('airport')}",
            "departure_local": (f.get("departure") or {}).get("local"),
            "arrival_local": (f.get("arrival") or {}).get("local"),
        }
        for f in itinerary.get("flights", [])
    ]


def command_aeroflot(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, key, booking_url = aeroflot.parse_pnr_source(args.url, args.pnr_locator, args.pnr_key)
    add_step(process, "parse_pnr_source")
    tz_map = {**aeroflot.DEFAULT_AIRPORT_TZ, **aeroflot.parse_tz_overrides(args.tz)}
    add_step(process, "load_timezone_map", overrides_count=len(args.tz))
    data = aeroflot.fetch_aeroflot_pnr(locator, key)
    add_step(process, "fetch_aeroflot_pnr")
    itinerary = aeroflot.convert_to_itinerary(data, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_ural(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, last_name, booking_url = ural.parse_ural_source(args.url, args.pnr, args.last_name)
    add_step(process, "parse_pnr_source")
    tz_map = {**ural.DEFAULT_AIRPORT_TZ, **ural.parse_tz_overrides(args.tz)}
    add_step(process, "load_timezone_map", overrides_count=len(args.tz))
    reservation = ural.fetch_ural_reservation(
        locator,
        last_name,
        booking_url=booking_url,
        frontend_base=args.frontend_base,
    )
    add_step(process, "fetch_ural_reservation")
    itinerary = ural.convert_to_itinerary(reservation, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_utair(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, last_name, booking_url = utair.parse_utair_source(args.url, args.rloc, args.last_name)
    add_step(process, "parse_pnr_source")
    tz_map = {**utair.DEFAULT_AIRPORT_TZ, **utair.parse_tz_overrides(args.tz)}
    add_step(process, "load_timezone_map", overrides_count=len(args.tz))
    bearer_value = utair.fetch_utair_token()
    add_step(process, "fetch_utair_token")
    orders = utair.fetch_utair_orders(locator, last_name, bearer_value=bearer_value)
    add_step(process, "fetch_utair_orders")
    itinerary = utair.convert_to_itinerary(orders, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_redwings(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, finder_code, booking_url = redwings.parse_redwings_source(args.url, args.pnr, args.access_code)
    add_step(process, "parse_redwings_source")
    tz_map = {**redwings.DEFAULT_AIRPORT_TZ, **redwings.parse_tz_overrides(args.tz)}
    add_step(process, "load_timezone_map", overrides_count=len(args.tz))
    order = redwings.fetch_redwings_order(locator, finder_code, graphql_endpoint=args.graphql_endpoint)
    add_step(process, "fetch_redwings_order")
    itinerary = redwings.convert_to_itinerary(order, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single CLI entrypoint for the flight-calendar-ics skill.")
    parser.add_argument("--json", action="store_true", help="Emit the stable machine-readable JSON envelope")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Report CLI contract and available commands")

    validate = sub.add_parser("validate", help="Validate an itinerary JSON without writing an .ics file")
    validate.add_argument("--input", "-i", required=True, type=Path, help="Path to itinerary JSON")
    validate.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders while validating")

    make = sub.add_parser("make", help="Validate an itinerary JSON and write an .ics file")
    make.add_argument("--input", "-i", required=True, type=Path, help="Path to itinerary JSON")
    make.add_argument("--output", "-o", type=Path, help="Output .ics path; defaults to input basename")
    make.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")

    aero = sub.add_parser("aeroflot", help="Fetch an Aeroflot PNR and write standard itinerary JSON, optionally .ics")
    aero.add_argument("--url", help="Aeroflot PNR share URL containing pnrKey and pnrLocator")
    aero.add_argument("--pnr-locator", help="Booking locator, if not using --url")
    aero.add_argument("--pnr-key", help="PNR key, if not using --url")
    aero.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    aero.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    aero.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    aero.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")

    ural_parser = sub.add_parser("ural", help="Fetch a Ural Airlines PNR and write standard itinerary JSON, optionally .ics")
    ural_parser.add_argument("--url", help="Ural Airlines manage-booking URL containing pnr and lastName")
    ural_parser.add_argument("--pnr", help="Booking locator, if not using --url")
    ural_parser.add_argument("--last-name", help="Passenger surname, if not using --url")
    ural_parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    ural_parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    ural_parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    ural_parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    ural_parser.add_argument("--frontend-base", help="Override Ural frontend base URL for diagnostics/tests")

    utair_parser = sub.add_parser("utair", help="Fetch a Utair PNR and write standard itinerary JSON, optionally .ics")
    utair_parser.add_argument("--url", help="Utair order-manage URL containing rloc and last_name")
    utair_parser.add_argument("--rloc", help="Booking locator, if not using --url")
    utair_parser.add_argument("--last-name", help="Passenger surname, if not using --url")
    utair_parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    utair_parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    utair_parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    utair_parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")

    redwings_parser = sub.add_parser("redwings", help="Fetch a Red Wings/Websky booking and write standard itinerary JSON, optionally .ics")
    redwings_parser.add_argument("--url", help="Red Wings direct email/manage link shaped #/find/<PNR>/<ACCESS_KEY>/Submit")
    redwings_parser.add_argument("--pnr", help="Booking locator, if not using --url")
    redwings_parser.add_argument("--access-key", dest="access_code", help="Access key from the direct email/manage link, if not using --url")
    redwings_parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    redwings_parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    redwings_parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    redwings_parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    redwings_parser.add_argument("--graphql-endpoint", help="Override Websky GraphQL endpoint for diagnostics/tests")
    return parser


def run_command(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    handlers: dict[str, Callable[[argparse.Namespace, list[dict[str, Any]]], tuple[int, dict[str, Any]]]] = {
        "doctor": command_doctor,
        "validate": command_validate,
        "make": command_make,
        "aeroflot": command_aeroflot,
        "ural": command_ural,
        "utair": command_utair,
        "redwings": command_redwings,
    }
    handler = handlers.get(args.command)
    if handler is None:
        raise CliFailure(f"unknown command: {args.command}", code="usage_error")
    return handler(args, process)


def infer_command(argv: list[str]) -> str:
    for token in argv:
        if token in COMMANDS:
            return token
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv_list
    parser = build_parser()
    process: list[dict[str, Any]] = []
    stderr_buffer = io.StringIO()
    args: argparse.Namespace | None = None
    try:
        parse_redirect = contextlib.redirect_stderr(stderr_buffer) if json_mode else contextlib.nullcontext()
        with parse_redirect:
            args = parser.parse_args(argv_list)
        add_step(process, "parse_args")
        stderr_buffer = io.StringIO()
        redirect = contextlib.redirect_stderr(stderr_buffer) if args.json else contextlib.nullcontext()
        with redirect:
            exit_code, data = run_command(args, process)
        add_step(process, "emit_json" if args.json else "emit_human")
        obj = envelope(ok=True, command=args.command, process=process, data=data)
        emit_json(obj) if args.json else emit_human(obj)
        return exit_code
    except CliFailure as exc:
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": exc.code, "message": redact(str(exc))},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return exc.exit_code
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if code == 0:
            return 0
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        message = stderr_buffer.getvalue().strip() or str(exc) or "command failed"
        message = re.sub(r"^ERROR:\s*", "", message)
        add_step(process, "parse_args" if args is None else "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": "usage_error" if args is None else "validation_error", "message": redact(message)},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return code
    except ValueError as exc:
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": "validation_error", "message": redact(str(exc))},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return 2
    except Exception as exc:  # pragma: no cover - defensive envelope for agents
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": "internal_error", "message": redact(f"{type(exc).__name__}: {exc}")},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
