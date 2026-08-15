"""Carrier adapters must emit only the minimal itinerary needed by the renderer."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

ROOT_FIELDS = {
    "schema_version",
    "pnr",
    "passengers",
    "ticket_number",
    "booking_url",
    "flights",
}
FLIGHT_FIELDS = {"flight_number", "departure", "arrival", "aircraft", "status"}
ENDPOINT_FIELDS = {"airport", "city", "local", "tz"}
REMOVED_FIELD_NAMES = {
    "booking_reference",
    "calendar_name",
    "alarms_minutes",
    "links",
    "url",
    "carrier",
    "carrier_code",
    "operating_carrier",
    "terminal",
    "gate",
    "seat",
    "baggage",
    "cabin",
    "fare",
    "notes",
    "source",
    "extensions",
}


class CarrierMinimalOutputTests(unittest.TestCase):
    maxDiff = None

    def assert_minimal_itinerary(self, itinerary: dict[str, object]) -> None:
        from flight_calendar import itinerary_contract

        itinerary_contract.validate_itinerary_schema(itinerary)
        itinerary_contract.validate_itinerary_semantics(itinerary)
        self.assertLessEqual(set(itinerary), ROOT_FIELDS)
        self.assertIn("pnr", itinerary)
        self.assertIn("booking_url", itinerary)
        self.assertIn("flights", itinerary)
        for flight in itinerary["flights"]:  # type: ignore[index]
            self.assertLessEqual(set(flight), FLIGHT_FIELDS)
            self.assertLessEqual(set(flight["departure"]), ENDPOINT_FIELDS)
            self.assertLessEqual(set(flight["arrival"]), ENDPOINT_FIELDS)
        serialized = json.dumps(itinerary, ensure_ascii=False)
        for field in REMOVED_FIELD_NAMES:
            self.assertNotIn(f'"{field}"', serialized)

    def test_aeroflot_converter_emits_minimal_itinerary(self) -> None:
        from flight_calendar.carriers import aeroflot

        data = {
            "pnr_locator": "ABC123",
            "passengers": [
                {
                    "last_name": "ORLOV",
                    "first_name": "KONSTANTIN",
                    "ticketing_documents": {"tickets": [{"number": "5552400000000"}]},
                }
            ],
            "warnings": [{"description": "legacy warning must not leak"}],
            "legs": [
                {
                    "segments": [
                        {
                            "origin": {
                                "airport_code": "SVO",
                                "city_name": "Москва",
                                "terminal_code": "B",
                            },
                            "destination": {
                                "airport_code": "SVX",
                                "city_name": "Екатеринбург",
                                "terminal_code": "A",
                            },
                            "departure": "2026-06-01 09:15",
                            "arrival": "2026-06-01 13:45",
                            "airline_code": "SU",
                            "airline_name": "Аэрофлот",
                            "flight_number": "1234",
                            "status_code": "HK",
                            "aircraft_type_name": "Boeing 737",
                            "fare_group_name": "Economy",
                            "cabin_name": "Y",
                            "franchise_info": ["1PC"],
                        }
                    ]
                }
            ],
        }

        itinerary = aeroflot.convert_to_itinerary(
            data,
            {"SVO": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"},
            booking_url="https://carrier.example/aero",
        )

        self.assert_minimal_itinerary(itinerary)
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["passengers"], ["ORLOV KONSTANTIN"])
        self.assertEqual(itinerary["ticket_number"], "5552400000000")

    def test_ural_converter_emits_minimal_itinerary(self) -> None:
        from flight_calendar.carriers import ural

        response = {
            "data": {
                "number": "ABC123",
                "passengers": [{"surname": "ORLOV", "firstName": "KONSTANTIN"}],
                "tickets": [{"number": "2622400000000", "flightReferences": ["seg-1"]}],
                "journey": {
                    "outboundFlights": [
                        {
                            "origin": "SVO",
                            "destination": "SVX",
                            "departureDate": "2026-06-01T09:15:00",
                            "arrivalDate": "2026-06-01T13:45:00",
                            "marketingCarrier": "U6",
                            "flightNumber": "123",
                            "referenceNumber": "seg-1",
                            "statuses": ["HK"],
                            "aircraft": "Airbus A320",
                            "classOfService": "Y",
                            "commercialFamily": "Promo",
                        }
                    ]
                },
            }
        }

        itinerary = ural.convert_to_itinerary(
            response,
            {"SVO": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"},
            booking_url="https://carrier.example/ural",
        )

        self.assert_minimal_itinerary(itinerary)
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["ticket_number"], "2622400000000")

    def test_utair_converter_emits_minimal_itinerary(self) -> None:
        from flight_calendar.carriers import utair

        data = {
            "orders": [
                {
                    "rloc": "ABC123",
                    "status": "ACTIVE",
                    "passengers": [{"last_name": "ORLOV", "first_name": "KONSTANTIN"}],
                    "tickets": [{"number": "2982400000000"}],
                    "offers": [{"segmentId": "1", "brandName": "Optimum"}],
                    "services": [{"segmentId": "1", "name": "Baggage 1PC"}],
                    "segments": [
                        {
                            "segmentId": "1",
                            "departure_airport_code": "VKO",
                            "arrival_airport_code": "SVX",
                            "departure_city": "Москва",
                            "arrival_city": "Екатеринбург",
                            "departure_terminal": "A",
                            "arrival_terminal": "1",
                            "departure_datetime": "2026-06-01T09:15:00",
                            "arrival_datetime": "2026-06-01T13:45:00",
                            "ak": "UT",
                            "flight_number": "100",
                            "status": "HK",
                            "aircraft": "Boeing 737",
                            "class": "Y",
                            "baggage": "1PC",
                        }
                    ],
                }
            ]
        }

        itinerary = utair.convert_to_itinerary(
            data,
            {"VKO": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"},
            booking_url="https://carrier.example/utair",
        )

        self.assert_minimal_itinerary(itinerary)
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["ticket_number"], "2982400000000")

    def test_redwings_converter_and_query_are_minimal(self) -> None:
        from flight_calendar.carriers import redwings

        data = {
            "data": {
                "FindOrder": {
                    "locator": "ABC123",
                    "status": "CONFIRMED",
                    "paymentStatus": "PAID",
                    "flight": {
                        "segmentGroups": [
                            {
                                "fareFamily": {"title": "Light"},
                                "fareGroup": {"name": "Promo"},
                                "segments": [
                                    {
                                        "id": "seg-1",
                                        "flightNumber": "123",
                                        "status": "CONFIRMED",
                                        "marketingAirline": {
                                            "name": "Red Wings",
                                            "iata": "WZ",
                                        },
                                        "aircraft": {"name": "Sukhoi Superjet"},
                                        "departure": {
                                            "date": "2026-06-01",
                                            "time": "09:15",
                                            "terminal": "1",
                                            "airport": {
                                                "iata": "SVO",
                                                "city": {"name": "Москва"},
                                            },
                                        },
                                        "arrival": {
                                            "date": "2026-06-01",
                                            "time": "13:45",
                                            "terminal": "A",
                                            "airport": {
                                                "iata": "SVX",
                                                "city": {"name": "Екатеринбург"},
                                            },
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                    "travellers": [
                        {
                            "values": [
                                {"type": "LastName", "value": "ORLOV"},
                                {"type": "FirstName", "value": "KONSTANTIN"},
                            ],
                            "tickets": [
                                {
                                    "number": "3092400000000",
                                    "coupons": [{"segment": {"id": "seg-1"}}],
                                }
                            ],
                            "services": {
                                "seats": [
                                    {
                                        "segment": {"id": "seg-1"},
                                        "seat": {"number": "12A"},
                                    }
                                ]
                            },
                        }
                    ],
                }
            }
        }

        itinerary = redwings.convert_to_itinerary(
            data,
            {"SVO": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"},
            booking_url="https://carrier.example/redwings",
        )

        self.assert_minimal_itinerary(itinerary)
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["ticket_number"], "3092400000000")
        self.assertNotIn("brandIncludedServices", redwings.FIND_ORDER_QUERY)
        self.assertNotIn("gdsServices", redwings.FIND_ORDER_QUERY)
        self.assertNotIn("preselectedServices", redwings.FIND_ORDER_QUERY)
        self.assertNotIn("fareFamily", redwings.FIND_ORDER_QUERY)
        self.assertNotIn("fareGroup", redwings.FIND_ORDER_QUERY)
        self.assertNotIn("terminal", redwings.FIND_ORDER_QUERY)
        self.assertNotIn("coupons", redwings.FIND_ORDER_QUERY)

    def test_s7_converter_emits_minimal_itinerary(self) -> None:
        from flight_calendar.carriers import s7

        data = [
            {
                "air": {
                    "pnr": "ABC123",
                    "status": "CONFIRMED",
                    "passengers": [
                        {
                            "name": {
                                "lastName": "ORLOV",
                                "firstName": "KONSTANTIN",
                                "fullName": "ORLOV KONSTANTIN",
                            },
                            "ticketNumber": "4212400000000",
                            "document": {"number": "must not leak"},
                        }
                    ],
                    "routes": [
                        {
                            "segments": [
                                {
                                    "departureDate": "2026-06-01T09:15:00",
                                    "arrivalDate": "2026-06-01T13:45:00",
                                    "departureTimeZone": "Europe/Moscow",
                                    "arrivalTimeZone": "Asia/Yekaterinburg",
                                    "departureAirport": {
                                        "code": "DME",
                                        "cityName": "Москва",
                                        "terminal": "T2",
                                    },
                                    "arrivalAirport": {
                                        "code": "SVX",
                                        "cityName": "Екатеринбург",
                                        "terminal": "A",
                                    },
                                    "marketingAirline": {
                                        "code": "S7",
                                        "displayCode": "S7",
                                        "flightNumber": "1234",
                                    },
                                    "operatingAirline": {
                                        "code": "S7",
                                        "displayCode": "S7",
                                        "flightNumber": "1234",
                                    },
                                    "aircraft": {"name": "Airbus A320"},
                                    "status": "CONFIRMED",
                                    "supplierStatus": "HK",
                                }
                            ]
                        }
                    ],
                }
            }
        ]

        itinerary = s7.convert_to_itinerary(
            data, {}, booking_url="https://carrier.example/s7"
        )

        self.assert_minimal_itinerary(itinerary)
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["passengers"], ["ORLOV KONSTANTIN"])
        self.assertEqual(itinerary["ticket_number"], "4212400000000")
        serialized = json.dumps(itinerary, ensure_ascii=False)
        self.assertNotIn("must not leak", serialized)


if __name__ == "__main__":
    unittest.main()
