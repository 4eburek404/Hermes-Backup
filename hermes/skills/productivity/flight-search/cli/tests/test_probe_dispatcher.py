from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from flights_cli.errors import CliError
from flights_cli.execution.probe_dispatcher import (
    SegmentProbeOptions,
    dispatch_segment_probe,
)
from flights_cli.execution.probe_ledger import ProbeRunLedger
from flights_cli.ports.providers import ProviderCapabilities, ProviderProbeResult
from flights_cli.store import Store
from helpers import coverage_completeness


def dispatcher_options(**overrides: object) -> SegmentProbeOptions:
    values = {
        "segment_limit": 3,
        "timeout": 10,
        "fail_fast": False,
    }
    values.update(overrides)
    return SegmentProbeOptions(**values)


class FakeProviderAdapter:
    name = "kupibilet"
    capabilities = ProviderCapabilities(probe_types=frozenset({"segment_direct"}))

    def __init__(self) -> None:
        self.segment_queries: list[dict[str, object]] = []

    def search_segment(self, query: dict[str, object]) -> ProviderProbeResult:
        self.segment_queries.append(query)
        provider_name = self.name
        segment_result = {
            "direction": query["direction"],
            "leg": query["leg"],
            "offers": [{"id": "adapter-offer"}],
        }
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or "adapter-probe"),
            probe_type="segment_direct",
            provider=provider_name,
            query={
                "origin": query["origin"],
                "destination": query["destination"],
                "date": query["date"],
            },
            execution_state="searched",
            cache_status="disabled",
            evidence_type="positive_live_evidence",
            result_summary={
                "direction": query["direction"],
                "leg": query["leg"],
                "origin": query["origin"],
                "destination": query["destination"],
                "date": query["date"],
                "provider": provider_name,
                "status": "ok",
                "offer_count": 1,
            },
            offers=tuple(segment_result["offers"]),
        )

    def search_aggregate(self, query: dict[str, object]) -> ProviderProbeResult:
        raise AssertionError("not used by segment dispatcher")


class NamedFakeProviderAdapter(FakeProviderAdapter):
    def __init__(self, name: str) -> None:
        self.name = name
        self.segment_queries: list[dict[str, object]] = []


class FailingProviderAdapter(FakeProviderAdapter):
    def search_segment(self, query: dict[str, object]) -> ProviderProbeResult:
        raise CliError("provider down", error_type="provider_unavailable")


