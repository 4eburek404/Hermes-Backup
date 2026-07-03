from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from flights_cli.errors import CliError
from flights_cli.execution.offer_query_runner import (
    PrimaryOfferQueryOptions,
    run_primary_offer_queries,
)
from flights_cli.execution.probe_ledger import ProbeExecutionLedger
from flights_cli.ports.providers import ProviderProbeResult
from flights_cli.store import Store


def store_with_airports(test_case: unittest.TestCase) -> Store:
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    cache = Path(tmp_dir.name)
    (cache / "airports_en.json").write_text(
        """
        [
          {"code": "SVX", "country_code": "RU", "flightable": true},
          {"code": "CDG", "country_code": "FR", "flightable": true}
        ]
        """,
        encoding="utf-8",
    )
    return Store(cache)


def primary_query(**overrides: Any) -> dict[str, Any]:
    query = {
        "role": "primary_offer_collection",
        "source_type": "provider_full_route",
        "probe_type": "full_route_aggregate",
        "provider": "kupibilet",
        "direction": "outbound",
        "origin": "SVX",
        "destination": "CDG",
        "date": "2026-08-16",
        "currency": "RUB",
        "direct_only": False,
        "limit": 10,
    }
    query.update(overrides)
    return query


class FailingAggregateAdapter:
    name = "kupibilet"

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        raise CliError(
            "provider timed out",
            error_type="timeout",
            details={"http_status": 504},
        )


class OfferQueryRunnerTests(unittest.TestCase):
    def test_provider_failure_is_structured_and_recorded_in_ledger(self) -> None:
        ledger = ProbeExecutionLedger()

        with patch(
            "flights_cli.execution.offer_query_runner.provider_adapter",
            return_value=FailingAggregateAdapter(),
        ):
            results = run_primary_offer_queries(
                [primary_query(probe_id="primary-1")],
                PrimaryOfferQueryOptions(no_live_cache=True),
                store=store_with_airports(self),
                probe_ledger=ledger,
            )

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted"})
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(results[0]["execution_state"], "failed")
        self.assertEqual(results[0]["error"]["classification"], "timeout")
        self.assertEqual(results[0]["probe_id"], "primary-1")
        self.assertEqual(
            [item["provider"] for item in diagnostics["failed_controls"]],
            ["kupibilet"],
        )

    def test_not_supported_provider_result_is_recorded_in_ledger(self) -> None:
        ledger = ProbeExecutionLedger()

        results = run_primary_offer_queries(
            [primary_query(provider="fli", probe_id="primary-fli")],
            PrimaryOfferQueryOptions(no_live_cache=True),
            store=store_with_airports(self),
            probe_ledger=ledger,
        )

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted"})
        self.assertEqual(results[0]["status"], "not_supported")
        self.assertEqual(results[0]["execution_state"], "not_supported")
        self.assertEqual(results[0]["provider"], "fli")
        self.assertEqual(
            [item["probe_id"] for item in diagnostics["not_supported_controls"]],
            ["primary-fli"],
        )

    def test_non_primary_offer_query_is_skipped_and_recorded_in_ledger(self) -> None:
        ledger = ProbeExecutionLedger()

        results = run_primary_offer_queries(
            [primary_query(role="mandatory_control", probe_id="skip-1")],
            PrimaryOfferQueryOptions(no_live_cache=True),
            store=store_with_airports(self),
            probe_ledger=ledger,
        )

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted"})
        self.assertEqual(results[0]["status"], "skipped")
        self.assertEqual(results[0]["reason"], "not_primary_offer_collection")
        self.assertEqual(
            [item["probe_id"] for item in diagnostics["skipped_controls"]],
            ["skip-1"],
        )

    def test_primary_offer_query_wave_index_is_recorded_in_ledger(self) -> None:
        ledger = ProbeExecutionLedger()

        results = run_primary_offer_queries(
            [primary_query(provider="fli", probe_id="primary-fli", wave_index=0)],
            PrimaryOfferQueryOptions(no_live_cache=True),
            store=store_with_airports(self),
            probe_ledger=ledger,
        )

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted"})
        self.assertEqual(results[0]["status"], "not_supported")
        self.assertEqual(diagnostics["planned_controls"][0]["wave_index"], 0)
        self.assertEqual(diagnostics["not_supported_controls"][0]["wave_index"], 0)


if __name__ == "__main__":
    unittest.main()
