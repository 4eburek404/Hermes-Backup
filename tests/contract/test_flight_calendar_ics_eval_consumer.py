#!/usr/bin/env python3
"""Executable public-contract check for the flight-calendar-ics eval."""
from __future__ import annotations

import json
import re
import hashlib
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
    expected_scenarios = ["url-success", "ural-url-success", "pdf-success"]
    if not isinstance(scenarios, dict) or list(scenarios) != expected_scenarios:
        fail(f"expected three scenarios {expected_scenarios!r}; got {scenarios!r}")
    if manifest.get("repeats") != 1:
        fail(f"expected one repeat; got {manifest.get('repeats')!r}")
    if len(models) * len(scenarios) * manifest["repeats"] != 9:
        fail("configured eval must contain exactly nine agent runs")

    prompt_shas = set()
    fixture_shas = set()
    for name in expected_scenarios:
        scenario = scenarios[name]
        for key in ("prompt", "fixture", "oracle", "evaluation"):
            if key not in scenario:
                fail(f"{name} scenario omits required field: {key}")
        prompt = EVAL / scenario["prompt"]
        fixture = EVAL / scenario["fixture"]
        if not prompt.is_file() or not fixture.is_file():
            fail(f"{name} prompt/fixture missing")
        prompt_shas.add(hashlib.sha256(prompt.read_bytes()).hexdigest())
        fixture_shas.add(hashlib.sha256(fixture.read_bytes()).hexdigest())
    if len(prompt_shas) != 3 or len(fixture_shas) != 3:
        fail("scenarios must have distinct prompt and fixture versions")

    if not (EVAL / "fixtures" / "ural" / "reservation.json").is_file():
        fail("Ural raw reservation fixture missing")
    if not (EVAL / "fixtures" / "pdf" / "ticket.pdf").is_file():
        fail("PDF fixture missing")
    if not (EVAL / "fixtures" / "pdf" / "anydoc.md").is_file():
        fail("AnyDoc replay fixture missing")
    if json.loads((EVAL / "fixtures" / "ural" / "reservation.json").read_text(encoding="utf-8"))["data"]["journey"] is None:
        fail("Ural fixture is not a raw reservation response")

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
    if not re.search(r"three\s+scenarios|3\s+scenarios", docs, re.IGNORECASE):
        fail("documentation must state that the eval has three scenarios")
    if not re.search(r"one\s+repeat|1\s+repeat", docs, re.IGNORECASE):
        fail("documentation must state that the eval has one repeat")
    if not re.search(r"nine\s+configured\s+agent\s+runs|9\s+agent\s+runs", docs, re.IGNORECASE):
        fail("documentation must state that the configured eval has nine agent runs")

    print("PASS: exact three provider/model pairs in required order")
    print("PASS: three scenarios, one repeat, nine configured agent runs")
    print("PASS: SPEC.md and README.md match the runtime matrix")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
