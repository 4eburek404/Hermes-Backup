from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..data.config_loader import load_yaml_mapping
from ..errors import CliError
from .vocabulary import MarketClass

DEFAULT_ROUTE_ACCESS_PROFILES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "route_access_profiles.yaml"
)
ROUTE_ACCESS_PROFILES_SCHEMA_VERSION = "route_access_profiles.v1"

PROFILE_RESTRICTED_ACCESS = "restricted_access_market"
PROFILE_NORMAL_RU_TOUCHING = "normal_ru_touching_market"
PROFILE_NORMAL_GLOBAL = "normal_global_market"
PROFILE_STRUCTURALLY_CONSTRAINED = "structurally_constrained_access"

MODE_REQUIRED = "required"
MODE_OPTIONAL_AFTER_PROVIDER_FAILURE = "optional_after_provider_failure"
MODE_DIAGNOSTIC_REQUIRED = "diagnostic_required"


@dataclass(frozen=True, slots=True)
class RouteAccessDecision:
    market_class: str
    route_access_profile: str
    gateway_discovery_mode: str
    route_access_reasons: tuple[str, ...] = ()
    prior_set: str | None = None
    matched_rule_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "market_class": self.market_class,
            "route_access_profile": self.route_access_profile,
            "gateway_discovery_mode": self.gateway_discovery_mode,
            "route_access_reasons": list(self.route_access_reasons),
        }
        if self.prior_set:
            payload["prior_set"] = self.prior_set
        if self.matched_rule_id:
            payload["matched_rule_id"] = self.matched_rule_id
        return payload


@dataclass(frozen=True, slots=True)
class RouteAccessRule:
    rule_id: str
    when: dict[str, Any]
    profile: str
    gateway_discovery_mode: str
    reasons: tuple[str, ...] = ()
    prior_set: str | None = None


@dataclass(frozen=True, slots=True)
class RouteAccessProfileCatalog:
    region_groups: dict[str, tuple[str, ...]]
    rules: tuple[RouteAccessRule, ...]

    def decision_for_route(
        self,
        *,
        market_class: str,
        origin_country: str | None,
        destination_country: str | None,
    ) -> RouteAccessDecision:
        origin = _country_code(origin_country)
        destination = _country_code(destination_country)
        for rule in self.rules:
            if self._matches(rule.when, market_class, origin, destination):
                return RouteAccessDecision(
                    market_class=market_class,
                    route_access_profile=rule.profile,
                    gateway_discovery_mode=rule.gateway_discovery_mode,
                    route_access_reasons=rule.reasons,
                    prior_set=rule.prior_set,
                    matched_rule_id=rule.rule_id,
                )
        return default_route_access_decision(market_class)

    def _matches(
        self,
        conditions: dict[str, Any],
        market_class: str,
        origin_country: str | None,
        destination_country: str | None,
    ) -> bool:
        for key, expected in conditions.items():
            if key == "market_class":
                if market_class not in _string_set(expected):
                    return False
            elif key == "route_touches_country":
                countries = _string_set(expected)
                if not ({origin_country, destination_country} & countries):
                    return False
            elif key == "origin_country_any":
                if origin_country not in _string_set(expected):
                    return False
            elif key == "destination_country_any":
                if destination_country not in _string_set(expected):
                    return False
            elif key == "origin_region_any":
                if not self._country_in_any_region(origin_country, expected):
                    return False
            elif key == "destination_region_any":
                if not self._country_in_any_region(destination_country, expected):
                    return False
            else:
                return False
        return True

    def _country_in_any_region(self, country: str | None, regions: Any) -> bool:
        if not country:
            return False
        for region in _key_set(regions):
            if country in self.region_groups.get(region, ()):
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTE_ACCESS_PROFILES_SCHEMA_VERSION,
            "region_groups": {
                key: list(values) for key, values in self.region_groups.items()
            },
            "route_access_rules": [
                {
                    "id": rule.rule_id,
                    "when": dict(rule.when),
                    "profile": rule.profile,
                    "gateway_discovery_mode": rule.gateway_discovery_mode,
                    "reasons": list(rule.reasons),
                    **({"prior_set": rule.prior_set} if rule.prior_set else {}),
                }
                for rule in self.rules
            ],
        }


def default_route_access_decision(market_class: str) -> RouteAccessDecision:
    if market_class == MarketClass.GLOBAL_NON_RU:
        return RouteAccessDecision(
            market_class=market_class,
            route_access_profile=PROFILE_NORMAL_GLOBAL,
            gateway_discovery_mode=MODE_OPTIONAL_AFTER_PROVIDER_FAILURE,
        )
    if market_class == MarketClass.STRUCTURALLY_CONSTRAINED:
        return RouteAccessDecision(
            market_class=market_class,
            route_access_profile=PROFILE_STRUCTURALLY_CONSTRAINED,
            gateway_discovery_mode=MODE_DIAGNOSTIC_REQUIRED,
            route_access_reasons=("catalog_country_metadata_incomplete",),
        )
    return RouteAccessDecision(
        market_class=market_class,
        route_access_profile=PROFILE_NORMAL_RU_TOUCHING,
        gateway_discovery_mode=MODE_OPTIONAL_AFTER_PROVIDER_FAILURE,
        prior_set="default_ru_touching_gateways",
    )


