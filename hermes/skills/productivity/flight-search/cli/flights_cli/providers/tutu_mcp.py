"""Tutu MCP transport orchestration, pagination, and live-cache façade."""

from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any

import httpx2
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT

from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
from ..errors import CliError
from ..store import Store
from .live_cache import live_cache_key, read_live_cache, write_live_cache
from .segment_normalization import provider_result_to_segment_result
from .tutu_parser import (
    TUTU_NORMALIZER_VERSION as TUTU_NORMALIZER_VERSION,
    _carrier_facets,
    _normalized_airport_scope,
    _tutu_location_input,
    parse_tutu_avia_search as parse_tutu_avia_search,
    resolve_tutu_carrier_facets,
)
from .tutu_client import TutuMcpClient, normalize_tutu_mcp_url

TUTU_PAGE_SIZE = 30
TUTU_MAX_PAGES = 3
TUTU_MAX_SCOPE_PAGES = 10
TUTU_MAX_ATTEMPTS = 2
TUTU_RETRY_BACKOFF_SECONDS = 0.25


def _exception_leaves(exc: Exception) -> list[Exception]:
    children = getattr(exc, "exceptions", None)
    if isinstance(children, (tuple, list)) and children:
        leaves: list[Exception] = []
        for child in children:
            if isinstance(child, Exception):
                leaves.extend(_exception_leaves(child))
            else:
                return [exc]
        return leaves
    return [exc]


def _is_retryable_transport_failure(exc: Exception) -> bool:
    leaves = _exception_leaves(exc)
    return bool(leaves) and all(
        isinstance(
            leaf,
            (httpx2.TransportError, TimeoutError, asyncio.TimeoutError),
        )
        or (
            isinstance(leaf, MCPError)
            and leaf.code in {CONNECTION_CLOSED, REQUEST_TIMEOUT}
        )
        for leaf in leaves
    )


def _terminal_error_types(exc: Exception) -> list[str]:
    return sorted({type(leaf).__name__ for leaf in _exception_leaves(exc)})


def _has_timeout_leaf(exc: Exception) -> bool:
    return any(
        isinstance(leaf, (TimeoutError, asyncio.TimeoutError))
        or (isinstance(leaf, MCPError) and leaf.code == REQUEST_TIMEOUT)
        for leaf in _exception_leaves(exc)
    )


async def _cancel_and_drain_task(task: asyncio.Task[Any]) -> None:
    task.cancel()
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    try:
        task.result()
    except BaseException:
        pass


def _final_tutu_error(
    exc: Exception,
    *,
    operation: str,
    attempts: int,
    timeout: float,
    timed_out: bool = False,
) -> CliError:
    error_types = _terminal_error_types(exc)
    message = (
        f"Tutu MCP {operation} failed after {attempts} attempt(s) "
        f"within {timeout:g}s deadline: {', '.join(error_types)}"
    )
    return CliError(
        message,
        error_type="timeout" if timed_out else "upstream_error",
        details={
            "provider": "tutu",
            "operation": operation,
            "tool": operation
            if operation in {"get_avia_instructions", "search_avia"}
            else None,
            "attempts": attempts,
            "deadline_seconds": timeout,
            "terminal_error_types": error_types,
        },
    )


