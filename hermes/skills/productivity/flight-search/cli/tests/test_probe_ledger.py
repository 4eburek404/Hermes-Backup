from __future__ import annotations

import unittest

from flights_cli.execution.probe_intent import ProbeIntent
from flights_cli.execution.probe_ledger import ProbeRunLedger
from flights_cli.ports.providers import ProviderProbeResult
from flights_cli.reporting.coverage import PROBE_BUCKETS
from helpers import coverage_completeness


def probe(**overrides: object) -> dict:
    values = {
        "type": "carrier_aggregate",
        "direction": "outbound",
        "origin": "SVX",
        "destination": "CDG",
        "date": "2026-08-16",
        "carrier": "SU",
    }
    values.update(overrides)
    return values


def terminal_bucket_count(diagnostics: dict) -> int:
    return sum(
        len(diagnostics[name])
        for name in (
            "searched_probes",
            "skipped_probes",
            "failed_probes",
            "unsupported_probes",
            "not_executed_probes",
            "deduped_probes",
        )
    )


class ProbeRunLedgerTests(unittest.TestCase):
    def test_provider_result_terminal_states_are_exhaustively_mapped(self) -> None:
        bucket_by_state = {
            "searched": "searched_probes",
            "skipped": "skipped_probes",
            "failed": "failed_probes",
            "not_executed": "not_executed_probes",
            "not_supported": "unsupported_probes",
        }
        for state, bucket in bucket_by_state.items():
            with self.subTest(state=state):
                item = probe(probe_id=f"state-{state}", provider="tutu")
                ledger = ProbeRunLedger()
                ledger.plan_probes([item])
                result = ProviderProbeResult(
                    probe_id=f"state-{state}",
                    probe_type="carrier_aggregate",
                    provider="tutu",
                    query=item,
                    execution_state=state,  # type: ignore[arg-type]
                    evidence_type=(
                        "provider_unavailable"
                        if state == "failed"
                        else "not_supported"
                        if state == "not_supported"
                        else "not_executed"
                    ),
                    result_summary={"reason": f"reason-{state}"},
                    errors=(
                        ({"type": "timeout", "message": "timed out"},)
                        if state == "failed"
                        else ()
                    ),
                )

                ledger.record_provider_result(item, result)
                diagnostics = ledger.to_diagnostics()

                self.assertEqual(len(diagnostics[bucket]), 1)
                self.assertEqual(terminal_bucket_count(diagnostics), 1)

    def test_probe_intent_plans_and_records_full_route_aggregate(self) -> None:
        intent = ProbeIntent(
            probe_type="full_route_aggregate",
            direction="outbound",
            origin="SVX",
            destination="CDG",
            date="2026-08-16",
            provider="kupibilet",
            probe_id="aggregate:kupibilet:outbound:SVX-CDG:2026-08-16:all",
            negative_evidence="aggregate_empty_only_not_route_absence",
        )
        ledger = ProbeRunLedger()
        ledger.plan_intents([intent])
        ledger.record_searched(
            intent,
            status="ok",
            provider="kupibilet",
            offer_count=2,
            cache_status="live",
        )
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()

        self.assertEqual(set(diagnostics), set(PROBE_BUCKETS))
        self.assertEqual(
            [item["type"] for item in diagnostics["planned_probes"]],
            ["full_route_aggregate"],
        )
        self.assertEqual(len(diagnostics["searched_probes"]), 1)
        self.assertEqual(
            diagnostics["searched_probes"][0]["execution_state"], "searched"
        )
        self.assertEqual(diagnostics["searched_probes"][0]["provider"], "kupibilet")
        self.assertEqual(diagnostics["searched_probes"][0]["offer_count"], 2)
        self.assertEqual(diagnostics["not_executed_probes"], [])
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )

    def test_provider_attempt_budget_marks_remaining_probe_not_executed(self) -> None:
        first = probe(probe_id="primary-001", provider="tutu")
        second = probe(probe_id="primary-002", provider="kupibilet")
        ledger = ProbeRunLedger(max_physical_attempts=1)
        ledger.plan_probes([first, second])

        first_claim = ledger.claim_probe(first)
        second_claim = ledger.claim_probe(second)

        self.assertTrue(first_claim.execution_allowed)
        self.assertFalse(second_claim.execution_allowed)
        self.assertEqual(
            second_claim.blocked_reason,
            "provider_attempt_budget_exhausted",
        )
        ledger.record_searched(
            first,
            status="ok",
            provider="tutu",
            offer_count=0,
        )
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()
        self.assertEqual(
            [item["probe_id"] for item in diagnostics["searched_probes"]],
            ["primary-001"],
        )
        self.assertEqual(
            [item["probe_id"] for item in diagnostics["not_executed_probes"]],
            ["primary-002"],
        )
        self.assertEqual(
            diagnostics["not_executed_probes"][0]["reason"],
            "provider_attempt_budget_exhausted",
        )
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )

    def test_probe_intent_records_not_supported_terminal_state(self) -> None:
        intent = ProbeIntent(
            probe_type="carrier_aggregate",
            direction="outbound",
            origin="SVX",
            destination="CDG",
            date="2026-08-16",
            provider="tutu",
            carrier="SU",
            probe_id="aggregate:tutu:outbound:SVX-CDG:2026-08-16:SU",
        )
        ledger = ProbeRunLedger()
        ledger.plan_intents([intent])
        ledger.record_not_supported(
            intent, provider="tutu", reason="aggregate_probe_not_supported"
        )
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()

        self.assertEqual(diagnostics["searched_probes"], [])
        self.assertEqual(len(diagnostics["unsupported_probes"]), 1)
        self.assertEqual(
            diagnostics["unsupported_probes"][0]["execution_state"], "not_supported"
        )
        self.assertEqual(diagnostics["unsupported_probes"][0]["provider"], "tutu")
        self.assertEqual(diagnostics["not_executed_probes"], [])
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )

    def test_planned_probe_without_runtime_event_becomes_not_executed(self) -> None:
        ledger = ProbeRunLedger()
        ledger.plan_probes([probe()])
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()

        self.assertEqual(len(diagnostics["not_executed_probes"]), 1)
        self.assertEqual(
            diagnostics["not_executed_probes"][0]["execution_state"], "not_executed"
        )
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )

    def test_failed_full_route_probe_appears_in_failed_probes(self) -> None:
        item = probe(type="full_route_aggregate", carrier=None)
        ledger = ProbeRunLedger()
        ledger.plan_probes([item])
        ledger.record_failed(
            item,
            provider="kupibilet",
            error={"type": "provider_error", "message": "timeout"},
        )
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()

        self.assertEqual(len(diagnostics["failed_probes"]), 1)
        self.assertEqual(diagnostics["failed_probes"][0]["execution_state"], "failed")
        self.assertEqual(diagnostics["failed_probes"][0]["provider"], "kupibilet")
        self.assertEqual(diagnostics["not_executed_probes"], [])
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )

    def test_repeated_terminal_write_is_idempotent(self) -> None:
        item = probe()
        ledger = ProbeRunLedger()
        ledger.plan_probes([item])
        ledger.record_searched(item, status="ok", provider="kupibilet", offer_count=0)
        ledger.record_searched(item, status="ok", provider="kupibilet", offer_count=0)
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()

        self.assertEqual(len(diagnostics["searched_probes"]), 1)
        self.assertEqual(diagnostics["deduped_probes"], [])
        self.assertEqual(coverage_completeness(diagnostics)["planned_count"], 1)
        self.assertEqual(terminal_bucket_count(diagnostics), 1)
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )

    def test_real_duplicate_is_a_distinct_planned_terminal_probe(self) -> None:
        first = probe(probe_id="primary-001", provider="kupibilet")
        duplicate = probe(probe_id="primary-002", provider="kupibilet")
        ledger = ProbeRunLedger()

        ledger.plan_probes([first, duplicate])
        ledger.record_searched(
            first,
            status="ok",
            provider="kupibilet",
            offer_count=0,
        )
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_diagnostics()
        self.assertEqual(
            [item["probe_id"] for item in diagnostics["planned_probes"]],
            ["primary-001", "primary-002"],
        )
        self.assertEqual(
            diagnostics["deduped_probes"],
            [
                {
                    "type": "carrier_aggregate",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "CDG",
                    "date": "2026-08-16",
                    "carrier": "SU",
                    "provider": "kupibilet",
                    "probe_id": "primary-002",
                    "execution_state": "deduped",
                    "status": "deduped",
                    "original_probe_id": "primary-001",
                }
            ],
        )
        self.assertEqual(coverage_completeness(diagnostics)["planned_count"], 2)
        self.assertEqual(
            coverage_completeness(diagnostics)["terminal_count"],
            terminal_bucket_count(diagnostics),
        )
        self.assertEqual(terminal_bucket_count(diagnostics), 2)

    def test_terminal_skipped_probe_cannot_be_reopened(self) -> None:
        item = probe(type="segment_hub_leg", leg="origin_to_gateway", provider="tutu")
        ledger = ProbeRunLedger()
        ledger.plan_probes([item])
        ledger.record_skipped(item, reason="direct_mode")
        ledger.finalize_unexecuted()

        ledger.plan_probes([item])
        ledger.record_searched(
            item,
            status="ok",
            provider="tutu",
            offer_count=1,
            cache_status="disabled",
        )
        ledger.finalize_unexecuted()
        diagnostics = ledger.to_diagnostics()

        self.assertEqual(diagnostics["searched_probes"], [])
        self.assertEqual(len(diagnostics["skipped_probes"]), 1)
        self.assertEqual(diagnostics["not_executed_probes"], [])
        self.assertEqual(len(diagnostics["deduped_probes"]), 1)
        self.assertEqual(
            diagnostics["deduped_probes"][0]["original_probe_id"],
            diagnostics["skipped_probes"][0]["probe_id"],
        )
        self.assertEqual(
            coverage_completeness(diagnostics)["terminal_count"],
            terminal_bucket_count(diagnostics),
        )
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )

    def test_terminal_not_executed_probe_cannot_be_reopened(self) -> None:
        item = probe(type="segment_hub_leg", leg="gateway_to_destination")
        ledger = ProbeRunLedger()
        ledger.plan_probes([item])
        ledger.finalize_unexecuted()

        ledger.record_searched(
            item,
            status="ok",
            provider="tutu",
            offer_count=1,
            cache_status="disabled",
        )
        ledger.finalize_unexecuted()
        diagnostics = ledger.to_diagnostics()

        self.assertEqual(diagnostics["searched_probes"], [])
        self.assertEqual(len(diagnostics["not_executed_probes"]), 1)
        self.assertEqual(diagnostics["deduped_probes"], [])
        self.assertEqual(
            coverage_completeness(diagnostics)["terminal_count"],
            terminal_bucket_count(diagnostics),
        )
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )

    def test_role_and_gateway_metadata_do_not_create_a_second_physical_query(
        self,
    ) -> None:
        first = probe(
            probe_id="gateway-001",
            provider="tutu",
            role="gateway_leg_probe",
            gateway="IST",
            origin="IST",
            destination="AMS",
            currency="RUB",
            direct_only=True,
            limit=30,
        )
        duplicate = {
            **first,
            "probe_id": "gateway-002",
            "role": "diagnostic_copy",
            "gateway": "DXB",
            "candidate_score": 0.2,
        }
        ledger = ProbeRunLedger()

        ledger.plan_probes([first, duplicate])
        first_claim = ledger.claim_probe(first)
        duplicate_claim = ledger.claim_probe(duplicate)

        self.assertFalse(first_claim.is_duplicate)
        self.assertTrue(duplicate_claim.is_duplicate)
        self.assertEqual(duplicate_claim.original_probe_id, "gateway-001")
        ledger.record_searched(first, status="ok", provider="tutu", offer_count=1)
        ledger.finalize_unexecuted()
        diagnostics = ledger.to_diagnostics()
        self.assertEqual(len(diagnostics["searched_probes"]), 1)
        self.assertEqual(len(diagnostics["deduped_probes"]), 1)
        self.assertEqual(diagnostics["deduped_probes"][0]["probe_id"], "gateway-002")
        self.assertEqual(
            diagnostics["deduped_probes"][0]["original_probe_id"], "gateway-001"
        )
        self.assertEqual(coverage_completeness(diagnostics)["planned_count"], 2)
        self.assertEqual(
            coverage_completeness(diagnostics)["terminal_count"],
            terminal_bucket_count(diagnostics),
        )
        self.assertTrue(
            coverage_completeness(diagnostics)["all_planned_probes_have_terminal_state"]
        )


if __name__ == "__main__":
    unittest.main()
