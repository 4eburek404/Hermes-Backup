# flight-calendar-ics minimal eval specification

## Target

The eval is a configuration-only, minimal agent-level check for the
`flight-calendar-ics` skill. It has one scenario, `url-success`, and exercises
three real Hermes runtime provider/model pairs.

## Runtime matrix

The manifest stores technical runtime identifiers, not display-name guesses:

- **GPT-5.6 Luna** — provider `openai-codex`, model `gpt-5.6-luna`.
- **Neural Deep — Qwen 3.8 27B** — provider `custom:neuraldeep`, model
  `qwen3.8-27b`.
- **Ollama Cloud — Nemotron 3 Super** — provider `ollama-cloud`, model
  `nemotron-3-super`.

The order is contractual: GPT-5.6 Luna is first, Qwen 3.8 27B through Neural
Deep is second, and Nemotron 3 Super through Ollama Cloud is third.

## Run shape

- One scenario: `url-success`.
- Three models.
- One repeat.
- Three agent runs in total (`3 models × 1 scenario × 1 repeat`).

## Non-goals

This minimal eval does not add scenarios, PDF/OCR processing,
baseline/candidate comparison, or other harness functionality. Live LLM runs
are separate from this configuration change.