async def _fetch_tutu_avia_search_attempt(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None,
    direct_only: bool,
    limit: int,
    mcp_url: str,
    store: Store | None,
    return_date: date | None,
    allowed_origins: list[str],
    allowed_destinations: list[str],
    deadline: float,
) -> dict[str, Any]:
    origin_input, origin_input_kind = _tutu_location_input(
        origin, allowed_origins, store
    )
    destination_input, destination_input_kind = _tutu_location_input(
        destination, allowed_destinations, store
    )

    arguments: dict[str, Any] = {
        "origin": origin_input,
        "destination": destination_input,
        "departure_date": depart_date.isoformat(),
        "adults": 1,
        "view": "compact",
        "sort": "departure_asc",
        "page_size": TUTU_PAGE_SIZE,
    }
    if return_date is not None:
        arguments["return_date"] = return_date.isoformat()
    if direct_only:
        arguments["direct_only"] = True

    carrier_name_overrides: dict[str, str] = {}
    unmatched_carriers: list[str] = []
    carrier_facets: list[str] = []
    async with TutuMcpClient(url=mcp_url, deadline=deadline) as client:
        if only_carriers:
            discovery_raw = await client.search_avia({**arguments, "page_size": 1})
            carrier_facets = _carrier_facets(discovery_raw)
            mcp_carriers, carrier_name_overrides, unmatched_carriers = (
                resolve_tutu_carrier_facets(
                    only_carriers,
                    facets=carrier_facets,
                    store=store,
                )
            )
            if not mcp_carriers:
                discovery_meta = (
                    discovery_raw.get("meta")
                    if isinstance(discovery_raw.get("meta"), dict)
                    else {}
                )
                empty_raw = {
                    "offers": [],
                    "meta": {
                        **discovery_meta,
                        "carrier_filter_unmatched": unmatched_carriers,
                        "carrier_facets_discovered": carrier_facets,
                        "pages_fetched": 1,
                        "total_returned": 0,
                        "origin_input": origin_input,
                        "origin_input_kind": origin_input_kind,
                        "origin_airports": allowed_origins,
                        "destination_input": destination_input,
                        "destination_input_kind": destination_input_kind,
                        "destination_airports": allowed_destinations,
                    },
                }
                return parse_tutu_avia_search(
                    empty_raw,
                    origin=origin.upper(),
                    destination=destination.upper(),
                    depart_date=depart_date.isoformat(),
                    currency=currency,
                    only_carriers=only_carriers,
                    direct_only=direct_only,
                    return_date=return_date.isoformat() if return_date else None,
                    limit=limit,
                    store=store,
                    source_url=mcp_url,
                    origin_airports=allowed_origins,
                    destination_airports=allowed_destinations,
                    carrier_name_overrides=carrier_name_overrides,
                )
            arguments["carriers"] = mcp_carriers

        raw = await client.search_avia(arguments)
        if not carrier_facets:
            carrier_facets = _carrier_facets(raw)
            _, carrier_name_overrides, _ = resolve_tutu_carrier_facets(
                [], facets=carrier_facets, store=store
            )

        all_offers = list(raw.get("offers") or [])
        meta = raw.get("meta") or {}
        page = 1
        pages_fetched = 1
        page_budget_exhausted = False
        empty_page_seen = False
        max_pages = (
            TUTU_MAX_SCOPE_PAGES
            if len(allowed_origins) > 1 or len(allowed_destinations) > 1
            else TUTU_MAX_PAGES
        )
        while meta.get("has_more") and page < max_pages:
            page += 1
            page_raw = await client.search_avia({**arguments, "page": page})
            pages_fetched += 1
            page_offers = list(page_raw.get("offers") or [])
            if not page_offers:
                empty_page_seen = True
                meta = page_raw.get("meta") or meta
                break
            all_offers.extend(page_offers)
            meta = page_raw.get("meta") or {}
        if meta.get("has_more") and page >= max_pages:
            page_budget_exhausted = True

        raw["offers"] = all_offers
        raw_meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        raw["meta"] = {
            **raw_meta,
            **(meta if isinstance(meta, dict) else {}),
            "page_size": TUTU_PAGE_SIZE,
            "pages_fetched": pages_fetched,
            "total_returned": len(all_offers),
            "max_pages": max_pages,
            "has_more_after_fetch": bool(meta.get("has_more"))
            if isinstance(meta, dict)
            else False,
            "not_fetched_due_to_page_budget": page_budget_exhausted,
            "airport_scope_incomplete": page_budget_exhausted
            and (len(allowed_origins) > 1 or len(allowed_destinations) > 1),
            "empty_page_seen": empty_page_seen,
            "origin_input": origin_input,
            "origin_input_kind": origin_input_kind,
            "origin_airports": allowed_origins,
            "destination_input": destination_input,
            "destination_input_kind": destination_input_kind,
            "destination_airports": allowed_destinations,
            "carrier_facets_discovered": carrier_facets,
            "carrier_filter_unmatched": unmatched_carriers,
        }

    return parse_tutu_avia_search(
        raw,
        origin=origin.upper(),
        destination=destination.upper(),
        depart_date=depart_date.isoformat(),
        currency=currency,
        only_carriers=only_carriers,
        direct_only=direct_only,
        return_date=return_date.isoformat() if return_date else None,
        limit=limit,
        store=store,
        source_url=mcp_url,
        origin_airports=allowed_origins,
        destination_airports=allowed_destinations,
        carrier_name_overrides=carrier_name_overrides,
    )


