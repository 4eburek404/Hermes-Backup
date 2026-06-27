from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__
from .apps.diagnose import command_diagnose_plan, command_diagnose_probe, command_diagnose_render
from .apps.search import command_search
from .commands.maint import command_maint_catalog_manifest, command_maint_catalog_refresh, command_maint_doctor
from .commands.maintenance import command_maintenance_check
from .commands.metadata import command_airports_explain, command_cities_search, metadata_evidence_scope
from .commands.providers import (
    command_fli_dates,
    command_fli_search,
    command_kb_roundtrip,
    command_kb_search,
)
from .commands.route import (
    command_route_assemble,
    command_route_rank,
    command_route_validate,
)
from .config import (
    DEFAULT_CURRENCY,
    DEFAULT_PROFILE,
    FLI_MCP_DEFAULT_URL,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR,
    RISK_PROFILES,
)
from .errors import CliError
from .output import emit_json, error_envelope, output_envelope, render_human
from .providers.static_catalog import (
    DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
    parse_ttl_seconds,
    refresh_static_catalog_if_needed,
)
from .store import Store


def add_connection_policy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    parser.add_argument("--profile", choices=sorted(RISK_PROFILES), default=DEFAULT_PROFILE, help="Risk/ranking profile.")
    parser.add_argument("--min-same-airport-min", type=int, default=120)
    parser.add_argument("--min-cross-airport-min", type=int, default=300)


def add_stop_policy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stop-policy",
        choices=["business-default", "strict-direct-one-stop", "allow-two-stop-tier", "debug-all"],
        default="business-default",
        help="Stop policy: prefer direct/one-stop; allow two-stop only as tier 2 by default; 3+ is suppressed in normal output.",
    )
    parser.add_argument("--max-connections", type=int, default=None, help="Preferred max connections per journey. Default 1.")
    parser.add_argument("--tier2-max-connections", type=int, default=None, help="Tier 2 max connections per journey. Default 2.")
    parser.add_argument("--include-stop-policy-diagnostics", action="store_true", help="Keep stop-policy diagnostics in agent_report.")


def add_carrier_selection_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only-carrier", action="append", help="Hard filter: every segment must use one of these carrier codes. Repeatable.")
    parser.add_argument("--exclude-carrier", action="append", help="Hard filter: reject candidates using this carrier code. Repeatable.")
    parser.add_argument("--prefer-carrier", action="append", help="Soft preference: demote candidates that do not use this carrier. Repeatable.")
    parser.add_argument("--avoid-carrier", action="append", help="Soft preference: penalize candidates using this carrier. Repeatable.")
    parser.add_argument("--include-filtered", type=int, default=20, help="Include first N carrier-filtered candidates in JSON output.")


def add_agent_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent-report",
        action="store_true",
        help="Include a compact agent_report block without changing other output limits.",
    )
    parser.add_argument(
        "--agent-brief",
        action="store_true",
        help="Emit only the compact agent_report in JSON output. Implies --agent-report.",
    )


def add_fli_mcp_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mcp-url", default=os.getenv("FLIGHTS_FLI_MCP_URL", FLI_MCP_DEFAULT_URL), help="FLI MCP HTTP URL. Default from FLIGHTS_FLI_MCP_URL or localhost.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds for FLI MCP calls.")


def add_provider_cache_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cache-ttl-seconds", type=int, default=DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, help="Short-lived live-search cache TTL seconds. Use 0 to disable.")
    parser.add_argument("--no-cache", action="store_true", help="Bypass live-search cache.")


def add_assembly_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit-per-pair", type=int, default=DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR)
    parser.add_argument("--candidate-pool-limit", type=int, default=5000, help="Maximum raw assembled candidates to score before ranked output is capped.")
    parser.add_argument("--max-candidates", type=int, default=50, help="Maximum ranked candidates to output after scoring.")
    parser.add_argument("--max-reasons", type=int, default=5)
    parser.add_argument("--include-candidates", type=int, default=5)
    parser.add_argument("--include-ranked-candidates", type=int, default=5, help="Include full candidate bodies for first N ranked candidates.")
    parser.add_argument("--include-rejected-pairs", type=int, default=20)


def _parent(add_flags) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    add_flags(parser)
    return parser


def connection_policy_parent() -> argparse.ArgumentParser:
    return _parent(add_connection_policy_flags)


def stop_policy_parent() -> argparse.ArgumentParser:
    return _parent(add_stop_policy_flags)


def carrier_selection_parent() -> argparse.ArgumentParser:
    return _parent(add_carrier_selection_flags)


