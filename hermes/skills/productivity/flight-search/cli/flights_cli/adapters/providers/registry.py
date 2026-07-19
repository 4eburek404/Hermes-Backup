from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from ...errors import CliError
from ...ports.providers import (
    FlightProviderPort,
    ProbeType,
    ProviderCapabilities,
    ProviderName,
    ProviderProbeResult,
)
from ...store import Store
from .kupibilet_adapter import KUPIBILET_CAPABILITIES, KupibiletProviderAdapter
from .tutu_adapter import TUTU_CAPABILITIES, TutuProviderAdapter

PROVIDER_REGISTRY: dict[str, FlightProviderPort] = {
    "tutu": TutuProviderAdapter(),
    "kupibilet": KupibiletProviderAdapter(),
}

# Cache keyed by (name, id(store)). Grows to at most 2×N where N is the number of
# distinct Store instances (typically 1 per CLI invocation). Custom fetcher calls
# bypass this cache entirely.
_adapter_cache: dict[tuple[str, int | None], FlightProviderPort] = {}
_PROVIDER_FACTORIES: dict[str, Callable[[Store | None], FlightProviderPort]] = {
    "tutu": lambda store: TutuProviderAdapter(store=store),
    "kupibilet": lambda store: KupibiletProviderAdapter(store=store),
}


def airport_country_code(store: Store, code: str) -> str | None:
    normalized = code.upper()
    airport = store.airport_by_code.get(normalized)
    if airport and airport.get("country_code"):
        return str(airport.get("country_code") or "").upper()
    city = store.city_by_code.get(normalized)
    if city and city.get("country_code"):
        return str(city.get("country_code") or "").upper()
    return None


def route_touches_ru(origin: Any, destination: Any, store: Store) -> bool:
    origin_country = airport_country_code(store, str(origin or ""))
    destination_country = airport_country_code(store, str(destination or ""))
    return "RU" in {origin_country, destination_country}


def is_ru_touching_segment(spec: dict[str, Any], store: Store) -> bool:
    return route_touches_ru(spec.get("origin"), spec.get("destination"), store)


def _normalize_provider_policy(policy: str) -> str:
    normalized_policy = str(policy or "auto").strip().lower()
    if normalized_policy != "auto" and normalized_policy not in PROVIDER_REGISTRY:
        raise CliError(
            "provider policy must be auto or a registered provider name",
            error_type="validation_error",
            details={"registered_providers": list(PROVIDER_REGISTRY)},
        )
    return normalized_policy


def offer_query_probe_type(query: dict[str, Any]) -> ProbeType:
    probe_type = str(query.get("probe_type") or "")
    if probe_type in {"full_route_aggregate", "carrier_aggregate"}:
        return cast(ProbeType, probe_type)
    if query.get("only_carriers"):
        return "carrier_aggregate"
    return "full_route_aggregate"


def provider_supports_offer_query(
    provider: str, query: dict[str, Any], store: Store
) -> bool:
    if provider not in PROVIDER_REGISTRY:
        return False
    capabilities = PROVIDER_REGISTRY[provider].capabilities
    probe_type = offer_query_probe_type(query)
    if probe_type not in capabilities.probe_types:
        return False
    if probe_type in {"full_route_aggregate", "carrier_aggregate"}:
        if not capabilities.supports_full_route_aggregate:
            return False
    if probe_type == "carrier_aggregate" and not capabilities.supports_carrier_filter:
        return False
    if bool(query.get("direct_only")) and not capabilities.supports_direct_only:
        return False
    return _provider_supports_offer_market(capabilities, query, store)


def _provider_supports_offer_market(
    capabilities: ProviderCapabilities, query: dict[str, Any], store: Store
) -> bool:
    if is_ru_touching_segment(query, store):
        return capabilities.supports_ru_touching
    return capabilities.supports_global


def _provider_supports_market(
    provider: str, query: dict[str, Any], store: Store
) -> bool:
    return _provider_supports_offer_market(
        PROVIDER_REGISTRY[provider].capabilities, query, store
    )


