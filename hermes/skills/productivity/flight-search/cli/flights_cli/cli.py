from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .commands.basic import (
    command_airports_explain,
    command_catalog_manifest,
    command_catalog_update,
    command_cities_search,
    command_doctor,
)
from .commands.metrics import command_metrics_workflow
from .commands.providers import (
    command_fli_dates,
    command_fli_search,
    command_kb_roundtrip,
    command_kb_search,
)
from .commands.route import command_route_assemble, command_route_kb_assemble, command_route_live_assemble, command_route_plan, command_route_rank, command_route_validate
from .config import (
    DEFAULT_COVERAGE_CONTROL_LIMIT,
    DEFAULT_CURRENCY,
    DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS,
    FLI_MCP_DEFAULT_URL,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR,
    DEFAULT_ROUTING_STRATEGY,
    RISK_PROFILES,
)
from .env import load_env_file
from .errors import CliError
from .output import emit_json, error_envelope, output_envelope, render_human
from .providers.static_catalog import (
    DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
    parse_ttl_seconds,
    refresh_static_catalog_if_needed,
)
from .store import Store

def add_common_route_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("origin", help="Origin city/airport, e.g. SVX or Ekaterinburg")
    parser.add_argument("destination", help="Destination city/airport, e.g. LON or London")
    parser.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD")
    parser.add_argument("--return-date", help="Return date YYYY-MM-DD")
    parser.add_argument("--hub", action="append", help="Hub airport. Repeatable. In auto strategy, passing --hub uses hub-list routing.")
    parser.add_argument(
        "--routing-strategy",
        choices=["auto", "hub-list", "ru-priority", "domestic-ru"],
        default=DEFAULT_ROUTING_STRATEGY,
        help="Routing strategy. auto selects domestic-ru for RU domestic routes, ru-priority for international default, or hub-list when --hub is passed.",
    )
    parser.add_argument("--origin-airport", action="append", help="Force origin airport. Repeatable.")
    parser.add_argument("--destination-airport", action="append", help="Force destination airport. Repeatable.")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency. Default RUB.")
    parser.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    parser.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced", help="Risk/ranking profile.")
    parser.add_argument("--min-same-airport-min", type=int, default=120)
    parser.add_argument("--min-cross-airport-min", type=int, default=300)
    parser.add_argument("--max-airports-per-city", type=int, default=6)
    parser.add_argument(
        "--coverage-mode",
        choices=["standard", "targeted", "full"],
        default="targeted",
        help="Coverage-control scope metadata. targeted adds exact-airport direct and aggregate/carrier controls without unbounded live fan-out.",
    )
    parser.add_argument(
        "--coverage-control",
        action="append",
        help="Repeatable targeted coverage control hint, e.g. carrier_aggregate:SU or exact_airport_direct. Exposed in diagnostics; no unbounded live fan-out.",
    )
    parser.add_argument(
        "--coverage-control-limit",
        type=int,
        default=DEFAULT_COVERAGE_CONTROL_LIMIT,
        help="Maximum planned coverage controls to surface in route metadata. Default 12; this is a fan-out guardrail, not a cache/rate-limit implementation.",
    )
    add_stop_policy_flags(parser)


def add_stop_policy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stop-policy",
        choices=["business-default", "strict-direct-one-stop", "allow-two-stop-fallback", "debug-all"],
        default="business-default",
        help="Stop policy: prefer direct/one-stop; allow two-stop only as fallback by default; 3+ is suppressed in normal output.",
    )
    parser.add_argument("--max-connections", type=int, default=None, help="Preferred max connections per journey. Default 1.")
    parser.add_argument("--fallback-max-connections", type=int, default=None, help="Fallback max connections per journey. Default 2.")
    parser.add_argument("--include-stop-policy-diagnostics", action="store_true", help="Keep stop-policy diagnostics in agent_report.")


