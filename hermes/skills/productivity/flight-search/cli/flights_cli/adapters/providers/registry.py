from __future__ import annotations

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
from .fli_adapter import FLI_CAPABILITIES, FliProviderAdapter
from .kupibilet_adapter import KUPIBILET_CAPABILITIES, KupibiletProviderAdapter
from .tutu_adapter import TUTU_CAPABILITIES, TutuProviderAdapter

PROVIDER_REGISTRY: dict[ProviderName, FlightProviderPort] = {
    "kupibilet": KupibiletProviderAdapter(),
    "fli": FliProviderAdapter(),
    "tutu": TutuProviderAdapter(),
}
PROVIDER_ROUTING_ORDER: tuple[ProviderName, ...] = ("tutu", "kupibilet", "fli")

# Cache keyed by (name, id(store)). Grows to at most 2×N where N is the number of
# distinct Store instances (typically 1 per CLI invocation). Custom fetcher calls
# bypass this cache entirely.
_adapter_cache: dict[tuple[str, int | None], FlightProviderPort] = {}


def location_country_code(store: Store, code: str) -> str | None:
    normalized = code.upper()
    airport = store.airport_by_code.get(normalized)
    if airport and airport.get("country_code"):
        return str(airport.get("country_code") or "").upper()
    city = store.city_by_code.get(normalized)
    if city and city.get("country_code"):
        return str(city.get("country_code") or "").upper()
    return None


def airport_country_code(store: Store, code: str) -> str | None:
    return location_country_code(store, code)


def route_touches_ru(origin: Any, destination: Any, store: Store) -> bool:
    origin_country = airport_country_code(store, str(origin or ""))
    destination_country = airport_country_code(store, str(destination or ""))
    return "RU" in {origin_country, destination_country}


def is_ru_touching_segment(spec: dict[str, Any], store: Store) -> bool:
    return route_touches_ru(spec.get("origin"), spec.get("destination"), store)


def _normalize_provider_policy(policy: str) -> str:
    normalized_policy = str(policy or "auto").strip().lower()
    if normalized_policy not in {"auto", "kupibilet", "fli", "tutu"}:
        raise CliError(
            "provider policy must be one of auto, kupibilet, fli, tutu",
            error_type="validation_error",
        )
    return normalized_policy


def _offer_query_probe_type(query: dict[str, Any]) -> ProbeType:
    probe_type = str(query.get("probe_type") or "")
    if probe_type in {"full_route_aggregate", "carrier_aggregate"}:
        return cast(ProbeType, probe_type)
    if query.get("only_carriers"):
        return "carrier_aggregate"
    return "full_route_aggregate"


def _provider_supports_offer_query(
    provider: ProviderName, query: dict[str, Any], store: Store
) -> bool:
    capabilities = PROVIDER_REGISTRY[provider].capabilities
    probe_type = _offer_query_probe_type(query)
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
    provider: ProviderName, query: dict[str, Any], store: Store
) -> bool:
    return _provider_supports_offer_market(
        PROVIDER_REGISTRY[provider].capabilities, query, store
    )


def _offer_query_policy_candidates(
    query: dict[str, Any], store: Store, policy: str
) -> list[ProviderName]:
    normalized_policy = _normalize_provider_policy(policy)
    if normalized_policy in {"kupibilet", "fli", "tutu"}:
        provider = cast(ProviderName, normalized_policy)
        return [provider] if _provider_supports_market(provider, query, store) else []
    return [
        provider
        for provider in PROVIDER_ROUTING_ORDER
        if _provider_supports_market(provider, query, store)
    ]


def _segment_policy_candidates(
    spec: dict[str, Any], store: Store, policy: str
) -> list[ProviderName]:
    normalized_policy = _normalize_provider_policy(policy)
    if normalized_policy in {"kupibilet", "fli", "tutu"}:
        provider = cast(ProviderName, normalized_policy)
        return [provider] if _provider_supports_market(provider, spec, store) else []
    return [
        provider
        for provider in PROVIDER_ROUTING_ORDER
        if _provider_supports_market(provider, spec, store)
    ]


def _route_query_policy_candidates(
    query: dict[str, Any], store: Store, policy: str
) -> list[ProviderName]:
    normalized_policy = _normalize_provider_policy(policy)
    if normalized_policy in {"kupibilet", "fli", "tutu"}:
        provider = cast(ProviderName, normalized_policy)
        return [provider] if _provider_supports_market(provider, query, store) else []
    return [
        provider
        for provider in PROVIDER_ROUTING_ORDER
        if _provider_supports_market(provider, query, store)
    ]


