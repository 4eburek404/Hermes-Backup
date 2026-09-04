from __future__ import annotations

from copy import deepcopy
import unittest

from flights_cli.contracts.validation import validate_contract_payload
from flights_cli.errors import CliError
from flights_cli.execution.search_evidence import SearchEvidence
from flights_cli.pipeline.result_contract import validate_flight_search_result
from tests.fixtures.result_fixtures import (
    DEPART,
    NEXT_DAY,
    connecting_option,
    direct_option,
    non_stop_round_trip_option,
    probe_ledger,
    request_payload,
    valid_result,
)


class ResultContractTests(unittest.TestCase):
    def test_search_evidence_is_deeply_frozen(self) -> None:
        evidence = SearchEvidence.freeze(
            primary_offer_results=[
                {"offer_count": 0, "top_offers": [{"id": "offer-1", "legs": [1]}]}
            ],
            probe_ledger={
                "failed_probes": [
                    {
                        "probe_id": "probe-failed",
                        "provider": "tutu",
                        "error": {"type": "upstream_error", "message": "offline"},
                    }
                ]
            },
            direct_inventory_searches=[],
            direct_inventory_results=[],
        )

        with self.assertRaises(TypeError):
            evidence.primary_offer_results[0]["offer_count"] = 1
        with self.assertRaises(TypeError):
            evidence.primary_offer_results[0]["top_offers"][0]["legs"].append(2)
        with self.assertRaises(TypeError):
            evidence.probe_ledger["failed_probes"][0]["error"]["type"] = "other"

    def test_result_has_one_public_output_path(self) -> None:
        result = valid_result()

        self.assertEqual(
            set(result),
            {
                "schema_version",
                "request",
                "route",
                "options",
                "evidence",
                "rendered_text",
            },
        )
        self.assertEqual(result["schema_version"], "flight_search_result.v1")

    def test_unknown_result_property_is_rejected(self) -> None:
        result = valid_result()
        result["unknown"] = True

        with self.assertRaises(CliError):
            validate_contract_payload("search_result", result)

    def test_route_must_repeat_the_request(self) -> None:
        result = valid_result()
        result["route"]["destination"] = "LED"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_option_cannot_come_from_an_unsearched_provider(self) -> None:
        # Провайдер, отброшенный по возможностям, до пробы не доходит.
        # Вариант «от него» означал бы, что источник в ответе выдуман.
        with self.assertRaises(CliError):
            valid_result(ledger=probe_ledger(searched=["tutu"]))

    def test_connection_must_match_the_flights_around_it(self) -> None:
        result = valid_result()
        result["options"][0]["directions"]["outbound"]["connections"][0]["minutes"] += 5

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_connection_count_must_match_the_gaps_between_flights(self) -> None:
        result = valid_result()
        leg = result["options"][0]["directions"]["outbound"]
        leg["connections"] = []

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_single_flight_leg_cannot_carry_a_connection(self) -> None:
        result = valid_result([direct_option()])
        result["options"][0]["directions"]["outbound"]["connections"] = [
            {"airport": "SVO", "minutes": 60, "comfort": "comfortable"}
        ]

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_segment_chain_must_be_continuous(self) -> None:
        result = valid_result()
        leg = result["options"][0]["directions"]["outbound"]
        leg["segments"][1]["origin"] = "LED"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_arrival_before_departure_is_rejected(self) -> None:
        result = valid_result()
        segment = result["options"][0]["directions"]["outbound"]["segments"][0]
        segment["arrival_at"] = f"{DEPART}T00:00:00+03:00"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_empty_leg_is_rejected(self) -> None:
        result = valid_result()
        result["options"][0]["directions"]["outbound"]["segments"] = []

        with self.assertRaises(CliError):
            validate_contract_payload("search_result", result)

    def test_leg_endpoints_must_match_the_request(self) -> None:
        result = valid_result()
        result["options"][0]["directions"]["outbound"]["segments"][0]["origin"] = "LED"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_segment_duration_must_match_timestamps(self) -> None:
        result = valid_result()
        result["options"][0]["directions"]["outbound"]["segments"][0][
            "duration_min"
        ] += 1

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_segment_requires_offset_timestamp(self) -> None:
        result = deepcopy(valid_result())
        result["options"][0]["directions"]["outbound"]["segments"][0][
            "departure_at"
        ] = f"{DEPART}T06:00:00"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_currency_mismatch_is_rejected(self) -> None:
        result = valid_result()
        result["options"][0]["price"]["currency"] = "EUR"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_round_trip_request_requires_both_legs(self) -> None:
        with self.assertRaises(CliError):
            valid_result(
                request=request_payload(return_date=NEXT_DAY),
            )

    def test_one_way_request_cannot_carry_a_return_leg(self) -> None:
        result = valid_result()
        result["options"][0]["directions"]["return"] = deepcopy(
            result["options"][0]["directions"]["outbound"]
        )

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_direct_option_states_no_ticket_protection(self) -> None:
        # Прямой рейс единым билетом нечему распасться: раньше он получал
        # single_pnr_unproven наравне со стыковочным.
        result = valid_result([direct_option()])
        option = result["options"][0]

        self.assertEqual(option["ticketing"], {"model": "provider_order"})
        self.assertEqual(
            option["warnings"], ["baggage_unknown", "verify_on_booking_screen"]
        )

    def test_connecting_option_must_state_ticket_protection(self) -> None:
        result = valid_result()
        result["options"][0]["ticketing"].pop("single_pnr")

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_single_flight_option_must_not_state_ticket_protection(self) -> None:
        result = valid_result([direct_option()])
        result["options"][0]["ticketing"]["single_pnr"] = "unproven"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_non_stop_round_trip_states_no_transfer_protection(self) -> None:
        # Туда и обратно — два рейса, но не стык. Счёт рейсов целиком давал
        # здесь 1 + 1 = 2 и требовал оговорок, которых маршруту не с чего иметь.
        result = valid_result(
            [non_stop_round_trip_option()],
            request=request_payload(return_date=NEXT_DAY),
        )
        option = result["options"][0]

        self.assertEqual(option["ticketing"], {"model": "provider_order"})
        self.assertEqual(
            option["warnings"], ["baggage_unknown", "verify_on_booking_screen"]
        )

    def test_non_stop_round_trip_cannot_claim_a_transfer_to_protect(self) -> None:
        result = valid_result(
            [non_stop_round_trip_option()],
            request=request_payload(return_date=NEXT_DAY),
        )
        result["options"][0]["ticketing"]["through_baggage"] = "unproven"
        result["options"][0]["warnings"].append("through_baggage_unproven")

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_assembled_route_states_single_pnr_without_a_connection(self) -> None:
        # Единый PNR — вопрос про число заказов: у собранного маршрута он
        # осмыслен и там, где пересадки нет.
        result = valid_result(
            [
                non_stop_round_trip_option(
                    ticketing_model="separate_ticket_sum",
                    ticket_protection={
                        "status": "unprotected",
                        "source": "separate_ticket_boundary",
                        "reasons": ["separate_tickets"],
                    },
                )
            ],
            request=request_payload(return_date=NEXT_DAY),
        )
        option = result["options"][0]

        self.assertEqual(
            option["ticketing"], {"model": "assembled", "single_pnr": "unproven"}
        )
        self.assertNotIn("through_baggage_unproven", option["warnings"])
        self.assertIn("single_pnr_unproven", option["warnings"])

    def test_warnings_must_agree_with_ticketing(self) -> None:
        result = valid_result()
        result["options"][0]["warnings"].remove("single_pnr_unproven")

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_options_are_numbered_from_one_in_order(self) -> None:
        result = valid_result([connecting_option(), direct_option()])

        self.assertEqual([option["number"] for option in result["options"]], [1, 2])
        result["options"][1]["number"] = 5
        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_missing_flight_number_is_allowed(self) -> None:
        option = direct_option()
        segments = [dict(option["journeys"][0]["segments"][0], flight_number=None)]
        option["journeys"] = [{"direction": "outbound", "segments": segments}]

        result = valid_result([option])

        validate_flight_search_result(result)
        self.assertIn("номер рейса не предоставлен", result["rendered_text"])


if __name__ == "__main__":
    unittest.main()
