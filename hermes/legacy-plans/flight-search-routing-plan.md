# Plan: sync `flight-search-routing` with the existing `flights` CLI

## Goal
Bring the `flight-search-routing` skill, companion references, README examples, and tests into alignment with the actual local `flights` CLI contract. The plan replaces the earlier speculative roadmap with an evidence-based execution plan.

## Context / evidence
Checked on 2026-05-04:

- Skill path: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/SKILL.md`, version `2.0.0`.
- CLI entrypoint: `/home/konstantin/.local/bin/flights`.
- CLI source path: `/home/konstantin/code/clis/flights/`.
- CLI project version: `0.7.0` in `/home/konstantin/code/clis/flights/pyproject.toml`.
- `route plan` is offline/dry planning; it does not call Travelpayouts.
- JSON mode is a global CLI flag: `flights --json route plan ...`, not `flights route plan ... --json`.
- `origin` and `destination` are positional args, not `--origin` / `--destination` flags.
- `--hub` is repeatable: `--hub IST --hub DXB`, not comma-list `--hub IST,DXB`.
- Existing tests were present and initially passed: `26 passed`; after this execution pass they pass as `28 passed`.
- No CI workflow files were found in the local CLI tree.
- At audit time, `references/layover_rules.md` was missing; this pass added it as a human-readable mirror of CLI rules (`MULTI_AIRPORT_GROUPS`, `connection_rule`).

Relevant prior-session findings:

- The original plan was created after a broad improvement analysis, but it mixed desired future features with already-implemented CLI behavior.
- Previous models correctly identified the need for an audit step, but one analysis incorrectly assumed tests were absent.
- Past route-analysis sessions established practical rules: airport mismatch should be rejected/flagged; self-transfer minimums need explicit documentation; LON and MOW city-code behavior requires caution.

## Non-goals for this execution pass

- Do not implement batch mode in the first pass.
- Do not add a new live refresh/cache-age feature unless the current CLI already exposes enough data.
- Do not tag releases or assume a `hermes-skills` repository exists.
- Do not duplicate full `--help` output in SKILL.md; CLI syntax source of truth remains argparse/help.
- Do not introduce third-party dependencies without first checking and deciding intentionally.

## Corrected execution scope

### Phase 0 — Contract audit / lock current facts
- [x] Check `flights route plan --help`.
- [x] Check `flights request search --help`.
- [x] Run a real JSON `route plan` sample.
- [x] Check test suite existence and status.
- [x] Check local CLI tree for CI/CHANGELOG presence.

### Phase 1 — Skill documentation sync
- [x] Update `SKILL.md` CLI examples to use global `--json` placement.
- [x] Add or tighten a `route plan` parameter section based on actual `argparse` behavior:
  - positional: `origin`, `destination`
  - required: `--depart-date`
  - optional: `--return-date`, repeatable `--hub`, repeatable `--origin-airport`, repeatable `--destination-airport`, `--currency`, `--ticketing`, `--profile`, `--min-same-airport-min`, `--min-cross-airport-min`, `--max-airports-per-city`, `--direct-only`
- [x] Split output contracts by command instead of one generic schema:
  - `route plan`: planning envelope, segment requests, warnings, metrics, itinerary families.
  - `request search`: dry/live request and Travelpayouts caveat.
  - `route assemble/rank`: prices, ranked candidates, rejected pairs, carrier policy.
- [x] Update Verification Checklist so `cache_age_minutes` is not required for offline `route plan`.

### Phase 2 — Layover / airport rules reference
- [x] Add `references/layover_rules.md` as a human-readable mirror of current CLI/skill rules.
- [x] Document source status explicitly:
  - checked facts from current CLI/skill code;
  - practical heuristics for separate tickets;
  - not official IATA MCT unless a cited source is added later.
- [x] Link the new reference from `SKILL.md`.
- [x] Avoid creating two silent sources of truth: the reference is labeled as a mirror and tests now lock key CLI behavior; direct doc-vs-code parsing was skipped to keep CLI tests portable.

### Phase 3 — CLI README and tests
- [x] Fix README examples if any still imply wrong `--json`, `--hub`, or positional syntax; README was inspected and already used canonical syntax for route planning.
- [x] Extend existing tests rather than creating a new `tests/` directory.
- [x] Add lightweight tests for:
  - global `--json` route-plan JSON envelope;
  - repeatable `--hub` behavior;
  - `normalize_global_json` behavior: trailing `--json` is accepted but canonical examples still use global placement;
  - key route-plan contract guard: no `cache_age_minutes` in offline `route plan`.
- [x] CI not added: local CLI tree is not a git repo, so adding workflow/release assumptions would be invented state.

### Phase 4 — Optional later product features
These require a separate decision/spec before implementation:

- Batch mode (`route batch --input file.yaml` or equivalent).
- Markdown report generation.
- Mermaid/visualization output.
- Cache-age reporting / refresh semantics.
- Release tagging / changelog policy.

## Verification

Before reporting done:

- [x] Re-read modified `SKILL.md` and the new/modified references.
- [x] Run `python -m pytest -q /home/konstantin/code/clis/flights/tests` from `/home/konstantin/code/clis/flights`.
- [x] Run at least one smoke command:
  ```bash
  /home/konstantin/.local/bin/flights --json route plan SVX LON --depart-date 2026-07-20 --hub IST --hub DXB
  ```
- [x] Confirm JSON examples in docs use `flights --json ...` syntax where JSON mode is shown.
- [x] Confirm no secrets/tokens/raw credentials were written.

## Risks / pitfalls

- **Docs/code drift:** `layover_rules.md` can become stale if code changes; mitigate with tests or explicit “human-readable mirror” wording.
- **Wrong command schema:** `route plan` is not a pricing command; do not add `total_price_*` to its schema.
- **Scope creep:** batch mode and cache refresh are product features, not documentation sync.
- **Version confusion:** skill version `2.0.0` and CLI version `0.7.0` are different artifacts.
- **Repository assumption:** `/home/konstantin/code/clis/flights/` may not itself be a git repo; verify before any branch/tag/release claims.

## Status
Current status: done

## Notes
- Plan rewritten and executed in-place at the user-requested Hermes-local path.
- Updated `SKILL.md`, added `references/layover_rules.md`, and patched `references/cli-reference.md`.
- Added CLI tests for route-plan JSON envelope, repeatable hubs, and `--json` normalization.
- Verification passed: `pytest` 28/28, `make test` 28/28, route-plan smoke command returned `ok=true`.