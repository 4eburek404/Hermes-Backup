# flight-calendar-ics minimal eval

This directory defines the smallest useful agent-level matrix for the
`flight-calendar-ics` skill. The harness consumes the technical identifiers in
`manifest.json`; the labels below are only human-readable names.

## Matrix

1. **GPT-5.6 Luna** — provider `openai-codex`, model `gpt-5.6-luna`.
2. **Neural Deep — Qwen 3.8 27B** — provider `custom:neuraldeep`, model
   `qwen3.8-27b`.
3. **Ollama Cloud — Nemotron 3 Super** — provider `ollama-cloud`, model
   `nemotron-3-super`.

## Scope

The eval has one scenario (`url-success`), one repeat, and three agent runs in
total. No extra scenarios, PDF/OCR, baseline/candidate comparison, or other
functionality is included.

The executable contract is:

```bash
python3 tests/contract/test_flight_calendar_ics_eval_consumer.py
```

It checks the manifest's three distinct provider/model pairs, the scenario and
repeat counts, the total run count, and consistency between this README,
`SPEC.md`, and `manifest.json`. It does not launch live LLM runs.
