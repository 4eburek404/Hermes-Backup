from __future__ import annotations

import argparse
import json
from typing import Any

from ..errors import CliError
from ..io import read_input_text, read_json_file
from ..orchestrators.live_assemble import run_live_route_assembly
from ..orchestrators.route_plan import build_route_plan
from ..services.agent_report import attach_agent_report
from ..services.assembly import assemble_segment_results, collect_segment_results
from ..services.ranking import extract_candidate_list, rank_candidate_list
from ..services.validation import validate_itinerary
from ..store import Store


def command_route_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return build_route_plan(args, store)


def command_route_validate(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    source = read_input_text(args.input)
    try:
        data = json.loads(source)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON input: {exc}", error_type="validation_error") from exc
    if not isinstance(data, dict):
        raise CliError("input JSON must be an object", error_type="validation_error")
    return validate_itinerary(data, args)


def command_route_rank(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    candidates = extract_candidate_list(read_json_file(args.input))
    return rank_candidate_list(candidates, args)


def command_route_kb_assemble(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return run_live_route_assembly(args, store)


def command_route_live_assemble(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return run_live_route_assembly(args, store)


def command_route_assemble(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    segment_results: list[dict[str, Any]] = []
    for path in (args.input or ["-"]):
        segment_results.extend(collect_segment_results(read_json_file(path)))
    return attach_agent_report(assemble_segment_results(segment_results, args), args, store)
