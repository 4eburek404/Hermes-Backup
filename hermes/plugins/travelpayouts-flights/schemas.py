"""Tool schemas shown to the LLM.

Important: Hermes tool schemas are guidance, not a security boundary. Some
Ollama cloud models do not reliably enforce json_schema-like constraints, so the
handler performs the real validation/clamping in Python.
"""
from __future__ import annotations

SUPPORTED_CURRENCIES = ["RUB", "USD", "EUR", "KZT", "BYN", "TRY", "AED"]

TRAVELPAYOUTS_FLIGHT_SEARCH_SCHEMA = {
    "name": "travelpayouts_flight_search",
    "description": (
        "⚠️ DO NOT USE THIS TOOL FOR ROUTE SEARCHES. Call skill_view('flight-search') "
        "first and follow its Golden Path (flights_cli route live-assemble). This tool "
        "returns cached unranked prices without connection validation, hub viability, "
        "or risk scoring. It is ONLY appropriate as a debug/validation fallback AFTER "
        "the CLI has been run, or when the user explicitly asks for cached-only "
        "advisory prices.\n\n"
        "Search cached Travelpayouts/Aviasales flight prices for one city/airport "
        "route and exact departure date. This tool cannot book or buy tickets. Prices "
        "are cached/upstream data and must be rechecked on the aggregator before "
        "purchase.\n\n"
        "origin/destination: 3-letter IATA code (SVX, MOW, DME, LED) OR city name "
        "in Russian/English (Екатеринбург, Moscow). If multiple cities match, the tool "
        "returns a disambiguation list with IATA codes to choose from."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": "Departure: IATA code (e.g. SVX, MOW) or city name (e.g. Екатеринбург, Moscow).",
            },
            "destination": {
                "type": "string",
                "description": "Arrival: IATA code (e.g. MOW, LED) or city name (e.g. Москва, Istanbul).",
            },
            "departure_date": {
                "type": "string",
                "description": "Exact departure date in ISO format YYYY-MM-DD.",
            },
            "return_date": {
                "type": "string",
                "description": "Optional exact return date in ISO format YYYY-MM-DD. Omit for one-way search.",
            },
            "direct_only": {
                "type": "boolean",
                "description": "If true, search only direct flights. Default false.",
            },
            "currency": {
                "type": "string",
                "enum": SUPPORTED_CURRENCIES,
                "description": "Currency code. Default RUB. Supported: RUB, USD, EUR, KZT, BYN, TRY, AED.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return. Default 10; clamped to 1..20 for Telegram-readable output.",
            },
        },
        "required": ["origin", "destination", "departure_date"],
    },
}