from __future__ import annotations

import argparse
import unittest
from typing import Any

from flights_cli.reporting.agent_report_builder import build_agent_report
from flights_cli.services.agent_report_contract import validate_agent_report
from flights_cli.services.assembly import assemble_segment_results, empty_assembled_result


LON_AIRPORTS = ["LHR", "LGW", "STN", "LTN"]
MOW_AIRPORTS = ["SVO", "DME", "VKO"]


def segment(origin: str, destination: str, depart: str, arrive: str, flight: str, carrier: str) -> dict[str, Any]:
    return {
        "origin": origin,
        "destination": destination,
        "departure_at": depart,
        "arrival_at": arrive,
        "flight_number": flight,
        "carrier": carrier,
        "operating_carrier": carrier,
    }


def offer(offer_id: str, price: int, segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": offer_id,
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0]["departure_at"],
        "arrival_at": segments[-1]["arrival_at"],
        "price": price,
        "currency": "RUB",
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "segments": segments,
    }


def segment_result(direction: str, leg: str, origin: str, destination: str, offers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "direction": direction,
        "leg": leg,
        "origin": origin,
        "destination": destination,
        "date": "2026-07-19",
        "provider": "fixture",
        "status": "ok",
        "offer_count": len(offers),
        "cache_status": "fixture",
        "query": {"origin": origin, "destination": destination, "date": "2026-07-19", "currency": "RUB"},
        "source_key": "fixture",
        "raw_count": len(offers),
        "parse_errors": 0,
        "offers": offers,
    }


