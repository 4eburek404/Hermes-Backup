from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from flights_cli.errors import CliError
from flights_cli.execution.gateway_leg_probe_executor import (
    GatewayLegProbeExecutor,
    GatewayLegProbeOptions,
)
from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.execution.probe_ledger import ProbeRunLedger
from flights_cli.ports.providers import ProviderProbeResult
from flights_cli.store import Store
from helpers import coverage_completeness


def executor_options(**overrides: object) -> GatewayLegProbeOptions:
    values = {
        "gateway_discovery_limit": 10,
        "gateway_probe_batch_size": 10,
        "gateway_probe_max_batches": 1,
        "segment_limit": 3,
        "timeout": 10,
        "fail_fast": False,
    }
    values.update(overrides)
    return GatewayLegProbeOptions(**values)


def gateway_queries(
    gateway: str,
    *,
    rank: int = 1,
    destination: str = "AMS",
    origin_leg_direct_only: bool = True,
    destination_leg_direct_only: bool = True,
) -> list[dict[str, Any]]:
    return [
        {
            "role": "gateway_leg_probe",
            "source_type": "gateway_discovery_candidate",
            "probe_type": "segment_direct"
            if origin_leg_direct_only
            else "segment_hub_leg",
            "direction": "outbound",
            "leg": "origin_to_gateway",
            "origin": "SVX",
            "destination": gateway,
            "date": "2026-08-15",
            "currency": "RUB",
            "direct_only": origin_leg_direct_only,
            "gateway": gateway,
            "gateway_rank": rank,
            "provider": "kupibilet",
            "execution_state": "not_executed",
        },
        {
            "role": "gateway_leg_probe",
            "source_type": "gateway_discovery_candidate",
            "probe_type": "segment_direct"
            if destination_leg_direct_only
            else "segment_hub_leg",
            "direction": "outbound",
            "leg": "gateway_to_destination",
            "origin": gateway,
            "destination": destination,
            "date": "2026-08-15",
            "currency": "RUB",
            "direct_only": destination_leg_direct_only,
            "gateway": gateway,
            "gateway_rank": rank,
            "provider": "tutu",
            "execution_state": "not_executed",
        },
    ]


def outcome_for(spec: dict[str, Any], *, offer_count: int) -> SegmentProbeOutcome:
    offers = [
        {
            "id": f"offer-{index}",
            "covers_requested_trip": True,
            "segments": [
                {
                    "origin": spec["origin"],
                    "destination": spec["destination"],
                    "departure_at": f"{spec['date']}T08:00:00+00:00",
                    "arrival_at": f"{spec['date']}T10:00:00+00:00",
                }
            ],
        }
        for index in range(offer_count)
    ]
    return SegmentProbeOutcome(
        summary={
            "status": "ok",
            "provider": spec["provider"],
            "offer_count": offer_count,
            "probe_id": f"probe-{spec['origin']}-{spec['destination']}",
            "cache_status": "disabled",
        },
        segment_result={
            "direction": spec["direction"],
            "leg": spec["leg"],
            "offers": offers,
        },
    )