def load_route_access_profiles(
    path: str | Path | None = None, *, strict: bool = False
) -> RouteAccessProfileCatalog:
    source_path = Path(path) if path is not None else DEFAULT_ROUTE_ACCESS_PROFILES_PATH
    raw = load_yaml_mapping(
        source_path,
        source_name="route access profiles",
        strict=strict,
        empty_is_missing=True,
    )
    if raw is None:
        return RouteAccessProfileCatalog(region_groups={}, rules=())
    return _catalog_from_raw(raw, source_path)


def _catalog_from_raw(raw: dict[str, Any], path: Path) -> RouteAccessProfileCatalog:
    schema_version = raw.get("schema_version")
    if schema_version != ROUTE_ACCESS_PROFILES_SCHEMA_VERSION:
        raise CliError(
            f"invalid route access profiles YAML {path}: schema_version must be {ROUTE_ACCESS_PROFILES_SCHEMA_VERSION}",
            error_type="configuration_error",
        )
    region_groups_raw = raw.get("region_groups") or {}
    if not isinstance(region_groups_raw, dict):
        raise CliError(
            f"invalid route access profiles YAML {path}: region_groups must be a mapping",
            error_type="configuration_error",
        )
    region_groups = {
        _normalize_key(key): tuple(_country_code(value) for value in values)
        for key, values in region_groups_raw.items()
        if isinstance(values, list)
    }
    rules_raw = raw.get("route_access_rules") or []
    if not isinstance(rules_raw, list):
        raise CliError(
            f"invalid route access profiles YAML {path}: route_access_rules must be a list",
            error_type="configuration_error",
        )
    rules = tuple(
        _normalize_rule(item, path, index) for index, item in enumerate(rules_raw, 1)
    )
    return RouteAccessProfileCatalog(region_groups=region_groups, rules=rules)


def _normalize_rule(item: dict[str, Any], path: Path, index: int) -> RouteAccessRule:
    if not isinstance(item, dict):
        raise CliError(
            f"invalid route access profiles YAML {path}: rule {index} must be a mapping; expected key: value",
            error_type="configuration_error",
        )
    rule_id = str(item.get("id") or "").strip()
    if not rule_id:
        raise CliError(
            f"invalid route access profiles YAML {path}: rule {index}.id is required",
            error_type="configuration_error",
        )
    when = item.get("when")
    if not isinstance(when, dict) or not when:
        raise CliError(
            f"invalid route access profiles YAML {path}: rule {rule_id}.when is required",
            error_type="configuration_error",
        )
    profile = str(item.get("profile") or "").strip()
    if not profile:
        raise CliError(
            f"invalid route access profiles YAML {path}: rule {rule_id}.profile is required",
            error_type="configuration_error",
        )
    mode = str(item.get("gateway_discovery_mode") or "").strip()
    if not mode:
        raise CliError(
            f"invalid route access profiles YAML {path}: rule {rule_id}.gateway_discovery_mode is required",
            error_type="configuration_error",
        )
    reasons = tuple(str(value).strip() for value in item.get("reasons") or [] if value)
    prior_set = str(item.get("prior_set") or "").strip() or None
    return RouteAccessRule(
        rule_id=rule_id,
        when=dict(when),
        profile=profile,
        gateway_discovery_mode=mode,
        reasons=reasons,
        prior_set=prior_set,
    )


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _country_code(value: Any) -> str | None:
    code = str(value or "").strip().upper()
    return code or None


def _string_set(value: Any) -> set[str | None]:
    if isinstance(value, list | tuple | set):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "").strip()
    return {text} if text else set()


def _key_set(value: Any) -> set[str]:
    return {_normalize_key(item) for item in _string_set(value)}


__all__ = [
    "DEFAULT_ROUTE_ACCESS_PROFILES_PATH",
    "MODE_DIAGNOSTIC_REQUIRED",
    "MODE_OPTIONAL_AFTER_PROVIDER_FAILURE",
    "MODE_REQUIRED",
    "PROFILE_NORMAL_GLOBAL",
    "PROFILE_NORMAL_RU_TOUCHING",
    "PROFILE_RESTRICTED_ACCESS",
    "PROFILE_STRUCTURALLY_CONSTRAINED",
    "ROUTE_ACCESS_PROFILES_SCHEMA_VERSION",
    "RouteAccessDecision",
    "RouteAccessProfileCatalog",
    "RouteAccessRule",
    "default_route_access_decision",
    "load_route_access_profiles",
]
