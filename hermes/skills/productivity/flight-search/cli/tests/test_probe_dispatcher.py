from __future__ import annotations

import argparse
import unittest
from datetime import date
from unittest.mock import patch

from flights_cli.errors import CliError
from flights_cli.execution.probe_dispatcher import dispatch_segment_probe, search_key
from flights_cli.execution.request_deduper import RequestDeduper
from flights_cli.store import Store


def dispatcher_args(**overrides: object) -> argparse.Namespace:
    values = {
        "segment_limit": 3,
        "timeout": 10,
        "fli_mcp_url": None,
        "fail_fast": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ProbeDispatcherTests(unittest.TestCase):
    def test_search_key_matches_logical_segment_identity(self) -> None:
        self.assertEqual(
            search_key({"direction": "outbound", "leg": "direct", "origin": "svx", "destination": "ist"}),
            ("outbound", "direct", "SVX", "IST"),
        )

    def test_dispatches_kupibilet_segment_with_fake_provider_call(self) -> None:
        spec = {"direction": "outbound", "leg": "origin_to_hub", "origin": "SVX", "destination": "IST", "date": "2026-08-12"}
        plan = {"currency": "RUB"}
        segment_result = {"direction": "outbound", "leg": "origin_to_hub", "offers": [{"id": "offer-1"}]}
        summary = {"status": "ok", "offer_count": 1}

        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["kupibilet"]), \
            patch("flights_cli.execution.probe_dispatcher.cached_kupibilet_search", return_value={"offers": [{"id": "raw-1"}]}) as search, \
            patch("flights_cli.execution.probe_dispatcher.kupibilet_result_to_segment_result", return_value=segment_result), \
            patch("flights_cli.execution.probe_dispatcher.kupibilet_segment_search_summary", return_value=summary):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                args=dispatcher_args(),
                store=Store(),
                only_carriers=["SU"],
                cache_ttl_seconds=30,
                use_live_cache=True,
                provider_policy="kupibilet",
            )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].summary["status"], "ok")
        self.assertEqual(outcomes[0].summary["offer_count"], 1)
        self.assertEqual(outcomes[0].summary["provider"], "kupibilet")
        self.assertEqual(outcomes[0].summary["cache_status"], "unknown")
        self.assertEqual(outcomes[0].segment_result, segment_result)
        self.assertIsNone(outcomes[0].failure)
        call = search.call_args
        self.assertEqual(call.args[:3], ("SVX", "IST", date(2026, 8, 12)))
        self.assertEqual(call.kwargs["only_carriers"], ["SU"])
        self.assertTrue(call.kwargs["direct_only"])
        self.assertTrue(call.kwargs["use_cache"])

    def test_provider_error_returns_failure_outcome_without_raising_when_not_fail_fast(self) -> None:
        spec = {"direction": "outbound", "leg": "hub_to_destination", "origin": "IST", "destination": "LHR", "date": "2026-08-12"}
        plan = {"currency": "RUB"}

        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["fli"]), \
            patch("flights_cli.execution.probe_dispatcher.cached_fli_mcp_search", side_effect=CliError("provider down", error_type="provider_unavailable")):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                args=dispatcher_args(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="fli",
            )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].summary["status"], "error")
        self.assertEqual(outcomes[0].failure, outcomes[0].summary)
        self.assertEqual(outcomes[0].failure["provider"], "fli")
        self.assertEqual(outcomes[0].failure["error"]["type"], "provider_unavailable")
        self.assertEqual(outcomes[0].failure["error"]["classification"], "provider_unavailable")

    def test_fail_fast_re_raises_provider_error(self) -> None:
        spec = {"direction": "outbound", "leg": "hub_to_destination", "origin": "IST", "destination": "LHR", "date": "2026-08-12"}
        plan = {"currency": "RUB"}

        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["fli"]), \
            patch("flights_cli.execution.probe_dispatcher.cached_fli_mcp_search", side_effect=CliError("provider down", error_type="provider_unavailable")):
            with self.assertRaises(CliError):
                dispatch_segment_probe(
                    spec=spec,
                    plan=plan,
                    args=dispatcher_args(fail_fast=True),
                    store=Store(),
                    only_carriers=[],
                    cache_ttl_seconds=0,
                    use_live_cache=False,
                    provider_policy="fli",
                )

    def test_duplicate_segment_probe_reuses_original_result_without_second_provider_call(self) -> None:
        spec = {"direction": "outbound", "leg": "origin_to_hub", "origin": "SVX", "destination": "IST", "date": "2026-08-12"}
        plan = {"currency": "RUB"}
        deduper = RequestDeduper()
        segment_result = {"direction": "outbound", "leg": "origin_to_hub", "offers": [{"id": "offer-1"}]}

        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["kupibilet"]), \
            patch("flights_cli.execution.probe_dispatcher.cached_kupibilet_search", return_value={"offers": [{"id": "raw-1"}], "cache": {"hit": False}}) as search, \
            patch("flights_cli.execution.probe_dispatcher.kupibilet_result_to_segment_result", return_value=segment_result), \
            patch("flights_cli.execution.probe_dispatcher.kupibilet_segment_search_summary", return_value={"status": "ok", "offer_count": 1}):
            first = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                args=dispatcher_args(),
                store=Store(),
                only_carriers=["SU"],
                cache_ttl_seconds=30,
                use_live_cache=True,
                provider_policy="kupibilet",
                request_deduper=deduper,
            )
            second = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                args=dispatcher_args(),
                store=Store(),
                only_carriers=["SU"],
                cache_ttl_seconds=30,
                use_live_cache=True,
                provider_policy="kupibilet",
                request_deduper=deduper,
            )

        self.assertEqual(search.call_count, 1)
        self.assertEqual(first[0].summary["status"], "ok")
        self.assertEqual(second[0].summary["status"], "deduped")
        self.assertEqual(second[0].summary["original_probe_id"], first[0].summary["probe_id"])
        self.assertEqual(second[0].segment_result, segment_result)
        self.assertFalse(second[0].include_segment_result)


if __name__ == "__main__":
    unittest.main()
