from __future__ import annotations

import unittest

from flights_cli.reporting.coverage import CoverageSnapshot


def ledger_facts(**overrides: object) -> dict:
    facts = {
        "planned_probes": [],
        "searched_probes": [],
        "skipped_probes": [],
        "failed_probes": [],
        "unsupported_probes": [],
        "not_executed_probes": [],
        "deduped_probes": [],
    }
    facts.update(overrides)
    return facts


class CoverageSnapshotTests(unittest.TestCase):
    def test_snapshot_owns_compact_and_answer_coverage_views(self) -> None:
        live = {
            "probe_ledger": ledger_facts(
                planned_probes=[{"probe_id": "p1"}, {"probe_id": "p2"}],
                searched_probes=[{"probe_id": "p1"}],
                failed_probes=[
                    {
                        "probe_id": "p2",
                        "provider": "tutu",
                        "error": {"type": "upstream_error", "message": "offline"},
                    }
                ],
            ),
        }

        snapshot = CoverageSnapshot.from_live(live)

        self.assertEqual(
            snapshot.summary["blocking_evidence"],
            ["failed_probes"],
        )
        self.assertEqual(
            snapshot.answer_evidence_status["answerability"], "answerable_with_caveats"
        )
        self.assertEqual(snapshot.answer_evidence_status["planned_probe_count"], 2)
        self.assertEqual(snapshot.answer_evidence_status["terminal_probe_count"], 2)
        self.assertEqual(snapshot.answer_evidence_status["provider_failure_count"], 1)

    def test_snapshot_is_defensive_against_source_mutation(self) -> None:
        diagnostics = ledger_facts(
            planned_probes=[{"probe_id": "p1"}],
            searched_probes=[{"probe_id": "p1"}],
        )
        snapshot = CoverageSnapshot.from_diagnostics(diagnostics)

        diagnostics["not_executed_probes"].append({"probe_id": "late"})

        self.assertEqual(snapshot.diagnostics["not_executed_probes"], [])
        self.assertTrue(snapshot.answer_evidence_status["evidence_complete"])

    def test_deduped_probe_is_a_terminal_state(self) -> None:
        snapshot = CoverageSnapshot.from_diagnostics(
            ledger_facts(
                planned_probes=[{"probe_id": "p1"}],
                deduped_probes=[{"probe_id": "p1", "original_probe_id": "original"}],
            )
        )

        self.assertEqual(snapshot.summary["completeness"]["terminal_count"], 1)
        self.assertTrue(
            snapshot.summary["completeness"]["all_planned_probes_have_terminal_state"]
        )

    def test_provider_failure_count_is_not_truncated_with_compact_details(self) -> None:
        failures = [
            {
                "probe_id": f"p{index}",
                "provider": "fake",
                "error": {"type": "upstream_error", "message": "offline"},
            }
            for index in range(3)
        ]
        snapshot = CoverageSnapshot.from_diagnostics(
            ledger_facts(
                planned_probes=[{"probe_id": item["probe_id"]} for item in failures],
                failed_probes=failures,
            ),
            failure_limit=1,
        )

        self.assertEqual(len(snapshot.provider_failures), 1)
        self.assertEqual(snapshot.answer_evidence_status["provider_failure_count"], 3)

    def test_live_snapshot_ignores_parallel_failure_fields(self) -> None:
        snapshot = CoverageSnapshot.from_live(
            {
                "probe_ledger": ledger_facts(),
                "failures": [
                    {
                        "probe_id": "legacy",
                        "provider": "fake",
                        "error": {"type": "upstream_error", "message": "stale"},
                    }
                ],
            }
        )

        self.assertEqual(snapshot.provider_failures, ())
        self.assertEqual(snapshot.answer_evidence_status["provider_failure_count"], 0)

    def test_snapshot_requires_the_complete_production_ledger_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing buckets"):
            CoverageSnapshot.from_diagnostics({"planned_probes": []})

        with self.assertRaisesRegex(ValueError, "requires a production probe_ledger"):
            CoverageSnapshot.from_live({})

    def test_snapshot_does_not_read_legacy_coverage_semantics(self) -> None:
        snapshot = CoverageSnapshot.from_diagnostics(
            {
                **ledger_facts(
                    planned_probes=[{"probe_id": "p1"}],
                    searched_probes=[{"probe_id": "p1"}],
                ),
                "negative_evidence_type": "legacy",
                "coverage_warnings": ["legacy"],
                "completeness": {
                    "planned_count": 99,
                    "terminal_count": 0,
                    "all_planned_probes_have_terminal_state": False,
                },
            }
        )

        self.assertEqual(
            snapshot.diagnostics["negative_evidence_type"],
            "bounded_live_probes_only",
        )
        self.assertNotEqual(snapshot.diagnostics["coverage_warnings"], ["legacy"])
        self.assertEqual(snapshot.summary["completeness"]["planned_count"], 1)
        self.assertEqual(snapshot.summary["completeness"]["terminal_count"], 1)
        self.assertTrue(
            snapshot.summary["completeness"]["all_planned_probes_have_terminal_state"]
        )


if __name__ == "__main__":
    unittest.main()
