#!/usr/bin/env python3
"""Executable contract for the minimal flight-calendar-ics eval matrix."""
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
    {
        "label": "GPT-5.6 Luna",
        "model": "gpt-5.6-luna",
        "provider": "openai-codex",
    },
    {
        "label": "Neural Deep — Qwen 3.8 27B",
        "model": "qwen3.8-27b",
        "provider": "custom:neuraldeep",
    },
    {
        "label": "Ollama Cloud — Nemotron 3 Super",
        "model": "nemotron-3-super",
        "provider": "ollama-cloud",
    },
]


def fail(message: str) -> "NoReturn":
    raise AssertionError(message)


def main() -> int:
    for path in (MANIFEST, SPEC, README):
        if not path.is_file():
            fail(f"required eval artifact missing: {path.relative_to(ROOT)}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    models = manifest.get("models")
    if models != EXPECTED_MODELS:
        fail(f"models do not match the required runtime matrix: {models!r}")
    if len(models) != 3 or len({(m["provider"], m["model"]) for m in models}) != 3:
        fail("manifest must contain exactly three distinct provider/model pairs")

    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or scenarios != ["url-success"]:
        fail(f"expected exactly one scenario, url-success; got {scenarios!r}")
    if manifest.get("repeats") != 1:
        fail(f"expected one repeat; got {manifest.get('repeats')!r}")
    expected_runs = len(models) * len(scenarios) * manifest["repeats"]
    if expected_runs != 3 or manifest.get("expected_agent_runs") != 3:
        fail("minimal eval must schedule exactly three agent runs")

    docs = "\n".join(path.read_text(encoding="utf-8") for path in (SPEC, README))
    for model in EXPECTED_MODELS:
        for value in (model["label"], model["model"], model["provider"]):
            if value not in docs:
                fail(f"documentation omits required matrix value: {value}")
    if not re.search(r"one\s+scenario|1\s+scenario", docs, re.IGNORECASE):
        fail("documentation must state that the eval has one scenario")
    if not re.search(r"one\s+repeat|1\s+repeat", docs, re.IGNORECASE):
        fail("documentation must state that the eval has one repeat")
    if not re.search(r"three\s+agent\s+runs|3\s+agent\s+runs", docs, re.IGNORECASE):
        fail("documentation must state that the eval has three agent runs")

    print("PASS: 3 runtime provider/model pairs")
    print("PASS: scenario=url-success, repeats=1, expected_agent_runs=3")
    print("PASS: SPEC.md and README.md match the manifest matrix")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