async def _fetch_tutu_avia_search_async(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None,
    direct_only: bool,
    limit: int,
    timeout: float,
    mcp_url: str,
    store: Store | None,
    return_date: date | None,
    origin_airports: list[str] | None,
    destination_airports: list[str] | None,
    deadline: float,
) -> dict[str, Any]:
    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
    last_error: Exception | None = None
    for attempt in range(1, TUTU_MAX_ATTEMPTS + 1):
        if deadline <= time.monotonic():
            timeout_error = TimeoutError("Tutu MCP deadline exhausted")
            raise _final_tutu_error(
                timeout_error,
                operation="mcp_session",
                attempts=attempt - 1,
                timeout=timeout,
                timed_out=True,
            ) from timeout_error
        try:
            attempt_task = asyncio.create_task(
                _fetch_tutu_avia_search_attempt(
                    origin,
                    destination,
                    depart_date,
                    currency=currency,
                    only_carriers=only_carriers,
                    direct_only=direct_only,
                    limit=limit,
                    mcp_url=mcp_url,
                    store=store,
                    return_date=return_date,
                    allowed_origins=allowed_origins,
                    allowed_destinations=allowed_destinations,
                    deadline=deadline,
                )
            )
            try:
                return await asyncio.shield(attempt_task)
            except asyncio.CancelledError:
                await _cancel_and_drain_task(attempt_task)
                raise
        except Exception as exc:
            if isinstance(exc, CliError):
                raise
            last_error = exc
            operation = str(getattr(exc, "_tutu_operation", "mcp_session"))
            if not _is_retryable_transport_failure(exc):
                raise _final_tutu_error(
                    exc,
                    operation=operation,
                    attempts=attempt,
                    timeout=timeout,
                ) from exc
            if attempt == TUTU_MAX_ATTEMPTS:
                raise _final_tutu_error(
                    exc,
                    operation=operation,
                    attempts=attempt,
                    timeout=timeout,
                    timed_out=_has_timeout_leaf(exc),
                ) from exc
            if deadline - time.monotonic() <= TUTU_RETRY_BACKOFF_SECONDS:
                raise _final_tutu_error(
                    exc,
                    operation=operation,
                    attempts=attempt,
                    timeout=timeout,
                    timed_out=True,
                ) from exc
            await asyncio.sleep(TUTU_RETRY_BACKOFF_SECONDS)
    assert last_error is not None
    raise _final_tutu_error(
        last_error,
        operation="mcp_session",
        attempts=TUTU_MAX_ATTEMPTS,
        timeout=timeout,
    )


def fetch_tutu_avia_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
    timeout: int = 60,
    mcp_url: str | None = None,
    store: Store | None = None,
    return_date: date | None = None,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
) -> dict[str, Any]:
    """Call Tutu MCP search_avia and normalize results."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise CliError(
            "Tutu synchronous provider contract cannot run inside an active event loop",
            error_type="sync_contract_error",
            details={"provider": "tutu", "operation": "fetch_tutu_avia_search"},
        )
    timeout_seconds = float(timeout)
    url = normalize_tutu_mcp_url(mcp_url)
    deadline = time.monotonic() + timeout_seconds
    return asyncio.run(
        _fetch_tutu_avia_search_async(
            origin,
            destination,
            depart_date,
            currency=currency,
            only_carriers=only_carriers,
            direct_only=direct_only,
            limit=limit,
            timeout=timeout_seconds,
            mcp_url=url,
            store=store,
            return_date=return_date,
            origin_airports=origin_airports,
            destination_airports=destination_airports,
            deadline=deadline,
        )
    )


def cached_tutu_avia_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str],
    direct_only: bool,
    limit: int,
    timeout: int,
    mcp_url: str | None = None,
    cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    use_cache: bool = True,
    fetcher: Any = fetch_tutu_avia_search,
    store: Store | None = None,
    return_date: date | None = None,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
) -> dict[str, Any]:
    url = normalize_tutu_mcp_url(mcp_url)
    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
    params = {
        "origin": origin,
        "destination": destination,
        "origin_airports": allowed_origins,
        "destination_airports": allowed_destinations,
        "depart_date": depart_date.isoformat(),
        "return_date": return_date.isoformat() if return_date else None,
        "currency": currency,
        "only_carriers": sorted(only_carriers),
        "direct_only": bool(direct_only),
        "limit": int(limit),
        "mcp_url": url,
        "normalizer": TUTU_NORMALIZER_VERSION,
    }
    key = live_cache_key("tutu_mcp_search_avia", params)
    if use_cache:
        cached = read_live_cache(key, ttl_seconds=int(cache_ttl_seconds))
        if cached is not None:
            return cached
    result = fetcher(
        origin,
        destination,
        depart_date,
        currency=currency,
        only_carriers=only_carriers,
        direct_only=direct_only,
        limit=limit,
        timeout=timeout,
        mcp_url=url,
        store=store,
        return_date=return_date,
        origin_airports=allowed_origins,
        destination_airports=allowed_destinations,
    )
    if use_cache and int(cache_ttl_seconds) > 0:
        return write_live_cache(key, result)
    result["cache"] = {"hit": False, "key": key, "disabled": True}
    return result


def tutu_result_to_segment_result(
    result: dict[str, Any], *, direction: str, leg: str
) -> dict[str, Any]:
    return provider_result_to_segment_result(
        result,
        direction=direction,
        leg=leg,
        source_key="tutu_mcp_search_avia",
        source_label="Tutu MCP search_avia",
        provider_prefix="tutu",
        raw_count_key="raw_count",
    )


def tutu_segment_search_summary(
    spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]
) -> dict[str, Any]:
    return {
        **spec,
        "provider": "tutu",
        "status": "ok",
        "raw_count": result.get("raw_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "offer_count": len(segment_result.get("offers") or []),
        "filters": result.get("filters", {}),
        "pagination": result.get("pagination", {}),
        "skipped": result.get("skipped", {}),
        "cache": result.get("cache", {"hit": False}),
    }
