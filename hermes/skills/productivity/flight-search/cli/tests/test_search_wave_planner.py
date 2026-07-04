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


class FakeWaveExecutor:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def run(
        self, queries: list[dict[str, Any]], plan: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(queries)
        wave_index = int(queries[0].get("wave_index") or 0)
        if wave_index == 0:
            return {
                "searched_gateways": 1,
                "viable_gateways": 0,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "coverage_evaluations": [],
                "gateways": [
                    {
                        "gateway": "AMS",
                        "searched": True,
                        "viable": False,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "NTE",
                            "destination": "AMS",
                            "date": "2026-07-09",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "nte-ams",
                                    "segments": [
                                        {
                                            "origin": "NTE",
                                            "destination": "AMS",
                                            "departure_at": "2026-07-09T17:20:00+02:00",
                                            "arrival_at": "2026-07-09T18:55:00+02:00",
                                        }
                                    ],
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "AMS",
                            "destination": "SVX",
                            "date": "2026-07-09",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ams-ist",
                                    "price": {"amount": 12000},
                                    "segments": [
                                        {
                                            "origin": "AMS",
                                            "destination": "IST",
                                            "departure_at": "2026-07-09T21:00:00+02:00",
                                            "arrival_at": "2026-07-10T01:20:00+03:00",
                                        }
                                    ],
                                }
                            ],
                        },
                        "provider_failures": [],
                        "skipped_reasons": [],
                        "missing_legs": ["destination_leg"],
                    }
                ],
            }
        return {
            "searched_gateways": 1,
            "viable_gateways": 0,
            "failed_gateways": 0,
            "not_searched_budget": 0,
            "coverage_evaluations": [],
            "gateways": [
                {
                    "gateway": "IST",
                    "searched": True,
                    "viable": False,
                    "origin_leg": None,
                    "destination_leg": {
                        "leg": "gateway_to_destination",
                        "origin": "IST",
                        "destination": "SVX",
                        "date": "2026-07-10",
                        "provider": "tutu",
                        "offer_count": 1,
                        "offers": [{"id": "ist-svx"}],
                    },
                    "provider_failures": [],
                    "skipped_reasons": ["origin_leg_query_missing"],
                    "missing_legs": ["origin_leg"],
                }
            ],
        }


class LateArrivalWaveExecutor:
    def __init__(self, arrival_at: str) -> None:
        self.arrival_at = arrival_at
        self.calls: list[list[dict[str, Any]]] = []

    def run(
        self, queries: list[dict[str, Any]], plan: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(queries)
        wave_index = int(queries[0].get("wave_index") or 0)
        if wave_index == 0:
            return {
                "searched_gateways": 1,
                "viable_gateways": 0,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "coverage_evaluations": [],
                "gateways": [
                    {
                        "gateway": "AMS",
                        "searched": True,
                        "viable": False,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "NTE",
                            "destination": "AMS",
                            "date": "2026-07-09",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "nte-ams",
                                    "segments": [
                                        {
                                            "origin": "NTE",
                                            "destination": "AMS",
                                            "departure_at": "2026-07-09T17:20:00+02:00",
                                            "arrival_at": "2026-07-09T18:55:00+02:00",
                                        }
                                    ],
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "AMS",
                            "destination": "SVX",
                            "date": "2026-07-09",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ams-ist",
                                    "price": {"amount": 12000},
                                    "segments": [
                                        {
                                            "origin": "AMS",
                                            "destination": "IST",
                                            "departure_at": "2026-07-09T21:00:00+02:00",
                                            "arrival_at": self.arrival_at,
                                        }
                                    ],
                                }
                            ],
                        },
                        "provider_failures": [],
                        "skipped_reasons": [],
                        "missing_legs": ["destination_leg"],
                    }
                ],
            }
        return {
            "searched_gateways": len(queries),
            "viable_gateways": 0,
            "failed_gateways": 0,
            "not_searched_budget": 0,
            "coverage_evaluations": [],
            "gateways": [],
        }


