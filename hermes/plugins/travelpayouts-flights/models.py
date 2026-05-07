"""Small self-contained flight domain models.

Adapted from /home/konstantin/bot/bot/modules/flights/models.py, but using
stdlib dataclasses to avoid coupling the plugin to bot settings or pydantic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class FlightLeg:
    origin: str = ""
    destination: str = ""
    flight_number: str = ""
    operating_carrier: str = ""
    aircraft_code: str = ""
    departure_at: str = ""
    arrival_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlightLeg":
        return cls(
            origin=str(data.get("origin") or ""),
            destination=str(data.get("destination") or ""),
            flight_number=str(data.get("flight_number") or ""),
            operating_carrier=str(data.get("operating_carrier") or ""),
            aircraft_code=str(data.get("aircraft_code") or ""),
            departure_at=str(data.get("departure_at") or ""),
            arrival_at=str(data.get("arrival_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "flight_number": self.flight_number,
            "operating_carrier": self.operating_carrier,
            "aircraft_code": self.aircraft_code,
            "departure_at": self.departure_at,
            "arrival_at": self.arrival_at,
        }


@dataclass(slots=True)
class Transfer:
    at: str = ""
    to: str = ""
    country_code: str = ""
    duration_seconds: int = 0
    night_transfer: bool = False
    visa_required: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transfer":
        return cls(
            at=str(data.get("at") or ""),
            to=str(data.get("to") or ""),
            country_code=str(data.get("country_code") or ""),
            duration_seconds=int(data.get("duration_seconds") or 0),
            night_transfer=bool(data.get("night_transfer") or False),
            visa_required=bool(data.get("visa_required") or False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "to": self.to,
            "country_code": self.country_code,
            "duration_seconds": self.duration_seconds,
            "night_transfer": self.night_transfer,
            "visa_required": self.visa_required,
        }


@dataclass(slots=True)
class FlightSegment:
    departure_at: str = ""
    arrival_at: str = ""
    flight_legs: list[FlightLeg] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "departure_at": self.departure_at,
            "arrival_at": self.arrival_at,
            "flight_legs": [leg.to_dict() for leg in self.flight_legs],
            "transfers": [transfer.to_dict() for transfer in self.transfers],
        }


@dataclass(slots=True)
class FlightPrice:
    origin: str
    destination: str
    depart_date: date
    return_date: date | None = None
    price: int = 0
    airline: str | None = None
    flight_number: int | None = None
    transfers: int = 0
    departure_at: str | None = None
    return_at: str | None = None
    expires_at: str | None = None
    trip_duration: int | None = None
    duration: int | None = None
    ticket_link: str | None = None
    outbound_segment: FlightSegment | None = None
    return_segment: FlightSegment | None = None

    def to_dict(self, currency: str, booking_url: str | None = None) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "depart_date": self.depart_date.isoformat(),
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "price": self.price,
            "currency": currency,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "transfers": self.transfers,
            "departure_at": self.departure_at,
            "return_at": self.return_at,
            "expires_at": self.expires_at,
            "trip_duration_days": self.trip_duration,
            "duration_minutes": self.duration,
            "ticket_link": self.ticket_link,
            "booking_url": booking_url,
            "outbound_segment": self.outbound_segment.to_dict() if self.outbound_segment else None,
            "return_segment": self.return_segment.to_dict() if self.return_segment else None,
        }
