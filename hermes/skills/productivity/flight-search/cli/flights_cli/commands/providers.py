from __future__ import annotations

import argparse

from ..providers.fli_mcp import (
    FliDatesOptions,
    FliSearchOptions,
    run_fli_dates,
    run_fli_search,
)
from ..providers.kupibilet import (
    KupiBiletRoundTripOptions,
    KupiBiletSearchOptions,
    run_kb_roundtrip,
    run_kb_search,
)
from ..providers.tutu_mcp import TutuSearchOptions, run_tutu_search
from ..store import Store


def command_kb_search(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_kb_search(
        KupiBiletSearchOptions(
            origin=args.origin,
            destination=args.destination,
            depart_date=args.depart_date,
            currency=args.currency,
            only_carrier=args.only_carrier,
            direct_only=args.direct_only,
            limit=args.limit,
            timeout=args.timeout,
            cache_ttl_seconds=args.cache_ttl_seconds,
            no_cache=args.no_cache,
        )
    )


def command_kb_roundtrip(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_kb_roundtrip(
        KupiBiletRoundTripOptions(
            origin=args.origin,
            destination=args.destination,
            depart_date=args.depart_date,
            return_date=args.return_date,
            currency=args.currency,
            only_carrier=args.only_carrier,
            direct_only=args.direct_only,
            limit=args.limit,
            timeout=args.timeout,
            cache_ttl_seconds=args.cache_ttl_seconds,
            no_cache=args.no_cache,
        )
    )


def command_tutu_search(args: argparse.Namespace, store: Store) -> dict:
    return run_tutu_search(
        TutuSearchOptions(
            origin=args.origin,
            destination=args.destination,
            depart_date=args.depart_date,
            return_date=args.return_date,
            currency=args.currency,
            only_carrier=args.only_carrier,
            direct_only=args.direct_only,
            limit=args.limit,
            timeout=args.timeout,
            tutu_mcp_url=args.tutu_mcp_url,
            cache_ttl_seconds=args.cache_ttl_seconds,
            no_cache=args.no_cache,
        ),
        store,
    )


def command_fli_search(args: argparse.Namespace, store: Store) -> dict:
    return run_fli_search(
        FliSearchOptions(
            origin=args.origin,
            destination=args.destination,
            depart_date=args.depart_date,
            currency=args.currency,
            only_carrier=args.only_carrier,
            direct_only=args.direct_only,
            limit=args.limit,
            timeout=args.timeout,
            mcp_url=args.mcp_url,
            cabin_class=args.cabin_class,
            max_stops=args.max_stops,
            sort_by=args.sort_by,
            passengers=args.passengers,
            cache_ttl_seconds=args.cache_ttl_seconds,
            no_cache=args.no_cache,
        ),
        store,
    )


def command_fli_dates(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_fli_dates(
        FliDatesOptions(
            origin=args.origin,
            destination=args.destination,
            from_date=args.from_date,
            to_date=args.to_date,
            trip_duration=args.trip_duration,
            round_trip=args.round_trip,
            only_carrier=args.only_carrier,
            direct_only=args.direct_only,
            max_stops=args.max_stops,
            cabin_class=args.cabin_class,
            sort_by_price=args.sort_by_price,
            passengers=args.passengers,
            limit=args.limit,
            mcp_url=args.mcp_url,
            timeout=args.timeout,
        )
    )
