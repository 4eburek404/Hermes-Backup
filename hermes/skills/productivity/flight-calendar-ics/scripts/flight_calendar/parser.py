#!/usr/bin/env python3
"""Parser and public command dispatcher for flight-calendar-ics.

The public executable remains ``scripts/flight_calendar_ics.py``. This module owns
argparse wiring and delegates to domain command modules while preserving the
stable JSON envelope contract.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from flight_calendar.carriers import aeroflot
from flight_calendar import itinerary_contract
from flight_calendar import carrier_http, ics_render
from flight_calendar import timezone_catalog as airport_catalog
from flight_calendar.carriers import ural
from flight_calendar.carriers import utair
from flight_calendar.carriers import redwings
from flight_calendar.common import parse_tz_overrides, secure_write_text
from flight_calendar.contracts import (
    BUILD_ROUTE_CHOICES,
    COMMANDS,
    SCHEMA_VERSION,
    build_agent_contract,
    build_command_registry,
)
from flight_calendar.build_command import run_build_command
from flight_calendar.bundle import bundle_paths, file_mode, verify_bundle_artifacts
from flight_calendar.envelope import (
    CliFailure,
    add_step,
    emit_human,
    emit_json,
    envelope,
    write_envelope_artifact_if_requested,
)
from flight_calendar.maintenance import (
    audit_report,
    clean_dry_run_report,
    contracts_report,
    refs_registry_check_report,
    source_runtime_diff_report,
    source_runtime_sync_report,
    timezone_catalog_report,
)
from flight_calendar.privacy import redact
from flight_calendar.route_detection import infer_build_route
from flight_calendar.segments import itinerary_flight_segments, safe_segment_summary
from flight_calendar.timezones import add_timezone_map_step

SKILL_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ENTRYPOINT = Path(__file__).resolve().parents[1] / "flight_calendar_ics.py"

AGENT_CONTRACT: dict[str, Any] = build_agent_contract()


def _fail_usage(message: str) -> None:
    raise CliFailure(message, code="usage_error")


def parse_cli_tz_overrides(items: list[str]) -> dict[str, str]:
    return parse_tz_overrides(items, fail=_fail_usage)


def load_airport_timezone_document(catalog_path: Path | None = None) -> dict[str, Any]:
    """Backward-compatible wrapper around the bundled airport timezone catalog."""
    return airport_catalog.load_catalog_document(catalog_path)


def load_airport_timezones(catalog_path: Path | None = None) -> dict[str, str]:
    """Backward-compatible wrapper around the bundled airport timezone map."""
    return airport_catalog.load_airport_timezones(catalog_path)


def build_timezone_map(
    overrides: dict[str, str] | None = None,
    *,
    catalog_path: Path | None = None,
) -> dict[str, str]:
    """Backward-compatible wrapper used by legacy tests and carrier commands."""
    return airport_catalog.build_timezone_map(overrides, catalog_path=catalog_path)


def build_make_bundle(args: argparse.Namespace, paths: dict[str, Path], process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    if args.input is None:
        raise CliFailure("build make requires --input", code="usage_error")
    data = ics_render.load_input(args.input)
    add_step(process, "load_input")
    data = validate_itinerary_contract(data, process)
    ics_text, summaries = ics_render.build_calendar(data, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    ics_render.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(paths["json"], json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0644")
    secure_write_text(paths["ics"], ics_text)
    add_step(process, "write_ics", artifact="ics", mode="0644")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "json_path": str(paths["json"]),
        "ics_path": str(paths["ics"]),
        "write_performed": True,
    }


def command_build(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    carrier_handlers = {
        "aeroflot": command_aeroflot,
        "ural": command_ural,
        "utair": command_utair,
        "redwings": command_redwings,
    }
    return run_build_command(
        args,
        process,
        make_bundle=build_make_bundle,
        carrier_handlers=carrier_handlers,
    )


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
    data = ics_render.load_input(input_path)
    add_step(process, "load_input")
    data = validate_itinerary_contract(data, process)
    ics_text, summaries = ics_render.build_calendar(data, no_alarms=no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    ics_render.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    return ics_text, summaries


def load_cli_timezone_map(args: argparse.Namespace, process: list[dict[str, Any]]) -> dict[str, str]:
    timezone_overrides = parse_cli_tz_overrides(args.tz)
    airport_catalog_timezones = load_airport_timezones()
    tz_map = build_timezone_map(timezone_overrides)
    add_timezone_map_step(process, airport_catalog_timezones, len(args.tz))
    return tz_map


def finish_carrier_build(
    args: argparse.Namespace,
    process: list[dict[str, Any]],
    itinerary: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = ics_render.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    ics_render.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0644")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0644")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": itinerary_flight_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_doctor(_args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    add_step(process, "load_input", "skipped", reason="doctor has no itinerary input")
    data = {
        "entrypoint": str(PUBLIC_ENTRYPOINT.resolve()),
        "entrypoint_kind": "single-python-executable",
        "http_transport": carrier_http.active_transport(),
        "schema_version": SCHEMA_VERSION,
        "commands": COMMANDS,
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
        "command_registry": build_command_registry(),
        "agent_contract": AGENT_CONTRACT,
    }
    return 0, data


def command_diagnose(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    if args.subcommand == "doctor":
        rc, data = command_doctor(args, process)
        data = dict(data)
        data.update(
            {
                "surface": "diagnostic",
                "subcommand": "doctor",
                "write_performed": False,
            }
        )
        add_step(process, "no_write")
        return rc, data
    if args.subcommand == "validate":
        rc, data = command_validate(args, process)
        data = dict(data)
        data.update({"surface": "diagnostic", "subcommand": "validate"})
        return rc, data
    if args.subcommand == "route-detect":
        route_detection = infer_build_route(args)
        add_step(
            process,
            "infer_route",
            route=route_detection["route"],
            confidence=route_detection["confidence"],
            evidence=route_detection["evidence"],
        )
        add_step(process, "no_write")
        return 0, {
            "surface": "diagnostic",
            "subcommand": "route-detect",
            "route_detection": route_detection,
            "write_performed": False,
        }
    if args.subcommand == "timezone" and getattr(args, "action", None) == "inspect":
        data = timezone_catalog_report(SKILL_ROOT)
        data.update({"surface": "diagnostic", "subcommand": "timezone inspect", "write_performed": False})
        add_step(process, "inspect_timezone_catalog")
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "bundle-check":
        paths = bundle_paths(args.bundle_dir)
        files = {
            name: {"exists": path.exists(), "mode": file_mode(path) if path.exists() else None}
            for name, path in paths.items()
        }
        verification: dict[str, Any] = {"ok": False, "event_count": 0}
        if paths["json"].exists() and paths["ics"].exists():
            event_count = paths["ics"].read_text(encoding="utf-8", errors="replace").count("BEGIN:VEVENT")
            try:
                verification = verify_bundle_artifacts(paths, event_count, process)
            except CliFailure as exc:
                verification = {"ok": False, "event_count": event_count, "error": redact(str(exc))}
        add_step(process, "no_write")
        return 0, {
            "surface": "diagnostic",
            "subcommand": "bundle-check",
            "bundle_dir": str(args.bundle_dir.resolve()),
            "files": files,
            "verification": verification,
            "write_performed": False,
        }
    if args.subcommand == "privacy-check":
        paths = bundle_paths(args.bundle_dir)
        checked_files: list[str] = []
        violations: list[dict[str, str]] = []
        for name, path in paths.items():
            if not path.exists() or not path.is_file():
                continue
            checked_files.append(name)
            text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
            if redact(text) != text:
                violations.append({"path": name, "kind": "credential_pattern", "matched": "[REDACTED]"})
        add_step(process, "no_write")
        return 0, {
            "surface": "diagnostic",
            "subcommand": "privacy-check",
            "checked_files": checked_files,
            "violations": violations,
            "private_contents_printed": False,
            "write_performed": False,
        }
    if args.subcommand == "carrier-probe":
        add_step(process, "no_write")
        return 0, {
            "surface": "diagnostic",
            "subcommand": "carrier-probe",
            "carrier": args.carrier,
            "safe_adapter_metadata": {"route": args.carrier, "network_performed": False},
            "write_performed": False,
        }
    raise CliFailure(f"unknown diagnose subcommand: {args.subcommand}", code="usage_error")


def command_maint(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    if args.subcommand in {"contracts", "doctor"}:
        data = contracts_report(build_command_registry())
        data.update(
            {
                "surface": "maintenance",
                "subcommand": args.subcommand,
                "write_performed": False,
                "command_registry": build_command_registry(),
            }
        )
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "source-runtime-sync":
        data = source_runtime_sync_report(args.source_dir, args.runtime_dir)
        data.update(
            {
                "surface": "maintenance",
                "subcommand": "source-runtime-sync",
                "write_performed": False,
            }
        )
        add_step(process, "scan_source_runtime")
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "source-runtime" and getattr(args, "action", None) == "diff":
        data = source_runtime_diff_report(args.source_dir, args.runtime_dir)
        data.update({"surface": "maintenance", "subcommand": "source-runtime diff", "write_performed": False})
        add_step(process, "scan_source_runtime")
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "refs" and getattr(args, "action", None) == "registry-check":
        data = refs_registry_check_report(SKILL_ROOT)
        data.update({"surface": "maintenance", "subcommand": "refs registry-check", "write_performed": False})
        add_step(process, "scan_reference_registry")
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "clean":
        if not args.dry_run:
            raise CliFailure("maint clean requires --dry-run in this read-only refactor scope", code="usage_error")
        data = clean_dry_run_report(args.target_dir)
        data.update({"surface": "maintenance", "subcommand": "clean", "write_performed": False})
        add_step(process, "scan_cleanup_candidates")
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "audit":
        data = audit_report(SKILL_ROOT, args.source_dir, args.runtime_dir, args.target_dir, build_command_registry())
        data.update({"surface": "maintenance", "subcommand": "audit", "write_performed": False})
        add_step(process, "aggregate_audit")
        add_step(process, "no_write")
        return 0, data
    if args.subcommand == "timezone-catalog" and getattr(args, "action", None) == "inspect":
        data = timezone_catalog_report(SKILL_ROOT)
        data.update({"surface": "maintenance", "subcommand": "timezone-catalog inspect", "write_performed": False})
        add_step(process, "inspect_timezone_catalog")
        add_step(process, "no_write")
        return 0, data
    raise CliFailure(f"unknown maint subcommand: {args.subcommand}", code="usage_error")


def command_validate(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    _ics_text, summaries = build_and_validate(args.input, no_alarms=args.no_alarms, process=process)
    add_step(process, "no_write")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "write_performed": False,
    }



def command_aeroflot(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, key, booking_url = aeroflot.resolve_pnr_source(
        args.url,
        args.pnr_locator,
        args.pnr_key,
        args.last_name,
        args.first_name,
    )
    add_step(process, "parse_pnr_source")
    tz_map = load_cli_timezone_map(args, process)
    data = aeroflot.fetch_aeroflot_pnr(locator, key)
    add_step(process, "fetch_aeroflot_pnr")
    itinerary = aeroflot.convert_to_itinerary(data, tz_map, booking_url=booking_url)
    return finish_carrier_build(args, process, itinerary)


def command_ural(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, last_name, booking_url = ural.parse_ural_source(args.url, args.pnr, args.last_name)
    add_step(process, "parse_pnr_source")
    tz_map = load_cli_timezone_map(args, process)
    reservation = ural.fetch_ural_reservation(
        locator,
        last_name,
        booking_url=booking_url,
        frontend_base=args.frontend_base,
    )
    add_step(process, "fetch_ural_reservation")
    itinerary = ural.convert_to_itinerary(reservation, tz_map, booking_url=booking_url)
    return finish_carrier_build(args, process, itinerary)


def command_utair(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, last_name, booking_url = utair.parse_utair_source(args.url, args.rloc, args.last_name)
    add_step(process, "parse_pnr_source")
    tz_map = load_cli_timezone_map(args, process)
    token = utair.fetch_utair_token()
    add_step(process, "fetch_utair_token")
    orders = utair.fetch_utair_orders(locator, last_name, token=token)
    add_step(process, "fetch_utair_orders")
    itinerary = utair.convert_to_itinerary(orders, tz_map, booking_url=booking_url)
    return finish_carrier_build(args, process, itinerary)


def command_redwings(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, finder_code, booking_url = redwings.parse_redwings_source(args.url, args.pnr, args.access_code)
    add_step(process, "parse_redwings_source")
    tz_map = load_cli_timezone_map(args, process)
    order = redwings.fetch_redwings_order(locator, finder_code, graphql_endpoint=args.graphql_endpoint)
    add_step(process, "fetch_redwings_order")
    itinerary = redwings.convert_to_itinerary(order, tz_map, booking_url=booking_url)
    return finish_carrier_build(args, process, itinerary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single CLI entrypoint for the flight-calendar-ics skill.")
    parser.add_argument("--json", action="store_true", help="Emit the stable machine-readable JSON envelope")
    parser.add_argument(
        "--full-envelope",
        action="store_true",
        help="With --json build, print the full diagnostic envelope to stdout instead of the delivery handoff",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Report CLI contract and available commands")

    def add_source_detection_args(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--input", "-i", type=Path, help="Canonical itinerary JSON")
        cmd.add_argument("--url", help="Carrier booking URL; prefer --url-file for private inputs")
        cmd.add_argument("--url-file", type=Path, help="Private file containing the carrier booking URL")
        cmd.add_argument("--pnr-locator", help="Aeroflot booking locator")
        cmd.add_argument("--pnr-key", help="Aeroflot PNR key")
        cmd.add_argument("--pnr", help="Carrier booking locator for Ural/Red Wings")
        cmd.add_argument("--rloc", help="Utair booking locator")
        cmd.add_argument("--last-name", help="Passenger surname for lookup routes")
        cmd.add_argument("--first-name", help="Passenger first name fallback for Aeroflot")
        cmd.add_argument("--access-key", dest="access_code", help="Red Wings access key")

    diagnose = sub.add_parser("diagnose", help="Diagnostic commands for CLI contracts and source triage")
    diagnose_sub = diagnose.add_subparsers(dest="subcommand", required=True)
    diagnose_sub.add_parser("doctor", help="Report diagnostic CLI contract without reading or writing itinerary artifacts")
    diagnose_validate = diagnose_sub.add_parser("validate", help="Validate canonical itinerary JSON without writing .ics")
    diagnose_validate.add_argument("--input", "-i", required=True, type=Path, help="Path to itinerary JSON")
    diagnose_validate.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders while validating")
    diagnose_route = diagnose_sub.add_parser("route-detect", help="Explain build auto route inference using redacted evidence")
    add_source_detection_args(diagnose_route)
    diagnose_bundle = diagnose_sub.add_parser("bundle-check", help="Verify existing private bundle metadata without dumping contents")
    diagnose_bundle.add_argument("--bundle-dir", required=True, type=Path, help="Existing private bundle directory")
    diagnose_privacy = diagnose_sub.add_parser("privacy-check", help="Scan bundle for redaction sentinel violations without printing contents")
    diagnose_privacy.add_argument("--bundle-dir", required=True, type=Path, help="Existing private bundle directory")
    diagnose_carrier = diagnose_sub.add_parser("carrier-probe", help="Report safe carrier probe metadata without being a delivery path")
    diagnose_carrier.add_argument("carrier", choices=["aeroflot", "ural", "utair", "redwings"], help="Carrier namespace to probe")
    add_source_detection_args(diagnose_carrier)
    diagnose_timezone = diagnose_sub.add_parser("timezone", help="Timezone catalog diagnostics")
    diagnose_timezone_sub = diagnose_timezone.add_subparsers(dest="action", required=True)
    diagnose_timezone_sub.add_parser("inspect", help="Report bundled timezone catalog metadata")

    maint = sub.add_parser("maint", help="Read-only maintenance diagnostics for contracts and source/runtime drift")
    maint_sub = maint.add_subparsers(dest="subcommand", required=True)
    maint_sub.add_parser("doctor", help="Report maintenance command-surface contract checks without writes")
    maint_sub.add_parser("contracts", help="Report command-surface contract checks without writes")
    source_runtime = maint_sub.add_parser("source-runtime", help="Source/runtime manifest reports")
    source_runtime_sub = source_runtime.add_subparsers(dest="action", required=True)
    source_runtime_diff = source_runtime_sub.add_parser("diff", help="Compare source and runtime skill trees without syncing or writing")
    source_runtime_diff.add_argument("--source-dir", type=Path, default=SKILL_ROOT, help="Source skill directory to scan")
    source_runtime_diff.add_argument("--runtime-dir", type=Path, default=Path.home() / ".hermes" / "skills" / "productivity" / "flight-calendar-ics", help="Runtime skill directory to scan")
    sync = maint_sub.add_parser("source-runtime-sync", help="Compatibility alias for read-only source/runtime diff")
    sync.add_argument("--source-dir", type=Path, default=SKILL_ROOT, help="Source skill directory to scan")
    sync.add_argument("--runtime-dir", type=Path, default=Path.home() / ".hermes" / "skills" / "productivity" / "flight-calendar-ics", help="Runtime skill directory to scan")
    refs = maint_sub.add_parser("refs", help="Reference registry checks")
    refs_sub = refs.add_subparsers(dest="action", required=True)
    refs_sub.add_parser("registry-check", help="Verify references/registry.md owns every reference")
    clean = maint_sub.add_parser("clean", help="Read-only generated artifact cleanup report")
    clean.add_argument("--dry-run", action="store_true", help="Required: report only, delete nothing")
    clean.add_argument("--target-dir", type=Path, default=SKILL_ROOT, help="Directory to scan for generated artifacts")
    audit = maint_sub.add_parser("audit", help="Aggregate read-only maintenance reports")
    audit.add_argument("--source-dir", type=Path, default=SKILL_ROOT, help="Source skill directory to scan")
    audit.add_argument("--runtime-dir", type=Path, default=Path.home() / ".hermes" / "skills" / "productivity" / "flight-calendar-ics", help="Runtime skill directory to scan")
    audit.add_argument("--target-dir", type=Path, default=SKILL_ROOT, help="Directory to scan for generated artifacts")
    timezone_catalog = maint_sub.add_parser("timezone-catalog", help="Timezone catalog maintenance reports")
    timezone_catalog_sub = timezone_catalog.add_subparsers(dest="action", required=True)
    timezone_catalog_sub.add_parser("inspect", help="Report bundled timezone catalog metadata")

    build = sub.add_parser("build", help="Create a private bundle: itinerary.json, flights.ics, envelope.json")
    build.add_argument("route", choices=BUILD_ROUTE_CHOICES, help="Source route to build from; use auto to let the CLI infer from input/source fingerprint")
    build.add_argument("--output-dir", type=Path, help="Optional bundle directory; defaults to a private /tmp/flight-ics.* directory")
    build.add_argument("--input", "-i", type=Path, help="Canonical itinerary JSON for build make")
    build.add_argument("--url", help="Carrier booking URL; prefer --url-file for private inputs")
    build.add_argument("--url-file", type=Path, help="Private file containing the carrier booking URL")
    build.add_argument("--pnr-locator", help="Aeroflot booking locator, if not using --url/--url-file")
    build.add_argument("--pnr-key", help="Aeroflot PNR key, if not using --url/--url-file")
    build.add_argument("--pnr", help="Carrier booking locator for Ural/Red Wings, if not using --url/--url-file")
    build.add_argument("--rloc", help="Utair booking locator, if not using --url/--url-file")
    build.add_argument("--last-name", help="Passenger surname for lookup routes")
    build.add_argument("--first-name", help="Passenger first name fallback for Aeroflot ambiguous surname lookup")
    build.add_argument("--access-key", dest="access_code", help="Red Wings access key, if not using --url/--url-file")
    build.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    build.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    build.add_argument("--frontend-base", help="Override Ural frontend base URL for diagnostics/tests")
    build.add_argument("--graphql-endpoint", help="Override Websky GraphQL endpoint for diagnostics/tests")

    return parser


def run_command(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    handlers: dict[str, Callable[[argparse.Namespace, list[dict[str, Any]]], tuple[int, dict[str, Any]]]] = {
        "doctor": command_doctor,
        "build": command_build,
        "diagnose": command_diagnose,
        "maint": command_maint,
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


def build_handoff_stdout_envelope(full_obj: dict[str, Any]) -> dict[str, Any]:
    """Project a successful full build envelope to the golden-path delivery handoff."""
    data = full_obj.get("data") or {}
    handoff_data = data.get("agent_handoff") or {}
    obj = envelope(
        ok=True,
        command="build",
        process=[{"step": "build_handoff", "status": "ok"}],
        data={
            "agent_handoff": handoff_data,
            "envelope_path": data["envelope_path"],
        },
    )
    # Top-level signal: models check "ok" first — put the stop signal right next to it.
    if handoff_data.get("no_further_action_needed") is True:
        obj["no_further_action_needed"] = True
    return obj


def should_emit_handoff_stdout(args: argparse.Namespace, data: dict[str, Any]) -> bool:
    return bool(
        args.json
        and args.command == "build"
        and not getattr(args, "full_envelope", False)
        and data.get("agent_handoff")
        and data.get("envelope_path")
    )


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
        if args.json and data.get("envelope_path"):
            add_step(process, "write_envelope", artifact="envelope", mode="0644")
        add_step(process, "emit_json" if args.json else "emit_human")
        obj = envelope(ok=True, command=args.command, process=process, data=data)
        if args.json:
            write_envelope_artifact_if_requested(data, obj)
            emit_json(build_handoff_stdout_envelope(obj) if should_emit_handoff_stdout(args, data) else obj)
        else:
            emit_human(obj)
        return exit_code
    except CliFailure as exc:
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        error_obj: dict[str, Any] = {"code": exc.code, "message": redact(str(exc))}
        for key in ("safe_candidates", "required_disambiguation"):
            if key in exc.details:
                error_obj[key] = exc.details[key]
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error=error_obj,
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
