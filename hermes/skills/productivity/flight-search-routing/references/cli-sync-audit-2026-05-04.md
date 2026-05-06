# CLI/skill sync audit — 2026-05-04

Session-specific evidence for maintaining the `flight-search-routing` skill against the local `flights` CLI.

## Scope

The task started from a plan at `/home/konstantin/.hermes/plans/flight-search-routing-plan.md` that mixed useful documentation-sync work with speculative product features. The safe scope was narrowed to synchronizing docs/references/tests with the existing CLI contract.

## Verified local state

- CLI entrypoint: `/home/konstantin/.local/bin/flights`
- CLI source path: `/home/konstantin/code/clis/flights/`
- CLI project version: `0.7.0`
- Skill path: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/SKILL.md`
- Skill version at audit time: `2.0.0`
- `/home/konstantin/code/clis/flights` was not a git repository:
  ```text
  fatal: not a git repository (or any of the parent directories): .git
  ```
- No local CI workflow files or `CHANGELOG*` were found in the CLI tree.

## Current `route plan` contract

Canonical form:

```bash
flights --json route plan SVX LON --depart-date 2026-07-20 --hub IST --hub DXB
```

Contract notes:

- `--json` is a global flag; trailing `--json` is normalized but should not be the documented canonical form.
- `origin` and `destination` are positional args, not `--origin` / `--destination`.
- `--hub` is repeatable, not comma-list syntax.
- `--depart-date` is required.
- `route plan` is offline/dry planning. It returns segment requests, warnings, metrics, and itinerary families; it does not return live prices or `cache_age_minutes`.

Smoke summary from the canonical command:

```text
True route plan ['IST', 'DXB'] 10 False
```

Meaning: `ok=true`, command `route plan`, hubs `['IST', 'DXB']`, 10 segment requests, no `cache_age_minutes` key.

## Changes made in that pass

- Rewrote `/home/konstantin/.hermes/plans/flight-search-routing-plan.md` as an evidence-based sync plan and marked it `Current status: done` after execution.
- Updated `SKILL.md` quick reference, route-plan contract, verification checklist, and loading discipline.
- Created `references/layover_rules.md` as a human-readable mirror of current CLI airport/connection rules, not as an official IATA MCT source.
- Patched `references/cli-reference.md` to prefer `flights --json ...` and repeatable `--hub` examples.
- Added offline tests in `/home/konstantin/code/clis/flights/tests/test_offline.py` for route-plan JSON envelope/repeatable hubs and trailing-`--json` normalization.

## Verification results

- Initial tests before changes: `26 passed`.
- After changes: `28 passed`.
- `make test`: passed, 28/28.
- Secret scan over modified files: no secrets/tokens/credentials detected.

## Maintenance lessons

1. Treat plans and previous model analyses as hypotheses until checked against live CLI help, source, and tests.
2. Do not add batch mode, cache refresh/cache-age semantics, release notes, or CI in a documentation-sync pass unless the user explicitly expands scope.
3. If the CLI is not a git repo locally, avoid branch/release/CI claims; report the exact repository-state evidence.
4. For route planning docs, separate offline planning (`route plan`) from live/request/pricing stages (`request search`, `route assemble`, `route rank`).
