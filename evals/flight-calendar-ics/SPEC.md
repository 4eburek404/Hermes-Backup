# flight-calendar-ics — Minimal Agent Eval Specification

## Purpose

Provide a fast first agent-level evaluation of the current
`flight-calendar-ics` skill.

This eval deliberately covers one normal successful booking-URL workflow only.
It is not a complete behavioral suite. Additional scenarios are added only when
there is a concrete defect, behavior change, or comparison need.

## Evaluated skill

The candidate is the complete skill directory from Git ref:

`update/flight-calendar-ics`

The common eval harness resolves the ref to an exact commit and materializes the
skill without merging or checking out that branch.

## Evaluation matrix

One scenario is executed once on each of three different model providers:

- `gpt-5.6-luna` / `openai-codex`
- `deepseek-v4-pro` / `deepseek`
- `glm-5.1` / `zai`

Therefore the first batch contains exactly 3 agent runs.

The scenario, prompt, recorded external response, evaluated skill source, and
evaluation rules are identical across the three runs.

## M1 — supported booking URL succeeds

### Given

- the user supplies one supported Aeroflot manage-booking URL;
- the URL contains synthetic booking credentials;
- external carrier HTTP is replaced by one checked-in recorded response;
- no live airline request is allowed;
- the recorded response describes two flight segments.

### When

Hermes executes the task with `flight-calendar-ics`.

### Then — Outcome

- the task completes successfully;
- one generated `.ics` artifact is retained as run evidence;
- the artifact is parseable as iCalendar;
- it contains exactly 2 `VEVENT` components;
- the events contain the expected fixture flights:
  - `SU 9001`, SVX → SVO, 2037-09-23 13:30 → 13:50 local;
  - `SU 9002`, SVO → SVX, 2037-09-25 15:25 → 19:50 local;
- the final agent answer returns the generated `.ics` artifact.

Outcome checks the resulting artifact, not the internal carrier parser
implementation.

### Then — Trajectory

The agent must:

1. use the booking-URL workflow;
2. invoke the bundled `flight_calendar_ics.py` CLI with
   `--json build --url <booking-url>`;
3. invoke that build CLI exactly once;
4. stop after the successful CLI result.

The run fails Trajectory if the agent:

- opens the booking URL with browser/web tooling;
- creates a temporary URL file;
- uses `--url-file` or `--url-stdin`;
- uses `mktemp`, `echo`, or `printf` to move the URL through another input;
- independently rewrites or parses the booking URL instead of giving it to the
  CLI;
- invokes the build CLI again after success;
- performs additional tool actions after the successful build instead of
  returning the artifact.

Skill loading itself is allowed and is not counted as an extra booking action.

### Then — Privacy

The user-visible final answer must not contain:

- the booking URL;
- the synthetic PNR;
- the synthetic booking key;
- passenger names;
- ticket numbers;
- raw `.ics` contents.

The booking URL is allowed in the terminal tool input because the skill must pass
it to the CLI. Its presence there is not a Privacy failure.

The retained `.ics` artifact may contain booking data by design and is not
scanned as a forbidden user-visible channel.

### Then — Efficiency

Record factual metrics only:

- tool-call count;
- CLI build-call count;
- agent turns/events when available;
- token/usage metrics when available;
- duration.

No efficiency PASS/FAIL threshold is defined in this first eval.

## Recorded fixture rule

The external carrier response is fixed test data and is not fetched live during
agent evaluation.

The evaluator oracle is separate from the prompt and is not exposed to the
agent.

## Explicitly out of scope for the first eval

Not evaluated yet:

- `route_unknown`;
- `route_input_insufficient`;
- PDF input;
- OCR fallback;
- carrier-specific failure recovery;
- separate Aeroflot/Ural/Utair/S7/Red Wings coverage;
- baseline-versus-candidate comparison;
- repeated stochastic runs.

These can be added later without changing the common harness.
