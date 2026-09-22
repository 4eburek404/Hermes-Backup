# flight-calendar-ics agent eval

Recorded, offline agent-level evaluation of the candidate `flight-calendar-ics`
skill. The configured manifest has **three scenarios**, one repeat, and **nine
configured agent runs**: three provider/model pairs for each scenario.

Scenarios:

- `url-success` — existing synthetic Aeroflot booking URL flow;
- `ural-url-success` — synthetic Ural Airlines booking URL flow with recorded
  deployment/bootstrap/clock/reservation replay;
- `pdf-success` — synthetic `ticket.pdf` converted through the recorded AnyDoc
  boundary, then mapped to private itinerary JSON and the production CLI.

The provider/model order is contractual:

1. GPT-5.6 Luna — `gpt-5.6-luna` / `openai-codex`;
2. Neural Deep — Qwen 3.8 27B — `qwen3.8-27b` / `custom:neuraldeep`;
3. Ollama Cloud — Nemotron 3 Super — `nemotron-3-super` / `ollama-cloud`.

## Prepare the next selected batch

The next run should select only Ural and PDF:

```bash
python3 evals/flight-calendar-ics/run_eval.py \
  --scenario ural-url-success \
  --scenario pdf-success
```

That selection produces **2 scenarios × 3 models × 1 repeat = 6 agent runs**.
Without `--scenario`, the runner executes all three configured scenarios. The
runner supports configured scenario names generically; it does not hardcode the
selected pair.

This preparation task does not run LLM evaluations. Provider credentials/OAuth
must already be configured before a future selected batch is launched.

## Recorded boundaries

The candidate is materialized from:

```json
{"source": "git", "ref": "update/flight-calendar-ics"}
```

The source checkout is never switched, merged, reset, or modified by the eval.
Only the isolated materialized skill copy receives `replay/carrier_http.py`.
Aeroflot keeps its existing fixture flow. Ural replay supplies only its external
HTTP boundary: frontend root, versioned `env.json`, `settings/CurrentDateUtc`,
and `Reservation`; production `ural.py` performs the normal deployment-cache,
clock, authentication-header, validation, conversion, timezone, and CLI logic.
Each run gets a fresh `FLIGHT_CALENDAR_CACHE_DIR`.

For PDF, `ticket.pdf` is copied into the isolated workspace. The eval-only `npx`
shim accepts only the documented `npx -y @firecrawl/anydoc ticket.pdf -o ...`
shape and writes checked-in `fixtures/pdf/anydoc.md`; it never uses the network.
The agent must still extract facts, create private itinerary JSON, call
`--json build --input ...` exactly once, and return the exact `MEDIA:` result.

## Evidence and report

Each scenario has its own prompt, raw fixture, oracle, prompt SHA, and fixture
SHA. The common harness report labels rows with `Scenario` and keeps Outcome,
Trajectory, and Privacy separate. URL-integrity aggregation includes only URL
scenarios; PDF rows show `URL = —`, `Source = PDF`, and AnyDoc count in their
facts/notes. Private URLs, names, PNRs, tickets, raw PDF text, and intermediate
JSON contents are not printed in `report.md`.
