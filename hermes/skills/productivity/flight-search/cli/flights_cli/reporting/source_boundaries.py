from __future__ import annotations


def source_boundaries() -> list[str]:
    return [
        "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.",
        "KupiBilet full-route offers can reveal provider-assembled itineraries, but ticket protection, baggage, fare rules, and final price still require booking-screen verification.",
        "Static city, airport, route, carrier, and aircraft catalogs are metadata only and cannot prove flight availability or absence.",
        "Cached or non-live price-source absence is not negative evidence.",
        "Provider failures such as unavailable FLI MCP are source availability failures, not route absence evidence.",
    ]
