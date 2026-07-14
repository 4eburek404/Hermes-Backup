from __future__ import annotations

import unittest
from typing import Any

from flights_cli.execution.search_wave_planner import (
    SearchWavePlanner,
    SearchWavePlannerOptions,
)


def wave_options(**overrides: object) -> SearchWavePlannerOptions:
    values = {
        "max_waves": 3,
        "probes_per_wave": 4,
        "max_segment_searches": 6,
        "top_k_partial_paths": 3,
        "timeout_seconds": 60,
    }
    values.update(overrides)
    return SearchWavePlannerOptions(**values)


def initial_queries() -> list[dict[str, Any]]:
    return [
        {
            "role": "gateway_leg_probe",
            "source_type": "gateway_discovery_candidate",
            "probe_type": "segment_direct",
            "direction": "outbound",
            "leg": "origin_to_gateway",
            "origin": "NTE",
            "destination": "AMS",
            "date": "2026-07-09",
            "currency": "RUB",
            "direct_only": True,
            "gateway": "AMS",
            "gateway_rank": 1,
            "provider": "tutu",
            "execution_state": "not_executed",
        },
        {
            "role": "gateway_leg_probe",
            "source_type": "gateway_discovery_candidate",
            "probe_type": "segment_hub_leg",
            "direction": "outbound",
            "leg": "gateway_to_destination",
            "origin": "AMS",
            "destination": "SVX",
            "date": "2026-07-09",
            "currency": "RUB",
            "direct_only": False,
            "gateway": "AMS",
            "gateway_rank": 1,
            "provider": "tutu",
            "execution_state": "not_executed",
        },
    ]


class EmptyWaveExecutor:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def run(
        self, queries: list[dict[str, Any]], plan: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(queries)
        return {
            "searched_gateways": 0,
            "viable_gateways": 0,
            "failed_gateways": 0,
            "not_searched_budget": 0,
            "coverage_evaluations": [],
            "gateways": [],
        }


class SearchWavePlannerTests(unittest.TestCase):
    def test_budget_exhaustion_returns_partial_answerability(self) -> None:
        queries = initial_queries()
        queries.extend(
            [
                {
                    **queries[0],
                    "destination": "IST",
                    "gateway": "IST",
                    "gateway_rank": 2,
                },
                {
                    **queries[1],
                    "origin": "IST",
                    "gateway": "IST",
                    "gateway_rank": 2,
                },
            ]
        )
        executor = EmptyWaveExecutor()
        planner = SearchWavePlanner(
            options=wave_options(max_segment_searches=2),
            executor=executor,
        )

        result = planner.run(
            queries,
            {"origin": "NTE", "destination": "SVX", "currency": "RUB"},
        )

        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(result["answerability"], "needs_more_evidence")
        self.assertEqual(
            result["wave_diagnostics"]["stop_reason"], "global_budget_exhausted"
        )
        self.assertEqual(result["not_searched_budget"], 1)


if __name__ == "__main__":
    unittest.main()
