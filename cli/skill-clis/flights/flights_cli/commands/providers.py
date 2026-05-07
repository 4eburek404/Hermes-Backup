from __future__ import annotations

import argparse

from ..io import read_json_file
from ..providers.fli_mcp import run_fli_dates, run_fli_search
from ..providers.kupibilet import run_kb_search
from ..providers.travelpayouts import parse_travelpayouts_results, run_request_search
from ..providers.travelpayouts_data import run_grouped_prices, run_prices_for_dates
from ..providers.u6 import run_u6_prices
from ..store import Store


def command_request_search(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_request_search(args)


def command_request_prices_for_dates(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_prices_for_dates(args)


def command_request_grouped_prices(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_grouped_prices(args)


def command_kb_search(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_kb_search(args)


def command_fli_search(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_fli_search(args)


def command_fli_dates(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_fli_dates(args)


def command_u6_prices(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_u6_prices(args)


def command_results_parse(args: argparse.Namespace, store: Store) -> dict:
    del store
    return parse_travelpayouts_results(args, read_json_file(args.input))