def providers_for_route_query(
    query: dict[str, Any], store: Store, provider_policy: str
) -> list[ProviderName]:
    """Return route-level providers by market applicability, not probe capability."""

    return _route_query_policy_candidates(query, store, provider_policy)


def route_query_provider_skip_reasons(
    query: dict[str, Any], store: Store, provider_policy: str
) -> dict[ProviderName, str]:
    normalized_policy = _normalize_provider_policy(provider_policy)
    if not route_touches_ru(query.get("origin"), query.get("destination"), store):
        return {}
    if normalized_policy == "fli":
        return {"fli": "route_touches_ru"}
    return {}


def providers_for_offer_query(
    query: dict[str, Any], store: Store, provider_policy: str
) -> list[ProviderName]:
    """Return providers capable of running the requested full-route offer probe."""

    return [
        provider
        for provider in _offer_query_policy_candidates(query, store, provider_policy)
        if _provider_supports_offer_query(provider, query, store)
    ]


def unsupported_providers_for_offer_query(
    query: dict[str, Any], store: Store, provider_policy: str
) -> list[ProviderName]:
    supported = set(providers_for_offer_query(query, store, provider_policy))
    return [
        provider
        for provider in _offer_query_policy_candidates(query, store, provider_policy)
        if provider not in supported
    ]


def provider_adapter(
    name: str,
    *,
    store: Store | None = None,
    kupibilet_fetcher: Any | None = None,
    fli_fetcher: Any | None = None,
) -> FlightProviderPort:
    normalized = name.strip().lower()
    # Custom fetcher = bespoke instance, never cached
    if kupibilet_fetcher is not None or fli_fetcher is not None:
        if normalized == "kupibilet":
            return KupibiletProviderAdapter(store=store, fetcher=kupibilet_fetcher)
        if normalized == "fli":
            return FliProviderAdapter(store=store, fetcher=fli_fetcher)
        raise CliError(f"unsupported provider {name!r}", error_type="validation_error")
    # Cache lookup
    cache_key = (normalized, id(store) if store is not None else None)
    cached = _adapter_cache.get(cache_key)
    if cached is not None:
        return cached
    # Construct and cache
    if normalized == "kupibilet":
        if store is None:
            result = PROVIDER_REGISTRY["kupibilet"]
        else:
            result = KupibiletProviderAdapter(store=store)
    elif normalized == "fli":
        if store is None:
            result = PROVIDER_REGISTRY["fli"]
        else:
            result = FliProviderAdapter(store=store)
    elif normalized == "tutu":
        if store is None:
            result = PROVIDER_REGISTRY["tutu"]
        else:
            result = TutuProviderAdapter(store=store)
    else:
        raise CliError(f"unsupported provider {name!r}", error_type="validation_error")
    _adapter_cache[cache_key] = result
    return result


def providers_for_segment(
    spec: dict[str, Any], store: Store, policy: str
) -> list[ProviderName]:
    return _segment_policy_candidates(spec, store, policy)


def provider_adapters_for_segment(
    spec: dict[str, Any],
    store: Store,
    policy: str,
    *,
    kupibilet_fetcher: Any | None = None,
    fli_fetcher: Any | None = None,
    tutu_fetcher: Any | None = None,
) -> list[FlightProviderPort]:
    adapters: list[FlightProviderPort] = []
    for name in providers_for_segment(spec, store, policy):
        if name == "kupibilet":
            adapters.append(
                provider_adapter(name, store=store, kupibilet_fetcher=kupibilet_fetcher)
            )
        elif name == "fli":
            adapters.append(
                provider_adapter(name, store=store, fli_fetcher=fli_fetcher)
            )
        elif name == "tutu":
            if tutu_fetcher is not None:
                adapters.append(TutuProviderAdapter(store=store, fetcher=tutu_fetcher))
            else:
                adapters.append(provider_adapter(name, store=store))
        else:
            adapters.append(provider_adapter(name, store=store))
    return adapters


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
    "FLI_CAPABILITIES",
    "KUPIBILET_CAPABILITIES",
    "TUTU_CAPABILITIES",
    "PROVIDER_REGISTRY",
    "PROVIDER_ROUTING_ORDER",
    "airport_country_code",
    "is_ru_touching_segment",
    "location_country_code",
    "not_supported_probe_result",
    "provider_adapter",
    "provider_adapters_for_segment",
    "providers_for_offer_query",
    "providers_for_route_query",
    "providers_for_segment",
    "route_query_provider_skip_reasons",
    "route_touches_ru",
    "unsupported_providers_for_offer_query",
]
