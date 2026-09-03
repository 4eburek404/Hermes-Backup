from __future__ import annotations

import unittest

from flights_cli.reporting.evidence import (
    all_planned_probes_are_terminal,
    build_evidence,
)


def ledger(**overrides: object) -> dict:
    facts: dict = {
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


class AnswerEvidenceTests(unittest.TestCase):
    def test_evidence_names_who_was_asked(self) -> None:
        evidence = build_evidence(
            ledger(
                planned_probes=[{"probe_id": "p1"}, {"probe_id": "p2"}],
                searched_probes=[
                    {"probe_id": "p1", "provider": "tutu"},
                    {"probe_id": "p2", "provider": "tutu"},
                ],
            )
        )

        # Именно этого не было в двенадцати полях покрытия: провайдер,
        # отброшенный по возможностям, до пробы не доходит, и без списка
        # спрошенных ответ выглядел полным.
        self.assertEqual(evidence["providers_searched"], ["tutu"])
        self.assertTrue(evidence["complete"])

    def test_failed_probe_makes_the_answer_incomplete(self) -> None:
        evidence = build_evidence(
            ledger(
                planned_probes=[{"probe_id": "p1"}, {"probe_id": "p2"}],
                searched_probes=[{"probe_id": "p1", "provider": "tutu"}],
                failed_probes=[
                    {
                        "probe_id": "p2",
                        "provider": "kupibilet",
                        "error": {
                            "type": "upstream_error",
                            "classification": "blocked_response",
                            "retryable": False,
                        },
                    }
                ],
            )
        )

        self.assertFalse(evidence["complete"])
        self.assertEqual(
            evidence["provider_failures"],
            [
                {
                    "provider": "kupibilet",
                    "classification": "blocked_response",
                    "retryable": False,
                }
            ],
        )
        # Упавшая проба всё же терминальна: она не потерялась.
        self.assertTrue(
            all_planned_probes_are_terminal(
                ledger(
                    planned_probes=[{"probe_id": "p2"}],
                    failed_probes=[{"probe_id": "p2"}],
                )
            )
        )

    def test_unfinished_probe_makes_the_answer_incomplete(self) -> None:
        facts = ledger(
            planned_probes=[{"probe_id": "p1"}, {"probe_id": "p2"}],
            searched_probes=[{"probe_id": "p1", "provider": "tutu"}],
            not_executed_probes=[{"probe_id": "p2"}],
        )

        self.assertTrue(all_planned_probes_are_terminal(facts))
        self.assertFalse(build_evidence(facts)["complete"])

    def test_lost_probe_is_not_terminal(self) -> None:
        facts = ledger(planned_probes=[{"probe_id": "p1"}, {"probe_id": "p2"}])

        self.assertFalse(all_planned_probes_are_terminal(facts))
        self.assertFalse(build_evidence(facts)["complete"])

    def test_broken_ledger_shape_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            build_evidence({"planned_probes": []})
        with self.assertRaises(ValueError):
            build_evidence(None)
        with self.assertRaises(ValueError):
            build_evidence(ledger(searched_probes={"probe_id": "p1"}))

    def test_date_window_rides_along_only_when_it_exists(self) -> None:
        facts = ledger(
            planned_probes=[{"probe_id": "p1"}],
            searched_probes=[{"probe_id": "p1", "provider": "tutu"}],
        )
        window = {
            "start": "2026-10-01",
            "end": "2026-10-02",
            "dates": [
                {"date": "2026-10-01", "status": "direct_offers", "offer_count": 2},
                {"date": "2026-10-02", "status": "no_direct_offers", "offer_count": 0},
            ],
        }

        self.assertNotIn("date_window", build_evidence(facts))
        self.assertEqual(
            build_evidence(facts, date_window=window)["date_window"], window
        )


if __name__ == "__main__":
    unittest.main()
