from __future__ import annotations

import argparse
from typing import Any

from ..io import read_json_input, read_json_object
from ..services.agent_report import agent_report_options_from_args, attach_agent_report
from ..services.assembly import assemble_segment_results, assembly_options_from_args, collect_segment_results
from ..services.ranking import extract_candidate_list, rank_candidate_list, ranking_options_from_args
from ..services.validation import validate_itinerary, validation_options_from_args
from ..store import Store


def command_route_validate(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    data = read_json_object(args.input)
    return validate_itinerary(data, validation_options_from_args(args))


def command_route_rank(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    candidates = extract_candidate_list(read_json_input(args.input))
    return rank_candidate_list(candidates, ranking_options_from_args(args))



def command_route_assemble(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    segment_results: list[dict[str, Any]] = []
    for path in (args.input or ["-"]):
        segment_results.extend(collect_segment_results(read_json_input(path)))
    assembled = assemble_segment_results(segment_results, assembly_options_from_args(args))
    return attach_agent_report(assembled, agent_report_options_from_args(args), store)
