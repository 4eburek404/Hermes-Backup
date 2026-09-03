from __future__ import annotations

import ast
import unittest
from pathlib import Path

from flights_cli.adapters.providers.registry import (
    PROVIDER_REGISTRY,
    not_supported_probe_result,
    provider_adapter,
    provider_adapters_for_segment,
    providers_for_offer_query,
    providers_for_segment,
    route_touches_ru,
)
from flights_cli.adapters.providers.common import (
    evidence_type_for_offer_count,
    segment_probe_type_from_query,
)
from flights_cli.errors import CliError
from flights_cli.execution.search_executor import SearchExecutor
from flights_cli.orchestrators.search_plan_builder import SearchPlanBuilder
from flights_cli.ports.providers import (
    FlightProviderPort,
    ProviderCapabilities,
    ProviderProbeResult,
)
from flights_cli.pipeline.search_request import search_request_from_payload
from flights_cli.reporting.evidence import all_planned_probes_are_terminal
from flights_cli.store import Store
from helpers import (
    future_departure_date,
    live_assembly_args,
    make_test_store,
)


TEST_AIRPORTS = [
    {"code": "SVX", "country_code": "RU", "flightable": True},
    {"code": "CDG", "country_code": "FR", "flightable": True},
    {"code": "IST", "country_code": "TR", "flightable": True},
    {"code": "LHR", "country_code": "GB", "flightable": True},
]


class RecordingProvider:
    def __init__(self, name: str, capabilities: ProviderCapabilities) -> None:
        self.name = name
        self.capabilities = capabilities
        self.calls = 0

    def search_segment(self, query: dict[str, object]) -> ProviderProbeResult:
        self.calls += 1
        raise AssertionError("unsupported provider must not be called")

    def search_aggregate(self, query: dict[str, object]) -> ProviderProbeResult:
        self.calls += 1
        raise AssertionError("unsupported provider must not be called")


