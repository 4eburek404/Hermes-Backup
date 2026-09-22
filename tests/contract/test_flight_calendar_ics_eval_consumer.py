#!/usr/bin/env python3
"""Executable public-contract check for the minimal flight-calendar-ics eval."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evals" / "flight-calendar-ics"
MANIFEST = EVAL / "manifest.json"
SPEC = EVAL / "SPEC.md"
README = EVAL / "README.md"

EXPECTED_MODELS = [
    {"model": "gpt-5.6-luna", "provider": "openai-codex"},
    {"model": "qwen3.8-27b", "provider": "custom:neuraldeep"},
    {"model": "nemotron-3-super", "provider": "ollama-cloud"},
]
FORBIDDEN_TEMPORARY_MODELS = ("deepseek-v4-pro", "glm-5.1")


def fail(message: str) -> NoReturn:
    raise AssertionError(message)


def main() -> int:
    for path in (MANIFEST, SPEC, README):
        if not path.is_file():
            fail(f"required eval artifact missing: {path.relative_to(ROOT)}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    models = manifest.get("models")
    if models != EXPECTED_MODELS:
        fail(f"runtime model matrix mismatch: {models!r}")
    if len(models) != 3 or len({(item["provider"], item["model"]) for item in models}) != 3:
        fail("manifest must contain exactly three distinct provider/model pairs")

    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, dict) or list(scenarios) != ["url-success"]:
        fail(f"expected exactly one scenario, url-success; got {scenarios!r}")
    if manifest.get("repeats") != 1:
        fail(f"expected one repeat; got {manifest.get('repeats')!r}")
    if len(models) * len(scenarios) * manifest["repeats"] != 3:
        fail("minimal eval must contain exactly three agent runs")

    scenario = scenarios["url-success"]
    for key in ("prompt", "fixture", "oracle", "evaluation"):
        if key not in scenario:
            fail(f"url-success scenario omits required field: {key}")

    docs = "\n".join(path.read_text(encoding="utf-8") for path in (SPEC, README))
    required_doc_values = (
        "GPT-5.6 Luna",
        "gpt-5.6-luna",
        "openai-codex",
        "Neural Deep",
        "Qwen 3.8 27B",
        "qwen3.8-27b",
        "custom:neuraldeep",
        "Ollama Cloud",
        "Nemotron 3 Super",
        "nemotron-3-super",
        "ollama-cloud",
    )
    for value in required_doc_values:
        if value not in docs:
            fail(f"documentation omits required matrix value: {value}")
    for value in FORBIDDEN_TEMPORARY_MODELS:
        if value in docs or value in MANIFEST.read_text(encoding="utf-8"):
            fail(f"temporary model remains in eval configuration: {value}")
    if not re.search(r"one\s+scenario|1\s+scenario", docs, re.IGNORECASE):
        fail("documentation must state that the eval has one scenario")
    if not re.search(r"one\s+repeat|1\s+repeat", docs, re.IGNORECASE):
        fail("documentation must state that the eval has one repeat")
    if not re.search(r"three\s+agent\s+runs|3\s+agent\s+runs", docs, re.IGNORECASE):
        fail("documentation must state that the eval has three agent runs")

    print("PASS: exact three provider/model pairs in required order")
    print("PASS: one url-success scenario, one repeat, three agent runs")
    print("PASS: SPEC.md and README.md match the runtime matrix")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
