from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOG_MANIFEST_FILENAME = "catalog_manifest.json"


def canonical_json_bytes(data: Any) -> bytes:
    return (
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class CatalogStorage:
    """Filesystem owner for static catalog files and their manifest."""

    cache_dir: Path

    def path(self, filename: str) -> Path:
        return self.cache_dir / filename

    def exists(self, filename: str) -> bool:
        return self.path(filename).exists()

    def read_bytes(self, filename: str) -> bytes | None:
        try:
            return self.path(filename).read_bytes()
        except OSError:
            return None

    def read_rows(self, filename: str) -> list[dict[str, Any]]:
        raw = self.read_bytes(filename)
        if raw is None:
            return []
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def read_mapping(self, filename: str) -> dict[str, Any]:
        raw = self.read_bytes(filename)
        if raw is None:
            return {}
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def read_manifest(self) -> dict[str, Any]:
        return self.read_mapping(CATALOG_MANIFEST_FILENAME)

    def sha256(self, filename: str) -> str | None:
        content = self.read_bytes(filename)
        return hashlib.sha256(content).hexdigest() if content is not None else None

    def write_bytes_atomic(self, filename: str, content: bytes) -> None:
        path = self.path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_bytes(content)
        temp_path.replace(path)

    def write_json(self, filename: str, data: Any) -> bytes:
        content = canonical_json_bytes(data)
        self.write_bytes_atomic(filename, content)
        return content

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        self.write_json(CATALOG_MANIFEST_FILENAME, manifest)
