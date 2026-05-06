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
    command_kb_search,
    command_request_grouped_prices,
    command_request_prices_for_dates,
    command_request_search,
    command_results_parse,
    command_u6_prices,
)
from .commands.route import command_route_assemble, command_route_kb_assemble, command_route_plan, command_route_rank, command_route_validate
from .config import (
    DEFAULT_CURRENCY,
    DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS,
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
        choices=["auto", "hub-list", "ru-priority"],
        default=DEFAULT_ROUTING_STRATEGY,
        help="Routing strategy. auto uses ru-priority unless --hub is passed; hub-list uses explicit/default hubs.",
    )
    parser.add_argument("--origin-airport", action="append", help="Force origin airport. Repeatable.")
    parser.add_argument("--destination-airport", action="append", help="Force destination airport. Repeatable.")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency. Default RUB.")
    parser.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    parser.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced", help="Risk/ranking profile.")
    parser.add_argument("--min-same-airport-min", type=int, default=120)
    parser.add_argument("--min-cross-airport-min", type=int, default=300)
    parser.add_argument("--max-airports-per-city", type=int, default=6)


def add_carrier_selection_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only-carrier", action="append", help="Hard filter: every segment must use one of these carrier codes. Repeatable.")
    parser.add_argument("--exclude-carrier", action="append", help="Hard filter: reject candidates using this carrier code. Repeatable.")
    parser.add_argument("--prefer-carrier", action="append", help="Soft preference: demote candidates that do not use this carrier. Repeatable.")
    parser.add_argument("--avoid-carrier", action="append", help="Soft preference: penalize candidates using this carrier. Repeatable.")
    parser.add_argument("--include-filtered", type=int, default=20, help="Include first N carrier-filtered candidates in JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flights",
        description="Offline-first flight routing helper for Hermes/Travelpayouts workflows.",
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

    u6_prices = sub.add_parser("u6-prices", help="Ural Airlines (U6) price calendar — daily min fares, price discovery, no auth required.")
    u6_prices.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    u6_prices.add_argument("destination", help="Destination IATA code (e.g. IST).")
    u6_prices.add_argument("--from-date", required=True, help="Start date YYYY-MM-DD (calendar covers ~3 months from this date).")
    u6_prices.add_argument("--lang", default="ru", help="Language code (default: ru).")
    u6_prices.add_argument("--date", dest="selected_date", help="Filter to a specific date YYYY-MM-DD.")
    u6_prices.add_argument("--sort", choices=["price", "date"], default="price", help="Sort results by price or date (default: price).")
    u6_prices.add_argument("--limit", type=int, default=20, help="Max results to show (default: 20).")
    u6_prices.add_argument("--min-price", type=int, help="Minimum price filter (RUB).")
    u6_prices.add_argument("--max-price", type=int, help="Maximum price filter (RUB).")
    u6_prices.set_defaults(func=command_u6_prices, command_name="u6-prices")

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

    route = sub.add_parser("route", help="Route planning and validation commands.")
    route_sub = route.add_subparsers(dest="route_command", required=True)
    route_plan = route_sub.add_parser("plan", help="Build segment query plan through hubs without API calls.")
    add_common_route_flags(route_plan)
    route_plan.add_argument("--direct-only", action="store_true")
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
    add_carrier_selection_flags(route_assemble)
    route_assemble.set_defaults(func=command_route_assemble, command_name="route assemble")

    route_kb_assemble = route_sub.add_parser(
        "kb-assemble",
        help="Run Kupibilet direct-only segment searches through hubs and assemble ranked candidates.",
    )
    add_common_route_flags(route_kb_assemble)
    route_kb_assemble.add_argument("--segment-limit", type=int, default=30, help="Max direct offers kept per live segment search.")
    route_kb_assemble.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds per Kupibilet segment search.")
    route_kb_assemble.add_argument(
        "--outbound-second-leg-day-offset",
        action="append",
        type=int,
        help="Day offset(s) for hub→destination searches after depart date. Repeatable. Default: 0 and 1.",
    )
    route_kb_assemble.add_argument(
        "--return-second-leg-day-offset",
        action="append",
        type=int,
        help="Day offset(s) for hub→origin searches after return date. Repeatable. Default: 0, 1, and 2.",
    )
    route_kb_assemble.add_argument("--limit-per-pair", type=int, default=DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR)
    route_kb_assemble.add_argument("--candidate-pool-limit", type=int, default=5000, help="Maximum raw assembled candidates to score before ranked output is capped.")
    route_kb_assemble.add_argument("--max-candidates", type=int, default=50, help="Maximum ranked candidates to output after scoring.")
    route_kb_assemble.add_argument("--max-reasons", type=int, default=5)
    route_kb_assemble.add_argument("--include-candidates", type=int, default=5)
    route_kb_assemble.add_argument("--include-ranked-candidates", type=int, default=5, help="Include full candidate bodies for first N ranked candidates.")
    route_kb_assemble.add_argument("--include-rejected-pairs", type=int, default=20)
    route_kb_assemble.add_argument("--include-segment-results", type=int, default=0, help="Include first N normalized segment-result blocks in JSON output.")
    route_kb_assemble.add_argument("--max-segment-searches", type=int, default=300, help="Safety cap for live segment requests.")
    route_kb_assemble.add_argument("--fail-fast", action="store_true", help="Abort on the first live segment-search error instead of keeping partial results.")
    route_kb_assemble.add_argument("--live-cache-ttl-seconds", type=int, default=DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, help="Short-lived Kupibilet segment cache TTL seconds. Use 0 to disable.")
    route_kb_assemble.add_argument("--no-live-cache", action="store_true", help="Bypass Kupibilet segment cache.")
    route_kb_assemble.add_argument("--direct-route-index-ttl-seconds", type=int, default=DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS, help="Official SVX seasonal direct-route index TTL seconds. Use 0 to disable route-intel fetching.")
    route_kb_assemble.add_argument("--no-direct-route-intel", action="store_true", help="Do not skip direct-control probes using the official SVX route index.")
    add_carrier_selection_flags(route_kb_assemble)
    route_kb_assemble.set_defaults(func=command_route_kb_assemble, command_name="route kb-assemble", requires_catalog=True)

    results = sub.add_parser("results", help="Parse provider results into normalized segment offers.")
    results_sub = results.add_subparsers(dest="results_command", required=True)
    results_parse = results_sub.add_parser("parse", help="Parse Travelpayouts GraphQL response or request-search cached fetch envelope.")
    results_parse.add_argument("--input", default="-", help="Raw response JSON or flights request-search envelope.")
    results_parse.add_argument("--direction", choices=["outbound", "return"], default="outbound")
    results_parse.add_argument(
        "--leg",
        choices=["direct_outbound", "direct_return", "origin_to_hub", "hub_to_destination", "destination_to_hub", "hub_to_origin", "segment"],
        default="segment",
    )
    results_parse.add_argument("--origin", help="Query origin IATA override.")
    results_parse.add_argument("--destination", help="Query destination IATA override.")
    results_parse.add_argument("--date", help="Query date YYYY-MM-DD override.")
    results_parse.add_argument("--currency", help="Currency override.")
    results_parse.add_argument("--limit", type=int, default=20)
    results_parse.set_defaults(func=command_results_parse, command_name="results parse")

    request = sub.add_parser("request", help="Raw Travelpayouts request builder/read-only escape hatch.")
    request_sub = request.add_subparsers(dest="request_command", required=True)
    request_search = request_sub.add_parser("search", help="Build or run one Travelpayouts GraphQL search.")
    request_search.add_argument("origin")
    request_search.add_argument("destination")
    request_search.add_argument("--depart-date", required=True)
    request_search.add_argument("--return-date")
    request_search.add_argument("--currency", default=DEFAULT_CURRENCY)
    request_search.add_argument("--direct-only", action="store_true")
    request_search.add_argument("--dry-run", action="store_true", help="Default behavior; included for explicitness.")
    request_search.add_argument("--fetch", action="store_true", help="Fetch Travelpayouts cached Data API using TRAVELPAYOUTS_TOKEN.")
    request_search.add_argument("--timeout", type=int, default=20)
    request_search.set_defaults(func=command_request_search, command_name="request search")

    request_prices = request_sub.add_parser("prices-for-dates", help="Build or run a Travelpayouts REST v3 prices_for_dates cached-price probe.")
    request_prices.add_argument("origin")
    request_prices.add_argument("destination")
    request_prices.add_argument("--departure-at", required=True, help="Departure date or month: YYYY-MM or YYYY-MM-DD.")
    request_prices.add_argument("--return-at", help="Return date or month: YYYY-MM or YYYY-MM-DD.")
    request_prices.add_argument("--one-way", action="store_true", help="Force one-way search; default when --return-at is omitted.")
    request_prices.add_argument("--direct", action="store_true", help="Only direct cached prices.")
    request_prices.add_argument("--market", default="ru")
    request_prices.add_argument("--currency", default=DEFAULT_CURRENCY)
    request_prices.add_argument("--limit", type=int, default=30)
    request_prices.add_argument("--page", type=int, default=1)
    request_prices.add_argument("--sorting", choices=["price", "route"], default="price")
    request_prices.add_argument("--unique", action="store_true")
    request_prices.add_argument("--dry-run", action="store_true", help="Default behavior; included for explicitness.")
    request_prices.add_argument("--fetch", action="store_true", help="Fetch Travelpayouts cached Data API using TRAVELPAYOUTS_TOKEN.")
    request_prices.add_argument("--timeout", type=int, default=20)
    request_prices.set_defaults(func=command_request_prices_for_dates, command_name="request prices-for-dates")

    request_grouped = request_sub.add_parser("grouped-prices", help="Build or run a Travelpayouts REST v3 grouped_prices cached calendar probe.")
    request_grouped.add_argument("origin")
    request_grouped.add_argument("destination")
    request_grouped.add_argument("--departure-at", required=True, help="Departure date or month: YYYY-MM or YYYY-MM-DD.")
    request_grouped.add_argument("--return-at", help="Return date or month: YYYY-MM or YYYY-MM-DD.")
    request_grouped.add_argument("--group-by", choices=["departure_at", "month"], default="departure_at")
    request_grouped.add_argument("--direct", action="store_true", help="Only direct cached prices.")
    request_grouped.add_argument("--market", default="ru")
    request_grouped.add_argument("--currency", default=DEFAULT_CURRENCY)
    request_grouped.add_argument("--min-trip-duration", type=int)
    request_grouped.add_argument("--max-trip-duration", type=int)
    request_grouped.add_argument("--dry-run", action="store_true", help="Default behavior; included for explicitness.")
    request_grouped.add_argument("--fetch", action="store_true", help="Fetch Travelpayouts cached Data API using TRAVELPAYOUTS_TOKEN.")
    request_grouped.add_argument("--timeout", type=int, default=20)
    request_grouped.set_defaults(func=command_request_grouped_prices, command_name="request grouped-prices")

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


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    argv = normalize_global_json(list(sys.argv if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    store = Store()
    try:
        catalog_auto_refresh = auto_refresh_catalog(args, store)
        data = args.func(args, store)
        if catalog_auto_refresh is not None and isinstance(data, dict):
            data["catalog_auto_refresh"] = catalog_auto_refresh
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