class RuPriorityAgentReportBuilderTests(unittest.TestCase):
    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            profile="business",
            ticketing="separate",
            min_same_airport_min=180,
            min_cross_airport_min=300,
            limit_per_pair=10,
            max_candidates=10,
            candidate_pool_limit=5000,
            max_reasons=5,
            only_carrier=None,
            exclude_carrier=None,
            prefer_carrier=None,
            avoid_carrier=None,
            include_filtered=20,
            stop_policy="business-default",
            max_connections=None,
            fallback_max_connections=None,
            agent_brief=True,
            return_date=None,
            include_candidates=0,
            include_ranked_candidates=10,
            include_rejected_pairs=0,
        )

    def _report(
        self,
        segment_results: list[dict[str, Any]],
        *,
        origin: str = "SVX",
        destination: str = "LON",
        origin_airports: list[str] | None = None,
        destination_airports: list[str] | None = None,
        routing_strategy: str = "ru-priority",
    ) -> dict[str, Any]:
        args = self._args()
        data = assemble_segment_results(segment_results, args) if segment_results else empty_assembled_result(args)
        data["live_search"] = {
            "source": "fixture",
            "provider_policy": "kupibilet",
            "plan": {
                "origin": origin,
                "destination": destination,
                "origin_airports": origin_airports or [origin],
                "destination_airports": destination_airports or [destination],
                "dates": {"depart": "2026-07-19", "return": None},
                "profile": "business",
                "routing_strategy": routing_strategy,
                "coverage_mode": "targeted",
                "coverage_controls": [],
                "coverage_limits": {},
            },
            "segment_searches": segment_results,
            "hub_viability": [],
            "aggregate_controls": [],
            "failures": [],
            "failure_count": 0,
        }
        report = build_agent_report(data)
        validate_agent_report(report)
        return report

    def _control_option(self, report: dict[str, Any], branch: str) -> dict[str, Any]:
        control = report["ru_priority_controls"][f"{branch}_control"]
        self.assertTrue(control["visible"], branch)
        self.assertIsInstance(control["priority_option_id"], str)
        option = next(item for item in report["priority_options"] if item["id"] == control["priority_option_id"])
        self.assertEqual(option.get("control_family"), "ru_priority")
        self.assertEqual(option.get("control_branch"), branch)
        self.assertEqual(option.get("visibility_role"), "priority_control")
        return option

    def test_direct_destination_branch_is_viable_visible_and_not_mixed_with_hubs(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "direct_outbound",
                    "SVX",
                    "LHR",
                    [
                        offer(
                            "svx-lhr-direct",
                            31000,
                            [segment("SVX", "LHR", "2026-07-19T07:00:00+05:00", "2026-07-19T09:30:00+01:00", "U6305", "U6")],
                        )
                    ],
                )
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["direct_destination_control"]["checked"])
        self.assertTrue(controls["direct_destination_control"]["viable"])
        self.assertFalse(controls["ist_primary_hub_control"]["viable"])
        self.assertFalse(controls["moscow_gateway_control"]["viable"])
        option = self._control_option(report, "direct_destination")
        self.assertEqual([segment["origin"] for segment in option["segments"]], ["SVX"])
        self.assertEqual([segment["destination"] for segment in option["segments"]], ["LHR"])

    def test_direct_destination_branch_accepts_connecting_itinerary_from_direct_search(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "direct_outbound",
                    "SVX",
                    "LHR",
                    [
                        offer(
                            "svx-lhr-via-ist-direct-search",
                            36000,
                            [
                                segment("SVX", "IST", "2026-07-19T07:00:00+05:00", "2026-07-19T09:00:00+03:00", "U6301", "U6"),
                                segment("IST", "LHR", "2026-07-19T14:00:00+03:00", "2026-07-19T16:00:00+01:00", "TK1985", "TK"),
                            ],
                        )
                    ],
                )
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        control = controls["direct_destination_control"]
        self.assertTrue(control["checked"])
        self.assertEqual(control["execution_state"], "executed")
        self.assertNotIn(control["execution_state"], {"partial", "not_generated"})
        self.assertTrue(control["viable"])
        self.assertTrue(control["visible"])
        self.assertIsInstance(control["priority_option_id"], str)
        self.assertFalse(controls["ist_primary_hub_control"]["viable"])
        self.assertFalse(controls["moscow_gateway_control"]["viable"])
        option = self._control_option(report, "direct_destination")
        self.assertEqual([segment["origin"] for segment in option["segments"]], ["SVX", "IST"])
        self.assertEqual([segment["destination"] for segment in option["segments"]], ["IST", "LHR"])

    def test_ist_primary_branch_is_viable_visible_and_not_moscow_gateway(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "IST",
                    [
                        offer(
                            "svx-ist",
                            25000,
                            [segment("SVX", "IST", "2026-07-19T07:00:00+05:00", "2026-07-19T09:00:00+03:00", "U6301", "U6")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "IST",
                    "LHR",
                    [
                        offer(
                            "ist-lhr",
                            18000,
                            [segment("IST", "LHR", "2026-07-19T14:00:00+03:00", "2026-07-19T16:00:00+01:00", "TK1985", "TK")],
                        )
                    ],
                ),
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["requested"])
        self.assertTrue(controls["checked"])
        self.assertEqual(set(controls["scope"]["destination_airports"]), set(LON_AIRPORTS))
        self.assertEqual(set(controls["scope"]["moscow_airports"]), set(MOW_AIRPORTS))
        self.assertTrue(controls["ist_primary_hub_control"]["checked"])
        self.assertTrue(controls["ist_primary_hub_control"]["viable"])
        self.assertFalse(controls["direct_destination_control"]["viable"])
        self.assertFalse(controls["direct_destination_control"]["visible"])
        self.assertFalse(controls["moscow_gateway_control"]["viable"])
        self._control_option(report, "ist_primary_hub")

    def test_moscow_gateway_branch_uses_mow_destination_direct_shape(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "SVO",
                    [
                        offer(
                            "svx-svo",
                            12000,
                            [segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "SVO",
                    "LHR",
                    [
                        offer(
                            "svo-lhr",
                            22000,
                            [segment("SVO", "LHR", "2026-07-19T11:00:00+03:00", "2026-07-19T13:00:00+01:00", "SU2578", "SU")],
                        )
                    ],
                ),
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["moscow_gateway_control"]["checked"])
        self.assertEqual(controls["moscow_gateway_control"]["execution_state"], "executed")
        self.assertTrue(controls["moscow_gateway_control"]["viable"])
        self.assertEqual(set(controls["scope"]["moscow_airports"]), set(MOW_AIRPORTS))
        option = self._control_option(report, "moscow_gateway")
        self.assertEqual([segment["origin"] for segment in option["segments"]], ["SVX", "SVO"])
        self.assertEqual([segment["destination"] for segment in option["segments"]], ["SVO", "LHR"])

    def test_moscow_gateway_partial_prefix_evidence_is_not_fully_executed(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "SVO",
                    [
                        offer(
                            "svx-svo",
                            12000,
                            [segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU")],
                        )
                    ],
                )
            ],
            destination_airports=LON_AIRPORTS,
        )

        control = report["ru_priority_controls"]["moscow_gateway_control"]
        self.assertTrue(control["checked"])
        self.assertEqual(control["execution_state"], "partial")
        self.assertFalse(control["viable"])
        self.assertFalse(control["visible"])
        self.assertIsNone(control["priority_option_id"])

    def test_moscow_gateway_executed_empty_searches_are_no_viable_result(self) -> None:
        report = self._report(
            [
                segment_result("outbound", "origin_to_hub", "SVX", "SVO", []),
                segment_result("outbound", "hub_to_destination", "SVO", "LHR", []),
            ],
            destination_airports=LON_AIRPORTS,
        )

        control = report["ru_priority_controls"]["moscow_gateway_control"]
        self.assertTrue(control["checked"])
        self.assertEqual(control["execution_state"], "executed_no_viable_result")
        self.assertFalse(control["viable"])
        self.assertFalse(control["visible"])
        self.assertIsNone(control["priority_option_id"])

    def test_moscow_via_ist_fallback_is_used_only_when_mow_destination_is_unviable(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "IST",
                    [
                        offer(
                            "svx-svo-ist",
                            26000,
                            [
                                segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU"),
                                segment("SVO", "IST", "2026-07-19T10:30:00+03:00", "2026-07-19T14:35:00+03:00", "SU2136", "SU"),
                            ],
                        )
                    ],
                ),
                segment_result("outbound", "hub_to_destination", "SVO", "LHR", []),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "IST",
                    "LHR",
                    [
                        offer(
                            "ist-lhr",
                            18000,
                            [segment("IST", "LHR", "2026-07-19T20:00:00+03:00", "2026-07-19T22:00:00+01:00", "TK1987", "TK")],
                        )
                    ],
                ),
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["moscow_gateway_control"]["checked"])
        self.assertFalse(controls["moscow_gateway_control"]["viable"])
        self.assertTrue(controls["moscow_via_ist_fallback_control"]["checked"])
        self.assertEqual(controls["moscow_via_ist_fallback_control"]["execution_state"], "assembled_evidence")
        self.assertTrue(controls["moscow_via_ist_fallback_control"]["viable"])
        option = self._control_option(report, "moscow_via_ist_fallback")
        self.assertEqual([segment["origin"] for segment in option["segments"]], ["SVX", "SVO", "IST"])
        self.assertEqual([segment["destination"] for segment in option["segments"]], ["SVO", "IST", "LHR"])

    def test_moscow_via_ist_fallback_is_not_priority_control_when_mow_destination_is_viable(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "SVO",
                    [
                        offer(
                            "svx-svo",
                            12000,
                            [segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "SVO",
                    "LHR",
                    [
                        offer(
                            "svo-lhr",
                            22000,
                            [segment("SVO", "LHR", "2026-07-19T11:00:00+03:00", "2026-07-19T13:00:00+01:00", "SU2578", "SU")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "IST",
                    [
                        offer(
                            "svx-svo-ist",
                            26000,
                            [
                                segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU"),
                                segment("SVO", "IST", "2026-07-19T10:30:00+03:00", "2026-07-19T14:35:00+03:00", "SU2136", "SU"),
                            ],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "IST",
                    "LHR",
                    [
                        offer(
                            "ist-lhr",
                            18000,
                            [segment("IST", "LHR", "2026-07-19T20:00:00+03:00", "2026-07-19T22:00:00+01:00", "TK1987", "TK")],
                        )
                    ],
                ),
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["moscow_gateway_control"]["checked"])
        self.assertTrue(controls["moscow_gateway_control"]["viable"])
        self.assertTrue(controls["moscow_gateway_control"]["visible"])
        self.assertFalse(controls["moscow_via_ist_fallback_control"]["viable"])
        self.assertFalse(controls["moscow_via_ist_fallback_control"]["visible"])
        self.assertEqual(
            controls["moscow_via_ist_fallback_control"]["execution_state"],
            "skipped_better_options_available",
        )
        self.assertIsNone(controls["moscow_via_ist_fallback_control"]["priority_option_id"])
        self._control_option(report, "moscow_gateway")
        fallback_priority_options = [
            item
            for item in report["priority_options"]
            if item.get("control_branch") == "moscow_via_ist_fallback" and item.get("visibility_role") == "priority_control"
        ]
        self.assertEqual(fallback_priority_options, [])

    def test_moscow_via_ist_fallback_is_skipped_when_one_stop_ist_primary_exists(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "IST",
                    [
                        offer(
                            "svx-ist",
                            25000,
                            [segment("SVX", "IST", "2026-07-19T07:00:00+05:00", "2026-07-19T09:00:00+03:00", "U6301", "U6")],
                        ),
                        offer(
                            "svx-svo-ist",
                            26000,
                            [
                                segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU"),
                                segment("SVO", "IST", "2026-07-19T10:30:00+03:00", "2026-07-19T14:35:00+03:00", "SU2136", "SU"),
                            ],
                        ),
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "IST",
                    "LHR",
                    [
                        offer(
                            "ist-lhr",
                            18000,
                            [segment("IST", "LHR", "2026-07-19T20:00:00+03:00", "2026-07-19T22:00:00+01:00", "TK1987", "TK")],
                        )
                    ],
                ),
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["ist_primary_hub_control"]["viable"])
        fallback = controls["moscow_via_ist_fallback_control"]
        self.assertTrue(fallback["checked"])
        self.assertEqual(fallback["execution_state"], "skipped_better_options_available")
        self.assertFalse(fallback["viable"])
        self.assertFalse(fallback["visible"])
        self.assertIsNone(fallback["priority_option_id"])
        self.assertEqual(fallback["evidence_option_ids"], [])
        fallback_priority_options = [
            item
            for item in report["priority_options"]
            if item.get("control_branch") == "moscow_via_ist_fallback" and item.get("visibility_role") == "priority_control"
        ]
        self.assertEqual(fallback_priority_options, [])

    def test_incomplete_svx_svo_ist_prefix_does_not_satisfy_moscow_control_to_london(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "IST",
                    [
                        offer(
                            "svx-svo-ist",
                            26000,
                            [
                                segment("SVX", "SVO", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "SU1401", "SU"),
                                segment("SVO", "IST", "2026-07-19T10:30:00+03:00", "2026-07-19T14:35:00+03:00", "SU2136", "SU"),
                            ],
                        )
                    ],
                )
            ],
            destination_airports=LON_AIRPORTS,
        )

        controls = report["ru_priority_controls"]
        self.assertFalse(controls["moscow_gateway_control"]["viable"])
        self.assertFalse(controls["moscow_via_ist_fallback_control"]["viable"])
        self.assertEqual(controls["decision"], "no_viable_ru_priority_control")

    def test_svx_mct_keeps_ist_primary_and_moscow_gateway_as_separate_branches(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "IST",
                    [
                        offer(
                            "svx-ist",
                            23000,
                            [segment("SVX", "IST", "2026-07-19T07:00:00+05:00", "2026-07-19T09:00:00+03:00", "U6301", "U6")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "IST",
                    "MCT",
                    [
                        offer(
                            "ist-mct",
                            16000,
                            [segment("IST", "MCT", "2026-07-19T14:00:00+03:00", "2026-07-19T20:00:00+04:00", "TK774", "TK")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "origin_to_hub",
                    "SVX",
                    "DME",
                    [
                        offer(
                            "svx-dme",
                            11000,
                            [segment("SVX", "DME", "2026-07-19T06:00:00+05:00", "2026-07-19T06:40:00+03:00", "U6261", "U6")],
                        )
                    ],
                ),
                segment_result(
                    "outbound",
                    "hub_to_destination",
                    "DME",
                    "MCT",
                    [
                        offer(
                            "dme-mct",
                            21000,
                            [segment("DME", "MCT", "2026-07-19T11:00:00+03:00", "2026-07-19T17:00:00+04:00", "WY184", "WY")],
                        )
                    ],
                ),
            ],
            destination="MCT",
            destination_airports=["MCT"],
        )

        controls = report["ru_priority_controls"]
        self.assertTrue(controls["ist_primary_hub_control"]["viable"])
        self.assertTrue(controls["moscow_gateway_control"]["viable"])
        self.assertFalse(controls["moscow_via_ist_fallback_control"]["viable"])
        self._control_option(report, "ist_primary_hub")
        self._control_option(report, "moscow_gateway")

    def test_non_ru_global_route_does_not_generate_ru_priority_controls(self) -> None:
        report = self._report(
            [
                segment_result(
                    "outbound",
                    "direct_outbound",
                    "IST",
                    "LHR",
                    [
                        offer(
                            "ist-lhr-direct",
                            18000,
                            [segment("IST", "LHR", "2026-07-19T14:00:00+03:00", "2026-07-19T16:00:00+01:00", "TK1985", "TK")],
                        )
                    ],
                )
            ],
            origin="IST",
            destination="LON",
            origin_airports=["IST"],
            destination_airports=LON_AIRPORTS,
            routing_strategy="hub-list",
        )

        self.assertNotIn("ru_priority_controls", report)
        self.assertFalse(any(item.get("control_family") == "ru_priority" for item in report["priority_options"]))


if __name__ == "__main__":
    unittest.main()