class SearchWavePlannerTests(unittest.TestCase):
    def test_cross_day_expansion_uses_actual_arrival_date(self) -> None:
        executor = FakeWaveExecutor()
        planner = SearchWavePlanner(
            options=wave_options(),
            executor=executor,
        )

        result = planner.run(
            initial_queries(),
            {"origin": "NTE", "destination": "SVX", "currency": "RUB"},
        )

        self.assertEqual(len(executor.calls), 2)
        second_wave = executor.calls[1]
        self.assertEqual(len(second_wave), 1)
        self.assertEqual(second_wave[0]["origin"], "IST")
        self.assertEqual(second_wave[0]["destination"], "SVX")
        self.assertEqual(second_wave[0]["date"], "2026-07-10")
        self.assertFalse(second_wave[0]["direct_only"])
        self.assertEqual(second_wave[0]["wave_index"], 1)
        self.assertEqual(
            second_wave[0]["date_strategy"], "arrival_date_from_partial_path"
        )
        self.assertEqual(result["wave_diagnostics"]["wave_count"], 2)

    def test_budget_exhaustion_returns_partial_answerability(self) -> None:
        executor = FakeWaveExecutor()
        planner = SearchWavePlanner(
            options=wave_options(max_segment_searches=2),
            executor=executor,
        )

        result = planner.run(
            initial_queries(),
            {"origin": "NTE", "destination": "SVX", "currency": "RUB"},
        )

        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(result["answerability"], "needs_more_evidence")
        self.assertEqual(
            result["wave_diagnostics"]["stop_reason"], "global_budget_exhausted"
        )
        self.assertEqual(result["not_searched_budget"], 1)

    def test_late_arrival_generates_day_zero_and_next_day_expansions(self) -> None:
        executor = LateArrivalWaveExecutor("2026-07-10T23:25:00+03:00")
        planner = SearchWavePlanner(
            options=wave_options(max_segment_searches=4),
            executor=executor,
        )

        planner.run(
            initial_queries(),
            {"origin": "NTE", "destination": "SVX", "currency": "RUB"},
        )

        self.assertEqual(len(executor.calls), 3)
        expansion_queries = [*executor.calls[1], *executor.calls[2]]
        self.assertEqual(
            [query["date"] for query in expansion_queries],
            ["2026-07-10", "2026-07-11"],
        )
        self.assertEqual(
            [query["date_strategy"] for query in expansion_queries],
            [
                "arrival_date_from_partial_path",
                "arrival_date_plus_one_late_arrival",
            ],
        )
        self.assertEqual(
            {query["parent_offer_id"] for query in expansion_queries},
            {"ams-ist"},
        )

    def test_daytime_arrival_generates_only_arrival_date_expansion(self) -> None:
        executor = LateArrivalWaveExecutor("2026-07-10T14:00:00+03:00")
        planner = SearchWavePlanner(
            options=wave_options(max_segment_searches=4),
            executor=executor,
        )

        planner.run(
            initial_queries(),
            {"origin": "NTE", "destination": "SVX", "currency": "RUB"},
        )

        self.assertEqual(len(executor.calls), 2)
        self.assertEqual(
            [query["date"] for query in executor.calls[1]],
            ["2026-07-10"],
        )

    def test_late_arrival_next_day_probe_is_clipped_first_by_budget(self) -> None:
        executor = LateArrivalWaveExecutor("2026-07-10T23:25:00+03:00")
        planner = SearchWavePlanner(
            options=wave_options(max_segment_searches=3),
            executor=executor,
        )

        planner.run(
            initial_queries(),
            {"origin": "NTE", "destination": "SVX", "currency": "RUB"},
        )

        self.assertEqual(len(executor.calls), 2)
        self.assertEqual(
            [query["date"] for query in executor.calls[1]],
            ["2026-07-10"],
        )
        self.assertEqual(
            executor.calls[1][0]["date_strategy"],
            "arrival_date_from_partial_path",
        )


if __name__ == "__main__":
    unittest.main()
