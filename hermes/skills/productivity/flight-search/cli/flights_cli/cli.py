from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__
from .commands.maint import (
    command_maint_catalog_manifest,
    command_maint_catalog_refresh,
    command_maint_doctor,
    command_maintenance_check,
)
from .commands.diagnose import (
    command_diagnose_plan,
    command_diagnose_probe,
    command_diagnose_render,
    command_diagnose_trace,
)
from .commands.metadata import (
    command_airports_explain,
    command_cities_search,
    metadata_evidence_scope,
)
from .commands.search import command_search
from .errors import CliError
from .output import emit_json, error_envelope, output_envelope, render_user_text
from .providers.static_catalog import (
    DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
    parse_ttl_seconds,
    refresh_static_catalog_if_needed,
)
from .store import Store


def _catalog_read_defaults(**kwargs: Any) -> dict[str, Any]:
    return {"catalog_access": "auto_refresh", "requires_catalog": True, **kwargs}


def _json_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    return parent


def _register_primary_search_commands(
    sub, json_parent: argparse.ArgumentParser
) -> None:
    search = sub.add_parser(
        "search",
        parents=[json_parent],
        help="Primary request-file route search; JSON output keeps compact flight_search_result envelope.",
    )
    search.add_argument(
        "--request",
        required=True,
        help="flight_search_request.v1 JSON file, or - for stdin.",
    )
    search.set_defaults(
        func=command_search, command_name="search", **_catalog_read_defaults()
    )


def _register_diagnose_commands(sub, json_parent: argparse.ArgumentParser) -> None:
    diagnose = sub.add_parser(
        "diagnose",
        parents=[json_parent],
        help="Diagnostics for plan/probe/render/trace workflows.",
    )
    diagnose_sub = diagnose.add_subparsers(dest="diagnose_command", required=True)
    plan = diagnose_sub.add_parser(
        "plan",
        parents=[json_parent],
        help="Render the route segment plan from a flight_search_request.v1 file without provider calls.",
    )
    plan.add_argument(
        "--request",
        required=True,
        help="flight_search_request.v1 JSON file, or - for stdin.",
    )
    plan.set_defaults(
        func=command_diagnose_plan,
        command_name="diagnose plan",
        **_catalog_read_defaults(),
    )
    probe = diagnose_sub.add_parser(
        "probe",
        parents=[json_parent],
        help="Run a single provider probe from a probe JSON file.",
    )
    probe.add_argument(
        "--provider", required=True, choices=["kupibilet", "fli", "tutu"]
    )
    probe.add_argument(
        "--request", required=True, help="Probe JSON file, or - for stdin."
    )
    probe.set_defaults(func=command_diagnose_probe, command_name="diagnose probe")
    render = diagnose_sub.add_parser(
        "render",
        parents=[json_parent],
        help="Validate and render user_answer from an agent_report JSON file.",
    )
    render.add_argument(
        "--input",
        required=True,
        help="agent_report JSON file, output envelope, or - for stdin.",
    )
    render.set_defaults(func=command_diagnose_render, command_name="diagnose render")
    trace = diagnose_sub.add_parser(
        "trace",
        parents=[json_parent],
        help="Run search and return the full route/live diagnostic trace.",
    )
    trace.add_argument(
        "--request",
        required=True,
        help="flight_search_request.v1 JSON file, or - for stdin.",
    )
    trace.set_defaults(
        func=command_diagnose_trace,
        command_name="diagnose trace",
        **_catalog_read_defaults(),
    )


def _register_maint_commands(sub, json_parent: argparse.ArgumentParser) -> None:
    maint = sub.add_parser(
        "maint", parents=[json_parent], help="Primary maintenance namespace."
    )
    maint_sub = maint.add_subparsers(dest="maint_command", required=True)
    check = maint_sub.add_parser(
        "check",
        parents=[json_parent],
        help="Report source/runtime provenance and local maintenance status without network calls.",
    )
    check.add_argument(
        "--runtime-path",
        help="Runtime flight-search skill path to compare against. Defaults to ~/.hermes/skills/productivity/flight-search.",
    )
    check.set_defaults(func=command_maintenance_check, command_name="maint check")
    doctor = maint_sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Check local caches and static catalog status without provider calls.",
    )
    doctor.set_defaults(func=command_maint_doctor, command_name="maint doctor")
    catalog = maint_sub.add_parser(
        "catalog",
        parents=[json_parent],
        help="Static catalog maintenance.",
    )
    catalog_sub = catalog.add_subparsers(dest="maint_catalog_command", required=True)
    manifest = catalog_sub.add_parser(
        "manifest",
        parents=[json_parent],
        help="Show the local static catalog manifest.",
    )
    manifest.set_defaults(
        func=command_maint_catalog_manifest, command_name="maint catalog manifest"
    )
    refresh = catalog_sub.add_parser(
        "refresh",
        parents=[json_parent],
        help="Download public static catalog JSON files explicitly.",
    )
    refresh.add_argument(
        "--only",
        action="append",
        help="Catalog item name. Repeatable; defaults to all static files.",
    )
    refresh.add_argument(
        "--timeout", type=int, default=30, help="HTTP timeout seconds per static file."
    )
    refresh.add_argument(
        "--dry-run",
        action="store_true",
        help="Show files that would be downloaded without writing cache.",
    )
    refresh.set_defaults(
        func=command_maint_catalog_refresh,
        command_name="maint catalog refresh",
        catalog_access="refresh_explicit",
    )


