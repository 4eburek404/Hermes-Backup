from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ..errors import CliError

DEFAULT_GATEWAY_PRIORS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "gateway_priors.yaml"
)
GATEWAY_PRIORS_SCHEMA_VERSION = "gateway_priors.v1"
IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True, slots=True)
class GatewayPriorCatalog:
    markets: dict[str, tuple[dict[str, Any], ...]]

    def for_market(self, market_key: str) -> list[dict[str, Any]]:
        key = normalize_market_key(market_key)
        return [dict(item) for item in self.markets.get(key, ())]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GATEWAY_PRIORS_SCHEMA_VERSION,
            "markets": {
                key: [dict(item) for item in values]
                for key, values in self.markets.items()
            },
        }


def normalize_market_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def load_gateway_priors(
    path: str | Path | None = None, *, strict: bool = False
) -> GatewayPriorCatalog:
    source_path = Path(path) if path is not None else DEFAULT_GATEWAY_PRIORS_PATH
    if not source_path.exists():
        if strict:
            raise CliError(
                f"gateway priors file not found: {source_path}",
                error_type="configuration_error",
            )
        return GatewayPriorCatalog(markets={})
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        if not strict:
            return GatewayPriorCatalog(markets={})
        raise CliError(
            f"could not read gateway priors file {source_path}: {exc}",
            error_type="configuration_error",
        ) from exc
    raw = _parse_gateway_priors_yaml(text, source_path)
    return _catalog_from_raw(raw, source_path)


def _parse_gateway_priors_yaml(text: str, path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    markets: dict[str, list[dict[str, Any]]] | None = None
    current_market: str | None = None
    current_prior: dict[str, Any] | None = None
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            _yaml_error(path, line_no, "tabs are not supported")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            key, value = _yaml_key_value(stripped, path, line_no)
            if key == "schema_version":
                root[key] = _yaml_scalar(value, path, line_no)
            elif key == "markets":
                if value.strip():
                    _yaml_error(path, line_no, "markets must be a mapping")
                markets = {}
                root["markets"] = markets
            else:
                _yaml_error(path, line_no, f"unsupported top-level key {key!r}")
            current_market = None
            current_prior = None
            continue
        if markets is None:
            _yaml_error(path, line_no, "market entries must appear under markets")
        if indent == 2:
            if not stripped.endswith(":") or ":" in stripped[:-1]:
                _yaml_error(path, line_no, "market key must be a mapping key")
            current_market = normalize_market_key(stripped[:-1])
            if not current_market:
                _yaml_error(path, line_no, "market key is required")
            markets[current_market] = []
            current_prior = None
            continue
        if indent == 4:
            if current_market is None:
                _yaml_error(path, line_no, "prior entry must appear under a market")
            if not stripped.startswith("- "):
                _yaml_error(path, line_no, "prior entries must use '- key: value'")
            current_prior = {}
            markets[current_market].append(current_prior)
            rest = stripped[2:].strip()
            if rest:
                key, value = _yaml_key_value(rest, path, line_no)
                current_prior[key] = _yaml_scalar(value, path, line_no)
            continue
        if indent == 6:
            if current_prior is None:
                _yaml_error(path, line_no, "prior field must follow a list item")
            key, value = _yaml_key_value(stripped, path, line_no)
            current_prior[key] = _yaml_scalar(value, path, line_no)
            continue
        _yaml_error(path, line_no, f"unsupported indentation level {indent}")
    return root


def _yaml_key_value(text: str, path: Path, line_no: int) -> tuple[str, str]:
    if ":" not in text:
        _yaml_error(path, line_no, "expected key: value")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        _yaml_error(path, line_no, "key is required")
    return key, value.strip()


def _yaml_scalar(value: str, path: Path, line_no: int) -> Any:
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            _yaml_error(path, line_no, "unterminated quoted string")
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _catalog_from_raw(raw: dict[str, Any], path: Path) -> GatewayPriorCatalog:
    schema_version = raw.get("schema_version")
    if schema_version != GATEWAY_PRIORS_SCHEMA_VERSION:
        raise CliError(
            f"invalid gateway priors YAML {path}: schema_version must be {GATEWAY_PRIORS_SCHEMA_VERSION}",
            error_type="configuration_error",
        )
    markets_raw = raw.get("markets")
    if not isinstance(markets_raw, dict):
        raise CliError(
            f"invalid gateway priors YAML {path}: markets mapping is required",
            error_type="configuration_error",
        )
    markets: dict[str, tuple[dict[str, Any], ...]] = {}
    for market_key, prior_items in markets_raw.items():
        if not isinstance(prior_items, list):
            raise CliError(
                f"invalid gateway priors YAML {path}: market {market_key!r} must contain a list",
                error_type="configuration_error",
            )
        normalized_key = normalize_market_key(market_key)
        markets[normalized_key] = tuple(
            _normalize_prior(item, path, normalized_key, index)
            for index, item in enumerate(prior_items, 1)
        )
    return GatewayPriorCatalog(markets=markets)


def _normalize_prior(
    item: dict[str, Any], path: Path, market_key: str, index: int
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise CliError(
            f"invalid gateway priors YAML {path}: prior {market_key}[{index}] must be a mapping",
            error_type="configuration_error",
        )
    code = str(item.get("code") or "").strip().upper()
    if not IATA_CODE_RE.match(code):
        raise CliError(
            f"invalid gateway priors YAML {path}: prior {market_key}[{index}].code must be a 3-letter IATA code",
            error_type="configuration_error",
        )
    if "prior_weight" not in item:
        raise CliError(
            f"invalid gateway priors YAML {path}: prior {market_key}[{index}].prior_weight is required",
            error_type="configuration_error",
        )
    prior_weight = item.get("prior_weight")
    if not isinstance(prior_weight, int | float):
        raise CliError(
            f"invalid gateway priors YAML {path}: prior {market_key}[{index}].prior_weight must be numeric",
            error_type="configuration_error",
        )
    reason = str(item.get("reason") or "").strip()
    if not reason:
        raise CliError(
            f"invalid gateway priors YAML {path}: prior {market_key}[{index}].reason is required",
            error_type="configuration_error",
        )
    source = str(item.get("source") or "static_prior").strip()
    if source != "static_prior":
        raise CliError(
            f"invalid gateway priors YAML {path}: prior {market_key}[{index}].source must be static_prior",
            error_type="configuration_error",
        )
    return {
        "code": code,
        "prior_weight": prior_weight,
        "reason": reason,
        "source": "static_prior",
    }


def _yaml_error(path: Path, line_no: int, message: str) -> None:
    raise CliError(
        f"invalid gateway priors YAML {path}:{line_no}: {message}",
        error_type="configuration_error",
    )


__all__ = [
    "DEFAULT_GATEWAY_PRIORS_PATH",
    "GATEWAY_PRIORS_SCHEMA_VERSION",
    "GatewayPriorCatalog",
    "load_gateway_priors",
    "normalize_market_key",
]
