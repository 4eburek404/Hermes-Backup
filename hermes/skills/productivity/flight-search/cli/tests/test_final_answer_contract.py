from __future__ import annotations

import copy
import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.reporting.final_answer_contract import (
    USER_ANSWER_SCHEMA_PACKAGE,
    USER_ANSWER_SCHEMA_RESOURCE,
    USER_ANSWER_SCHEMA_VERSION,
    build_user_answer_contract,
    load_user_answer_schema,
    validate_user_answer_contract,
)
from tests.test_agent_report_contract import valid_option, valid_report


def report_with_required_caveats() -> dict:
    report = valid_report()
    priority = valid_option()
    priority["id"] = "priority-svo"
    priority["category"] = "moscow_gateway_control"
    report["priority_options"] = [priority]
    report["provider_failures"] = [
        {
            "direction": "outbound",
            "leg": "hub_to_destination",
            "origin": "IST",
            "destination": "LHR",
            "date": "2026-06-01",
            "provider": "fli",
            "error": {"type": "upstream_error", "message": "FLI MCP unavailable"},
        }
    ]
    report["through_fare_checks"] = [
        {
            "direction": "outbound",
            "route": "SVX->DEL",
            "date": "2026-06-01",
            "carrier": "SU",
            "reason": "Same-carrier route can indicate through-fare opportunity.",
            "verify_with": ["airline website", "booking screen fare rules"],
        }
    ]
    report["answer_lines"] = [
        "Best CLI-ranked option: 10 000 RUB risk=good/1 elapsed=2h.",
        "Provider failure: FLI failed on 1 segment search; first IST->LHR 2026-06-01: FLI MCP unavailable.",
        "Through-fare check required: verify SU SVX->DEL on airline/GDS before pricing it as separate legs.",
        "Coverage is incomplete: planned controls without terminal live evidence are not_executed, not no-flight evidence.",
        "Provider aggregate candidate: ticketing_protection=unknown; verify single-PNR/protection, baggage, fare rules, and final fare on the booking screen.",
        "Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.",
    ]
    return report