class GatewayLegProbeExecutorTests(unittest.TestCase):
    def run_executor(
        self,
        queries: list[dict[str, Any]],
        *,
        offers_by_pair: dict[tuple[str, str], int],
        options: GatewayLegProbeOptions | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        calls: list[dict[str, Any]] = []

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            calls.append(kwargs)
            spec = kwargs["spec"]
            pair = (str(spec["origin"]), str(spec["destination"]))
            return [outcome_for(spec, offer_count=offers_by_pair.get(pair, 0))]

        executor = GatewayLegProbeExecutor(
            options=options or executor_options(),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(queries, {"currency": "RUB"})
        return result, calls

    def test_both_legs_found_marks_gateway_viable(self) -> None:
        result, calls = self.run_executor(
            gateway_queries("IST"),
            offers_by_pair={("SVX", "IST"): 1, ("IST", "AMS"): 1},
        )

        self.assertEqual(result["searched_gateways"], 1)
        self.assertEqual(result["viable_gateways"], 1)
        self.assertNotIn("failed_gateways", result)
        gateway = result["gateways"][0]
        self.assertTrue(gateway["viable"])
        self.assertEqual(gateway["origin_leg"]["offer_count"], 1)
        self.assertEqual(gateway["destination_leg"]["offer_count"], 1)
        self.assertEqual(
            [call["provider_policy"] for call in calls], ["kupibilet", "tutu"]
        )

    def test_non_direct_access_leg_is_dispatched_without_rewriting_flag(self) -> None:
        result, calls = self.run_executor(
            gateway_queries("IST", origin_leg_direct_only=False),
            offers_by_pair={("SVX", "IST"): 1, ("IST", "AMS"): 1},
        )

        self.assertEqual(result["viable_gateways"], 1)
        self.assertEqual(
            [(call["spec"]["leg"], call["spec"]["direct_only"]) for call in calls],
            [("origin_to_gateway", False), ("gateway_to_destination", True)],
        )

    def test_origin_leg_missing_makes_gateway_not_viable(self) -> None:
        result, _calls = self.run_executor(
            gateway_queries("IST"),
            offers_by_pair={("SVX", "IST"): 0, ("IST", "AMS"): 1},
        )

        gateway = result["gateways"][0]
        self.assertFalse(gateway["viable"])
        self.assertEqual(gateway["missing_legs"], ["origin_leg"])
        self.assertEqual(result["viable_gateways"], 0)

    def test_destination_leg_missing_makes_gateway_not_viable(self) -> None:
        result, _calls = self.run_executor(
            gateway_queries("IST"),
            offers_by_pair={("SVX", "IST"): 1, ("IST", "AMS"): 0},
        )

        gateway = result["gateways"][0]
        self.assertFalse(gateway["viable"])
        self.assertEqual(gateway["missing_legs"], ["destination_leg"])
        self.assertEqual(result["viable_gateways"], 0)

    def test_provider_failure_falls_back_to_next_provider_without_parallel_failure_truth(
        self,
    ) -> None:
        calls: list[str] = []

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            provider = str(spec["provider"])
            calls.append(provider)
            if provider == "tutu" and spec["leg"] == "origin_to_gateway":
                raise CliError("provider down", error_type="provider_unavailable")
            return [outcome_for(spec, offer_count=1)]

        ledger = ProbeRunLedger()
        executor = GatewayLegProbeExecutor(
            options=executor_options(),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
            probe_ledger=ledger,
        )
        base_queries = gateway_queries("IST", rank=1)
        first_provider = {**base_queries[0], "provider": "tutu"}
        fallback_provider = {**base_queries[0], "provider": "kupibilet"}
        queries = [first_provider, fallback_provider, base_queries[1]]
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(queries, {"currency": "RUB"})

        self.assertEqual(result["searched_gateways"], 1)
        self.assertEqual(result["viable_gateways"], 1)
        self.assertEqual(calls, ["tutu", "kupibilet", "tutu"])
        self.assertNotIn("failed_gateways", result)
        gateway = result["gateways"][0]
        self.assertNotIn("provider_failures", gateway)
        self.assertNotIn("failure", gateway["origin_leg"])
        diagnostics = ledger.to_diagnostics()
        self.assertEqual(
            diagnostics["failed_probes"][0]["error"]["classification"],
            "provider_unavailable",
        )
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )

    def test_returned_failed_state_is_failed_and_falls_back(self) -> None:
        calls: list[str] = []
        ledger = ProbeRunLedger()
        base_queries = gateway_queries("IST")
        first = {**base_queries[0], "provider": "tutu"}
        fallback = {**base_queries[0], "provider": "kupibilet"}

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            calls.append(str(spec["provider"]))
            if spec["provider"] == "tutu" and spec["leg"] == "origin_to_gateway":
                provider_result = ProviderProbeResult(
                    probe_id=str(spec.get("probe_id") or "returned-failure"),
                    probe_type="segment_direct",
                    provider="tutu",
                    query=spec,
                    execution_state="failed",
                    evidence_type="provider_unavailable",
                    errors=({"type": "timeout", "message": "provider timed out"},),
                )
                return [
                    SegmentProbeOutcome(
                        summary={
                            "provider": "tutu",
                            "status": "error",
                            "execution_state": "failed",
                            "offer_count": 0,
                        },
                        provider_result=provider_result,
                    )
                ]
            return [outcome_for(spec, offer_count=1)]

        executor = GatewayLegProbeExecutor(
            options=executor_options(),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
            probe_ledger=ledger,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(
                [first, fallback, base_queries[1]], {"currency": "RUB"}
            )

        self.assertEqual(calls, ["tutu", "kupibilet", "tutu"])
        self.assertTrue(result["gateways"][0]["viable"])
        failed = ledger.to_diagnostics()["failed_probes"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["error"]["classification"], "timeout")

    def test_malformed_direct_does_not_suppress_broad_probe(self) -> None:
        calls: list[tuple[str, bool]] = []
        base_queries = gateway_queries("IST")
        direct_origin = {**base_queries[0], "provider": "tutu"}
        broad_origin = {
            **base_queries[0],
            "provider": "kupibilet",
            "probe_type": "segment_hub_leg",
            "direct_only": False,
        }

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            calls.append((str(spec["provider"]), bool(spec["direct_only"])))
            if spec is direct_origin or (
                spec["provider"] == "tutu" and spec["leg"] == "origin_to_gateway"
            ):
                return [
                    SegmentProbeOutcome(
                        summary={
                            "status": "ok",
                            "provider": "tutu",
                            "offer_count": 1,
                        },
                        segment_result={
                            "offers": [
                                {
                                    "covers_requested_trip": True,
                                    "segments": [
                                        {
                                            "origin": spec["origin"],
                                            "destination": spec["destination"],
                                            "departure_at": f"{spec['date']}T08:00:00+00:00",
                                            "arrival_at": None,
                                        }
                                    ],
                                }
                            ]
                        },
                    )
                ]
            return [outcome_for(spec, offer_count=1)]

        executor = GatewayLegProbeExecutor(
            options=executor_options(),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(
                [direct_origin, broad_origin, base_queries[1]], {"currency": "RUB"}
            )

        self.assertIn(("kupibilet", False), calls)
        self.assertTrue(result["gateways"][0]["viable"])

    def test_malformed_result_falls_through_provider_chain(self) -> None:
        calls: list[str] = []
        base_queries = gateway_queries("IST")
        first = {**base_queries[0], "provider": "tutu"}
        fallback = {**base_queries[0], "provider": "kupibilet"}

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            calls.append(str(spec["provider"]))
            if spec["provider"] == "tutu" and spec["leg"] == "origin_to_gateway":
                malformed = outcome_for(spec, offer_count=1)
                malformed.segment_result["offers"][0]["segments"][0]["arrival_at"] = (
                    "not-a-time"
                )
                return [malformed]
            return [outcome_for(spec, offer_count=1)]

        executor = GatewayLegProbeExecutor(
            options=executor_options(),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(
                [first, fallback, base_queries[1]], {"currency": "RUB"}
            )

        self.assertEqual(calls, ["tutu", "kupibilet", "tutu"])
        self.assertTrue(result["gateways"][0]["viable"])

    def test_provider_failure_raises_when_fail_fast_enabled(self) -> None:
        def dispatch(**_: Any) -> list[SegmentProbeOutcome]:
            raise CliError("provider down", error_type="provider_unavailable")

        ledger = ProbeRunLedger()
        executor = GatewayLegProbeExecutor(
            options=executor_options(fail_fast=True),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
            probe_ledger=ledger,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            with self.assertRaises(CliError):
                executor.run(gateway_queries("IST"), {"currency": "RUB"})

        diagnostics = ledger.to_diagnostics()
        self.assertEqual(len(diagnostics["failed_probes"]), 1)
        self.assertEqual(
            diagnostics["failed_probes"][0]["error"]["classification"],
            "provider_unavailable",
        )

    def test_stop_after_viable_first_batch(self) -> None:
        queries = [
            *gateway_queries("IST", rank=1),
            *gateway_queries("DXB", rank=2),
            *gateway_queries("BEG", rank=3),
        ]
        result, calls = self.run_executor(
            queries,
            offers_by_pair={("SVX", "IST"): 1, ("IST", "AMS"): 1},
            options=executor_options(
                gateway_discovery_limit=10,
                gateway_probe_batch_size=1,
                gateway_probe_max_batches=3,
            ),
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(result["searched_gateways"], 1)
        self.assertEqual(result["viable_gateways"], 1)
        self.assertEqual(result["not_searched_budget"], 2)
        self.assertFalse(result["coverage_evaluation"]["continue_search"])
        self.assertIn(
            "viable_gateway_found",
            result["coverage_evaluation"]["reasons"],
        )
        self.assertEqual(
            result["gateways"][1]["skipped_reasons"],
            ["gateway_probe_coverage_satisfied"],
        )

    def test_continue_after_empty_first_batch(self) -> None:
        queries = [
            *gateway_queries("IST", rank=1),
            *gateway_queries("DXB", rank=2),
            *gateway_queries("BEG", rank=3),
        ]
        result, calls = self.run_executor(
            queries,
            offers_by_pair={("SVX", "DXB"): 1, ("DXB", "AMS"): 1},
            options=executor_options(
                gateway_discovery_limit=10,
                gateway_probe_batch_size=1,
                gateway_probe_max_batches=3,
            ),
        )

        self.assertEqual(len(calls), 4)
        self.assertEqual(result["searched_gateways"], 2)
        self.assertEqual(result["viable_gateways"], 1)
        self.assertEqual(result["not_searched_budget"], 1)
        self.assertTrue(result["coverage_evaluations"][0]["continue_search"])
        self.assertIn(
            "no_viable_gateway_yet",
            result["coverage_evaluations"][0]["reasons"],
        )
        self.assertFalse(result["coverage_evaluation"]["continue_search"])
        self.assertIn(
            "viable_gateway_found",
            result["coverage_evaluation"]["reasons"],
        )

    def test_stop_at_max_batches(self) -> None:
        queries = [
            *gateway_queries("IST", rank=1),
            *gateway_queries("DXB", rank=2),
            *gateway_queries("BEG", rank=3),
        ]
        result, calls = self.run_executor(
            queries,
            offers_by_pair={},
            options=executor_options(
                gateway_discovery_limit=10,
                gateway_probe_batch_size=1,
                gateway_probe_max_batches=2,
            ),
        )

        self.assertEqual(len(calls), 4)
        self.assertEqual(result["searched_gateways"], 2)
        self.assertEqual(result["viable_gateways"], 0)
        self.assertEqual(result["not_searched_budget"], 1)
        self.assertFalse(result["coverage_evaluation"]["continue_search"])
        self.assertIn("max_batches_reached", result["coverage_evaluation"]["reasons"])
        self.assertEqual(
            result["gateways"][2]["skipped_reasons"],
            ["gateway_probe_budget_exhausted"],
        )

    def test_batch_limit_records_not_searched_budget(self) -> None:
        queries = [
            *gateway_queries("IST", rank=1),
            *gateway_queries("DXB", rank=2),
            *gateway_queries("BEG", rank=3),
        ]
        result, calls = self.run_executor(
            queries,
            offers_by_pair={},
            options=executor_options(
                gateway_discovery_limit=10,
                gateway_probe_batch_size=1,
                gateway_probe_max_batches=1,
            ),
        )

        self.assertEqual(result["searched_gateways"], 1)
        self.assertEqual(result["viable_gateways"], 0)
        self.assertEqual(result["not_searched_budget"], 2)
        self.assertEqual(len(calls), 2)
        self.assertFalse(result["coverage_evaluation"]["continue_search"])
        self.assertIn("max_batches_reached", result["coverage_evaluation"]["reasons"])
        self.assertEqual(
            [gateway["gateway"] for gateway in result["gateways"]],
            ["IST", "DXB", "BEG"],
        )
        self.assertEqual(
            result["gateways"][1]["skipped_reasons"],
            ["gateway_probe_budget_exhausted"],
        )

    def test_multiple_destination_dates_are_merged_into_one_gateway_leg(self) -> None:
        queries = gateway_queries("IST")
        next_day = dict(queries[1])
        next_day["date"] = "2026-08-16"
        result, calls = self.run_executor(
            [*queries, next_day],
            offers_by_pair={("SVX", "IST"): 1, ("IST", "AMS"): 1},
        )

        self.assertEqual(len(calls), 3)
        destination_leg = result["gateways"][0]["destination_leg"]
        self.assertEqual(destination_leg["offer_count"], 2)
        self.assertEqual(
            destination_leg["searched_dates"], ["2026-08-15", "2026-08-16"]
        )

    def test_same_gateway_is_executed_independently_for_round_trip_directions(
        self,
    ) -> None:
        outbound_direct = gateway_queries("IST", destination="CDG")
        return_direct = [
            {
                **outbound_direct[0],
                "direction": "return",
                "origin": "CDG",
                "destination": "IST",
                "date": "2026-08-22",
                "provider": "tutu",
            },
            {
                **outbound_direct[1],
                "direction": "return",
                "origin": "IST",
                "destination": "SVX",
                "date": "2026-08-22",
                "provider": "tutu",
            },
        ]

        def broad_copy(query: dict[str, Any]) -> dict[str, Any]:
            return {
                **query,
                "probe_type": "segment_hub_leg",
                "direct_only": False,
            }

        queries = [
            outbound_direct[0],
            broad_copy(outbound_direct[0]),
            outbound_direct[1],
            broad_copy(outbound_direct[1]),
            return_direct[0],
            broad_copy(return_direct[0]),
            return_direct[1],
            broad_copy(return_direct[1]),
        ]
        calls: list[tuple[str, str, bool]] = []
        ledger = ProbeRunLedger()

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            direction = str(spec["direction"])
            direct_only = bool(spec["direct_only"])
            calls.append((direction, str(spec["leg"]), direct_only))
            offer_count = 1 if direction == "outbound" or not direct_only else 0
            return [outcome_for(spec, offer_count=offer_count)]

        executor = GatewayLegProbeExecutor(
            options=executor_options(
                gateway_discovery_limit=1,
                gateway_probe_batch_size=1,
                gateway_probe_max_batches=1,
            ),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
            probe_ledger=ledger,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(queries, {"currency": "RUB"})

        self.assertEqual(result["searched_gateways"], 2)
        self.assertEqual(result["viable_gateways"], 2)
        self.assertEqual(
            [
                (gateway["direction"], gateway["gateway"])
                for gateway in result["gateways"]
            ],
            [("outbound", "IST"), ("return", "IST")],
        )
        self.assertEqual(
            [gateway["origin_leg"]["direction"] for gateway in result["gateways"]],
            ["outbound", "return"],
        )
        self.assertEqual(
            [gateway["destination_leg"]["direction"] for gateway in result["gateways"]],
            ["outbound", "return"],
        )
        self.assertEqual(
            [evaluation["direction"] for evaluation in result["coverage_evaluations"]],
            ["outbound", "return"],
        )
        self.assertFalse(
            any(
                direction == "outbound" and not direct_only
                for direction, _leg, direct_only in calls
            )
        )
        self.assertEqual(
            {
                leg
                for direction, leg, direct_only in calls
                if direction == "return" and not direct_only
            },
            {"origin_to_gateway", "gateway_to_destination"},
        )
        diagnostics = ledger.to_diagnostics()
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )


if __name__ == "__main__":
    unittest.main()
