"""Tutu MCP transport orchestration, pagination, and live-cache façade."""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from typing import Any

from .. import __version__
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
from .tutu_transport import (
    MCP_PROTOCOL_VERSION,
    normalize_tutu_mcp_url,
    tutu_mcp_http_post as _transport_http_post,
)

TUTU_PAGE_SIZE = 30
TUTU_MAX_PAGES = 3
TUTU_MAX_SCOPE_PAGES = 10
TutuToolPayload = dict[str, Any] | list[Any] | str


def tutu_mcp_http_post(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: int,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    return _transport_http_post(
        url,
        payload,
        timeout=timeout,
        session_id=session_id,
        urlopen=urllib.request.urlopen,
        sleep=time.sleep,
    )


def ensure_jsonrpc_ok(response: dict[str, Any], context: str) -> dict[str, Any]:
    error = response.get("error")
    if isinstance(error, dict):
        message = error.get("message") or json.dumps(
            error, ensure_ascii=False, sort_keys=True
        )
        raise CliError(
            f"Tutu MCP {context} failed: {message}", error_type="upstream_error"
        )
    result = response.get("result")
    if isinstance(result, dict):
        return result
    if result is None:
        return {}
    raise CliError(
        f"Tutu MCP {context} returned an unsupported result",
        error_type="upstream_error",
    )


def extract_tool_payload(result: dict[str, Any]) -> TutuToolPayload:
    if result.get("isError"):
        messages = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("text"):
                messages.append(str(item["text"]))
        raise CliError(
            "Tutu MCP tool error: " + ("; ".join(messages) or "unknown error"),
            error_type="upstream_error",
        )
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        if isinstance(structured.get("result"), (dict, list, str)):
            return structured["result"]
        return structured
    if isinstance(structured, list):
        return structured

    first_text: str | None = None
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if first_text is None:
            first_text = text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list, str)):
            # Tutu MCP wraps the payload in a {"result": "..."} string
            if isinstance(parsed, dict) and isinstance(parsed.get("result"), str):
                try:
                    inner = json.loads(parsed["result"])
                    if isinstance(inner, (dict, list, str)):
                        return inner
                except json.JSONDecodeError:
                    return parsed["result"]
            return parsed
    if first_text is not None:
        return first_text
    raise CliError(
        "Tutu MCP tool response did not include a content payload",
        error_type="upstream_error",
    )


def call_tutu_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    mcp_url: str | None = None,
    timeout: int = 60,
) -> TutuToolPayload:
    url = normalize_tutu_mcp_url(mcp_url)
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "hermes-flights-cli", "version": __version__},
        },
    }
    init_response, session_id = tutu_mcp_http_post(url, init_payload, timeout=timeout)
    ensure_jsonrpc_ok(init_response, "initialize")

    initialized_payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    tutu_mcp_http_post(url, initialized_payload, timeout=timeout, session_id=session_id)

    call_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    call_response, _ = tutu_mcp_http_post(
        url, call_payload, timeout=timeout, session_id=session_id
    )
    return extract_tool_payload(
        ensure_jsonrpc_ok(call_response, f"tools/call {tool_name}")
    )


def require_tutu_tool_object(
    payload: TutuToolPayload, tool_name: str
) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    raise CliError(
        f"Tutu MCP tool {tool_name} returned a non-JSON payload",
        error_type="upstream_error",
        details={"tool": tool_name, "payload_type": type(payload).__name__},
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
    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
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
    if only_carriers:
        discovery_arguments = {**arguments, "page_size": 1}
        discovery_raw = require_tutu_tool_object(
            call_tutu_mcp_tool(
                "search_avia",
                discovery_arguments,
                mcp_url=mcp_url,
                timeout=timeout,
            ),
            "search_avia",
        )
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
                source_url=normalize_tutu_mcp_url(mcp_url),
                origin_airports=allowed_origins,
                destination_airports=allowed_destinations,
                carrier_name_overrides=carrier_name_overrides,
            )
        arguments["carriers"] = mcp_carriers

    # Fetch first page
    raw = require_tutu_tool_object(
        call_tutu_mcp_tool("search_avia", arguments, mcp_url=mcp_url, timeout=timeout),
        "search_avia",
    )
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
        page_args = dict(arguments)
        page_args["page"] = page
        page_raw = require_tutu_tool_object(
            call_tutu_mcp_tool(
                "search_avia", page_args, mcp_url=mcp_url, timeout=timeout
            ),
            "search_avia",
        )
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
        source_url=normalize_tutu_mcp_url(mcp_url),
        origin_airports=allowed_origins,
        destination_airports=allowed_destinations,
        carrier_name_overrides=carrier_name_overrides,
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
