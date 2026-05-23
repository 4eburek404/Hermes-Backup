from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PLUGIN_PATH = Path.home() / ".hermes" / "plugins" / "travelpayouts-flights"

CACHE_DIR = PLUGIN_PATH / "cache"

LIVE_SEARCH_CACHE_DIR = CACHE_DIR / "live_search"

ROUTE_INTEL_CACHE_DIR = CACHE_DIR / "route_intel"

HERMES_ENV_PATH = Path.home() / ".hermes" / ".env"

KUPIBILET_FRONTEND_SEARCH_URL = "https://api-rs-lb.kupibilet.ru/frontend_search"

FLI_MCP_DEFAULT_URL = "http://127.0.0.1:8000/mcp"

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

DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR = 10

DEFAULT_COVERAGE_CONTROL_LIMIT = 12

DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS = [0, 1]

DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS = [0, 1, 2]

DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS = 6 * 60 * 60

DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS = 7 * 24 * 60 * 60

SVX_OFFICIAL_SCHEDULE_URL = "https://ar-svx.ru/schedule/"

SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL = "https://ar-svx.ru/schedule/?type=arr"

DEFAULT_ROUTE_HUBS = (
    "IST",
    "DXB",
    "DOH",
    "AUH",
    "BEG",
    "TAS",
    "GYD",
    "PEK",
    "PVG",
    "CAN",
    "ADD",
    "CAI",
    "MCT",
)

DOMESTIC_RU_HUBS = ("SVO", "DME", "VKO")
DUBAI_DEFAULT_AIRPORTS = ("DXB", "DWC")
DUBAI_EXCLUDED_BY_DEFAULT = ("SHJ",)

DEFAULT_ROUTING_STRATEGY = "auto"
ROUTING_STRATEGIES = {"auto", "hub-list", "ru-priority", "domestic-ru"}


PRIORITY_ROUTE_CARRIERS = ("U6", "SU", "TK")

PRIORITY_PRIMARY_HUB = "IST"

PRIORITY_MOSCOW_GATEWAY = "SVO"

PRIORITY_SECONDARY_HUB = "DXB"

PRIORITY_ASIA_HUB = "SVO"

ASIA_OCEANIA_COUNTRIES = {
    "AM",
    "AZ",
    "BH",
    "CN",
    "HK",
    "ID",
    "IN",
    "JP",
    "KG",
    "KH",
    "KR",
    "KZ",
    "MO",
    "MY",
    "PH",
    "SG",
    "TH",
    "TJ",
    "TM",
    "TW",
    "UZ",
    "VN",
    "AU",
    "NZ",
}

ASIA_DESTINATION_CODES = {
    "BJS",
    "PEK",
    "PKX",
    "PVG",
    "SHA",
    "CAN",
    "HKG",
    "MFM",
    "TYO",
    "NRT",
    "HND",
    "SEL",
    "ICN",
    "PUS",
    "BKK",
    "HKT",
    "SGN",
    "HAN",
    "SIN",
    "KUL",
    "DPS",
    "MNL",
    "SYD",
    "MEL",
    "AKL",
}

DEFAULT_ROUTE_HUB_NOTES = {
    "IST": "Broadest Russia-origin hub.",
    "DXB": "Main competitor for Asia, Africa, and Australia routings.",
    "DOH": "Strong long-haul hub via Qatar.",
    "AUH": "Useful backup for DXB and DOH.",
    "BEG": "Europe and some North America coverage, but not global.",
    "TAS": "Regional hub with partial long-haul coverage.",
    "GYD": "Regional hub with partial long-haul coverage.",
    "PEK": "Asia, China, and Oceania-oriented fallback.",
    "PVG": "Asia, China, and Oceania-oriented fallback.",
    "CAN": "Asia, China, and Oceania-oriented fallback.",
    "ADD": "Niche Africa, Middle East, India, and price hub.",
    "CAI": "Niche Africa, Middle East, India, and price hub.",
    "MCT": "Niche Africa, Middle East, India, and price hub.",
    "SHJ": "Niche Africa, Middle East, India, and price hub.",
}

IATA_RE = re.compile(r"^[A-Z]{3}$")

CARRIER_RE = re.compile(r"^[A-Z0-9]{2,3}$")

TRAVELPAYOUTS_ENV_KEYS = {"TRAVELPAYOUTS_TOKEN", "TRAVELPAYOUTS_MARKER"}

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

PREFERRED_AIRPORT_TIERS = {
    "LON": [
        {"tier": 1, "airports": ["LHR"], "role": "preferred"},
        {"tier": 2, "airports": ["LGW"], "role": "fallback"},
    ],
}

CITY_AIRPORTS_EXCLUDED_BY_DEFAULT = {
    "LON": ["STN", "LTN"],
    "IST": ["SAW"],
}

KUPIBILET_CITY_CODE_FIRST_AIRPORTS = {
    "MOW": ["SVO", "DME", "VKO"],
}

SPECIAL_CITY_AIRPORTS = {
    "LON": ["LHR", "LGW"],
    "MOW": ["SVO", "DME", "VKO"],
    "IST": ["IST"],
    "PAR": ["CDG", "ORY"],
    "BJS": ["PEK", "PKX"],
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
    "Provider price data can be cached or stale; prices and seats must be rechecked before purchase."
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
