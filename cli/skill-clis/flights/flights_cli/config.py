from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import __version__

U6_CALENDAR_URL = "https://www.uralairlines.ru/ajax.php"

U6_CALENDAR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.uralairlines.ru/",
    "Accept": "application/json",
    "User-Agent": f"flights-cli/{__version__}",
}

PLUGIN_PATH = Path.home() / ".hermes" / "plugins" / "travelpayouts-flights"

CACHE_DIR = PLUGIN_PATH / "cache"

HERMES_ENV_PATH = Path.home() / ".hermes" / ".env"

GRAPHQL_URL = "https://api.travelpayouts.com/graphql/v1/query"

KUPIBILET_FRONTEND_SEARCH_URL = "https://api-rs-lb.kupibilet.ru/frontend_search"

KUPIBILET_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Origin": "https://www.kupibilet.ru",
    "Referer": "https://www.kupibilet.ru/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
}

DEFAULT_CURRENCY = "RUB"

SUPPORTED_CURRENCIES = {"RUB", "USD", "EUR", "KZT", "BYN", "TRY", "AED"}

DEFAULT_HUBS = ["IST", "SAW", "AYT"]

DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR = 10

DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS = [0, 1]

DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS = [0, 1, 2]

IATA_RE = re.compile(r"^[A-Z]{3}$")

CARRIER_RE = re.compile(r"^[A-Z0-9]{2,3}$")

TRAVELPAYOUTS_ENV_KEYS = {"TRAVELPAYOUTS_TOKEN", "TRAVELPAYOUTS_MARKER"}

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

MULTI_AIRPORT_GROUPS: dict[str, dict[str, Any]] = {
    "istanbul": {
        "label": "Istanbul",
        "airports": ["IST", "SAW"],
        "cross_transfer_min": 90,
        "min_cross_connection_min": 300,
        "note": "IST and SAW are separate airports; separate-ticket transfer needs border, bags, and ground transfer.",
    },
    "moscow": {
        "label": "Moscow",
        "airports": ["SVO", "DME", "VKO"],
        "cross_transfer_min": 90,
        "min_cross_connection_min": 300,
        "note": "SVO, DME, and VKO are separate airports; cross-airport transfer is a high-risk self-transfer.",
    },
    "london": {
        "label": "London",
        "airports": ["LHR", "LGW", "STN", "LTN"],
        "cross_transfer_min": 75,
        "min_cross_connection_min": 300,
        "note": "London airports are separate; acceptable for a stay in London, risky for same-day self-transfer.",
    },
}

SPECIAL_CITY_AIRPORTS = {
    "LON": ["LHR", "LGW", "STN", "LTN"],
    "MOW": ["SVO", "DME", "VKO"],
    "IST": ["IST", "SAW"],
}

AIRPORT_TO_GROUP: dict[str, str] = {}

for group_key, group in MULTI_AIRPORT_GROUPS.items():
    for code in group["airports"]:
        AIRPORT_TO_GROUP[code] = group_key

SINGLE_AIRPORT_NOTES = {
    "AYT": "Antalya is one airport, but leisure/charter schedules can create marginal self-transfer windows.",
    "GYD": "Baku is usually a single-airport hub for this workflow; still verify bags and ticket protection.",
    "DXB": "Dubai DXB is one airport for this workflow, typically reliable but often expensive.",
}

CACHE_NOTE = (
    "Travelpayouts/Aviasales data can be cached; prices and seats must be rechecked before purchase."
)

LOW_COST_CARRIERS = {"FR", "U2", "W6", "W9", "PC", "VF", "XQ", "2S"}

LEISURE_HUBS = {"AYT"}

RISK_PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "description": "Risk first, then price and total elapsed time.",
        "ideal_same_min": 180,
        "ideal_same_max": 420,
        "cross_airport_base": 32,
        "too_short_penalty": 76,
        "missing_time_penalty": 12,
        "night_penalty": 8,
        "api_night_transfer_penalty": 7,
        "visa_transfer_penalty": 52,
        "long_internal_transfer_penalty": 6,
        "leisure_hub_penalty": 7,
        "lowcost_penalty": 4,
        "unpreferred_airport_penalty": {"LTN": 4, "STN": 3},
        "rank_order": ["reject", "risk", "price", "elapsed"],
    },
    "safe": {
        "description": "Best connection quality first; price is secondary.",
        "ideal_same_min": 210,
        "ideal_same_max": 480,
        "cross_airport_base": 42,
        "too_short_penalty": 86,
        "missing_time_penalty": 18,
        "night_penalty": 12,
        "api_night_transfer_penalty": 12,
        "visa_transfer_penalty": 72,
        "long_internal_transfer_penalty": 9,
        "leisure_hub_penalty": 12,
        "lowcost_penalty": 7,
        "unpreferred_airport_penalty": {"LTN": 7, "STN": 6, "SAW": 4},
        "rank_order": ["reject", "risk", "elapsed", "price"],
    },
    "cheap": {
        "description": "Lowest price first among non-rejected itineraries; still demotes unsafe transfers.",
        "ideal_same_min": 150,
        "ideal_same_max": 540,
        "cross_airport_base": 26,
        "too_short_penalty": 72,
        "missing_time_penalty": 10,
        "night_penalty": 5,
        "api_night_transfer_penalty": 4,
        "visa_transfer_penalty": 40,
        "long_internal_transfer_penalty": 3,
        "leisure_hub_penalty": 3,
        "lowcost_penalty": 1,
        "unpreferred_airport_penalty": {},
        "rank_order": ["reject", "price", "risk", "elapsed"],
    },
    "business": {
        "description": "Same-airport, predictable, shorter elapsed time; penalizes budget airports/carriers.",
        "ideal_same_min": 180,
        "ideal_same_max": 360,
        "cross_airport_base": 48,
        "too_short_penalty": 88,
        "missing_time_penalty": 18,
        "night_penalty": 14,
        "api_night_transfer_penalty": 14,
        "visa_transfer_penalty": 76,
        "long_internal_transfer_penalty": 10,
        "leisure_hub_penalty": 13,
        "lowcost_penalty": 9,
        "unpreferred_airport_penalty": {"LTN": 12, "STN": 10, "LGW": 4, "SAW": 5},
        "rank_order": ["reject", "risk", "elapsed", "price"],
    },
}
