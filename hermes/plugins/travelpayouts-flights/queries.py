"""GraphQL queries for Travelpayouts Data API flight price search."""
from __future__ import annotations

GRAPHQL_ONE_WAY_QUERY = """
query PricesOneWay(
    $origin: String!,
    $destination: String!,
    $depart_dates: [Date!],
    $direct: Boolean!,
    $currency: String!
) {
    prices_one_way(
        params: {
            origin: $origin,
            destination: $destination,
            depart_dates: $depart_dates,
            direct: $direct
        },
        paging: { limit: 30, offset: 0 },
        sorting: VALUE_ASC,
        grouping: NONE,
        currency: $currency
    ) {
        departure_at
        value
        number_of_changes
        main_airline
        ticket_link
        trip_duration
        duration
        segments {
            departure_at
            arrival_at
            flight_legs {
                origin
                destination
                flight_number
                operating_carrier
                aircraft_code
                departure_at
                arrival_at
            }
            transfers {
                at
                to
                country_code
                duration_seconds
                night_transfer
                visa_required
            }
        }
    }
}
"""

GRAPHQL_ROUND_TRIP_QUERY = """
query PricesRoundTrip(
    $origin: String!,
    $destination: String!,
    $depart_dates: [Date!],
    $return_dates: [Date!]!,
    $direct: Boolean!,
    $currency: String!
) {
    prices_round_trip(
        params: {
            origin: $origin,
            destination: $destination,
            depart_dates: $depart_dates,
            return_dates: $return_dates,
            direct: $direct
        },
        paging: { limit: 30, offset: 0 },
        sorting: VALUE_ASC,
        grouping: NONE,
        currency: $currency
    ) {
        departure_at
        return_at
        value
        number_of_changes
        main_airline
        ticket_link
        trip_duration
        duration
        segments {
            departure_at
            arrival_at
            flight_legs {
                origin
                destination
                flight_number
                operating_carrier
                aircraft_code
                departure_at
                arrival_at
            }
            transfers {
                at
                to
                country_code
                duration_seconds
                night_transfer
                visa_required
            }
        }
    }
}
"""
