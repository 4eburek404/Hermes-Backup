#!/usr/bin/env python3
"""Probe Hermes memory provider/config without dumping secrets."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

status = subprocess.run(["hermes", "memory", "status"], text=True, capture_output=True, timeout=30)
config_path = Path.home() / ".hermes/config.yaml"
config_summary = {"config_exists": config_path.exists()}
if config_path.exists() and yaml is not None:
    data = yaml.safe_load(config_path.read_text()) or {}
    config_summary.update({
        "memory": data.get("memory"),
        "plugin_hermes_memory_store": (data.get("plugins") or {}).get("hermes-memory-store"),
    })
elif yaml is None:
    config_summary["yaml_available"] = False

print(json.dumps({
    "hermes_memory_status_exit": status.returncode,
    "hermes_memory_status_stdout": status.stdout.strip(),
    "hermes_memory_status_stderr": status.stderr.strip(),
    "config_summary": config_summary,
}, ensure_ascii=False, indent=2))
