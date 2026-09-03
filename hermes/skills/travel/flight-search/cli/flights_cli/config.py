from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path.home() / ".hermes" / "cache" / "flight-search"


def resolve_cache_dir() -> Path:
    override = os.environ.get("FLIGHTS_CACHE_DIR")
    if override and override.strip():
        return Path(override).expanduser()
    return DEFAULT_CACHE_DIR


MAX_DATE_WINDOW_DAYS = 14

KUPIBILET_FRONTEND_SEARCH_URL = "https://api-rs-lb.kupibilet.ru/frontend_search"

TUTU_MCP_DEFAULT_URL = "https://mcp.tutu.ru/mcp"

KUPIBILET_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Origin": "https://www.kupibilet.ru",
    "Referer": "https://www.kupibilet.ru/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
}

DEFAULT_CURRENCY = "RUB"

DEFAULT_PROFILE = "business"

DEFAULT_CATALOG_LIMIT = 10

DEFAULT_DIRECT_CATALOG_LIMIT = 30

DEFAULT_GATEWAY_MAX_ALTERNATIVES = 2

DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS = 4

DEFAULT_FIRST_CARRIER_MAX_OPTIONS = 2

DEFAULT_GATEWAY_DISCOVERY_LIMIT = 1

DEFAULT_GATEWAY_PROBE_BATCH_SIZE = 1

DEFAULT_GATEWAY_PROBE_MAX_BATCHES = 1

DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS = 30 * 60

# Бюджеты прогона. В публичном запросе их нет — их ставят ключи CLI.
DEFAULT_MAX_SEGMENT_SEARCHES = 300

DEFAULT_SEGMENT_LIMIT = 30

DEFAULT_TIMEOUT_SECONDS = 60

DEFAULT_FAIL_FAST = False

# Ширина аэропортового охвата, когда вызывающий не назвал аэропорты сам.
DEFAULT_MAX_AIRPORTS_PER_CITY = 6


DEFAULT_ROUTING_STRATEGY = "auto"

IATA_RE = re.compile(r"^[A-Z]{3}$")

CARRIER_RE = re.compile(r"^[A-Z0-9]{2,3}$")

MULTI_AIRPORT_GROUPS: dict[str, dict[str, Any]] = {
    "istanbul": {
        "label": "Istanbul",
        "airports": ["IST", "SAW"],
        "note": "IST and SAW are separate airports and cannot form one connection in this workflow.",
    },
    "moscow": {
        "label": "Moscow",
        "airports": ["SVO", "DME", "VKO"],
        "note": "SVO, DME, and VKO are separate airports and cannot form one connection in this workflow.",
    },
    "london": {
        "label": "London",
        "airports": ["LHR", "LGW", "STN", "LTN"],
        "note": "London airports are separate and cannot form one connection in this workflow.",
    },
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

RISK_PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "description": "Risk first, then price and total elapsed time.",
        "ideal_same_min": 180,
        "ideal_same_max": 420,
        "rank_order": ["reject", "risk", "price", "elapsed"],
    },
    "safe": {
        "description": "Best connection quality first; price is secondary.",
        "ideal_same_min": 210,
        "ideal_same_max": 480,
        "rank_order": ["reject", "risk", "elapsed", "price"],
    },
    "cheap": {
        "description": "Lowest price first among non-rejected itineraries; still demotes unsafe transfers.",
        "ideal_same_min": 150,
        "ideal_same_max": 540,
        "rank_order": ["reject", "price", "risk", "elapsed"],
    },
    "business": {
        "description": "Same-airport, predictable, shorter elapsed time; penalizes budget airports/carriers.",
        "ideal_same_min": 180,
        "ideal_same_max": 360,
        "rank_order": ["reject", "risk", "elapsed", "price"],
    },
}
