from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.domain.gateway_priors import load_gateway_priors
from flights_cli.errors import CliError
from flights_cli.orchestrators.search_plan_builder import build_route_context
from flights_cli.store import Store
from helpers import future_departure_date, live_assembly_args


VALID_GATEWAY_PRIORS_YAML = """
schema_version: gateway_priors.v1
markets:
  ru_touching_western_europe:
    - code: IST
      prior_weight: 100
      reason: Primary gateway prior.
      source: static_prior
    - code: DXB
      prior_weight: 40
      reason: Secondary fallback prior.
      source: static_prior
  global_non_ru:
    - code: DOH
      prior_weight: 55
      reason: Generic global hub-list prior.
      source: static_prior
  moscow_control:
    - code: SVO
      prior_weight: 70
      reason: Moscow gateway prior.
      source: static_prior
      control_layer: moscow_svo_control
    - code: SVO
      prior_weight: 20
      reason: Explicit ordinary SVO gateway prior.
      source: static_prior
      allow_as_gateway: true
"""


class GatewayPriorsTests(unittest.TestCase):
    def write_file(self, name: str, text: str) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_gateway_priors_yaml_loads_static_prior_data(self) -> None:
        path = self.write_file("gateway_priors.yaml", VALID_GATEWAY_PRIORS_YAML)

        catalog = load_gateway_priors(path)
        priors = catalog.for_market("ru_touching_western_europe")

        self.assertEqual(
            priors,
            [
                {
                    "code": "IST",
                    "prior_weight": 100,
                    "reason": "Primary gateway prior.",
                    "source": "static_prior",
                },
                {
                    "code": "DXB",
                    "prior_weight": 40,
                    "reason": "Secondary fallback prior.",
                    "source": "static_prior",
                },
            ],
        )

    def test_missing_gateway_priors_yaml_returns_empty_catalog(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        missing_path = Path(tmp_dir.name) / "missing_gateway_priors.yaml"

        catalog = load_gateway_priors(missing_path)
        store = Store(gateway_priors_path=missing_path)

        self.assertEqual(catalog.for_market("ru_touching_western_europe"), [])
        self.assertEqual(
            store.gateway_priors_for_market("ru_touching_western_europe"), []
        )

    def test_invalid_gateway_priors_yaml_raises_clear_configuration_error(self) -> None:
        path = self.write_file(
            "gateway_priors.yaml",
            """
schema_version: gateway_priors.v1
markets:
  ru_touching_western_europe:
    - code IST
      prior_weight: heavy
""",
        )

        with self.assertRaises(CliError) as caught:
            load_gateway_priors(path, strict=True)

        self.assertEqual(caught.exception.error_type, "configuration_error")
        self.assertIn("invalid gateway priors YAML", caught.exception.message)
        self.assertIn(str(path), caught.exception.message)

    def test_store_lookup_normalizes_market_key(self) -> None:
        path = self.write_file("gateway_priors.yaml", VALID_GATEWAY_PRIORS_YAML)
        store = Store(gateway_priors_path=path)

        self.assertEqual(
            store.gateway_priors_for_market("RU-TOUCHING-WESTERN-EUROPE"),
            [
                {
                    "code": "IST",
                    "prior_weight": 100,
                    "reason": "Primary gateway prior.",
                    "source": "static_prior",
                },
                {
                    "code": "DXB",
                    "prior_weight": 40,
                    "reason": "Secondary fallback prior.",
                    "source": "static_prior",
                },
            ],
        )

    def test_control_layer_and_explicit_gateway_metadata_loads(self) -> None:
        path = self.write_file("gateway_priors.yaml", VALID_GATEWAY_PRIORS_YAML)

        priors = load_gateway_priors(path).for_market("moscow_control")

        self.assertEqual(
            priors,
            [
                {
                    "code": "SVO",
                    "prior_weight": 70,
                    "reason": "Moscow gateway prior.",
                    "source": "static_prior",
                    "control_layer": "moscow_svo_control",
                },
                {
                    "code": "SVO",
                    "prior_weight": 20,
                    "reason": "Explicit ordinary SVO gateway prior.",
                    "source": "static_prior",
                    "allow_as_gateway": True,
                },
            ],
        )

    def test_gateway_priors_do_not_leak_into_route_context(self) -> None:
        path = self.write_file("gateway_priors.yaml", VALID_GATEWAY_PRIORS_YAML)
        store = Store(gateway_priors_path=path)
        depart = future_departure_date()

        plan = build_route_context(
            live_assembly_args(
                origin="SVX",
                destination="CDG",
                depart_date=depart.isoformat(),
                return_date=None,
                routing_strategy="ru-priority",
                no_live_cache=True,
            ),
            store,
        )

        self.assertNotIn("gateway_priors", plan)
        self.assertNotIn("segments", plan)


if __name__ == "__main__":
    unittest.main()