def _policy_candidates(query: dict[str, Any], store: Store, policy: str) -> list[str]:
    normalized_policy = _normalize_provider_policy(policy)
    if normalized_policy != "auto":
        return [normalized_policy]
    return [
        provider
        for provider in PROVIDER_REGISTRY
        if _provider_supports_market(provider, query, store)
    ]


def providers_for_offer_query(
    query: dict[str, Any], store: Store, provider_policy: str
) -> list[str]:
    """Return providers capable of running the requested full-route offer probe."""

    normalized_policy = _normalize_provider_policy(provider_policy)
    if normalized_policy != "auto":
        return [normalized_policy]
    return [
        provider
        for provider in _policy_candidates(query, store, normalized_policy)
        if provider_supports_offer_query(provider, query, store)
    ]


def provider_adapter(
    name: str,
    *,
    store: Store | None = None,
) -> FlightProviderPort:
    normalized = name.strip().lower()
    # Cache lookup
    cache_key = (normalized, id(store) if store is not None else None)
    cached = _adapter_cache.get(cache_key)
    if cached is not None:
        return cached
    # Construct and cache
    if normalized not in PROVIDER_REGISTRY:
        raise CliError(f"unsupported provider {name!r}", error_type="validation_error")
    if store is None:
        result = PROVIDER_REGISTRY[normalized]
    else:
        factory = _PROVIDER_FACTORIES.get(normalized)
        result = (
            factory(store) if factory is not None else PROVIDER_REGISTRY[normalized]
        )
    _adapter_cache[cache_key] = result
    return result


def provider_supports_segment(
    provider: str, spec: dict[str, Any], store: Store
) -> bool:
    if provider not in PROVIDER_REGISTRY:
        return False
    probe_type = str(spec.get("probe_type") or "segment_direct")
    capabilities = PROVIDER_REGISTRY[provider].capabilities
    return bool(
        probe_type in capabilities.probe_types
        and (not bool(spec.get("direct_only")) or capabilities.supports_direct_only)
        and (not spec.get("only_carriers") or capabilities.supports_carrier_filter)
        and _provider_supports_market(provider, spec, store)
    )


def providers_for_segment(spec: dict[str, Any], store: Store, policy: str) -> list[str]:
    normalized_policy = _normalize_provider_policy(policy)
    if normalized_policy != "auto":
        return [normalized_policy]
    return [
        provider
        for provider in _policy_candidates(spec, store, normalized_policy)
        if provider_supports_segment(provider, spec, store)
    ]


def provider_adapters_for_segment(
    spec: dict[str, Any],
    store: Store,
    policy: str,
    *,
    adapter_resolver: Callable[..., FlightProviderPort] | None = None,
) -> list[FlightProviderPort]:
    resolver = adapter_resolver or provider_adapter
    return [
        resolver(name, store=store)
        for name in providers_for_segment(spec, store, policy)
    ]


def not_supported_probe_result(
    *,
    provider: ProviderName,
    probe_type: ProbeType,
    query: dict[str, Any],
    reason: str,
    probe_id: str = "probe-unsupported",
) -> ProviderProbeResult:
    return ProviderProbeResult(
        probe_id=probe_id,
        probe_type=probe_type,
        provider=provider,
        query=query,
        execution_state="not_supported",
        cache_status="unknown",
        evidence_type="not_supported",
        result_summary={"reason": reason},
        source_boundary={
            "warning": "provider capability does not support this probe type"
        },
        errors=[{"type": "not_supported", "message": reason}],
    )


__all__ = [
    "KUPIBILET_CAPABILITIES",
    "TUTU_CAPABILITIES",
    "PROVIDER_REGISTRY",
    "airport_country_code",
    "is_ru_touching_segment",
    "not_supported_probe_result",
    "offer_query_probe_type",
    "provider_adapter",
    "provider_adapters_for_segment",
    "provider_supports_offer_query",
    "provider_supports_segment",
    "providers_for_offer_query",
    "providers_for_segment",
    "route_touches_ru",
]
