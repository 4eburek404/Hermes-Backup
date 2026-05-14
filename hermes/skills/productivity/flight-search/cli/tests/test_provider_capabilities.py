from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.adapters.providers.registry import (
    PROVIDER_REGISTRY,
    not_supported_probe_result,
    providers_for_segment,
)
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


if __name__ == "__main__":
    unittest.main()