def _register_metadata_commands(sub, json_parent: argparse.ArgumentParser) -> None:
    cities = sub.add_parser(
        "cities", parents=[json_parent], help="City lookup commands."
    )
    cities_sub = cities.add_subparsers(dest="cities_command", required=True)
    cities_search = cities_sub.add_parser(
        "search",
        parents=[json_parent],
        help="Search city name or IATA code in local cache.",
    )
    cities_search.add_argument("query")
    cities_search.add_argument("--limit", type=int, default=5)
    cities_search.set_defaults(
        func=command_cities_search,
        command_name="cities search",
        **_catalog_read_defaults(),
    )

    airports = sub.add_parser(
        "airports", parents=[json_parent], help="Airport rule lookup commands."
    )
    airports_sub = airports.add_subparsers(dest="airports_command", required=True)
    airports_explain = airports_sub.add_parser(
        "explain",
        parents=[json_parent],
        help="Explain airport and multi-airport risk rules.",
    )
    airports_explain.add_argument("code", nargs="+")
    airports_explain.set_defaults(
        func=command_airports_explain,
        command_name="airports explain",
        **_catalog_read_defaults(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flights",
        description="Provider-policy flight routing helper for Hermes live flight-search workflows.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit stable JSON envelope."
    )
    parser.add_argument(
        "--catalog-refresh",
        choices=["auto", "always", "never"],
        default=os.getenv("FLIGHTS_CATALOG_REFRESH", "auto"),
        help="Static catalog refresh policy for catalog-dependent commands. Default: auto.",
    )
    parser.add_argument(
        "--catalog-max-age",
        default=os.getenv("FLIGHTS_CATALOG_MAX_AGE", "2w"),
        help="Refresh static catalog when older than this TTL, e.g. 12h, 7d, 2w. Default: 2w.",
    )
    parser.add_argument(
        "--catalog-refresh-timeout",
        type=int,
        default=int(os.getenv("FLIGHTS_CATALOG_REFRESH_TIMEOUT", "30")),
        help="HTTP timeout seconds per static catalog file during auto-refresh.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    json_parent = _json_parent()

    _register_primary_search_commands(sub, json_parent)
    _register_diagnose_commands(sub, json_parent)
    _register_maint_commands(sub, json_parent)
    _register_metadata_commands(sub, json_parent)

    return parser


def validate_cli_config(args: argparse.Namespace) -> None:
    if args.catalog_refresh not in {"auto", "always", "never"}:
        raise CliError(
            "catalog refresh policy must be one of auto, always, never",
            error_type="validation_error",
        )
    parse_ttl_seconds(args.catalog_max_age)


def auto_refresh_catalog(args: argparse.Namespace, store: Store) -> dict | None:
    # Catalog-dependent commands need a complete local static catalog before
    # routing commands. They refresh only when files are missing/stale unless the
    # caller disables this with `--catalog-refresh never`.
    if getattr(args, "catalog_access", None) != "auto_refresh":
        return None
    if args.catalog_refresh == "never":
        return {
            "enabled": False,
            "reason": "disabled",
            "evidence_scope": metadata_evidence_scope("catalog auto refresh"),
        }
    max_age = (
        0
        if args.catalog_refresh == "always"
        else parse_ttl_seconds(args.catalog_max_age)
    )
    result = refresh_static_catalog_if_needed(
        store.cache_dir,
        max_age_seconds=max_age
        if args.catalog_refresh != "always"
        else DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
        timeout=args.catalog_refresh_timeout,
        force=args.catalog_refresh == "always",
    )
    result["evidence_scope"] = metadata_evidence_scope("catalog auto refresh")
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    try:
        validate_cli_config(args)
        store = Store()
        catalog_auto_refresh = auto_refresh_catalog(args, store)
        data = args.func(args, store)
        if catalog_auto_refresh is not None and isinstance(data, dict):
            data["catalog_auto_refresh"] = catalog_auto_refresh
    except CliError as exc:
        if args.json:
            emit_json(error_envelope(exc))
        else:
            print(f"error: {exc.message}", file=sys.stderr)
            if exc.details is not None:
                print(
                    json.dumps(exc.details, ensure_ascii=False, indent=2),
                    file=sys.stderr,
                )
        return 1

    if args.json:
        emit_json(output_envelope(args.command_name, data))
    else:
        print(render_user_text(args.command_name, data))
    return 0