def agent_output_parent() -> argparse.ArgumentParser:
    return _parent(add_agent_output_flags)


def assembly_output_parent() -> argparse.ArgumentParser:
    return _parent(add_assembly_output_flags)


def _catalog_read_defaults(**kwargs: Any) -> dict[str, Any]:
    return {"catalog_access": "auto_refresh", "requires_catalog": True, **kwargs}


def _register_primary_search_commands(sub) -> None:
    search = sub.add_parser("search", help="Primary request-file route search; JSON output keeps flight_search_result.v1 envelope.")
    search.add_argument("--request", required=True, help="flight_search_request.v1 JSON file, or - for stdin.")
    search.set_defaults(func=command_search, command_name="search", **_catalog_read_defaults())


def _register_diagnose_commands(sub) -> None:
    diagnose = sub.add_parser("diagnose", help="Diagnostics for plan/probe/render workflows.")
    diagnose_sub = diagnose.add_subparsers(dest="diagnose_command", required=True)
    plan = diagnose_sub.add_parser("plan", help="Render the route segment plan from a flight_search_request.v1 file without provider calls.")
    plan.add_argument("--request", required=True, help="flight_search_request.v1 JSON file, or - for stdin.")
    plan.set_defaults(func=command_diagnose_plan, command_name="diagnose plan", **_catalog_read_defaults())
    probe = diagnose_sub.add_parser("probe", help="Run a single provider probe from a probe JSON file.")
    probe.add_argument("--provider", required=True, choices=["kupibilet", "fli"])
    probe.add_argument("--request", required=True, help="Probe JSON file, or - for stdin.")
    probe.set_defaults(func=command_diagnose_probe, command_name="diagnose probe")
    render = diagnose_sub.add_parser("render", help="Render human-answer diagnostics from an agent_report JSON file.")
    render.add_argument("--input", required=True, help="agent_report JSON file, output envelope, or - for stdin.")
    render.set_defaults(func=command_diagnose_render, command_name="diagnose render")

    kb_search = diagnose_sub.add_parser("kb-search", help="Kupibilet live aggregate diagnostic; use --only-carrier SU for Aeroflot-marketed flights.")
    _add_kb_search_flags(kb_search)
    kb_search.set_defaults(func=command_kb_search, command_name="diagnose kb-search")

    kb_roundtrip = diagnose_sub.add_parser("kb-roundtrip", help="Kupibilet live round-trip aggregate diagnostic using a two-trip frontend_search request.")
    _add_kb_roundtrip_flags(kb_roundtrip)
    kb_roundtrip.set_defaults(func=command_kb_roundtrip, command_name="diagnose kb-roundtrip")

    fli_search = diagnose_sub.add_parser("fli-search", help="FLI MCP live Google Flights diagnostic through a self-hosted MCP HTTP server.")
    _add_fli_search_flags(fli_search)
    fli_search.set_defaults(func=command_fli_search, command_name="diagnose fli-search", **_catalog_read_defaults())

    fli_dates = diagnose_sub.add_parser("fli-dates", help="FLI MCP flexible-date diagnostic through a self-hosted MCP HTTP server.")
    _add_fli_dates_flags(fli_dates)
    fli_dates.set_defaults(func=command_fli_dates, command_name="diagnose fli-dates")


def _register_maint_commands(sub) -> None:
    maint = sub.add_parser("maint", help="Primary maintenance namespace.")
    maint_sub = maint.add_subparsers(dest="maint_command", required=True)
    check = maint_sub.add_parser(
        "check",
        help="Report source/runtime provenance and local maintenance status without network calls.",
    )
    check.add_argument(
        "--runtime-path",
        help="Runtime flight-search skill path to compare against. Defaults to ~/.hermes/skills/productivity/flight-search.",
    )
    check.set_defaults(func=command_maintenance_check, command_name="maint check")
    doctor = maint_sub.add_parser("doctor", help="Check local caches and static catalog status without provider calls.")
    doctor.set_defaults(func=command_maint_doctor, command_name="maint doctor")
    catalog = maint_sub.add_parser("catalog", help="Static catalog maintenance.")
    catalog_sub = catalog.add_subparsers(dest="maint_catalog_command", required=True)
    manifest = catalog_sub.add_parser("manifest", help="Show the local static catalog manifest.")
    manifest.set_defaults(func=command_maint_catalog_manifest, command_name="maint catalog manifest")
    refresh = catalog_sub.add_parser("refresh", help="Download public static catalog JSON files explicitly.")
    refresh.add_argument("--only", action="append", help="Catalog item name. Repeatable; defaults to all static files.")
    refresh.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds per static file.")
    refresh.add_argument("--dry-run", action="store_true", help="Show files that would be downloaded without writing cache.")
    refresh.set_defaults(func=command_maint_catalog_refresh, command_name="maint catalog refresh", catalog_access="refresh_explicit")

