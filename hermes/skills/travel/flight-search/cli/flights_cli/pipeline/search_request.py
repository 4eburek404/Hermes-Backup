from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import (
    DEFAULT_CATALOG_LIMIT,
    DEFAULT_CURRENCY,
    DEFAULT_DIRECT_CATALOG_LIMIT,
    DEFAULT_FAIL_FAST,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_MAX_SEGMENT_SEARCHES,
    DEFAULT_SEGMENT_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
)
from ..domain.normalize import parse_iso_date
from ..contracts.validation import validate_contract_payload
from ..errors import CliError


SEARCH_REQUEST_SCHEMA_VERSION = "flight_search_request.v1"


@dataclass(frozen=True, slots=True)
class RouteOptions:
    origin: str
    destination: str
    depart_date: str
    return_date: str | None
    date_window_end: str | None
    origin_airports: tuple[str, ...]
    destination_airports: tuple[str, ...]
    max_connections: int | None
    preferred_connections: int | None


@dataclass(frozen=True, slots=True)
class FilterOptions:
    only_carriers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionSettings:
    """Бюджеты прогона.

    Это не то, что просит путешественник, поэтому в публичном запросе их нет:
    значения приходят из конфигурации и ключей командной строки.
    """

    max_segment_searches: int = DEFAULT_MAX_SEGMENT_SEARCHES
    live_cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
    no_live_cache: bool = False
    segment_limit: int = DEFAULT_SEGMENT_LIMIT
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    fail_fast: bool = DEFAULT_FAIL_FAST


