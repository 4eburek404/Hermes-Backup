#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from travel_expense.constants import CANON_AMOUNT, CANON_CARRIER, CANON_DATE, CANON_DETAILS
from travel_expense.render import render_json, render_markdown, write_output
from travel_expense.summary import analyze_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize travel-expense spreadsheets by aviation, rail, lodging, and Unknown.")
    parser.add_argument("path", type=Path, help="Path to .xlsx/.xlsm/.xls/.csv file")
    parser.add_argument("--sheet", help="Excel sheet name/index; default: first sheet")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, help="Write output to file instead of stdout")
    parser.add_argument("--overrides", type=Path, help="JSON file with pattern overrides")
    parser.add_argument("--show-review", action="store_true", help="Show Unknown/review rows in Markdown output")
    parser.add_argument("--strict", action="store_true", help="Return non-zero code when review or reconciliation issues remain")
    parser.add_argument("--date-col", help="Manual source column name for date")
    parser.add_argument("--carrier-col", help="Manual source column name for carrier/vendor")
    parser.add_argument("--details-col", help="Manual source column name for details/route/service")
    parser.add_argument("--amount-col", help="Manual source column name for amount")
    return parser


def _parse_sheet(value: str | None) -> str | int | None:
    if value is None:
        return None
    return int(value) if value.isdigit() else value


def _column_overrides(args: argparse.Namespace) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if args.date_col:
        overrides[CANON_DATE] = args.date_col
    if args.carrier_col:
        overrides[CANON_CARRIER] = args.carrier_col
    if args.details_col:
        overrides[CANON_DETAILS] = args.details_col
    if args.amount_col:
        overrides[CANON_AMOUNT] = args.amount_col
    return overrides


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = analyze_file(
            args.path,
            sheet=_parse_sheet(args.sheet),
            overrides_path=args.overrides,
            column_overrides=_column_overrides(args),
        )
    except Exception as exc:  # noqa: BLE001 - concise CLI error for agent/user
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    content = render_json(result) if args.format == "json" else render_markdown(result, show_review=args.show_review)
    write_output(args.output, content)
    if args.output is None:
        print(content)

    if args.strict:
        if result.get("unknown_rows") or result.get("review_rows"):
            return 3
        verification = result.get("verification", {})
        if verification.get("source_total_sum_matches") is False or verification.get("source_total_count_matches") is False:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
