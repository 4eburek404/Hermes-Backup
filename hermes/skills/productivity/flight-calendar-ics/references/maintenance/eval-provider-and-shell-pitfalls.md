# Eval Provider and Shell Path Pitfalls

Use this note when maintaining or running cross-model `flight-calendar-ics` evaluations.

## Provider identity: Ollama Cloud models

When a target model is served through Ollama Cloud, request it through the canonical Hermes provider:

```text
provider=ollama-cloud
model=<ollama model name>
```

Examples:

- `provider=ollama-cloud`, `model=deepseek-v4-pro`
- `provider=ollama-cloud`, `model=glm-5.1`
- `provider=ollama-cloud`, `model=gemini-3-flash-preview`
- `provider=ollama-cloud`, `model=gemma4:31b`

Do not label these rows as native `deepseek`, `zai`, `gemini`, or `gemma4` providers unless the runtime session metadata proves that the native provider actually handled the run. If a native provider lacks credentials or fails before success, Hermes may fall back to another configured provider; that row is invalid for model comparison unless re-bucketed under the effective provider/model.

Verification fields to capture per run:

- requested provider/model;
- actual/effective session model;
- base URL or provider profile source;
- whether fallback occurred;
- whether the row is valid for model comparison.

## Codex and same-line shell assignments

Do not prompt agents to run commands like:

```bash
SKILL_DIR=/abs/skill URL_FILE=/private/url OUT_DIR=/tmp/out python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file "$URL_FILE" --output-dir "$OUT_DIR"
```

POSIX shells expand command words before those temporary assignments are applied to the command. `$SKILL_DIR` can therefore expand empty and become:

```text
/scripts/flight_calendar_ics.py
```

Preferred automated eval prompt:

```bash
python "/abs/skill/scripts/flight_calendar_ics.py" --json build auto --url-file "/private/url" --output-dir "/tmp/out"
```

Acceptable manual/operator variant:

```bash
export SKILL_DIR=/abs/skill
export URL_FILE=/private/url
export OUT_DIR=/tmp/out
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file "$URL_FILE" --output-dir "$OUT_DIR"
```

## Fast-model interpretation

Direct CLI smoke isolates product latency. Model wall-clock mostly measures agent/tool-loop behavior plus provider/network variance. Fast/compliant rows usually:

1. read `SKILL.md` once;
2. run `build auto` once;
3. verify the JSON envelope/path/mode/counts;
4. stop.

Extra `doctor`, source/reference inspection, generated `.ics` reads, broad scanner commands, or retries are agent-loop overhead, not necessarily CLI regression.
