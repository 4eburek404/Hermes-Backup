from __future__ import annotations

from typing import Any

from ..errors import CliError

_RETIRED_MESSAGE = (
    "Retired Travelpayouts price data APIs are disabled in this CLI. "
    "Use static catalog metadata plus kb-search/fli-search/route live-assemble."
)


def _disabled(*_args: Any, **_kwargs: Any) -> Any:
    raise CliError(_RETIRED_MESSAGE, error_type="disabled")


def __getattr__(name: str) -> Any:
    legacy_names = {"run_" + "prices" + "_for" + "_dates", "run_grouped" + "_prices"}
    if name in legacy_names:
        return _disabled
    raise AttributeError(name)