def add_carrier_selection_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only-carrier", action="append", help="Hard filter: every segment must use one of these carrier codes. Repeatable.")
    parser.add_argument("--exclude-carrier", action="append", help="Hard filter: reject candidates using this carrier code. Repeatable.")
    parser.add_argument("--prefer-carrier", action="append", help="Soft preference: demote candidates that do not use this carrier. Repeatable.")
    parser.add_argument("--avoid-carrier", action="append", help="Soft preference: penalize candidates using this carrier. Repeatable.")
    parser.add_argument("--include-filtered", type=int, default=20, help="Include first N carrier-filtered candidates in JSON output.")


def add_agent_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent-mode",
        action="store_true",
        help="Lite-agent preset: compact output, top-ranked candidate details, and an agent_report block.",
    )
    parser.add_argument(
        "--agent-report",
        action="store_true",
        help="Include a compact agent_report block without changing other output limits.",
    )
    parser.add_argument(
        "--agent-brief",
        action="store_true",
        help="Emit only the compact agent_report in JSON output. Implies --agent-mode defaults.",
    )


def add_fli_mcp_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mcp-url", default=os.getenv("FLIGHTS_FLI_MCP_URL", FLI_MCP_DEFAULT_URL), help="FLI MCP HTTP URL. Default from FLIGHTS_FLI_MCP_URL or localhost.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds for FLI MCP calls.")


