from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from flights_cli.domain.gateway_discovery import GatewayDiscoveryService
from flights_cli.store import Store


def provider_result(*offers: dict[str, Any], provider: str = "kupibilet") -> dict[str, Any]:
    return {
        "role": "primary_offer_collection",
        "source_type": "provider_full_route",
        "provider": provider,
        "status": "ok",
        "top_offers": list(offers),
    }


def offer(offer_id: str, segments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = {"id": offer_id}
    if segments is not None:
        payload["segments"] = segments
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
        self.assertEqual(candidates[0].score, 135)
        self.assertEqual(
            [signal.source for signal in candidates[0].signals],
            ["static_prior", "provider_returned_route"],
        )
        self.assertEqual(candidates[0].signals[1].provider, "kupibilet")
        self.assertEqual(candidates[0].signals[1].offer_id, "kb-1")

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
        self.assertEqual(candidates[0].score, 100)
        self.assertEqual(candidates[0].signals[0].source, "provider_returned_route")

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
            all(candidate.signals[0].source == "provider_returned_route" for candidate in candidates)
        )

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
                    "reason": "airport_mismatch_between_segments",
                    "arrival_airport": "DME",
                    "next_departure_airport": "SVO",
                    "debug": {"ground_transfer_required": True},
                }
            ],
        )

    def test_missing_segment_detail_does_not_fail_discovery(self) -> None:
        diagnostics: dict[str, Any] = {}
        service = GatewayDiscoveryService(self.store_with_priors())

        candidates = service.discover(
            "ru_to_western_europe_bridge",
            primary_offer_results=[provider_result(offer("missing"))],
            diagnostics=diagnostics,
        )

        self.assertEqual(candidates, [])
        self.assertEqual(
            diagnostics["rejected_gateway_signals"],
            [
                {
                    "source": "provider_returned_route",
                    "provider": "kupibilet",
                    "offer_id": "missing",
                    "reason": "missing_segment_detail",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
