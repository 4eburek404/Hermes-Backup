from __future__ import annotations

import unittest

from flights_cli.pipeline.search_request import search_request_from_payload

from helpers import future_departure_date


class RequestNormalizationTests(unittest.TestCase):
    def test_v3_request_normalizes_to_current_input_version(self) -> None:
        """Вход без версии и вход v3 приезжают к текущей версии запроса.

        Раньше это утверждение жило в тест-файле про маршрутные гипотезы и
        уехало бы вместе со шлюзовым слоем. Гипотезы к нормализации входа
        отношения не имеют: поле схлопывается в пустое, и это про вход.
        """
        depart = future_departure_date()
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "PUS",
                "destination": "SVX",
                "depart_date": depart.isoformat(),
            }
        )

        self.assertEqual(request.route_hypotheses, ())
        self.assertEqual(
            request.to_payload()["schema_version"], "flight_search_request.v4"
        )


if __name__ == "__main__":
    unittest.main()
