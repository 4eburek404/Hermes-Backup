from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import HERMES_ENV_PATH, TRAVELPAYOUTS_ENV_KEYS

_DOTENV_LOADED_KEYS: set[str] = set()

def load_env_file(path: Path = HERMES_ENV_PATH) -> set[str]:
    """Load Travelpayouts auth from Hermes .env without overriding process env."""
    loaded: set[str] = set()
    if not path.exists():
        return loaded
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return loaded
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[len("export ") :].strip()
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key not in TRAVELPAYOUTS_ENV_KEYS or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
        loaded.add(key)
    _DOTENV_LOADED_KEYS.update(loaded)
    return loaded


def auth_presence(key: str) -> dict[str, Any]:
    available = bool(os.getenv(key))
    if not available:
        return {"available": False, "source": "missing"}
    source = "hermes_env" if key in _DOTENV_LOADED_KEYS else "env"
    return {"available": True, "source": source}
