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
from flights_cli.store import Store


def executor_options(**overrides: object) -> GatewayLegProbeOptions:
    values = {
        "gateway_discovery_limit": 10,
        "gateway_probe_batch_size": 10,
        "gateway_probe_max_batches": 1,
        "segment_limit": 3,
        "timeout": 10,
        "fli_mcp_url": "http://127.0.0.1:8000/mcp",
        "fail_fast": False,
    }
    values.update(overrides)
    return GatewayLegProbeOptions(**values)


def gateway_queries(
    gateway: str,
    *,
    rank: int = 1,
    destination: str = "AMS",
) -> list[dict[str, Any]]:
    return [
        {
            "role": "gateway_leg_probe",
            "source_type": "gateway_discovery_candidate",
            "probe_type": "segment_direct",
            "direction": "outbound",
            "leg": "origin_to_gateway",
            "origin": "SVX",
            "destination": gateway,
            "date": "2026-08-15",
            "currency": "RUB",
            "direct_only": True,
            "gateway": gateway,
            "gateway_rank": rank,
            "provider": "kupibilet",
            "execution_state": "not_executed",
        },
        {
            "role": "gateway_leg_probe",
            "source_type": "gateway_discovery_candidate",
            "probe_type": "segment_direct",
            "direction": "outbound",
            "leg": "gateway_to_destination",
            "origin": gateway,
            "destination": destination,
            "date": "2026-08-15",
            "currency": "RUB",
            "direct_only": True,
            "gateway": gateway,
            "gateway_rank": rank,
            "provider": "fli",
            "execution_state": "not_executed",
        },
    ]


def outcome_for(spec: dict[str, Any], *, offer_count: int) -> SegmentProbeOutcome:
    offers = [{"id": f"offer-{index}"} for index in range(offer_count)]
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
        self.assertEqual(result["failed_gateways"], 0)
        gateway = result["gateways"][0]
        self.assertTrue(gateway["viable"])
        self.assertEqual(gateway["origin_leg"]["offer_count"], 1)
        self.assertEqual(gateway["destination_leg"]["offer_count"], 1)
        self.assertEqual([call["provider_policy"] for call in calls], ["kupibilet", "fli"])

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

    def test_provider_failure_does_not_stop_other_gateways_without_fail_fast(
        self,
    ) -> None:
        calls: list[tuple[str, str]] = []

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            pair = (str(spec["origin"]), str(spec["destination"]))
            calls.append(pair)
            if pair == ("IST", "AMS"):
                raise CliError("provider down", error_type="provider_unavailable")
            return [outcome_for(spec, offer_count=1)]

        executor = GatewayLegProbeExecutor(
            options=executor_options(),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
        )
        queries = [
            *gateway_queries("IST", rank=1),
            *gateway_queries("DXB", rank=2),
        ]
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(queries, {"currency": "RUB"})

        self.assertEqual(result["searched_gateways"], 2)
        self.assertEqual(result["viable_gateways"], 1)
        self.assertEqual(result["failed_gateways"], 1)
        self.assertIn(("DXB", "AMS"), calls)
        ist = result["gateways"][0]
        self.assertEqual(ist["gateway"], "IST")
        self.assertFalse(ist["viable"])
        self.assertEqual(
            ist["provider_failures"][0]["error"]["classification"],
            "provider_unavailable",
        )

    def test_provider_failure_raises_when_fail_fast_enabled(self) -> None:
        def dispatch(**_: Any) -> list[SegmentProbeOutcome]:
            raise CliError("provider down", error_type="provider_unavailable")

        executor = GatewayLegProbeExecutor(
            options=executor_options(fail_fast=True),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
        )
        with patch(
            "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            with self.assertRaises(CliError):
                executor.run(gateway_queries("IST"), {"currency": "RUB"})

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


if __name__ == "__main__":
    unittest.main()
