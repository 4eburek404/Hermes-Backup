from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..errors import CliError


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
    if not any(
        line.strip() and not line.lstrip().startswith("#")
        for line in text.splitlines()
    ):
        return {}
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CliError(
            f"invalid {source_name} YAML {source_path}: {exc}",
            error_type="configuration_error",
        ) from exc
    if not isinstance(value, dict):
        raise CliError(
            f"invalid {source_name} YAML {source_path}: top-level value must be a mapping",
            error_type="configuration_error",
        )
    return value


__all__ = ["load_yaml_mapping"]