class ProviderCapabilitiesTests(unittest.TestCase):
    def test_request_provider_name_is_validated_by_registry_at_runtime(self) -> None:
        depart = future_departure_date()
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "CDG",
                "depart_date": depart.isoformat(),
                "provider_policy": "future_provider",
            }
        )
        store = make_test_store(self, TEST_AIRPORTS)

        with self.assertRaises(CliError) as caught:
            providers_for_offer_query(
                {
                    "probe_type": "full_route_aggregate",
                    "origin": "SVX",
                    "destination": "CDG",
                },
                store,
                request.provider_policy,
            )

        self.assertEqual(caught.exception.error_type, "validation_error")
        self.assertEqual(
            set(caught.exception.details["registered_providers"]),
            {"tutu", "kupibilet"},
        )

    def test_provider_adapters_do_not_import_other_provider_adapters(self) -> None:
        adapter_dir = (
            Path(__file__).parents[1] / "flights_cli" / "adapters" / "providers"
        )
        for filename in ("tutu_adapter.py", "kupibilet_adapter.py"):
            tree = ast.parse((adapter_dir / filename).read_text(encoding="utf-8"))
            imported_adapters = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("_adapter")
            ]
            self.assertEqual(imported_adapters, [], filename)

    def test_registry_exposes_expected_provider_capabilities(self) -> None:
        kupibilet = PROVIDER_REGISTRY["kupibilet"].capabilities
        tutu = PROVIDER_REGISTRY["tutu"].capabilities

        self.assertEqual(set(PROVIDER_REGISTRY), {"kupibilet", "tutu"})
        self.assertTrue(kupibilet.supports_ru_touching)
        self.assertTrue(kupibilet.supports_full_route_aggregate)
        self.assertTrue(tutu.supports_ru_touching)
        self.assertTrue(tutu.supports_global)
        self.assertTrue(tutu.supports_full_route_aggregate)
        self.assertTrue(tutu.supports_direct_only)
        self.assertTrue(tutu.supports_carrier_filter)
        self.assertIn("carrier_aggregate", tutu.probe_types)

    def test_registry_values_are_concrete_provider_ports(self) -> None:
        self.assertEqual(set(PROVIDER_REGISTRY), {"kupibilet", "tutu"})
        for name, adapter in PROVIDER_REGISTRY.items():
            with self.subTest(provider=name):
                self.assertIsInstance(adapter, FlightProviderPort)
                self.assertEqual(adapter.name, name)
                self.assertTrue(callable(adapter.search_segment))
                self.assertTrue(callable(adapter.search_aggregate))

    def test_provider_adapter_lookup_returns_configured_adapter_object(self) -> None:
        adapter = provider_adapter("kupibilet")

        self.assertIs(adapter, PROVIDER_REGISTRY["kupibilet"])
        self.assertIsInstance(adapter, FlightProviderPort)

    def test_policy_can_return_adapter_objects_for_execution(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        adapters = provider_adapters_for_segment(
            {"origin": "IST", "destination": "LHR"}, store, "auto"
        )

        self.assertEqual([adapter.name for adapter in adapters], ["tutu", "kupibilet"])
        self.assertTrue(
            all(isinstance(adapter, FlightProviderPort) for adapter in adapters)
        )

    def test_auto_policy_uses_capability_registry_for_ru_touching_and_global_segments(
        self,
    ) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        self.assertEqual(
            providers_for_segment(
                {"origin": "SVX", "destination": "IST"}, store, "auto"
            ),
            ["tutu", "kupibilet"],
        )
        self.assertEqual(
            providers_for_segment(
                {"origin": "IST", "destination": "LHR"}, store, "auto"
            ),
            ["tutu", "kupibilet"],
        )
        with self.assertRaises(CliError):
            providers_for_segment(
                {"origin": "SVX", "destination": "IST"}, store, "unsupported"
            )

    def test_both_policy_is_rejected(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        with self.assertRaises(CliError):
            providers_for_segment(
                {"origin": "IST", "destination": "LHR"}, store, "both"
            )

    def test_offer_query_policy_uses_full_route_aggregate_capabilities(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)
        query = {
            "probe_type": "full_route_aggregate",
            "origin": "SVX",
            "destination": "CDG",
            "direct_only": False,
        }

        self.assertEqual(
            providers_for_offer_query(query, store, "kupibilet"), ["kupibilet"]
        )
        with self.assertRaises(CliError):
            providers_for_offer_query(query, store, "unsupported")
        self.assertEqual(providers_for_offer_query(query, store, "tutu"), ["tutu"])

    def test_auto_offer_query_uses_market_and_capability_routing(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        self.assertEqual(
            providers_for_offer_query(
                {
                    "probe_type": "full_route_aggregate",
                    "origin": "SVX",
                    "destination": "CDG",
                },
                store,
                "auto",
            ),
            ["tutu", "kupibilet"],
        )
        self.assertEqual(
            providers_for_offer_query(
                {
                    "probe_type": "full_route_aggregate",
                    "origin": "IST",
                    "destination": "LHR",
                },
                store,
                "auto",
            ),
            ["tutu", "kupibilet"],
        )

    def test_auto_carrier_aggregate_keeps_tutu_primary(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        self.assertEqual(
            providers_for_offer_query(
                {
                    "probe_type": "carrier_aggregate",
                    "origin": "IST",
                    "destination": "LHR",
                    "only_carriers": ["TK"],
                },
                store,
                "auto",
            ),
            ["tutu", "kupibilet"],
        )

    def test_route_query_ru_boundary(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        self.assertTrue(route_touches_ru("SVX", "CDG", store))
        self.assertFalse(route_touches_ru("IST", "LHR", store))

    def test_gateway_segments_follow_existing_ru_non_ru_provider_split(self) -> None:
        store = make_test_store(self, TEST_AIRPORTS)

        self.assertEqual(
            providers_for_segment(
                {"origin": "SVX", "destination": "IST"}, store, "auto"
            ),
            ["tutu", "kupibilet"],
        )
        self.assertEqual(
            providers_for_segment(
                {"origin": "IST", "destination": "LHR"}, store, "auto"
            ),
            ["tutu", "kupibilet"],
        )

    def test_unsupported_probe_result_is_explicit_not_supported_evidence(self) -> None:
        result = not_supported_probe_result(
            provider="tutu",
            probe_type="full_route_aggregate",
            query={"origin": "SVX", "destination": "DEL"},
            reason="provider does not support this probe",
            probe_id="probe-123",
        )

        payload = result.as_dict()
        self.assertEqual(payload["execution_state"], "not_supported")
        self.assertEqual(payload["evidence_type"], "not_supported")
        self.assertEqual(payload["provider"], "tutu")
        self.assertEqual(payload["probe_id"], "probe-123")
        self.assertEqual(payload["errors"][0]["type"], "not_supported")
        self.assertIn("offers", payload)

    def test_explicit_unsupported_provider_is_planned_and_terminalized(self) -> None:
        provider = RecordingProvider("limited", ProviderCapabilities())
        PROVIDER_REGISTRY[provider.name] = provider
        try:
            store = Store()
            depart = future_departure_date()
            request = live_assembly_args(
                origin="SVX",
                destination="CDG",
                depart_date=depart.isoformat(),
                return_date=None,
                provider_policy=provider.name,
                preferred_connections=0,
                max_connections=0,
                no_live_cache=True,
            )
            plan = SearchPlanBuilder(store).build(request)

            self.assertEqual(len(plan.all_attempts), 1)
            self.assertEqual(plan.all_attempts[0].provider, provider.name)
            evidence = SearchExecutor(store).execute(plan)
        finally:
            PROVIDER_REGISTRY.pop(provider.name, None)

        ledger = evidence.probe_ledger
        self.assertEqual(provider.calls, 0)
        self.assertEqual(len(ledger["unsupported_probes"]), 1)
        self.assertEqual(ledger["unsupported_probes"][0]["provider"], provider.name)
        self.assertTrue(all_planned_probes_are_terminal(ledger))

    def test_auto_plan_fans_out_to_registered_third_provider(self) -> None:
        depart = future_departure_date()
        capabilities = ProviderCapabilities(
            supports_ru_touching=True,
            supports_global=True,
            supports_direct_only=True,
            supports_carrier_filter=True,
            supports_full_route_aggregate=True,
            probe_types=frozenset(
                {
                    "segment_direct",
                    "segment_hub_leg",
                    "full_route_aggregate",
                    "carrier_aggregate",
                }
            ),
        )
        provider = RecordingProvider("third", capabilities)
        PROVIDER_REGISTRY[provider.name] = provider
        try:
            plan = SearchPlanBuilder(Store()).build(
                live_assembly_args(
                    origin="SVX",
                    destination="CDG",
                    depart_date=depart.isoformat(),
                    return_date=None,
                    provider_policy="auto",
                    preferred_connections=0,
                    max_connections=0,
                    no_live_cache=True,
                )
            )
        finally:
            PROVIDER_REGISTRY.pop(provider.name, None)

        self.assertEqual(
            [attempt.provider for attempt in plan.phases.primary],
            ["tutu", "kupibilet", "third"],
        )

    def test_provider_adapter_returns_same_instance_for_same_store(self) -> None:
        """provider_adapter with same (name, store) returns cached instance."""
        store = make_test_store(self, TEST_AIRPORTS)
        a1 = provider_adapter("kupibilet", store=store)
        a2 = provider_adapter("kupibilet", store=store)
        self.assertIs(a1, a2)

    def test_provider_adapter_returns_different_instance_for_different_store(
        self,
    ) -> None:
        """provider_adapter with different store returns different instance."""
        store_a = make_test_store(self, TEST_AIRPORTS)
        store_b = make_test_store(self, TEST_AIRPORTS)
        a1 = provider_adapter("kupibilet", store=store_a)
        a2 = provider_adapter("kupibilet", store=store_b)
        self.assertIsNot(a1, a2)

    def test_provider_adapter_no_store_returns_singleton(self) -> None:
        """provider_adapter with store=None returns the registry singleton."""
        adapter = provider_adapter("kupibilet")
        self.assertIs(adapter, PROVIDER_REGISTRY["kupibilet"])

    def test_segment_probe_and_evidence_projection_use_shared_provider_helpers(
        self,
    ) -> None:
        capabilities = ProviderCapabilities(
            probe_types=frozenset({"segment_direct", "segment_hub_leg"})
        )

        self.assertEqual(
            segment_probe_type_from_query(
                {"probe_type": "segment_direct", "leg": "hub"}, capabilities
            ),
            "segment_direct",
        )
        self.assertEqual(
            segment_probe_type_from_query(
                {"leg": "direct_destination_probe"}, capabilities
            ),
            "segment_direct",
        )
        self.assertEqual(
            segment_probe_type_from_query({"leg": "hub_leg"}, capabilities),
            "segment_hub_leg",
        )
        self.assertEqual(
            evidence_type_for_offer_count(offer_count=1, cache_status="live"),
            "positive_live_evidence",
        )
        self.assertEqual(
            evidence_type_for_offer_count(offer_count=1, cache_status="cache_hit"),
            "positive_cached_hint",
        )
        self.assertEqual(
            evidence_type_for_offer_count(offer_count=0, cache_status="live"),
            "negative_provider_empty",
        )
        self.assertEqual(
            evidence_type_for_offer_count(
                offer_count=0, cache_status="stale_cache_used"
            ),
            "negative_cache_absence",
        )


if __name__ == "__main__":
    unittest.main()
