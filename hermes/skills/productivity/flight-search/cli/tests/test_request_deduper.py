from __future__ import annotations

import unittest

from flights_cli.execution.request_deduper import RequestDeduper, segment_probe_key


SPEC = {"direction": "outbound", "leg": "direct", "origin": "SVX", "destination": "IST", "date": "2026-08-12"}
PLAN = {"currency": "RUB"}


class RequestDeduperTests(unittest.TestCase):
    def test_identical_segment_probe_dedupes_to_original(self) -> None:
        deduper = RequestDeduper()
        first = deduper.claim_segment_probe(spec=SPEC, provider="kupibilet", plan=PLAN, only_carriers=["SU"], limit=5, provider_policy="kupibilet")
        deduper.record(first, {"summary": "ok"})
        second = deduper.claim_segment_probe(spec=SPEC, provider="kupibilet", plan=PLAN, only_carriers=["SU"], limit=5, provider_policy="kupibilet")

        self.assertFalse(first.is_duplicate)
        self.assertTrue(second.is_duplicate)
        self.assertEqual(second.original_probe_id, first.probe_id)
        self.assertEqual(second.original, {"summary": "ok"})

    def test_different_provider_date_carrier_or_limit_does_not_dedupe(self) -> None:
        base = segment_probe_key(spec=SPEC, provider="kupibilet", plan=PLAN, only_carriers=["SU"], limit=5, provider_policy="auto", direct_only=True)
        self.assertNotEqual(base, segment_probe_key(spec=SPEC, provider="fli", plan=PLAN, only_carriers=["SU"], limit=5, provider_policy="auto", direct_only=True))
        self.assertNotEqual(base, segment_probe_key(spec={**SPEC, "date": "2026-08-13"}, provider="kupibilet", plan=PLAN, only_carriers=["SU"], limit=5, provider_policy="auto", direct_only=True))
        self.assertNotEqual(base, segment_probe_key(spec=SPEC, provider="kupibilet", plan=PLAN, only_carriers=["EK"], limit=5, provider_policy="auto", direct_only=True))
        self.assertNotEqual(base, segment_probe_key(spec=SPEC, provider="kupibilet", plan=PLAN, only_carriers=["SU"], limit=6, provider_policy="auto", direct_only=True))


if __name__ == "__main__":
    unittest.main()
