from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.adapters.providers.registry import (
    PROVIDER_REGISTRY,
    not_supported_probe_result,
    provider_adapter,
    provider_adapters_for_segment,
    providers_for_segment,
)
from flights_cli.adapters.providers.common import evidence_type_for_offer_count, segment_probe_type_from_query
from flights_cli.ports.providers import FlightProviderPort, ProviderCapabilities, ProviderProbeResult
from flights_cli.store import Store


def store_with_airports(test_case: unittest.TestCase) -> Store:
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    cache = Path(tmp_dir.name)
    (cache / "airports_en.json").write_text(
        """
        [
          {"code": "SVX", "country_code": "RU", "flightable": true},
          {"code": "IST", "country_code": "TR", "flightable": true},
          {"code": "LHR", "country_code": "GB", "flightable": true}
        ]
        """,
        encoding="utf-8",
    )
    return Store(cache)


class ProviderCapabilitiesTests(unittest.TestCase):
    def test_registry_exposes_expected_provider_capabilities(self) -> None:
        kupibilet = PROVIDER_REGISTRY["kupibilet"].capabilities
        fli = PROVIDER_REGISTRY["fli"].capabilities

        self.assertEqual(set(PROVIDER_REGISTRY), {"kupibilet", "fli"})
        self.assertTrue(kupibilet.supports_ru_touching)
        self.assertTrue(kupibilet.supports_full_route_aggregate)
        self.assertTrue(fli.supports_global)
        self.assertFalse(fli.supports_full_route_aggregate)

    def test_registry_values_are_concrete_provider_ports(self) -> None:
        self.assertEqual(set(PROVIDER_REGISTRY), {"kupibilet", "fli"})
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
        store = store_with_airports(self)

        adapters = provider_adapters_for_segment({"origin": "IST", "destination": "LHR"}, store, "both")

        self.assertEqual([adapter.name for adapter in adapters], ["kupibilet", "fli"])
        self.assertTrue(all(isinstance(adapter, FlightProviderPort) for adapter in adapters))

    def test_auto_policy_uses_capability_registry_for_ru_touching_and_global_segments(self) -> None:
        store = store_with_airports(self)

        self.assertEqual(providers_for_segment({"origin": "SVX", "destination": "IST"}, store, "auto"), ["kupibilet"])
        self.assertEqual(providers_for_segment({"origin": "IST", "destination": "LHR"}, store, "auto"), ["fli"])
        self.assertEqual(providers_for_segment({"origin": "IST", "destination": "LHR"}, store, "both"), ["kupibilet", "fli"])

    def test_unsupported_probe_result_is_explicit_not_supported_evidence(self) -> None:
        result = not_supported_probe_result(
            provider="fli",
            probe_type="full_route_aggregate",
            query={"origin": "SVX", "destination": "DEL"},
            reason="fli does not support full-route aggregate probes",
            probe_id="probe-123",
        )

        payload = result.as_dict()
        self.assertEqual(payload["execution_state"], "not_supported")
        self.assertEqual(payload["evidence_type"], "not_supported")
        self.assertEqual(payload["provider"], "fli")
        self.assertEqual(payload["probe_id"], "probe-123")
        self.assertEqual(payload["errors"][0]["type"], "not_supported")
        self.assertIn("normalized_result", payload)

    def test_fli_adapter_reports_aggregate_not_supported_through_common_result_shape(self) -> None:
        result = provider_adapter("fli").search_aggregate(
            {
                "probe_id": "agg-fli-1",
                "probe_type": "full_route_aggregate",
                "origin": "IST",
                "destination": "LHR",
                "date": "2026-08-12",
            }
        )

        self.assertIsInstance(result, ProviderProbeResult)
        self.assertEqual(result.execution_state, "not_supported")
        self.assertEqual(result.evidence_type, "not_supported")
        self.assertEqual(result.provider, "fli")

    def test_segment_probe_and_evidence_projection_use_shared_provider_helpers(self) -> None:
        capabilities = ProviderCapabilities(probe_types=frozenset({"segment_direct", "city_pair_direct"}))

        self.assertEqual(
            segment_probe_type_from_query({"probe_type": "city_pair_direct", "leg": "hub"}, capabilities),
            "city_pair_direct",
        )
        self.assertEqual(segment_probe_type_from_query({"leg": "direct_destination_control"}, capabilities), "segment_direct")
        self.assertEqual(segment_probe_type_from_query({"leg": "hub_leg"}, capabilities), "segment_hub_leg")
        self.assertEqual(evidence_type_for_offer_count(offer_count=1, cache_status="live"), "positive_live_evidence")
        self.assertEqual(evidence_type_for_offer_count(offer_count=1, cache_status="cache_hit"), "positive_cached_hint")
        self.assertEqual(evidence_type_for_offer_count(offer_count=0, cache_status="live"), "negative_provider_empty")
        self.assertEqual(evidence_type_for_offer_count(offer_count=0, cache_status="stale_cache_used"), "negative_cache_absence")


if __name__ == "__main__":
    unittest.main()