def _register_metadata_commands(sub) -> None:
    cities = sub.add_parser("cities", help="City lookup commands.")
    cities_sub = cities.add_subparsers(dest="cities_command", required=True)
    cities_search = cities_sub.add_parser("search", help="Search city name or IATA code in local cache.")
    cities_search.add_argument("query")
    cities_search.add_argument("--limit", type=int, default=5)
    cities_search.set_defaults(func=command_cities_search, command_name="cities search", **_catalog_read_defaults())

    airports = sub.add_parser("airports", help="Airport rule lookup commands.")
    airports_sub = airports.add_subparsers(dest="airports_command", required=True)
    airports_explain = airports_sub.add_parser("explain", help="Explain airport and multi-airport risk rules.")
    airports_explain.add_argument("code", nargs="+")
    airports_explain.set_defaults(func=command_airports_explain, command_name="airports explain", **_catalog_read_defaults())


def _add_kb_search_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    parser.add_argument("destination", help="Destination city/airport IATA code (e.g. MOW or SVO).")
    parser.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD.")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency code (default: RUB).")
    parser.add_argument("--only-carrier", action="append", help="Require each flight leg to match this marketing or operating carrier. Repeatable.")
    parser.add_argument("--direct-only", action="store_true", help="Only direct one-leg offers.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum normalized offers to show.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    add_provider_cache_flags(parser)


def _add_kb_roundtrip_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    parser.add_argument("destination", help="Destination city/airport IATA code (e.g. BJS or PKX).")
    parser.add_argument("--depart-date", required=True, help="Outbound date YYYY-MM-DD.")
    parser.add_argument("--return-date", required=True, help="Return date YYYY-MM-DD.")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency code (default: RUB).")
    parser.add_argument("--only-carrier", action="append", help="Require every outbound/return flight leg to match this marketing or operating carrier. Repeatable.")
    parser.add_argument("--direct-only", action="store_true", help="Only direct one-leg outbound and direct one-leg return offers.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum normalized round-trip fare packages to show.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    add_provider_cache_flags(parser)


def _add_fli_search_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("origin", help="Origin airport IATA code (e.g. IST).")
    parser.add_argument("destination", help="Destination airport IATA code (e.g. LHR).")
    parser.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD.")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY, help="Fallback currency code when FLI omits one (default: RUB).")
    parser.add_argument("--only-carrier", action="append", help="Filter by airline IATA code. Repeatable.")
    parser.add_argument("--direct-only", action="store_true", help="Request non-stop results only.")
    parser.add_argument("--max-stops", choices=["ANY", "NON_STOP", "ONE_STOP", "TWO_PLUS_STOPS"], default="ANY")
    parser.add_argument("--cabin-class", choices=["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], default="ECONOMY")
    parser.add_argument("--sort-by", choices=["TOP_FLIGHTS", "BEST", "CHEAPEST", "DEPARTURE_TIME", "ARRIVAL_TIME", "DURATION", "EMISSIONS"], default="CHEAPEST")
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=20, help="Maximum normalized offers to show.")
    add_fli_mcp_flags(parser)
    add_provider_cache_flags(parser)


def _add_fli_dates_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("origin", help="Origin airport IATA code (e.g. IST).")
    parser.add_argument("destination", help="Destination airport IATA code (e.g. LHR).")
    parser.add_argument("--from-date", required=True, help="Start date YYYY-MM-DD.")
    parser.add_argument("--to-date", required=True, help="End date YYYY-MM-DD.")
    parser.add_argument("--trip-duration", type=int, default=3, help="Trip duration in days for round-trip date search.")
    parser.add_argument("--round-trip", action="store_true", help="Search round-trip date prices.")
    parser.add_argument("--only-carrier", action="append", help="Filter by airline IATA code. Repeatable.")
    parser.add_argument("--direct-only", action="store_true", help="Request non-stop results only.")
    parser.add_argument("--max-stops", choices=["ANY", "NON_STOP", "ONE_STOP", "TWO_PLUS_STOPS"], default="ANY")
    parser.add_argument("--cabin-class", choices=["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], default="ECONOMY")
    parser.add_argument("--sort-by-price", action="store_true", help="Sort dates by lowest price.")
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=30)
    add_fli_mcp_flags(parser)


def _register_route_commands(sub) -> None:
    route = sub.add_parser("route", help="Route planning and validation commands.")
    route_sub = route.add_subparsers(dest="route_command", required=True)

    route_validate = route_sub.add_parser("validate", parents=[connection_policy_parent()], help="Validate airport compatibility and connection windows from JSON.")
    route_validate.add_argument("--input", default="-", help="Input JSON file, or - for stdin.")
    route_validate.set_defaults(func=command_route_validate, command_name="route validate")

    route_rank = route_sub.add_parser(
        "rank",
        parents=[connection_policy_parent(), carrier_selection_parent(), stop_policy_parent()],
        help="Score and rank itinerary candidates from JSON.",
    )
    route_rank.add_argument("--input", default="-", help="Input JSON list, or object with itineraries/candidates.")
    route_rank.add_argument("--max-reasons", type=int, default=5)
    route_rank.set_defaults(func=command_route_rank, command_name="route rank")

    route_assemble = route_sub.add_parser(
        "assemble",
        parents=[connection_policy_parent(), assembly_output_parent(), stop_policy_parent(), agent_output_parent(), carrier_selection_parent()],
        help="Assemble parsed segment results into ranked itinerary candidates.",
    )
    route_assemble.add_argument("--input", action="append", help="Parsed result JSON. Repeatable; omit for stdin.")
    route_assemble.set_defaults(func=command_route_assemble, command_name="route assemble")

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flights",
        description="Provider-policy flight routing helper for Hermes live flight-search workflows.",
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON envelope.")
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    _register_primary_search_commands(sub)
    _register_diagnose_commands(sub)
    _register_maint_commands(sub)
    _register_metadata_commands(sub)
    _register_route_commands(sub)

    return parser


def normalize_global_json(argv: list[str]) -> list[str]:
    if "--json" not in argv[1:]:
        return argv
    return [argv[0], "--json"] + [item for item in argv[1:] if item != "--json"]


def validate_cli_config(args: argparse.Namespace) -> None:
    if args.catalog_refresh not in {"auto", "always", "never"}:
        raise CliError("catalog refresh policy must be one of auto, always, never", error_type="validation_error")
    parse_ttl_seconds(args.catalog_max_age)


def auto_refresh_catalog(args: argparse.Namespace, store: Store) -> dict | None:
    # Catalog-dependent commands need a complete local static catalog before
    # routing commands. They refresh only when files are missing/stale unless the
    # caller disables this with `--catalog-refresh never`.
    if getattr(args, "catalog_access", None) != "auto_refresh":
        return None
    if args.catalog_refresh == "never":
        return {"enabled": False, "reason": "disabled", "evidence_scope": metadata_evidence_scope("catalog auto refresh")}
    max_age = 0 if args.catalog_refresh == "always" else parse_ttl_seconds(args.catalog_max_age)
    result = refresh_static_catalog_if_needed(
        store.cache_dir,
        max_age_seconds=max_age if args.catalog_refresh != "always" else DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
        timeout=args.catalog_refresh_timeout,
        force=args.catalog_refresh == "always",
    )
    result["evidence_scope"] = metadata_evidence_scope("catalog auto refresh")
    return result


def apply_agent_output_defaults(args: argparse.Namespace) -> None:
    if bool(getattr(args, "agent_brief", False)):
        args.agent_report = True


def apply_agent_brief_output(args: argparse.Namespace, data: object) -> object:
    if not bool(getattr(args, "agent_brief", False)):
        return data
    if isinstance(data, dict) and isinstance(data.get("agent_report"), dict):
        return {"agent_report": data["agent_report"]}
    return data


def main(argv: list[str] | None = None) -> int:
    argv = normalize_global_json(list(sys.argv if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    try:
        validate_cli_config(args)
        apply_agent_output_defaults(args)
        store = Store()
        catalog_auto_refresh = auto_refresh_catalog(args, store)
        data = args.func(args, store)
        if catalog_auto_refresh is not None and isinstance(data, dict):
            data["catalog_auto_refresh"] = catalog_auto_refresh
        data = apply_agent_brief_output(args, data)
    except CliError as exc:
        if args.json:
            emit_json(error_envelope(exc))
        else:
            print(f"error: {exc.message}", file=sys.stderr)
            if exc.details is not None:
                print(json.dumps(exc.details, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if args.json:
        emit_json(output_envelope(args.command_name, data))
    else:
        print(render_human(args.command_name, data))
    return 0