class ProbeDispatcherTests(unittest.TestCase):
    def test_dispatches_kupibilet_segment_with_fake_provider_call(self) -> None:
        spec = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVX",
            "destination": "IST",
            "date": "2026-08-12",
        }
        plan = {"currency": "RUB"}
        segment_result = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "offers": [{"id": "offer-1"}],
        }
        summary = {"status": "ok", "offer_count": 1}

        with (
            patch(
                "flights_cli.adapters.providers.registry.providers_for_segment",
                return_value=["kupibilet"],
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.cached_kupibilet_search",
                return_value={"offers": [{"id": "raw-1"}]},
            ) as search,
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.kupibilet_result_to_segment_result",
                return_value=segment_result,
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.kupibilet_segment_search_summary",
                return_value=summary,
            ),
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                options=dispatcher_options(),
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

    def test_dispatcher_executes_segment_probe_through_provider_port(self) -> None:
        spec = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVX",
            "destination": "IST",
            "date": "2026-08-12",
        }
        adapter = FakeProviderAdapter()

        with patch(
            "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
            return_value=[adapter],
            create=True,
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=["SU"],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].summary["provider"], "kupibilet")
        self.assertEqual(outcomes[0].summary["status"], "ok")
        self.assertEqual(outcomes[0].summary["cache_status"], "disabled")
        self.assertEqual(
            outcomes[0].segment_result["offers"], [{"id": "adapter-offer"}]
        )
        self.assertEqual(adapter.segment_queries[0]["only_carriers"], ["SU"])
        self.assertTrue(adapter.segment_queries[0]["direct_only"])

    def test_tutu_segment_success_skips_fallback_adapters(self) -> None:
        spec = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVX",
            "destination": "IST",
            "date": "2026-08-12",
        }
        tutu = NamedFakeProviderAdapter("tutu")
        kupibilet = NamedFakeProviderAdapter("kupibilet")

        with patch(
            "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
            return_value=[tutu, kupibilet],
            create=True,
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="auto",
            )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].summary["provider"], "tutu")
        self.assertEqual(len(tutu.segment_queries), 1)
        self.assertEqual(len(kupibilet.segment_queries), 0)

    def test_dispatcher_preserves_non_direct_access_probe_flag(self) -> None:
        spec = {
            "direction": "outbound",
            "leg": "origin_to_gateway",
            "origin": "NTE",
            "destination": "IST",
            "date": "2026-07-09",
            "direct_only": False,
            "probe_type": "segment_hub_leg",
        }
        adapter = FakeProviderAdapter()

        with patch(
            "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
            return_value=[adapter],
            create=True,
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="tutu",
                probe_ledger=ProbeRunLedger(),
            )

        self.assertEqual(len(outcomes), 1)
        self.assertFalse(adapter.segment_queries[0]["direct_only"])
        self.assertEqual(adapter.segment_queries[0]["probe_type"], "segment_hub_leg")

    def test_dispatcher_preserves_and_normalizes_exact_airport_scope(self) -> None:
        spec = {
            "direction": "outbound",
            "leg": "origin_to_gateway",
            "origin": "ORG",
            "destination": "DST",
            "origin_airports": [" aab ", "AAA", "aaa"],
            "destination_airports": ["bbb"],
            "date": "2026-08-12",
            "direct_only": False,
            "probe_type": "segment_hub_leg",
        }
        adapter = FakeProviderAdapter()

        with patch(
            "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
            return_value=[adapter],
            create=True,
        ):
            dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
                probe_ledger=ProbeRunLedger(),
            )

        self.assertEqual(adapter.segment_queries[0]["origin_airports"], ["AAA", "AAB"])
        self.assertEqual(adapter.segment_queries[0]["destination_airports"], ["BBB"])

    def test_provider_error_returns_failure_outcome_without_raising_when_not_fail_fast(
        self,
    ) -> None:
        spec = {
            "direction": "outbound",
            "leg": "hub_to_destination",
            "origin": "IST",
            "destination": "LHR",
            "date": "2026-08-12",
        }
        plan = {"currency": "RUB"}

        with patch(
            "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
            return_value=[FailingProviderAdapter()],
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].summary["status"], "error")
        self.assertEqual(outcomes[0].failure, outcomes[0].summary)
        self.assertEqual(outcomes[0].failure["provider"], "kupibilet")
        self.assertEqual(outcomes[0].failure["error"]["type"], "provider_unavailable")
        self.assertEqual(
            outcomes[0].failure["error"]["classification"], "provider_unavailable"
        )

    def test_fail_fast_re_raises_provider_error(self) -> None:
        spec = {
            "direction": "outbound",
            "leg": "hub_to_destination",
            "origin": "IST",
            "destination": "LHR",
            "date": "2026-08-12",
        }
        plan = {"currency": "RUB"}
        ledger = ProbeRunLedger()

        with patch(
            "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
            return_value=[FailingProviderAdapter()],
        ):
            with self.assertRaises(CliError):
                dispatch_segment_probe(
                    spec=spec,
                    plan=plan,
                    options=dispatcher_options(fail_fast=True),
                    store=Store(),
                    only_carriers=[],
                    cache_ttl_seconds=0,
                    use_live_cache=False,
                    provider_policy="kupibilet",
                    probe_ledger=ledger,
                )

        diagnostics = ledger.to_diagnostics()
        self.assertEqual(len(diagnostics["failed_probes"]), 1)
        self.assertEqual(diagnostics["failed_probes"][0]["provider"], "kupibilet")
        self.assertEqual(
            diagnostics["failed_probes"][0]["error"]["classification"],
            "provider_unavailable",
        )
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )

    def test_duplicate_segment_probe_reuses_original_result_without_second_provider_call(
        self,
    ) -> None:
        spec = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVX",
            "destination": "IST",
            "date": "2026-08-12",
        }
        plan = {"currency": "RUB"}
        ledger = ProbeRunLedger()
        segment_result = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "offers": [{"id": "offer-1"}],
        }

        with (
            patch(
                "flights_cli.adapters.providers.registry.providers_for_segment",
                return_value=["kupibilet"],
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.cached_kupibilet_search",
                return_value={"offers": [{"id": "raw-1"}], "cache": {"hit": False}},
            ) as search,
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.kupibilet_result_to_segment_result",
                return_value=segment_result,
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.kupibilet_segment_search_summary",
                return_value={"status": "ok", "offer_count": 1},
            ),
        ):
            first = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                options=dispatcher_options(),
                store=Store(),
                only_carriers=["SU"],
                cache_ttl_seconds=30,
                use_live_cache=True,
                provider_policy="kupibilet",
                probe_ledger=ledger,
            )
            second = dispatch_segment_probe(
                spec=spec,
                plan=plan,
                options=dispatcher_options(),
                store=Store(),
                only_carriers=["SU"],
                cache_ttl_seconds=30,
                use_live_cache=True,
                provider_policy="kupibilet",
                probe_ledger=ledger,
            )

        self.assertEqual(search.call_count, 1)
        self.assertEqual(first[0].summary["status"], "ok")
        self.assertEqual(second[0].summary["status"], "deduped")
        self.assertEqual(
            second[0].summary["original_probe_id"], first[0].summary["probe_id"]
        )
        self.assertEqual(second[0].segment_result, segment_result)


if __name__ == "__main__":
    unittest.main()
