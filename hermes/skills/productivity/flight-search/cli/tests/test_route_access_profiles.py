from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.domain.route_access_profiles import load_route_access_profiles
from flights_cli.errors import CliError
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.store import Store
from helpers import live_assembly_args


CUSTOM_ROUTE_ACCESS_YAML = """
schema_version: route_access_profiles.v1
region_groups:
  test_restricted: [TR]
route_access_rules:
  - id: ru_to_test_restricted
    when:
      origin_country_any: [RU]
      destination_region_any: [test_restricted]
    profile: restricted_access_market
    gateway_discovery_mode: required
    reasons:
      - test_config_rule
    prior_set: test_bridge_gateways
  - id: default_ru_touching
    when:
      route_touches_country: RU
    profile: normal_ru_touching_market
    gateway_discovery_mode: optional_after_provider_failure
    reasons: []
    prior_set: default_ru_touching_gateways
  - id: default_global_non_ru
    when:
      market_class: global_non_ru
    profile: normal_global_market
    gateway_discovery_mode: optional_after_provider_failure
    reasons: []
"""


class RouteAccessProfileTests(unittest.TestCase):
    def write_file(self, name: str, text: str) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def flow(self, origin: str, destination: str, store: Store | None = None):
        return build_live_route_search_flow(
            live_assembly_args(
                origin=origin,
                destination=destination,
                return_date=None,
                no_live_cache=True,
                no_direct_route_intel=True,
            ),
            store or Store(),
        ).flow_decision

    def assert_restricted(self, origin: str, destination: str) -> None:
        decision = self.flow(origin, destination)

        self.assertEqual(decision.market_class, "ru_touching_international")
        self.assertEqual(decision.route_access_profile, "restricted_access_market")
        self.assertEqual(decision.gateway_discovery_mode, "required")
        self.assertIn("airspace_restrictions", decision.route_access_reasons)
        self.assertEqual(decision.route_access_prior_set, "restricted_bridge_gateways")

    def test_restricted_ru_to_eu(self) -> None:
        self.assert_restricted("SVX", "AMS")
        self.assert_restricted("SVX", "FRA")

    def test_restricted_ru_to_uk(self) -> None:
        self.assert_restricted("SVX", "LON")
        self.assert_restricted("SVX", "LHR")

    def test_restricted_ru_to_north_america_if_configured(self) -> None:
        self.assert_restricted("SVX", "JFK")
        self.assert_restricted("SVX", "YYZ")

    def test_normal_ru_to_china_is_not_hardcoded_restricted(self) -> None:
        decision = self.flow("SVX", "PEK")

        self.assertEqual(decision.market_class, "ru_touching_international")
        self.assertEqual(decision.route_access_profile, "normal_ru_touching_market")
        self.assertEqual(
            decision.gateway_discovery_mode, "optional_after_provider_failure"
        )
        self.assertEqual(decision.route_access_reasons, ())

    def test_normal_global_non_ru(self) -> None:
        decision = self.flow("IST", "AMS")

        self.assertEqual(decision.market_class, "global_non_ru")
        self.assertEqual(decision.route_access_profile, "normal_global_market")
        self.assertEqual(
            decision.gateway_discovery_mode, "optional_after_provider_failure"
        )

    def test_domestic_ru_not_restricted(self) -> None:
        decision = self.flow("SVX", "AER")

        self.assertEqual(decision.market_class, "ru_domestic")
        self.assertNotEqual(decision.route_access_profile, "restricted_access_market")

    def test_config_driven_not_code_driven(self) -> None:
        path = self.write_file("route_access_profiles.yaml", CUSTOM_ROUTE_ACCESS_YAML)
        store = Store(route_access_profiles_path=path)

        decision = self.flow("SVX", "IST", store)

        self.assertEqual(decision.route_access_profile, "restricted_access_market")
        self.assertEqual(decision.gateway_discovery_mode, "required")
        self.assertEqual(decision.route_access_reasons, ("test_config_rule",))
        self.assertEqual(decision.route_access_rule_id, "ru_to_test_restricted")
        self.assertEqual(decision.route_access_prior_set, "test_bridge_gateways")

    def test_missing_or_empty_config_safe_default(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        missing = Path(tmp_dir.name) / "missing.yaml"
        empty = self.write_file("empty.yaml", "")

        missing_decision = self.flow(
            "SVX", "PEK", Store(route_access_profiles_path=missing)
        )
        empty_decision = self.flow("IST", "AMS", Store(route_access_profiles_path=empty))

        self.assertEqual(
            missing_decision.route_access_profile, "normal_ru_touching_market"
        )
        self.assertEqual(empty_decision.route_access_profile, "normal_global_market")

    def test_invalid_config_raises_clear_configuration_error(self) -> None:
        path = self.write_file(
            "route_access_profiles.yaml",
            """
schema_version: route_access_profiles.v1
route_access_rules:
  - id broken
""",
        )

        with self.assertRaises(CliError) as caught:
            load_route_access_profiles(path, strict=True)

        self.assertEqual(caught.exception.error_type, "configuration_error")
        self.assertIn("invalid route access profiles YAML", caught.exception.message)
        self.assertIn("expected key: value", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
