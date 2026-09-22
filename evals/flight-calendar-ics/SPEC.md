# flight-calendar-ics — Agent Eval Specification

## Scope and matrix

The eval is recorded/offline and evaluates the complete candidate skill from Git
ref `update/flight-calendar-ics`. The configured manifest contains three
scenarios, one repeat, and nine configured agent runs: each scenario executes on
these three provider/model pairs in order:

- GPT-5.6 Luna: `gpt-5.6-luna` / `openai-codex`;
- Neural Deep — Qwen 3.8 27B: `qwen3.8-27b` / `custom:neuraldeep`;
- Ollama Cloud — Nemotron 3 Super: `nemotron-3-super` / `ollama-cloud`.

The next selected matrix is `ural-url-success` plus `pdf-success`: six agent
runs total. `url-success` remains configured and must continue to work.

Every scenario owns a prompt, raw fixture, oracle, evaluation rules, prompt SHA,
and fixture SHA. The evaluator oracle is not exposed to the agent.

## `url-success`

This is the preserved synthetic Aeroflot booking-URL success flow. It requires
one direct `--json build --url` CLI call, no URL-file detour, stop after success,
two semantic VEVENTs, and the exact `MEDIA:` delivery protocol. Its existing
fixture and oracle remain unchanged.

## `ural-url-success`

The prompt is an ordinary request containing the synthetic URL:

`https://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV`

`fixtures/ural/reservation.json` is a checked-in raw carrier response copied from
the candidate executable spec. It is not a prebuilt itinerary. The scenario-aware
replay supplies deterministic responses for the service root, `/12345/env/env.json`,
`/api/settings/CurrentDateUtc`, and `/api/Reservation`; no live HTTP is allowed.
The isolated run sets a fresh `FLIGHT_CALENDAR_CACHE_DIR`.

Expected semantic output is two VEVENTs:

- `U6 273`, DME → SVX, 21.09.2026 08:25–12:55 local, Airbus A320;
  `DTSTART:20260921T052500Z`, `DTEND:20260921T075500Z`;
- `U6 270`, SVX → DME, 24.09.2026 20:30–21:00 local, Airbus A321;
  `DTSTART:20260924T153000Z`, `DTEND:20260924T180000Z`.

The oracle is checked against the candidate production timezone catalog: DME is
`Europe/Moscow`, SVX is `Asia/Yekaterinburg`. Outcome checks artifact existence,
two events, flight number, route, UTC times, and aircraft. Trajectory requires
one direct URL CLI call and stop-after-CLI. Privacy forbids the URL, credentials,
synthetic passenger/ticket markers, and raw fixture markers in the final answer.

The observable ICS contract does not include a flight-number line in
`DESCRIPTION`; flight numbers are covered by the Ural production executable
specs, not duplicated as an impossible ICS assertion here.

## `pdf-success`

`fixtures/pdf/ticket.pdf` is fully synthetic and contains a human-readable
itinerary, not JSON. `prepare()` copies it to the isolated workspace as exactly
`ticket.pdf`; the prompt names that file. The eval-only executable `npx` shim
accepts only the documented AnyDoc invocation and replays
`fixtures/pdf/anydoc.md`. It performs no network request and rejects unexpected
arguments.

The agent must follow this trajectory:

1. load/use the skill;
2. run `npx -y @firecrawl/anydoc ticket.pdf -o <private-markdown>` exactly once;
3. extract flight facts from usable Markdown;
4. write private itinerary JSON;
5. call the production CLI exactly once with `--json build --input <json>`;
6. return the exact `MEDIA:` value and stop.

`--url`, `--url-file`, browser/web, OCR, Tesseract, and PyMuPDF fallbacks after
usable AnyDoc are forbidden. Markdown must not be passed directly to the CLI.
When unambiguous, the actual `--input` JSON is retained as run evidence for
diagnostics, never used as the oracle.

Expected semantic output is two VEVENTs:

- `SU9011`, SVO → SVX, 03.10.2037 09:15–13:45 local, Boeing 737-800;
  `DTSTART:20371003T061500Z`, `DTEND:20371003T084500Z`;
- `SU9012`, SVX → SVO, 06.10.2037 18:10–18:45 local, Airbus A320;
  `DTSTART:20371006T131000Z`, `DTEND:20371006T154500Z`.

The catalog confirmation is SVO=`Europe/Moscow`, SVX=`Asia/Yekaterinburg`.
The final answer must be only the exact `MEDIA:` success protocol and must not
contain passenger, PNR, ticket, raw PDF text, or intermediate JSON contents.

The PDF oracle checks flight numbers in retained intermediate itinerary evidence
and checks only renderer-observable route/time/aircraft fields in the final ICS.

Before any selected model matrix, the runner creates deterministic known-good
reference output through the production CLI and applies the Outcome evaluator.
If that reference fails, the matrix is not launched. Saved batches can be
reevaluated with `run_eval.py --reevaluate`; reevaluation writes derived scores
and a report outside the source batch and executes zero agents.

## Common report contract

The common `report.md` has one configured human timezone, `DD.MM.YYYY` dates,
human durations, separate Outcome/Trajectory/Privacy results, and no raw
microsecond timestamps. Multi-scenario model tables include an explicit
`Scenario` column. Failed runs remain visible. URL-integrity summaries include
only URL scenarios; PDF uses `URL = —` and reports source/AnyDoc facts.
