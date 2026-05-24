from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...errors import CliError
from ...ports.providers import ProbeType, ProviderCapabilities, ProviderName, ProviderProbeResult
from ...store import Store


@dataclass(frozen=True)
class ProviderDescriptor:
    name: ProviderName
    capabilities: ProviderCapabilities

    def supports_probe(self, probe_type: ProbeType) -> bool:
        return probe_type in self.capabilities.probe_types


PROVIDER_REGISTRY: dict[ProviderName, ProviderDescriptor] = {
    "kupibilet": ProviderDescriptor(
        name="kupibilet",
        capabilities=ProviderCapabilities(
            supports_ru_touching=True,
            supports_global=True,
            supports_city_code=True,
            supports_direct_only=True,
            supports_carrier_filter=True,
            supports_full_route_aggregate=True,
            supports_round_trip=False,
            supports_cache=True,
            probe_types=frozenset({"segment_direct", "segment_hub_leg", "full_route_aggregate", "carrier_aggregate", "city_pair_direct"}),
        ),
    ),
    "fli": ProviderDescriptor(
        name="fli",
        capabilities=ProviderCapabilities(
            supports_ru_touching=False,
            supports_global=True,
            supports_city_code=False,
            supports_direct_only=True,
            supports_carrier_filter=True,
            supports_full_route_aggregate=False,
            supports_round_trip=False,
            supports_cache=True,
            probe_types=frozenset({"segment_direct", "segment_hub_leg", "city_pair_direct"}),
        ),
    ),
}


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


def is_ru_touching_segment(spec: dict[str, Any], store: Store) -> bool:
    origin_country = airport_country_code(store, str(spec.get("origin") or ""))
    destination_country = airport_country_code(store, str(spec.get("destination") or ""))
    return "RU" in {origin_country, destination_country}


def provider_descriptor(name: str) -> ProviderDescriptor:
    normalized = name.strip().lower()
    if normalized not in PROVIDER_REGISTRY:
        raise CliError(f"unsupported provider {name!r}", error_type="validation_error")
    return PROVIDER_REGISTRY[normalized]  # type: ignore[index]


def providers_for_segment(spec: dict[str, Any], store: Store, policy: str) -> list[ProviderName]:
    normalized_policy = str(policy or "auto").strip().lower()
    if normalized_policy in {"kupibilet", "fli"}:
        return [provider_descriptor(normalized_policy).name]
    if normalized_policy == "both":
        return ["kupibilet", "fli"]
    if normalized_policy != "auto":
        raise CliError("provider policy must be one of auto, kupibilet, fli, both", error_type="validation_error")
    if is_ru_touching_segment(spec, store):
        return ["kupibilet"]
    return ["fli"]


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