class FinalAnswerContractTests(unittest.TestCase):
    def _round_trip_option(self, option_id: str) -> dict:
        option = copy.deepcopy(valid_option())
        option["id"] = option_id
        option["category"] = "assembled_round_trip_control"
        option["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "SU100",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "LHR",
                "departure_at": "2026-07-19T06:00:00+05:00",
                "arrival_at": "2026-07-19T08:00:00+01:00",
                "aircraft_code": "320",
                "duration_min": 360,
            },
            {
                "direction": "return",
                "flight_number": "SU101",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "LHR",
                "destination": "SVX",
                "departure_at": "2026-07-24T09:00:00+01:00",
                "arrival_at": "2026-07-24T19:00:00+05:00",
                "aircraft_code": "320",
                "duration_min": 360,
            },
        ]
        return option

    def _provider_aggregate_option(self, direction: str) -> dict:
        option = copy.deepcopy(valid_option())
        option["rank"] = None
        option["id"] = f"provider-aggregate:{direction}:agg-{direction}"
        option["category"] = "provider_aggregate_candidate"
        option["price_text"] = "21 208 RUB"
        option["elapsed"] = "9h05"
        option["risk"]["grade"] = None
        option["max_connections_per_journey"] = 1
        if direction == "outbound":
            option["segments"] = [
                {"direction": "outbound", "flight_number": "A1", "carrier": "A", "origin": "SVX", "destination": "EVN"},
                {"direction": "outbound", "flight_number": "A2", "carrier": "A", "origin": "EVN", "destination": "LTN"},
            ]
        else:
            option["segments"] = [
                {"direction": "return", "flight_number": "B1", "carrier": "B", "origin": "LGW", "destination": "AYT"},
                {"direction": "return", "flight_number": "B2", "carrier": "B", "origin": "AYT", "destination": "SVX"},
            ]
        return option

    def _two_one_way_pair_option(self) -> dict:
        option = copy.deepcopy(valid_option())
        option.update(
            {
                "rank": None,
                "id": "provider-aggregate:two-one-way-pair:agg-outbound+agg-return",
                "category": "provider_aggregate_candidate",
                "reason": "Two directional provider aggregate offers can be shown together for the requested round trip.",
                "detail_status": "summary_only",
                "price": {"amount": 64000, "currency": "RUB"},
                "price_text": "Sum of displayed one-way prices: 64 000 RUB",
                "elapsed_min": None,
                "elapsed": None,
                "outbound_time": {"itinerary_elapsed_min": 660, "flight_time_min": 300, "layover_total_min": 360},
                "return_time": {"itinerary_elapsed_min": 570, "flight_time_min": 440, "layover_total_min": 130},
                "risk": {"score": None, "grade": None, "reject": None, "top_reasons": []},
                "validation_summary": {"candidate_type": "two_one_way_pair"},
                "stop_tier": "T1_ONE_STOP",
                "max_connections_per_journey": 1,
                "journey_scope": "two_one_way_pair",
                "covers_requested_trip": True,
                "direction": None,
                "directional_only": False,
                "composed_of_directional_offers": True,
                "ticketing_model": "separate_one_way_offers",
                "user_facing_label": (
                    "Two separate one-way offers: outbound SVX→LON 21 000 RUB + return LON→SVX 43 000 RUB. "
                    "Sum of displayed one-way prices: 64 000 RUB."
                ),
                "disclaimer": (
                    "Not proven as a single PNR, protected round-trip, baggage-through itinerary, through fare, or final fare. "
                    "Verify ticketing, baggage, refund, and disruption protection on the booking screen."
                ),
                "connections": [],
                "segments": [],
                "ticketing_note": "Two separate one-way offers; verify booking-screen ticketing and protection before purchase.",
            }
        )
        return option

    def _valid_round_trip_answer(self) -> dict:
        report = report_with_required_caveats()
        report["route"]["dates"] = {"depart_date": "2026-07-19", "return_date": "2026-07-24"}
        report["recommended_options"] = [self._round_trip_option("assembled-primary")]
        return build_user_answer_contract(report)

    def _minimal_alternative(self, alternative_id: str, **overrides: object) -> dict:
        alternative = {
            "id": alternative_id,
            "category": "provider_aggregate_candidate",
            "price_text": "21 208 RUB",
            "elapsed": "9h05",
            "risk_grade": None,
            "segment_count": 2,
            "stop_tier": "T1_ONE_STOP",
            "max_connections_per_journey": 1,
        }
        alternative.update(overrides)
        return alternative

    def test_user_answer_schema_is_valid_package_resource(self) -> None:
        schema = load_user_answer_schema()
        text = resources.files(USER_ANSWER_SCHEMA_PACKAGE).joinpath(USER_ANSWER_SCHEMA_RESOURCE).read_text(encoding="utf-8")
        parsed = json.loads(text)

        Draft202012Validator.check_schema(schema)
        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:flight-search-user-answer:v1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], USER_ANSWER_SCHEMA_VERSION)
        self.assertLessEqual(len(text.encode("utf-8")), 10000)

    def test_builds_valid_user_answer_contract_from_agent_report(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())

        validate_user_answer_contract(answer)
        self.assertEqual(answer["schema_version"], USER_ANSWER_SCHEMA_VERSION)
        self.assertEqual(answer["primary_recommendation"]["id"], "assembled-1:SVX-DEL")
        self.assertEqual(answer["primary_recommendation"]["max_connections_per_journey"], 0)
        self.assertEqual(answer["stop_policy_status"]["policy"], "business_default")
        self.assertEqual(answer["evidence_status"]["provider_failure_count"], 1)
        self.assertTrue(answer["required_caveats"]["provider_failures_acknowledged"])
        self.assertTrue(answer["required_caveats"]["through_fare_verification_required"])

    def test_round_trip_provider_aggregate_alternatives_are_directional_not_full_trip(self) -> None:
        report = report_with_required_caveats()
        report["route"]["dates"] = {"depart_date": "2026-07-19", "return_date": "2026-07-24"}
        report["recommended_options"] = [self._round_trip_option("assembled-primary")]
        report["priority_options"] = [
            self._round_trip_option("assembled-round-trip"),
            self._provider_aggregate_option("outbound"),
            self._provider_aggregate_option("return"),
        ]

        answer = build_user_answer_contract(report)

        validate_user_answer_contract(answer)
        alternatives = {item["id"]: item for item in answer["alternatives"]}
        assembled = alternatives["assembled-round-trip"]
        outbound = alternatives["provider-aggregate:outbound:agg-outbound"]
        inbound = alternatives["provider-aggregate:return:agg-return"]
        self.assertEqual(assembled["journey_scope"], "round_trip")
        self.assertTrue(assembled["covers_requested_trip"])
        self.assertFalse(assembled["directional_only"])
        self.assertEqual(outbound["journey_scope"], "outbound_only")
        self.assertEqual(outbound["direction"], "outbound")
        self.assertTrue(outbound["directional_only"])
        self.assertFalse(outbound["covers_requested_trip"])
        self.assertIn("One-way outbound", outbound["user_facing_label"])
        self.assertIn("Does not cover requested round trip", outbound["user_facing_label"])
        self.assertEqual(inbound["journey_scope"], "return_only")
        self.assertEqual(inbound["direction"], "return")
        self.assertTrue(inbound["directional_only"])
        self.assertFalse(inbound["covers_requested_trip"])
        self.assertIn("One-way return", inbound["user_facing_label"])
        self.assertIn("Does not cover requested round trip", inbound["user_facing_label"])
        combined_text = " ".join(
            str(value)
            for item in (outbound, inbound)
            for value in (item.get("user_facing_label"), item.get("disclaimer"))
            if value
        ).lower()
        self.assertNotIn("single pnr", combined_text.replace("not proven as single pnr", ""))
        self.assertNotIn("protected round-trip", combined_text.replace("not proven as single pnr / protected round-trip", ""))

    def test_build_user_answer_contract_preserves_two_one_way_pair_alternative(self) -> None:
        report = report_with_required_caveats()
        report["route"]["dates"] = {"depart_date": "2026-07-19", "return_date": "2026-07-24"}
        report["recommended_options"] = [self._round_trip_option("assembled-primary")]
        report["priority_options"] = [
            self._round_trip_option(f"assembled-filler-{index}") for index in range(5)
        ] + [self._two_one_way_pair_option()]

        answer = build_user_answer_contract(report)
        validate_user_answer_contract(answer)

        alternatives = {item["id"]: item for item in answer["alternatives"]}
        self.assertIn("provider-aggregate:two-one-way-pair:agg-outbound+agg-return", alternatives)
        pair = alternatives["provider-aggregate:two-one-way-pair:agg-outbound+agg-return"]
        self.assertEqual(pair["journey_scope"], "two_one_way_pair")
        self.assertTrue(pair["covers_requested_trip"])
        self.assertIsNone(pair["direction"])
        self.assertFalse(pair["directional_only"])
        self.assertTrue(pair["composed_of_directional_offers"])
        self.assertEqual(pair["ticketing_model"], "separate_one_way_offers")
        self.assertEqual(pair["outbound_time"], {"itinerary_elapsed_min": 660, "flight_time_min": 300, "layover_total_min": 360})
        self.assertEqual(pair["return_time"], {"itinerary_elapsed_min": 570, "flight_time_min": 440, "layover_total_min": 130})
        self.assertIn("Two separate one-way offers", pair["user_facing_label"])
        self.assertIn("Not proven as a single PNR", pair["disclaimer"])

    def test_rejects_two_one_way_pair_without_separate_one_way_ticketing_model(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad-ticketing",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="provider_aggregate",
                user_facing_label="Two separate one-way offers: outbound SVX→LON + return LON→SVX.",
                disclaimer="Two separate one-way offers; verify ticketing and protection on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(any("ticketing_model" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_two_one_way_pair_claiming_single_pnr_or_protected_round_trip(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad-claim",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="separate_one_way_offers",
                user_facing_label="Two separate one-way offers: outbound SVX→LON + return LON→SVX.",
                disclaimer="Two separate one-way offers. This is a single PNR protected round-trip through fare.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("single PNR", messages)
        self.assertIn("protected", messages)

    def test_rejects_provider_aggregate_travel_time_label_when_only_flight_time_is_known(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:outbound:bad-time-label",
                journey_scope="outbound_only",
                covers_requested_trip=False,
                direction="outbound",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
                itinerary_elapsed_min=None,
                flight_time_min=545,
                layover_total_min=None,
                user_facing_label="One-way outbound alternative: SVX→LON, 21 208 RUB. Travel time: 9h05.",
                disclaimer="Provider aggregate one-way offer; verify final fare on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(any("Travel time" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_provider_aggregate_ambiguous_duration_or_elapsed_wording(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:outbound:bad-duration-wording",
                journey_scope="outbound_only",
                covers_requested_trip=False,
                direction="outbound",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
                itinerary_elapsed_min=660,
                flight_time_min=300,
                layover_total_min=360,
                user_facing_label="One-way outbound alternative: SVX→LON, 21 208 RUB. Duration: 11h00 elapsed.",
                disclaimer="Provider aggregate one-way offer; verify final fare on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("ambiguous", messages)

    def test_rejects_two_one_way_pair_with_combined_itinerary_elapsed(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad-combined-time",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="separate_one_way_offers",
                itinerary_elapsed_min=1230,
                user_facing_label="Two separate one-way offers: outbound SVX→LON + return LON→SVX. Total journey time: 20h30.",
                disclaimer="Two separate one-way offers; verify ticketing and protection on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("combined", messages)

    def test_rejects_round_trip_outbound_aggregate_without_directional_label(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:outbound:bad",
                journey_scope="round_trip",
                covers_requested_trip=True,
                direction="outbound",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("outbound_only", messages)
        self.assertIn("one-way outbound", messages)

    def test_rejects_round_trip_return_aggregate_without_directional_label(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:return:bad",
                journey_scope="round_trip",
                covers_requested_trip=True,
                direction="return",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("return_only", messages)
        self.assertIn("one-way return", messages)

    def test_rejects_two_one_way_pair_without_separate_one_way_disclaimer(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="separate_one_way_offers",
                user_facing_label="Combined provider aggregate offers",
                disclaimer="Verify fare rules and baggage on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(
            any("two separate one-way offers" in error["message"] for error in ctx.exception.details["errors"])
        )

    def test_rejects_missing_provider_failure_acknowledgement(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["provider_failures_acknowledged"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(any("provider failures" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_missing_through_fare_verification(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["through_fare_verification_required"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(any("through-fare" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_missing_coverage_incompleteness_acknowledgement(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["coverage_incompleteness_acknowledged"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(any("incomplete coverage" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_missing_source_boundary_and_purchase_verification(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["source_boundaries_included"] = False
        answer["required_caveats"]["purchase_screen_verification_required"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("source-boundary", messages)
        self.assertIn("purchase-screen", messages)


if __name__ == "__main__":
    unittest.main()
