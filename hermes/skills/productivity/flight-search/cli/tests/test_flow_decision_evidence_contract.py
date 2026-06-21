from __future__ import annotations

from datetime import date
import unittest

from flights_cli.execution.probe_ledger import ProbeExecutionLedger
from flights_cli.orchestrators.live_assemble import build_live_route_segment_plan
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.store import Store
from tests.helpers import live_assembly_args


class FlowDecisionEvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store()

    def flow_for(self, **overrides: object):
        args = live_assembly_args(**overrides)
        return build_live_route_search_flow(args)

    def flow_for_today(self, today: date, **overrides: object):
        args = live_assembly_args(**overrides)
        return build_live_route_search_flow(args, today_provider=lambda: today)

    def plan_for(self, **overrides: object) -> dict:
        args = live_assembly_args(**overrides)
        return build_live_route_segment_plan(args, self.store)

    def test_global_non_ru_auto_does_not_inherit_ru_priority_or_moscow_controls(self) -> None:
        flow = self.flow_for(origin="BER", destination="MAD", provider_policy="auto", return_date=None)
        plan = self.plan_for(origin="BER", destination="MAD", provider_policy="auto", return_date=None)

        self.assertEqual(flow.flow_decision.market_class, "global_non_ru")
        self.assertEqual(flow.flow_decision.routing_strategy, "hub-list")
        self.assertEqual(flow.flow_decision.provider_plan["default_provider"], "fli")
        self.assertEqual(plan["routing_strategy"], "hub-list")
        self.assertNotIn("ru-priority", {family.get("id") for family in plan.get("route_families") or []})
        self.assertFalse({"SVO", "DME", "VKO"} & set(plan.get("hubs") or []))
        self.assertNotIn("moscow_gateway_control", {segment.get("route_family") for segment in plan.get("segments") or []})
        self.assertEqual(plan["flow_decision"]["market_class"], "global_non_ru")

    def test_ru_domestic_auto_gets_domestic_ru_route_mode(self) -> None:
        flow = self.flow_for(origin="SVX", destination="KUF", provider_policy="auto", return_date=None)
        plan = self.plan_for(origin="SVX", destination="KUF", provider_policy="auto", return_date=None)

        self.assertEqual(flow.flow_decision.market_class, "ru_domestic")
        self.assertEqual(flow.flow_decision.routing_strategy, "domestic-ru")
        self.assertEqual(flow.flow_decision.route_mode, "domestic_ru")
        self.assertEqual(plan["routing_strategy"], "domestic-ru")
        self.assertIn("domestic_ru", {family.get("id") for family in plan.get("route_families") or []})

    def test_ru_touching_international_auto_uses_ru_priority_with_structured_reason(self) -> None:
        flow = self.flow_for(origin="SVX", destination="IST", provider_policy="auto", return_date=None)
        plan = self.plan_for(origin="SVX", destination="IST", provider_policy="auto", return_date=None)

        self.assertEqual(flow.flow_decision.market_class, "ru_touching_international")
        self.assertEqual(flow.flow_decision.routing_strategy, "ru-priority")
        self.assertIn("ru_touching_market_uses_ru_priority_controls", flow.flow_decision.limitations)
        self.assertEqual(plan["flow_decision"]["market_class"], "ru_touching_international")
        self.assertIn("ru_touching_market_uses_ru_priority_controls", plan["flow_decision"]["limitations"])

    def test_direct_inventory_request_compiles_to_direct_only_flow_and_controls(self) -> None:
        flow = self.flow_for(origin="SVX", destination="KUF", max_connections=0, tier2_max_connections=0, return_date=None)
        plan = self.plan_for(origin="SVX", destination="KUF", max_connections=0, tier2_max_connections=0, return_date=None)

        self.assertEqual(flow.flow_decision.intent_class, "direct_inventory")
        self.assertEqual(flow.flow_decision.evidence_class, "absence_claim")
        self.assertEqual(flow.flow_decision.route_mode, "direct_inventory")
        self.assertTrue(flow.evidence_plan.direct_only)
        self.assertIn("exact_airport_direct", flow.evidence_plan.required_controls)
        self.assertTrue(plan["direct_only"])
        self.assertTrue(plan["segments"])
        self.assertTrue(all(str(segment.get("leg") or "").startswith("direct_") for segment in plan["segments"]))
        self.assertTrue(all(control.get("type") == "exact_airport_direct" for control in plan["coverage_controls"]))

    def test_carrier_specific_request_compiles_to_carrier_scope_and_required_controls(self) -> None:
        flow = self.flow_for(origin="SVX", destination="IST", only_carrier=["SU"], return_date=None)

        self.assertEqual(flow.flow_decision.intent_class, "carrier_or_airport_scope")
        self.assertEqual(flow.flow_decision.evidence_class, "absence_claim")
        self.assertIn("carrier_aggregate", flow.evidence_plan.required_controls)
        self.assertIn("carrier_scope_requires_targeted_controls", flow.flow_decision.limitations)

    def test_exclude_carrier_is_hard_scope_and_required_control(self) -> None:
        flow = self.flow_for(origin="BER", destination="MAD", exclude_carrier=["XX"], return_date=None)

        self.assertEqual(flow.flow_decision.intent_class, "carrier_or_airport_scope")
        self.assertEqual(flow.flow_decision.evidence_class, "absence_claim")
        self.assertIn("carrier_aggregate", flow.evidence_plan.required_controls)

    def test_prefer_carrier_is_soft_ranking_preference_not_absence_scope(self) -> None:
        flow = self.flow_for(origin="BER", destination="MAD", prefer_carrier=["LH"], return_date=None)

        self.assertEqual(flow.flow_decision.intent_class, "route_recommendation")
        self.assertEqual(flow.flow_decision.evidence_class, "shopping_advisory")
        self.assertNotIn("carrier_aggregate", flow.evidence_plan.required_controls)
        self.assertNotIn("absence_claim_requires_live_freshness", flow.evidence_plan.freshness_policy["reasons"])

    def test_avoid_carrier_is_soft_ranking_preference_not_absence_scope(self) -> None:
        flow = self.flow_for(origin="BER", destination="MAD", avoid_carrier=["FR"], return_date=None)

        self.assertEqual(flow.flow_decision.intent_class, "route_recommendation")
        self.assertEqual(flow.flow_decision.evidence_class, "shopping_advisory")
        self.assertNotIn("carrier_aggregate", flow.evidence_plan.required_controls)

    def test_mixed_hard_and_soft_carrier_filters_keep_hard_evidence_scope(self) -> None:
        flow = self.flow_for(origin="BER", destination="MAD", only_carrier=["LH"], prefer_carrier=["IB"], return_date=None)

        self.assertEqual(flow.flow_decision.intent_class, "carrier_or_airport_scope")
        self.assertEqual(flow.flow_decision.evidence_class, "absence_claim")
        self.assertIn("carrier_aggregate", flow.evidence_plan.required_controls)

    def test_empty_provider_output_is_provider_empty_not_structural_absence(self) -> None:
        ledger = ProbeExecutionLedger()
        control = {
            "type": "exact_airport_direct",
            "direction": "outbound",
            "origin": "BER",
            "destination": "MAD",
            "date": "2026-08-12",
            "negative_evidence": "provider_empty_only_not_route_absence",
        }
        ledger.plan_controls([control])
        ledger.record_searched(control, status="ok", provider="fli", offer_count=0, cache_status="live")

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted", "coverage_limits": {}})
        searched = diagnostics["searched_controls"][0]
        self.assertEqual(searched["evidence_type"], "provider_empty")
        self.assertEqual(searched["absence_class"], "provider_empty_not_structural_absence")
        self.assertNotEqual(searched.get("absence_class"), "structural_unavailability")

    def test_cache_freshness_policy_is_represented_for_absence_claims(self) -> None:
        flow = self.flow_for(origin="SVX", destination="KUF", max_connections=0, tier2_max_connections=0, return_date=None)

        self.assertFalse(flow.evidence_plan.live_cache_enabled)
        self.assertEqual(flow.evidence_plan.live_cache_ttl_seconds, 0)
        self.assertTrue(flow.evidence_plan.freshness_policy["requires_fresh_live"])
        self.assertIn("absence_claim_requires_live_freshness", flow.evidence_plan.freshness_policy["reasons"])
        self.assertIn("provider_empty", flow.evidence_plan.absence_taxonomy)

    def test_freshness_policy_uses_injected_today_provider(self) -> None:
        flow = self.flow_for_today(
            date(2026, 8, 10),
            origin="BER",
            destination="MAD",
            depart_date="2026-08-12",
            return_date=None,
        )

        freshness = flow.evidence_plan.freshness_policy
        self.assertEqual(freshness["today"], "2026-08-10")
        self.assertEqual(freshness["depart_date"], "2026-08-12")
        self.assertEqual(freshness["days_until_departure"], 2)
        self.assertTrue(freshness["requires_fresh_live"])
        self.assertIn("near_departure_requires_live_freshness", freshness["reasons"])


if __name__ == "__main__":
    unittest.main()
