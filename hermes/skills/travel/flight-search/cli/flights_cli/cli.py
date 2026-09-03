from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__
from .command_surface import (
    AIRPORTS_EXPLAIN_COMMAND,
    CITIES_SEARCH_COMMAND,
    MAINT_CATALOG_MANIFEST_COMMAND,
    MAINT_CATALOG_REFRESH_COMMAND,
    MAINT_CHECK_COMMAND,
    MAINT_DOCTOR_COMMAND,
    SEARCH_COMMAND,
    CommandSpec,
)
from .commands.maint import (
    command_maint_catalog_manifest,
    command_maint_catalog_refresh,
    command_maint_doctor,
    command_maintenance_check,
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


def _set_leaf_defaults(
    parser: argparse.ArgumentParser, spec: CommandSpec, handler: Any
) -> None:
    defaults: dict[str, Any] = {"func": handler, "command_name": spec.name}
    if spec.catalog_access is not None:
        defaults["catalog_access"] = spec.catalog_access
    if spec.requires_catalog:
        defaults["requires_catalog"] = True
    parser.set_defaults(**defaults)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return number


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
        SEARCH_COMMAND.path[0],
        parents=[json_parent],
        help=SEARCH_COMMAND.help,
    )
    search.add_argument(
        "--request",
        required=True,
        help="flight_search_request.v1 JSON file, or - for stdin.",
    )
    # Бюджеты прогона. В запросе их нет: запрос описывает желание, а не то,
    # сколько на него потратить. Ноль отвергается, а не подменяется
    # умолчанием: «ноль попыток» — это не «сколько получится».
    search.add_argument(
        "--timeout", type=_positive_int, help="Provider request timeout, seconds."
    )
    search.add_argument(
        "--max-searches",
        type=_positive_int,
        help="Maximum provider attempts for one search.",
    )
    search.add_argument(
        "--segment-limit",
        type=_positive_int,
        help="Maximum offers pulled from one probe.",
    )
    search.add_argument(
        "--live-cache-ttl",
        type=_non_negative_int,
        help="Live provider cache TTL, seconds. Zero disables reuse.",
    )
    search.add_argument(
        "--no-live-cache", action="store_true", help="Bypass the live provider cache."
    )
    search.add_argument(
        "--fail-fast", action="store_true", help="Stop on the first provider failure."
    )
    _set_leaf_defaults(search, SEARCH_COMMAND, command_search)


def _register_maint_commands(sub, json_parent: argparse.ArgumentParser) -> None:
    maint = sub.add_parser(
        MAINT_CHECK_COMMAND.path[0],
        parents=[json_parent],
        help="Primary maintenance namespace.",
    )
    maint_sub = maint.add_subparsers(dest="maint_command", required=True)
    check = maint_sub.add_parser(
        MAINT_CHECK_COMMAND.leaf,
        parents=[json_parent],
        help=MAINT_CHECK_COMMAND.help,
    )
    check.add_argument(
        "--runtime-path",
        help="Runtime flight-search skill path to compare against. Defaults to ~/.hermes/skills/travel/flight-search.",
    )
    _set_leaf_defaults(check, MAINT_CHECK_COMMAND, command_maintenance_check)
    doctor = maint_sub.add_parser(
        MAINT_DOCTOR_COMMAND.leaf,
        parents=[json_parent],
        help=MAINT_DOCTOR_COMMAND.help,
    )
    _set_leaf_defaults(doctor, MAINT_DOCTOR_COMMAND, command_maint_doctor)
    catalog = maint_sub.add_parser(
        MAINT_CATALOG_MANIFEST_COMMAND.path[1],
        parents=[json_parent],
        help="Static catalog maintenance.",
    )
    catalog_sub = catalog.add_subparsers(dest="maint_catalog_command", required=True)
    manifest = catalog_sub.add_parser(
        MAINT_CATALOG_MANIFEST_COMMAND.leaf,
        parents=[json_parent],
        help=MAINT_CATALOG_MANIFEST_COMMAND.help,
    )
    _set_leaf_defaults(
        manifest, MAINT_CATALOG_MANIFEST_COMMAND, command_maint_catalog_manifest
    )
    refresh = catalog_sub.add_parser(
        MAINT_CATALOG_REFRESH_COMMAND.leaf,
        parents=[json_parent],
        help=MAINT_CATALOG_REFRESH_COMMAND.help,
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
    _set_leaf_defaults(
        refresh, MAINT_CATALOG_REFRESH_COMMAND, command_maint_catalog_refresh
    )


def _register_metadata_commands(sub, json_parent: argparse.ArgumentParser) -> None:
    cities = sub.add_parser(
        CITIES_SEARCH_COMMAND.path[0],
        parents=[json_parent],
        help="City lookup commands.",
    )
    cities_sub = cities.add_subparsers(dest="cities_command", required=True)
    cities_search = cities_sub.add_parser(
        CITIES_SEARCH_COMMAND.leaf,
        parents=[json_parent],
        help=CITIES_SEARCH_COMMAND.help,
    )
    cities_search.add_argument("query")
    cities_search.add_argument("--limit", type=int, default=5)
    _set_leaf_defaults(cities_search, CITIES_SEARCH_COMMAND, command_cities_search)

    airports = sub.add_parser(
        AIRPORTS_EXPLAIN_COMMAND.path[0],
        parents=[json_parent],
        help="Airport rule lookup commands.",
    )
    airports_sub = airports.add_subparsers(dest="airports_command", required=True)
    airports_explain = airports_sub.add_parser(
        AIRPORTS_EXPLAIN_COMMAND.leaf,
        parents=[json_parent],
        help=AIRPORTS_EXPLAIN_COMMAND.help,
    )
    airports_explain.add_argument("code", nargs="+")
    _set_leaf_defaults(
        airports_explain, AIRPORTS_EXPLAIN_COMMAND, command_airports_explain
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
        # Обслуживание каталога — не часть ответа путешественнику: в `.v1`
        # его нет, и класть его в результат поиска больше нельзя.
        if (
            args.command_name != SEARCH_COMMAND.name
            and catalog_auto_refresh is not None
            and isinstance(data, dict)
        ):
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