def add_live_assembly_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--segment-limit", type=int, default=30, help="Max direct offers kept per live segment search.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds per live segment search.")
    parser.add_argument(
        "--outbound-second-leg-day-offset",
        action="append",
        type=int,
        help="Day offset(s) for hub→destination searches after depart date. Repeatable. Default: 0 and 1.",
    )
    parser.add_argument(
        "--return-second-leg-day-offset",
        action="append",
        type=int,
        help="Day offset(s) for hub→origin searches after return date. Repeatable. Default: 0, 1, and 2.",
    )
    parser.add_argument("--limit-per-pair", type=int, default=DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR)
    parser.add_argument("--candidate-pool-limit", type=int, default=5000, help="Maximum raw assembled candidates to score before ranked output is capped.")
    parser.add_argument("--max-candidates", type=int, default=50, help="Maximum ranked candidates to output after scoring.")
    parser.add_argument("--max-reasons", type=int, default=5)
    parser.add_argument("--include-candidates", type=int, default=5)
    parser.add_argument("--include-ranked-candidates", type=int, default=5, help="Include full candidate bodies for first N ranked candidates.")
    parser.add_argument("--include-rejected-pairs", type=int, default=20)
    parser.add_argument("--include-segment-results", type=int, default=0, help="Include first N normalized segment-result blocks in JSON output.")
    parser.add_argument(
        "--aggregate-control-limit",
        type=int,
        default=0,
        help="Run non-direct Kupibilet full-route aggregate controls and keep N cheap offers after provider-offer filtering. 0 disables; --agent-mode sets 10.",
    )
    parser.add_argument(
        "--aggregate-control-carrier",
        action="append",
        help="Also run a full-route aggregate control where every leg matches this carrier, e.g. SU for Aeroflot. Repeatable.",
    )
    parser.add_argument("--max-segment-searches", type=int, default=300, help="Safety cap for live segment requests.")
    parser.add_argument("--fail-fast", action="store_true", help="Abort on the first live segment-search error instead of keeping partial results.")
    parser.add_argument("--live-cache-ttl-seconds", type=int, default=DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, help="Short-lived live-search cache TTL seconds. Use 0 to disable.")
    parser.add_argument("--no-live-cache", action="store_true", help="Bypass live-search cache.")
    parser.add_argument("--direct-route-index-ttl-seconds", type=int, default=DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS, help="Official SVX seasonal direct-route index TTL seconds. Use 0 to disable route-intel fetching.")
    parser.add_argument("--no-direct-route-intel", action="store_true", help="Do not skip direct-control probes using the official SVX route index.")
    add_agent_output_flags(parser)
    add_carrier_selection_flags(parser)


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
        default=os.getenv("FLIGHTS_CATALOG_MAX_AGE", "7d"),
        help="Refresh static catalog when older than this TTL, e.g. 12h, 7d, 2w. Default: 7d.",
    )
    parser.add_argument(
        "--catalog-refresh-timeout",
        type=int,
        default=int(os.getenv("FLIGHTS_CATALOG_REFRESH_TIMEOUT", "30")),
        help="HTTP timeout seconds per static catalog file during auto-refresh.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local caches, plugin path, and auth presence.")
    doctor.set_defaults(func=command_doctor, command_name="doctor")

    catalog = sub.add_parser("catalog", help="Travelpayouts static catalog commands.")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_update = catalog_sub.add_parser("update", help="Download no-token Travelpayouts static catalog JSON files.")
    catalog_update.add_argument("--only", action="append", help="Catalog item name. Repeatable; defaults to all static files.")
    catalog_update.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds per static file.")
    catalog_update.add_argument("--dry-run", action="store_true", help="Show files that would be downloaded without writing cache.")
    catalog_update.set_defaults(func=command_catalog_update, command_name="catalog update")
    catalog_manifest = catalog_sub.add_parser("manifest", help="Show the local static catalog manifest.")
    catalog_manifest.set_defaults(func=command_catalog_manifest, command_name="catalog manifest")

    cities = sub.add_parser("cities", help="City lookup commands.")
    cities_sub = cities.add_subparsers(dest="cities_command", required=True)
    cities_search = cities_sub.add_parser("search", help="Search city name or IATA code in local cache.")
    cities_search.add_argument("query")
    cities_search.add_argument("--limit", type=int, default=5)
    cities_search.set_defaults(func=command_cities_search, command_name="cities search", requires_catalog=True)

    airports = sub.add_parser("airports", help="Airport rule lookup commands.")
    airports_sub = airports.add_subparsers(dest="airports_command", required=True)
    airports_explain = airports_sub.add_parser("explain", help="Explain airport and multi-airport risk rules.")
    airports_explain.add_argument("code", nargs="+")
    airports_explain.set_defaults(func=command_airports_explain, command_name="airports explain", requires_catalog=True)

    kb_search = sub.add_parser("kb-search", help="Kupibilet live aggregate search; use --only-carrier SU for Aeroflot-marketed flights.")
    kb_search.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    kb_search.add_argument("destination", help="Destination city/airport IATA code (e.g. MOW or SVO).")
    kb_search.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD.")
    kb_search.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency code (default: RUB).")
    kb_search.add_argument("--only-carrier", action="append", help="Require each flight leg to match this marketing or operating carrier. Repeatable.")
    kb_search.add_argument("--direct-only", action="store_true", help="Only direct one-leg offers.")
    kb_search.add_argument("--limit", type=int, default=20, help="Maximum normalized offers to show.")
    kb_search.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    kb_search.add_argument("--cache-ttl-seconds", type=int, default=DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, help="Short-lived live-search cache TTL seconds. Use 0 to disable.")
    kb_search.add_argument("--no-cache", action="store_true", help="Bypass live-search cache.")
    kb_search.set_defaults(func=command_kb_search, command_name="kb-search")

    kb_roundtrip = sub.add_parser("kb-roundtrip", help="Kupibilet live round-trip aggregate search using a two-trip frontend_search request.")
    kb_roundtrip.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    kb_roundtrip.add_argument("destination", help="Destination city/airport IATA code (e.g. BJS or PKX).")
    kb_roundtrip.add_argument("--depart-date", required=True, help="Outbound date YYYY-MM-DD.")
    kb_roundtrip.add_argument("--return-date", required=True, help="Return date YYYY-MM-DD.")
    kb_roundtrip.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency code (default: RUB).")
    kb_roundtrip.add_argument("--only-carrier", action="append", help="Require every outbound/return flight leg to match this marketing or operating carrier. Repeatable.")
    kb_roundtrip.add_argument("--direct-only", action="store_true", help="Only direct one-leg outbound and direct one-leg return offers.")
    kb_roundtrip.add_argument("--limit", type=int, default=20, help="Maximum normalized round-trip fare packages to show.")
    kb_roundtrip.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    kb_roundtrip.add_argument("--cache-ttl-seconds", type=int, default=DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, help="Short-lived live-search cache TTL seconds. Use 0 to disable.")
    kb_roundtrip.add_argument("--no-cache", action="store_true", help="Bypass live-search cache.")
    kb_roundtrip.set_defaults(func=command_kb_roundtrip, command_name="kb-roundtrip")

    fli_search = sub.add_parser("fli-search", help="FLI MCP live Google Flights search through a self-hosted MCP HTTP server.")
    fli_search.add_argument("origin", help="Origin airport IATA code (e.g. IST).")
    fli_search.add_argument("destination", help="Destination airport IATA code (e.g. LHR).")
    fli_search.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD.")
    fli_search.add_argument("--currency", default=DEFAULT_CURRENCY, help="Fallback currency code when FLI omits one (default: RUB).")
    fli_search.add_argument("--only-carrier", action="append", help="Filter by airline IATA code. Repeatable.")
    fli_search.add_argument("--direct-only", action="store_true", help="Request non-stop results only.")
    fli_search.add_argument("--max-stops", choices=["ANY", "NON_STOP", "ONE_STOP", "TWO_PLUS_STOPS"], default="ANY")
    fli_search.add_argument("--cabin-class", choices=["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], default="ECONOMY")
    fli_search.add_argument("--sort-by", choices=["TOP_FLIGHTS", "BEST", "CHEAPEST", "DEPARTURE_TIME", "ARRIVAL_TIME", "DURATION", "EMISSIONS"], default="CHEAPEST")
    fli_search.add_argument("--passengers", type=int, default=1)
    fli_search.add_argument("--limit", type=int, default=20, help="Maximum normalized offers to show.")
    add_fli_mcp_flags(fli_search)
    fli_search.add_argument("--cache-ttl-seconds", type=int, default=DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, help="Short-lived live-search cache TTL seconds. Use 0 to disable.")
    fli_search.add_argument("--no-cache", action="store_true", help="Bypass live-search cache.")
    fli_search.set_defaults(func=command_fli_search, command_name="fli-search", requires_catalog=True)

    fli_dates = sub.add_parser("fli-dates", help="FLI MCP flexible date search through a self-hosted MCP HTTP server.")
    fli_dates.add_argument("origin", help="Origin airport IATA code (e.g. IST).")
    fli_dates.add_argument("destination", help="Destination airport IATA code (e.g. LHR).")
    fli_dates.add_argument("--from-date", required=True, help="Start date YYYY-MM-DD.")
    fli_dates.add_argument("--to-date", required=True, help="End date YYYY-MM-DD.")
    fli_dates.add_argument("--trip-duration", type=int, default=3, help="Trip duration in days for round-trip date search.")
    fli_dates.add_argument("--round-trip", action="store_true", help="Search round-trip date prices.")
    fli_dates.add_argument("--only-carrier", action="append", help="Filter by airline IATA code. Repeatable.")
    fli_dates.add_argument("--direct-only", action="store_true", help="Request non-stop results only.")
    fli_dates.add_argument("--max-stops", choices=["ANY", "NON_STOP", "ONE_STOP", "TWO_PLUS_STOPS"], default="ANY")
    fli_dates.add_argument("--cabin-class", choices=["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], default="ECONOMY")
    fli_dates.add_argument("--sort-by-price", action="store_true", help="Sort dates by lowest price.")
    fli_dates.add_argument("--passengers", type=int, default=1)
    fli_dates.add_argument("--limit", type=int, default=30)
    add_fli_mcp_flags(fli_dates)
    fli_dates.set_defaults(func=command_fli_dates, command_name="fli-dates")

    route = sub.add_parser("route", help="Route planning and validation commands.")
    route_sub = route.add_subparsers(dest="route_command", required=True)
    route_plan = route_sub.add_parser("plan", help="Build segment query plan through hubs without API calls.")
    add_common_route_flags(route_plan)
    route_plan.set_defaults(func=command_route_plan, command_name="route plan", requires_catalog=True)

    route_validate = route_sub.add_parser("validate", help="Validate airport compatibility and connection windows from JSON.")
    route_validate.add_argument("--input", default="-", help="Input JSON file, or - for stdin.")
    route_validate.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    route_validate.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced")
    route_validate.add_argument("--min-same-airport-min", type=int, default=120)
    route_validate.add_argument("--min-cross-airport-min", type=int, default=300)
    route_validate.set_defaults(func=command_route_validate, command_name="route validate")

    route_rank = route_sub.add_parser("rank", help="Score and rank itinerary candidates from JSON.")
    route_rank.add_argument("--input", default="-", help="Input JSON list, or object with itineraries/candidates.")
    route_rank.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    route_rank.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced")
    route_rank.add_argument("--min-same-airport-min", type=int, default=120)
    route_rank.add_argument("--min-cross-airport-min", type=int, default=300)
    route_rank.add_argument("--max-reasons", type=int, default=5)
    add_carrier_selection_flags(route_rank)
    add_stop_policy_flags(route_rank)
    route_rank.set_defaults(func=command_route_rank, command_name="route rank")

    route_assemble = route_sub.add_parser("assemble", help="Assemble parsed segment results into ranked itinerary candidates.")
    route_assemble.add_argument("--input", action="append", help="Parsed result JSON. Repeatable; omit for stdin.")
    route_assemble.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    route_assemble.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced")
    route_assemble.add_argument("--min-same-airport-min", type=int, default=120)
    route_assemble.add_argument("--min-cross-airport-min", type=int, default=300)
    route_assemble.add_argument(
        "--limit-per-pair",
        type=int,
        default=DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR,
        help=(
            "Depth per segment-result list before pairing (default: 10). "
            "Keep >=10 for complex routes so frontier-relevant options (schedule, duration, "
            "connection safety, airport/carrier preference) are not truncated before ranking."
        ),
    )
    route_assemble.add_argument("--candidate-pool-limit", type=int, default=5000, help="Maximum raw assembled candidates to score before ranked output is capped.")
    route_assemble.add_argument("--max-candidates", type=int, default=50, help="Maximum ranked candidates to output after scoring.")
    route_assemble.add_argument("--max-reasons", type=int, default=5)
    route_assemble.add_argument("--include-candidates", type=int, default=5, help="Include first N raw assembled candidates in JSON output.")
    route_assemble.add_argument("--include-ranked-candidates", type=int, default=5, help="Include full candidate bodies for first N ranked candidates.")
    route_assemble.add_argument("--include-rejected-pairs", type=int, default=20, help="Include first N rejected/airport-mismatch pairs.")
    add_stop_policy_flags(route_assemble)
    add_agent_output_flags(route_assemble)
    add_carrier_selection_flags(route_assemble)
    route_assemble.set_defaults(func=command_route_assemble, command_name="route assemble")

    route_kb_assemble = route_sub.add_parser(
        "kb-assemble",
        help="Run Kupibilet direct-only segment searches through hubs and assemble ranked candidates.",
    )
    add_common_route_flags(route_kb_assemble)
    add_live_assembly_flags(route_kb_assemble)
    route_kb_assemble.set_defaults(provider_policy="kupibilet", fli_mcp_url=None)
    route_kb_assemble.set_defaults(func=command_route_kb_assemble, command_name="route kb-assemble", requires_catalog=True)

    route_live_assemble = route_sub.add_parser(
        "live-assemble",
        help="Run provider-policy live segment searches: Kupibilet for Russia-touching legs, FLI MCP for global legs.",
    )
    add_common_route_flags(route_live_assemble)
    add_live_assembly_flags(route_live_assemble)
    route_live_assemble.add_argument(
        "--provider-policy",
        choices=["auto", "kupibilet", "fli", "both"],
        default="auto",
        help="Live provider policy. auto uses Kupibilet for RU-touching segments and FLI MCP for non-RU segments.",
    )
    route_live_assemble.add_argument("--fli-mcp-url", default=os.getenv("FLIGHTS_FLI_MCP_URL", FLI_MCP_DEFAULT_URL), help="FLI MCP HTTP URL for provider-policy fli/both/auto.")
    route_live_assemble.set_defaults(func=command_route_live_assemble, command_name="route live-assemble", requires_catalog=True)

    metrics = sub.add_parser("metrics", help="Workflow metrics commands.")
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_workflow = metrics_sub.add_parser("workflow", help="Compare manual planning operations with CLI planning.")
    add_common_route_flags(metrics_workflow)
    metrics_workflow.set_defaults(func=command_metrics_workflow, command_name="metrics workflow", requires_catalog=True)

    return parser


def normalize_global_json(argv: list[str]) -> list[str]:
    if "--json" not in argv[1:]:
        return argv
    return [argv[0], "--json"] + [item for item in argv[1:] if item != "--json"]


def auto_refresh_catalog(args: argparse.Namespace, store: Store) -> dict | None:
    if not getattr(args, "requires_catalog", False):
        return None
    if args.catalog_refresh not in {"auto", "always", "never"}:
        raise CliError("catalog refresh policy must be one of auto, always, never", error_type="validation_error")
    if args.catalog_refresh == "never":
        return {"enabled": False, "reason": "disabled"}
    max_age = 0 if args.catalog_refresh == "always" else parse_ttl_seconds(args.catalog_max_age)
    return refresh_static_catalog_if_needed(
        store.cache_dir,
        max_age_seconds=max_age if args.catalog_refresh != "always" else DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
        timeout=args.catalog_refresh_timeout,
        force=args.catalog_refresh == "always",
    )


def apply_agent_mode_defaults(args: argparse.Namespace) -> None:
    if bool(getattr(args, "agent_brief", False)):
        args.agent_mode = True
    if not bool(getattr(args, "agent_mode", False)):
        return
    args.agent_report = True
    if hasattr(args, "include_candidates"):
        args.include_candidates = 0
    if hasattr(args, "include_ranked_candidates"):
        args.include_ranked_candidates = max(5, int(args.include_ranked_candidates))
    if hasattr(args, "include_rejected_pairs"):
        args.include_rejected_pairs = min(5, int(args.include_rejected_pairs))
    if hasattr(args, "include_segment_results"):
        args.include_segment_results = 0
    if hasattr(args, "max_candidates"):
        args.max_candidates = min(10, int(args.max_candidates))
    if hasattr(args, "aggregate_control_limit") and int(args.aggregate_control_limit) <= 0:
        args.aggregate_control_limit = 10


def apply_agent_brief_output(args: argparse.Namespace, data: object) -> object:
    if not bool(getattr(args, "agent_brief", False)):
        return data
    if isinstance(data, dict) and isinstance(data.get("agent_report"), dict):
        return {"agent_report": data["agent_report"]}
    return data


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    argv = normalize_global_json(list(sys.argv if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    apply_agent_mode_defaults(args)
    store = Store()
    try:
        catalog_auto_refresh = auto_refresh_catalog(args, store)
        data = args.func(args, store)
        if catalog_auto_refresh is not None and isinstance(data, dict):
            data["catalog_auto_refresh"] = catalog_auto_refresh
        data = apply_agent_brief_output(args, data)
    except CliError as exc:
        if args.json:
            print(json.dumps(error_envelope(exc), ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
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