@dataclass(frozen=True, slots=True)
class OutputOptions:
    catalog_limit: int
    direct_catalog_limit: int
    requested_limit: int | None = None


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Каноничный неизменяемый вход: что просят, а не как это исполнять."""

    route: RouteOptions
    filters: FilterOptions
    execution: ExecutionSettings
    output: OutputOptions
    provider_policy: str
    currency: str

    @classmethod
    def from_payload(
        cls, payload: dict[str, Any], execution: ExecutionSettings
    ) -> SearchRequest:
        """Собрать запрос из плоского payload `.v1` и бюджетов прогона."""

        limit = _optional_int(payload.get("limit"))
        catalog_limit = DEFAULT_CATALOG_LIMIT
        direct_catalog_limit = DEFAULT_DIRECT_CATALOG_LIMIT
        if limit is not None:
            catalog_limit = direct_catalog_limit = limit
        return cls(
            route=RouteOptions(
                origin=str(payload.get("origin") or ""),
                destination=str(payload.get("destination") or ""),
                depart_date=str(payload.get("depart_date") or ""),
                return_date=(
                    str(payload.get("return_date"))
                    if payload.get("return_date")
                    else None
                ),
                date_window_end=(
                    str(payload.get("date_window_end"))
                    if payload.get("date_window_end")
                    else None
                ),
                origin_airports=_str_tuple(payload.get("origin_airports")),
                destination_airports=_str_tuple(payload.get("destination_airports")),
                max_connections=_optional_int(payload.get("max_connections")),
                preferred_connections=_optional_int(
                    payload.get("preferred_connections")
                ),
            ),
            filters=FilterOptions(
                only_carriers=_str_tuple(payload.get("only_carriers")),
            ),
            execution=execution,
            output=OutputOptions(
                catalog_limit=catalog_limit,
                direct_catalog_limit=direct_catalog_limit,
                requested_limit=limit,
            ),
            provider_policy=str(payload.get("provider_policy") or "auto"),
            currency=str(payload.get("currency") or DEFAULT_CURRENCY),
        )

    def to_payload(self) -> dict[str, Any]:
        """Каноничный повтор входа после применения умолчаний."""

        payload: dict[str, Any] = {
            "schema_version": SEARCH_REQUEST_SCHEMA_VERSION,
            "origin": self.route.origin,
            "destination": self.route.destination,
            "depart_date": self.route.depart_date,
            "return_date": self.route.return_date,
            "date_window_end": self.route.date_window_end,
            "currency": self.currency,
            "provider_policy": self.provider_policy,
            "only_carriers": list(self.filters.only_carriers),
            "origin_airports": list(self.route.origin_airports),
            "destination_airports": list(self.route.destination_airports),
        }
        # Эхо повторяет то, что просили. Умолчание не подставляем: без
        # `limit` потолок выдачи зависит от того, нашлись ли прямые, и
        # одним числом его честно не назвать.
        if self.output.requested_limit is not None:
            payload["limit"] = self.output.requested_limit
        if self.route.max_connections is not None:
            payload["max_connections"] = self.route.max_connections
        if self.route.preferred_connections is not None:
            payload["preferred_connections"] = self.route.preferred_connections
        return payload

    def effective_only_carriers(self) -> tuple[str, ...]:
        return _unique_strs(self.filters.only_carriers)

    @property
    def origin(self) -> str:
        return self.route.origin

    @property
    def destination(self) -> str:
        return self.route.destination

    @property
    def depart_date(self) -> str:
        return self.route.depart_date

    @property
    def return_date(self) -> str | None:
        return self.route.return_date

    @property
    def primary_offer_limit(self) -> int:
        return max(self.output.catalog_limit, self.output.direct_catalog_limit)

    @property
    def origin_airports(self) -> tuple[str, ...]:
        return self.route.origin_airports

    @property
    def destination_airports(self) -> tuple[str, ...]:
        return self.route.destination_airports

    @property
    def max_connections(self) -> int | None:
        return self.route.max_connections

    @property
    def preferred_connections(self) -> int | None:
        return self.route.preferred_connections

    @property
    def date_window_end(self) -> str | None:
        return self.route.date_window_end

    @property
    def max_segment_searches(self) -> int:
        return self.execution.max_segment_searches

    @property
    def live_cache_ttl_seconds(self) -> int:
        return self.execution.live_cache_ttl_seconds

    @property
    def no_live_cache(self) -> bool:
        return self.execution.no_live_cache

    @property
    def only_carriers(self) -> tuple[str, ...]:
        return self.filters.only_carriers


def _as_tuple(value: object) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _str_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _as_tuple(value) if str(item))


def _unique_strs(*values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for group in values:
        for item in group:
            text = str(item).strip().upper()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
    return tuple(result)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def normalize_search_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Каноничный регистр и умолчания на границе входа."""

    normalized = dict(payload)
    normalized.setdefault("schema_version", SEARCH_REQUEST_SCHEMA_VERSION)
    for name in ("origin", "destination", "currency"):
        if name in normalized:
            normalized[name] = str(normalized[name]).upper()
    if "provider_policy" in normalized:
        normalized["provider_policy"] = str(normalized["provider_policy"]).lower()
    for name in ("origin_airports", "destination_airports", "only_carriers"):
        if isinstance(normalized.get(name), list):
            normalized[name] = [str(item).upper() for item in normalized[name]]
    return normalized


def validate_search_request_semantics(request: SearchRequest) -> None:
    depart = parse_iso_date(request.depart_date, "depart-date")
    if request.origin == request.destination:
        raise ValueError("origin and destination must differ")
    if request.return_date:
        return_date = parse_iso_date(request.return_date, "return-date")
        if return_date < depart:
            raise ValueError("return-date must be on or after depart-date")
    if request.date_window_end:
        window_end = parse_iso_date(request.date_window_end, "date-window-end")
        if window_end < depart:
            raise ValueError("date-window-end must be on or after depart-date")
        if request.return_date:
            raise ValueError("date-window-end cannot be combined with return-date")
    if (
        request.max_connections is not None
        and request.preferred_connections is not None
        and request.preferred_connections > request.max_connections
    ):
        raise ValueError("preferred-connections must not exceed max-connections")


def is_direct_only(request: "SearchRequest") -> bool:
    """Запрос «только прямые»: жёсткий потолок пересадок равен нулю."""
    return request.max_connections == 0


def search_request_from_payload(
    payload: dict[str, Any], execution: ExecutionSettings | None = None
) -> SearchRequest:
    normalized = normalize_search_request_payload(payload)
    validate_contract_payload(
        "search_request", normalized, error_type="validation_error"
    )
    request = SearchRequest.from_payload(normalized, execution or ExecutionSettings())
    try:
        validate_search_request_semantics(request)
    except ValueError as exc:
        raise CliError(str(exc), error_type="validation_error") from exc
    return request
