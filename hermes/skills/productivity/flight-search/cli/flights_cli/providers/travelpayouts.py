from __future__ import annotations

from typing import Any

from ..errors import CliError

_RETIRED_MESSAGE = (
    "Retired Travelpayouts price search is disabled in this CLI. "
    "Use static catalog metadata plus kb-search/fli-search/route live-assemble."
)


def _disabled(*_args: Any, **_kwargs: Any) -> Any:
    raise CliError(_RETIRED_MESSAGE, error_type="disabled")


def run_request_search(*args: Any, **kwargs: Any) -> Any:
    return _disabled(*args, **kwargs)


def parse_travelpayouts_results(*args: Any, **kwargs: Any) -> Any:
    return _disabled(*args, **kwargs)


def build_request_payload(*args: Any, **kwargs: Any) -> Any:
    return _disabled(*args, **kwargs)


def compact_request_payload(*args: Any, **kwargs: Any) -> Any:
    return _disabled(*args, **kwargs)


def segment_request_command(*args: Any, **kwargs: Any) -> Any:
    return _disabled(*args, **kwargs)
