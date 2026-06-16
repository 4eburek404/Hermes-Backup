from __future__ import annotations

from typing import Any, cast

from ...errors import CliError
from ...ports.providers import FlightProviderPort, ProbeType, ProviderName, ProviderProbeResult
from ...store import Store
from flights_cli.pipeline._shared import resolve_country_code
from .fli_adapter import FLI_CAPABILITIES, FliProviderAdapter
from .kupibilet_adapter import KUPIBILET_CAPABILITIES, KupibiletProviderAdapter


PROVIDER_REGISTRY: dict[ProviderName, FlightProviderPort] = {
    "kupibilet": KupibiletProviderAdapter(),
    "fli": FliProviderAdapter(),
}


def location_country_code(store: Store, code: str) -> str | None:
    return resolve_country_code(store, code)


def airport_country_code(store: Store, code: str) -> str | None:
    return location_country_code(store, code)


def is_ru_touching_segment(spec: dict[str, Any], store: Store) -> bool:
    origin_country = airport_country_code(store, str(spec.get("origin") or ""))
    destination_country = airport_country_code(store, str(spec.get("destination") or ""))
    return "RU" in {origin_country, destination_country}


def provider_adapter(name: str, *, store: Store | None = None, kupibilet_fetcher: Any | None = None, fli_fetcher: Any | None = None) -> FlightProviderPort:
    normalized = name.strip().lower()
    if normalized == "kupibilet":
        if store is None and kupibilet_fetcher is None:
            return PROVIDER_REGISTRY["kupibilet"]
        kwargs: dict[str, Any] = {"store": store}
        if kupibilet_fetcher is not None:
            kwargs["fetcher"] = kupibilet_fetcher
        return KupibiletProviderAdapter(**kwargs)
    if normalized == "fli":
        if store is None and fli_fetcher is None:
            return PROVIDER_REGISTRY["fli"]
        return FliProviderAdapter(store=store, fetcher=fli_fetcher)
    raise CliError(f"unsupported provider {name!r}", error_type="validation_error")



def providers_for_segment(spec: dict[str, Any], store: Store, policy: str) -> list[ProviderName]:
    normalized_policy = str(policy or "auto").strip().lower()
    if normalized_policy in {"kupibilet", "fli"}:
        return [cast(ProviderName, provider_adapter(normalized_policy).name)]
    if normalized_policy == "both":
        return ["kupibilet", "fli"]
    if normalized_policy != "auto":
        raise CliError("provider policy must be one of auto, kupibilet, fli, both", error_type="validation_error")
    if is_ru_touching_segment(spec, store):
        return ["kupibilet"]
    return ["fli"]


def provider_adapters_for_segment(
    spec: dict[str, Any],
    store: Store,
    policy: str,
    *,
    kupibilet_fetcher: Any | None = None,
    fli_fetcher: Any | None = None,
) -> list[FlightProviderPort]:
    return [
        provider_adapter(name, store=store, kupibilet_fetcher=kupibilet_fetcher, fli_fetcher=fli_fetcher)
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
        source_boundary={"warning": "provider capability does not support this probe type"},
        errors=[{"type": "not_supported", "message": reason}],
    )


__all__ = [
    "FLI_CAPABILITIES",
    "KUPIBILET_CAPABILITIES",
    "PROVIDER_REGISTRY",
    "airport_country_code",
    "is_ru_touching_segment",
    "location_country_code",
    "not_supported_probe_result",
    "provider_adapter",
    "provider_adapters_for_segment",
    "providers_for_segment",
]
