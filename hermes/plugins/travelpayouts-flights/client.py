"""Async Travelpayouts GraphQL client with bounded resource usage."""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import aiohttp

from .models import FlightPrice
from .parsers import flight_dedup_key, parse_graphql_flight
from .queries import GRAPHQL_ONE_WAY_QUERY, GRAPHQL_ROUND_TRIP_QUERY

BASE_URL = "https://api.travelpayouts.com"
GRAPHQL_URL = f"{BASE_URL}/graphql/v1/query"
AVIASALES_BASE_URL = "https://www.aviasales.ru"
DEFAULT_TIMEOUT_SECONDS = 20
CACHE_TTL_SECONDS = 300
MIN_REPEAT_INTERVAL_SECONDS = 1.5


class RateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded; retry after {retry_after}s")


class TravelpayoutsAPIError(Exception):
    pass


@dataclass(slots=True)
class CacheEntry:
    created_at: float
    flights: list[FlightPrice]
    raw_count: int
    parse_errors: int


_cache: dict[tuple[Any, ...], CacheEntry] = {}
_last_request_at: dict[tuple[Any, ...], float] = {}
_lock = asyncio.Lock()


def build_booking_url(ticket_link: str | None, marker: str | None = None) -> str | None:
    """Normalize Travelpayouts/Aviasales ticket link and append marker safely."""
    if not ticket_link:
        return None
    link = str(ticket_link).strip()
    if not link:
        return None
    if link.startswith("http://") or link.startswith("https://"):
        url = link
    else:
        url = urljoin(AVIASALES_BASE_URL, link)

    if marker:
        parsed = urlparse(url)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        lower_keys = {key.lower() for key, _ in query_pairs}
        if "marker" not in lower_keys:
            query_pairs.append(("marker", marker))
        url = urlunparse(parsed._replace(query=urlencode(query_pairs, doseq=True)))
    return url


class TravelpayoutsClient:
    def __init__(self, token: str | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.token = token or os.getenv("TRAVELPAYOUTS_TOKEN")
        self.timeout_seconds = timeout_seconds

    async def _graphql_request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise TravelpayoutsAPIError("TRAVELPAYOUTS_TOKEN is not configured")

        headers = {
            "X-Access-Token": self.token,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "HermesAgent-TravelpayoutsFlights/0.1",
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        payload = {"query": query, "variables": variables}

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(GRAPHQL_URL, json=payload, headers=headers) as resp:
                if resp.status == 429:
                    retry_after_raw = resp.headers.get("Retry-After", "60")
                    try:
                        retry_after = max(1, min(3600, int(float(retry_after_raw))))
                    except ValueError:
                        retry_after = 60
                    raise RateLimitError(retry_after)

                if resp.status >= 400:
                    # Do not include headers or token in error output.
                    body = await resp.text()
                    raise TravelpayoutsAPIError(f"HTTP {resp.status}: {body[:500]}")

                try:
                    data = await resp.json()
                except Exception as exc:
                    raise TravelpayoutsAPIError(f"Malformed JSON response: {type(exc).__name__}") from exc

        if isinstance(data, dict) and data.get("errors"):
            messages = []
            for err in data.get("errors", []):
                if isinstance(err, dict):
                    messages.append(str(err.get("message") or "Unknown GraphQL error"))
                else:
                    messages.append(str(err))
            raise TravelpayoutsAPIError("; ".join(messages)[:1000])

        if not isinstance(data, dict):
            raise TravelpayoutsAPIError("Unexpected non-object GraphQL response")
        return data.get("data") or {}

    async def get_prices(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date | None = None,
        currency: str = "RUB",
        direct_only: bool = False,
    ) -> tuple[list[FlightPrice], dict[str, int | bool]]:
        cache_key = (origin, destination, depart_date.isoformat(), return_date.isoformat() if return_date else None, currency, direct_only)
        now = time.monotonic()

        async with _lock:
            cached = _cache.get(cache_key)
            if cached and now - cached.created_at < CACHE_TTL_SECONDS:
                return list(cached.flights), {"cache_hit": True, "raw_count": cached.raw_count, "parse_errors": cached.parse_errors}

            last_at = _last_request_at.get(cache_key, 0)
            if now - last_at < MIN_REPEAT_INTERVAL_SECONDS:
                if cached:
                    return list(cached.flights), {"cache_hit": True, "raw_count": cached.raw_count, "parse_errors": cached.parse_errors}
                await asyncio.sleep(MIN_REPEAT_INTERVAL_SECONDS - (now - last_at))
            _last_request_at[cache_key] = time.monotonic()

        variables: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "depart_dates": [depart_date.isoformat()],
            "direct": direct_only,
            "currency": currency,
        }
        if return_date is None:
            query = GRAPHQL_ONE_WAY_QUERY
            query_key = "prices_one_way"
        else:
            query = GRAPHQL_ROUND_TRIP_QUERY
            query_key = "prices_round_trip"
            variables["return_dates"] = [return_date.isoformat()]

        data = await self._graphql_request(query, variables)
        flights_data = data.get(query_key, []) if isinstance(data, dict) else []
        if not isinstance(flights_data, list):
            flights_data = []

        parsed: list[FlightPrice] = []
        parse_errors = 0
        for item in flights_data:
            if not isinstance(item, dict):
                parse_errors += 1
                continue
            try:
                flight = parse_graphql_flight(item, origin, destination)
            except Exception:
                parse_errors += 1
                continue
            if flight.depart_date != depart_date:
                continue
            if return_date and (not flight.return_segment or not flight.return_segment.departure_at.startswith(return_date.isoformat())):
                continue
            parsed.append(flight)

        seen: dict[str, FlightPrice] = {}
        for flight in parsed:
            key = flight_dedup_key(flight)
            if key not in seen or flight.price < seen[key].price:
                seen[key] = flight
        unique = sorted(seen.values(), key=lambda f: f.price)

        async with _lock:
            _cache[cache_key] = CacheEntry(
                created_at=time.monotonic(),
                flights=list(unique),
                raw_count=len(flights_data),
                parse_errors=parse_errors,
            )
        return unique, {"cache_hit": False, "raw_count": len(flights_data), "parse_errors": parse_errors}
