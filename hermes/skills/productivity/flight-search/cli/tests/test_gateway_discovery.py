from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from flights_cli.domain.gateway_discovery import (
    PROVIDER_RETURNED_ROUTE_WEIGHT,
    GatewayDiscoveryService,
    extract_provider_returned_gateway_signals,
)
from flights_cli.store import Store


def provider_result(
    *offers: dict[str, Any], provider: str = "kupibilet", direction: str | None = None
) -> dict[str, Any]:
    payload = {
        "role": "primary_offer_collection",
        "source_type": "provider_full_route",
        "provider": provider,
        "status": "ok",
        "top_offers": list(offers),
    }
    if direction is not None:
        payload["direction"] = direction
    return payload


def legacy_aggregate_result(*offers: dict[str, Any], provider: str = "kupibilet") -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "ok",
        "top_offers": list(offers),
    }


def offer(
    offer_id: str,
    segments: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {"id": offer_id}
    if segments is not None:
        payload["segments"] = segments
    payload.update(extra)
    return payload


class GatewayDiscoveryTests(unittest.TestCase):
    def store_with_priors(self, yaml_body: str | None = None) -> Store:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        priors_path = Path(tmp_dir.name) / "gateway_priors.yaml"
        if yaml_body is not None:
            priors_path.write_text(yaml_body, encoding="utf-8")
        return Store(gateway_priors_path=priors_path)

    def test_static_priors_create_sorted_candidates_with_reasons(self) -> None:
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  ru_to_western_europe_bridge:
    - code: IST
      prior_weight: 35
      reason: common bridge gateway
      source: static_prior
    - code: DXB
      prior_weight: 20
      reason: secondary bridge gateway
      source: static_prior
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "ru_to_western_europe_bridge"
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST", "DXB"])
        self.assertEqual(candidates[0].score, 35)
        self.assertEqual(candidates[0].signals[0].source, "static_prior")
        self.assertEqual(candidates[0].signals[0].reason, "common bridge gateway")
        self.assertEqual(candidates[0].debug, {"market": "ru_to_western_europe_bridge"})

    def test_provider_returned_gateway_dedupes_with_static_prior(self) -> None:
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  ru_to_western_europe_bridge:
    - code: IST
      prior_weight: 35
      reason: common bridge gateway
      source: static_prior
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "kb-1",
                        [
                            {"origin": "SVX", "destination": "IST"},
                            {"origin": "IST", "destination": "AMS"},
                        ],
                    )
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST"])
        self.assertEqual(candidates[0].score, 35 + PROVIDER_RETURNED_ROUTE_WEIGHT)
        self.assertEqual(
            [signal.source for signal in candidates[0].signals],
            ["static_prior", "provider_returned_route"],
        )
        self.assertEqual(candidates[0].signals[1].provider, "kupibilet")
        self.assertEqual(candidates[0].signals[1].offer_id, "kb-1")
        self.assertGreater(
            candidates[0].signals[1].weight,
            candidates[0].signals[0].weight,
        )

    def test_provider_returned_gateway_outranks_static_only_gateway(self) -> None:
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  ru_to_western_europe_bridge:
    - code: IST
      prior_weight: 100
      reason: strongest static gateway
      source: static_prior
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "kb-2",
                        [
                            {"origin": "SVX", "destination": "BEG"},
                            {"origin": "BEG", "destination": "AMS"},
                        ],
                    )
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["BEG", "IST"])
        self.assertEqual(candidates[0].signals[0].source, "provider_returned_route")

    def test_stable_order_preserves_first_signal_order_for_equal_scores(self) -> None:
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  ru_to_western_europe_bridge:
    - code: IST
      prior_weight: 50
      reason: first equal gateway
      source: static_prior
    - code: BEG
      prior_weight: 50
      reason: second equal gateway
      source: static_prior
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "ru_to_western_europe_bridge"
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST", "BEG"])

    def test_empty_discovery_returns_empty_list(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge", primary_offer_results=[]
        )

        self.assertEqual(candidates, [])

    def test_moscow_control_prior_is_not_ranked_as_gateway_candidate(self) -> None:
        diagnostics: dict[str, Any] = {}
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  ru_touching_asia_oceania:
    - code: SVO
      prior_weight: 100
      reason: Moscow/SVO control evidence, not an ordinary gateway.
      source: static_prior
      control_layer: moscow_svo_control
    - code: IST
      prior_weight: 80
      reason: bridge gateway
      source: static_prior
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "ru_touching_asia_oceania", diagnostics=diagnostics
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST"])
        self.assertEqual(
            diagnostics["rejected_gateway_signals"],
            [
                {
                    "source": "static_prior",
                    "code": "SVO",
                    "reason": "control_layer_prior_not_gateway_candidate",
                    "control_layer": "moscow_svo_control",
                    "market": "ru_touching_asia_oceania",
                    "debug": {
                        "static_prior_not_ranked": True,
                        "allow_as_gateway_required": True,
                    },
                }
            ],
        )

    def test_moscow_airport_static_prior_requires_explicit_gateway_opt_in(
        self,
    ) -> None:
        diagnostics: dict[str, Any] = {}
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  accidental_moscow_gateway:
    - code: SVO
      prior_weight: 90
      reason: accidental ordinary prior
      source: static_prior
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "accidental_moscow_gateway", diagnostics=diagnostics
        )

        self.assertEqual(candidates, [])
        self.assertEqual(
            diagnostics["rejected_gateway_signals"][0]["reason"],
            "control_layer_prior_not_gateway_candidate",
        )
        self.assertEqual(
            diagnostics["rejected_gateway_signals"][0]["control_layer"],
            "moscow_svo_control",
        )

    def test_explicit_moscow_gateway_prior_can_be_ranked(self) -> None:
        store = self.store_with_priors(
            """
schema_version: gateway_priors.v1
markets:
  explicit_moscow_gateway:
    - code: SVO
      prior_weight: 90
      reason: explicitly configured ordinary gateway prior
      source: static_prior
      allow_as_gateway: true
"""
        )

        candidates = GatewayDiscoveryService(store).discover(
            "explicit_moscow_gateway"
        )

        self.assertEqual([candidate.code for candidate in candidates], ["SVO"])
        self.assertEqual(candidates[0].signals[0].debug, {"allow_as_gateway": True})

    def test_provider_returned_svo_remains_provider_route_evidence(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "via-svo",
                        [
                            {"origin": "SVX", "destination": "SVO"},
                            {"origin": "SVO", "destination": "AMS"},
                        ],
                    )
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["SVO"])
        self.assertEqual(candidates[0].signals[0].source, "provider_returned_route")

    def test_bundled_asia_svo_prior_is_control_layer_diagnostic(self) -> None:
        diagnostics: dict[str, Any] = {}

        candidates = GatewayDiscoveryService(Store()).discover(
            "ru_touching_asia_oceania", diagnostics=diagnostics
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST", "DXB"])
        self.assertEqual(diagnostics["rejected_gateway_signals"][0]["code"], "SVO")
        self.assertEqual(
            diagnostics["rejected_gateway_signals"][0]["control_layer"],
            "moscow_svo_control",
        )

    def test_direct_offer_does_not_create_gateway(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "direct",
                        [{"origin": "SVX", "destination": "AMS"}],
                    )
                )
            ],
        )

        self.assertEqual(candidates, [])

    def test_one_stop_offer_creates_one_provider_signal(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "one-stop",
                        [
                            {"origin": "SVX", "destination": "IST"},
                            {"origin": "IST", "destination": "AMS"},
                        ],
                    )
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST"])
        self.assertEqual(candidates[0].score, PROVIDER_RETURNED_ROUTE_WEIGHT)
        self.assertEqual(candidates[0].signals[0].source, "provider_returned_route")
        self.assertEqual(
            candidates[0].signals[0].reason,
            "provider returned route via intermediate airport",
        )

    def test_two_stop_offer_creates_two_provider_signals(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "two-stop",
                        [
                            {"origin": "SVX", "destination": "IST"},
                            {"origin": "IST", "destination": "BEG"},
                            {"origin": "BEG", "destination": "AMS"},
                        ],
                    )
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["IST", "BEG"])
        self.assertTrue(
            all(
                candidate.signals[0].source == "provider_returned_route"
                for candidate in candidates
            )
        )
        self.assertEqual(candidates[0].signals[0].debug["between_segments"], [0, 1])
        self.assertEqual(candidates[1].signals[0].debug["between_segments"], [1, 2])

    def test_nested_journeys_extract_provider_gateways_with_direction(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "global_non_ru",
            provider_results=[
                provider_result(
                    offer(
                        "journey-offer",
                        journeys=[
                            {
                                "direction": "return",
                                "segments": [
                                    {"origin": "JFK", "destination": "DXB"},
                                    {"origin": "DXB", "destination": "SVX"},
                                ],
                            }
                        ],
                    ),
                    provider="fli",
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["DXB"])
        signal = candidates[0].signals[0]
        self.assertEqual(signal.provider, "fli")
        self.assertEqual(signal.direction, "return")
        self.assertEqual(signal.debug["source_path"], "journeys")
        self.assertEqual(signal.debug["journey_index"], 0)

    def test_legacy_aggregate_controls_are_provider_signal_sources(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "global_non_ru",
            provider_results=[
                legacy_aggregate_result(
                    offer(
                        "legacy-aggregate",
                        [
                            {"origin": "SVX", "destination": "TAS"},
                            {"origin": "TAS", "destination": "BKK"},
                        ],
                    ),
                    provider="fli",
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["TAS"])
        self.assertEqual(candidates[0].signals[0].provider, "fli")

    def test_airport_mismatch_is_not_normal_gateway_and_is_diagnostic(self) -> None:
        diagnostics: dict[str, Any] = {}
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer(
                        "mismatch",
                        [
                            {"origin": "SVX", "destination": "DME"},
                            {"origin": "SVO", "destination": "AMS"},
                        ],
                    )
                )
            ],
            diagnostics=diagnostics,
        )

        self.assertEqual(candidates, [])
        self.assertEqual(
            diagnostics["rejected_gateway_signals"],
            [
                {
                    "source": "provider_returned_route",
                    "provider": "kupibilet",
                    "offer_id": "mismatch",
                    "segment_index": 0,
                    "reason": "airport_mismatch",
                    "arrival_airport": "DME",
                    "next_departure_airport": "SVO",
                    "debug": {
                        "source_path": "segments",
                        "ground_transfer_required": True,
                    },
                }
            ],
        )

    def test_malformed_offer_does_not_crash_discovery(self) -> None:
        diagnostics: dict[str, Any] = {}
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[
                provider_result(
                    offer("missing"),
                    offer(
                        "malformed",
                        [
                            {"origin": "SVX", "destination": "IST"},
                            "bad-segment",
                        ],
                    ),
                    offer(
                        "valid",
                        [
                            {"origin": "SVX", "destination": "DXB"},
                            {"origin": "DXB", "destination": "JFK"},
                        ],
                    ),
                )
            ],
            diagnostics=diagnostics,
        )

        self.assertEqual([candidate.code for candidate in candidates], ["DXB"])
        self.assertEqual(
            diagnostics["rejected_gateway_signals"],
            [
                {
                    "source": "provider_returned_route",
                    "provider": "kupibilet",
                    "offer_id": "missing",
                    "reason": "missing_segments",
                },
                {
                    "source": "provider_returned_route",
                    "provider": "kupibilet",
                    "offer_id": "malformed",
                    "segment_index": 0,
                    "reason": "malformed_segments",
                    "debug": {"source_path": "segments"},
                },
            ],
        )

    def test_city_code_not_used_as_gateway(self) -> None:
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "global_non_ru",
            primary_offer_results=[
                provider_result(
                    offer(
                        "airport-scope",
                        [
                            {"origin": "SVX", "destination": "SVO"},
                            {"origin": "SVO", "destination": "LHR"},
                            {"origin": "LHR", "destination": "JFK"},
                        ],
                        origin="MOW",
                        destination="LON",
                    )
                )
            ],
        )

        self.assertEqual([candidate.code for candidate in candidates], ["SVO", "LHR"])
        self.assertNotIn("MOW", [candidate.code for candidate in candidates])
        self.assertNotIn("LON", [candidate.code for candidate in candidates])

    def test_extract_helper_is_pure_and_returns_rejections(self) -> None:
        extracted, rejected = extract_provider_returned_gateway_signals(
            [
                provider_result(
                    offer(
                        "helper",
                        [
                            {"origin": "SVX", "destination": "IST"},
                            {"origin": "IST", "destination": "AMS"},
                        ],
                    )
                ),
                provider_result(offer("missing")),
            ]
        )

        self.assertEqual([code for code, _signal in extracted], ["IST"])
        self.assertEqual(extracted[0][1].code, "IST")
        self.assertEqual(extracted[0][1].provider, "kupibilet")
        self.assertEqual(rejected[0]["reason"], "missing_segments")


if __name__ == "__main__":
    unittest.main()
