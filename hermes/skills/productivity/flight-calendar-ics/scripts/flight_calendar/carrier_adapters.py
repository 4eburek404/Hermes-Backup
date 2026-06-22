"""Carrier-specific argument adapters for `build <route>` commands."""
from __future__ import annotations

import argparse
from pathlib import Path

from flight_calendar.envelope import CliFailure
from flight_calendar.route_detection import first_url_from_args


def build_route_args(args: argparse.Namespace, paths: dict[str, Path]) -> argparse.Namespace:
    url = first_url_from_args(args)
    if args.route == "aeroflot":
        return argparse.Namespace(
            url=url,
            pnr_locator=args.pnr_locator,
            pnr_key=args.pnr_key,
            last_name=args.last_name,
            first_name=args.first_name,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
        )
    if args.route == "ural":
        return argparse.Namespace(
            url=url,
            pnr=args.pnr,
            last_name=args.last_name,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
            frontend_base=args.frontend_base,
        )
    if args.route == "utair":
        return argparse.Namespace(
            url=url,
            rloc=args.rloc,
            last_name=args.last_name,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
        )
    if args.route == "redwings":
        return argparse.Namespace(
            url=url,
            pnr=args.pnr,
            access_code=args.access_code,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
            graphql_endpoint=args.graphql_endpoint,
        )
    raise CliFailure(f"unknown build route: {args.route}", code="usage_error")
