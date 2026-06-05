# Output Bundle Design

Use this when maintaining or extending `scripts/flight_calendar_ics.py` output handling.

## Boundary

The normal agent path uses the CLI-owned bundle command:

```bash
python scripts/flight_calendar_ics.py --json build <route> ...
```

The CLI, not the agent shell wrapper, owns these invariants:

- private run directory creation (`0700`);
- canonical artifact names;
- `itinerary.json` write (`0600`);
- `flights.ics` write (`0600`);
- final `envelope.json` persistence (`0600`);
- structural bundle verification before `ok=true`.

Canonical bundle layout:

```text
<run-dir>/
  itinerary.json   0600
  flights.ics      0600
  envelope.json    0600
```

`--output-dir` is an override for tests, reproducible diagnostics, cron artifacts, or explicit user-selected destinations. It is not required on the normal path.

## Design rules

1. **Mandatory invariant → CLI default.** Agents should not have to choose repeated filenames or wire `--output-json`/`--output-ics` for happy-path calendar generation.
2. **Risky shell plumbing → CLI responsibility.** Avoid requiring `tee`, stdout redirects, `mktemp`, `chmod`, or manual `umask` for output artifacts.
3. **Success means deliverable ICS.** `build` must not return `ok=true` unless `data.ics_path` points to a verified `flights.ics`.
4. **Verification is part of build.** `data.verification.ok=true` means file modes, `VEVENT` count, UTC `DTSTART`/`DTEND`, and placeholder checks passed.
5. **Private inputs prefer files over argv.** For booking URLs and credential-bearing links, prefer `--url-file` over raw `--url` when practical.
6. **Compatibility commands stay tested.** Direct `make`/carrier commands with explicit output flags remain for transition and diagnostics, but `doctor.data.agent_contract.dispatch_matrix` should advertise `build` templates.

## Maintenance checklist

- Add or update RED tests before changing bundle behavior.
- Validate real `doctor` and `build` envelopes against `schemas/cli-envelope.v1.schema.json`.
- Keep `SKILL.md` Golden Path aligned with `doctor.data.agent_contract`.
- Preserve the privacy boundary: stdout/stderr/process data may include safe paths and route/time summaries, not booking credentials or passenger/ticket data.
