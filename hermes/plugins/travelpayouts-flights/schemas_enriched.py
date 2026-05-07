# schemas_enriched.py
"""Enriched DTO models for flight search output.

Adapted from bot/modules/flights/api_schemas.py — these models carry
human-readable names (airline, airport, city, aircraft) resolved from
Data API caches alongside raw IATA codes.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# --- City search (used for city name → IATA resolution) ---

class CityResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str           # "SVX"
    name: str           # "Екатеринбург"
    country_code: str   # "RU"
    name_en: str | None = None


class CitiesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cities: list[CityResult]


# --- Enriched flight detail ---

class LegOut(BaseModel):
    """A single flight leg (non-stop segment) with human-readable names."""
    model_config = ConfigDict(extra="ignore")
    origin: str                           # IATA code, e.g. "SVX"
    destination: str                       # IATA code, e.g. "DME"
    origin_name: str                      # "Екатеринбург (SVX)" — city + IATA
    destination_name: str                 # "Москва (DME)"
    flight_number: str                    # "U6123"
    carrier: str                          # IATA code, e.g. "U6"
    carrier_name: str                     # "Уральские авиалинии"
    departure_at: str                     # ISO datetime
    arrival_at: str                       # ISO datetime
    departure_formatted: str = ""         # "06:30" — human-readable departure time
    arrival_formatted: str = ""           # "08:05" — human-readable arrival time
    aircraft_code: str                    # "738"
    aircraft_name: str                    # "Boeing 737-800"
    duration_min: int                     # Flight duration in minutes


class TransferOut(BaseModel):
    """Transfer info between flight legs."""
    model_config = ConfigDict(extra="ignore")
    airport: str              # IATA code, e.g. "DXB"
    airport_name: str         # "Дубай (DXB)"
    country_code: str         # "AE"
    duration_min: int         # Transfer duration in minutes
    night_transfer: bool      # Night transfer
    visa_required: bool      # Visa required
    formatted: str = ""       # "🔄 Пересадка в Москва (SVO) · 2ч 35м · 🌙 ночная · ⚠️ виза"


class SegmentOut(BaseModel):
    """A flight segment (outbound or inbound) with legs and transfers."""
    model_config = ConfigDict(extra="ignore")
    departure_at: str
    arrival_at: str
    duration_min: int
    transfers_count: int
    legs: list[LegOut]
    transfers: list[TransferOut]
    departure_formatted: str = ""    # "06:30, 1 май" — human-readable
    arrival_formatted: str = ""      # "08:05, 1 май"
    duration_formatted: str = ""     # "2ч 35м"


class FlightOut(BaseModel):
    """Enriched flight offer for output."""
    model_config = ConfigDict(extra="ignore")
    price: int
    currency: str
    airline: str | None = None
    airline_name: str | None = None
    transfers: int
    departure_at: str
    arrival_at: str | None = None         # end of outbound segment
    duration_min: int | None = None
    outbound: SegmentOut | None = None
    inbound: SegmentOut | None = None
    booking_url: str | None = None
    transfers_formatted: str = ""          # "Прямой" | "1 пересадка" | "2 пересадки"
    duration_formatted: str = ""           # "2ч 35м"
    price_formatted: str = ""              # "12 500 ₽"
    direct_not_available: bool = False     # True when direct_only requested but only transfers found


class FlightsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    flights: list[FlightOut]
    total: int
    origin: str
    destination: str
    departure_date: str
    return_date: str | None = None