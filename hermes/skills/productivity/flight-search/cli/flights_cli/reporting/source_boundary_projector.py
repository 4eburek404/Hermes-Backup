from __future__ import annotations


def source_boundaries() -> list[str]:
    return [
        "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.",
        "Kupibilet aggregate controls can reveal provider-assembled route offers, but ticket protection, baggage, fare rules, and final price still require booking-screen verification.",
        "Cached or legacy price-source absence is not negative evidence.",
        "Provider failures such as unavailable FLI MCP are source availability failures, not route absence evidence.",
    ]
