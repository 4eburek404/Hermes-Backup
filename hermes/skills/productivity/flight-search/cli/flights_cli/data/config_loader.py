from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import CliError
from .yaml_subset import YamlSubsetError, parse_yaml_subset


def load_yaml_mapping(
    path: str | Path,
    *,
    source_name: str,
    strict: bool = False,
    empty_is_missing: bool = False,
) -> dict[str, Any] | None:
    """Load one YAML mapping with the shared config-file failure policy."""

    source_path = Path(path)
    if not source_path.exists():
        if strict:
            raise CliError(
                f"{source_name} file not found: {source_path}",
                error_type="configuration_error",
            )
        return None
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        if not strict:
            return None
        raise CliError(
            f"could not read {source_name} file {source_path}: {exc}",
            error_type="configuration_error",
        ) from exc
    if empty_is_missing and not text.strip():
        return None
    try:
        return parse_yaml_subset(text, source_path)
    except YamlSubsetError as exc:
        raise CliError(
            f"invalid {source_name} YAML {exc}",
            error_type="configuration_error",
        ) from exc


__all__ = ["load_yaml_mapping"]
