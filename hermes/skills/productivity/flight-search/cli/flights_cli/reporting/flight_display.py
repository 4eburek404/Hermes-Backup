from __future__ import annotations

# Compatibility shim: diagnostic itinerary display moved under reporting.projections.
from .projections.itinerary_display import build_flight_display, build_itinerary_display

__all__ = ["build_flight_display", "build_itinerary_display"]