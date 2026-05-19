from __future__ import annotations

import argparse

from ..providers.fli_mcp import run_fli_dates, run_fli_search
from ..providers.kupibilet import run_kb_search
from ..store import Store


def command_kb_search(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_kb_search(args)


def command_fli_search(args: argparse.Namespace, store: Store) -> dict:
    return run_fli_search(args, store)


def command_fli_dates(args: argparse.Namespace, store: Store) -> dict:
    del store
    return run_fli_dates(args)
