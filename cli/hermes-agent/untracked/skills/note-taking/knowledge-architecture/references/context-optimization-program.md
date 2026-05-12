# Context Optimization Program Structure

> Session-specific detail for the `knowledge-architecture` skill. Documents the
> structure and lifecycle of the context-input-overhead optimization program
> running in the `context-input-baseline` branch.

## Program overview

A staged, evidence-driven program to reduce Hermes provider input-context
overhead. All work follows a strict pattern: audit → design → validate →
implement, with each stage producing a committed doc before any code changes.

## Doc lifecycle pattern

1. **Audit doc** — read-only evidence gathering (e.g. `context-tool-output-overhead-audit.md`)
2. **Experiment plan** — what to change, how to measure, rollback (e.g. `context-cronjob-toolset-experiment-plan.md`)
3. **Change + validation doc** — post-change measurement confirming expected effect (e.g. `context-cronjob-removal-validation.md`)
4. **Schema/design doc** — planning-only schema for future implementation (e.g. `context-tool-output-summary-schema.md`)
5. **Implementation** — code change behind config flag, with before/after analyzer reports

## Current program inventory

| Doc | Type | Status |
|---|---|---|
| `context-optimization-plan.md` | Master plan | Active |
| `context-tool-output-overhead-audit.md` | Audit | Complete |
| `context-toolset-cronjob-audit.md` | Audit | Complete |
| `context-cronjob-toolset-experiment-plan.md` | Experiment plan | Complete (commit 72e9f41c) |
| `context-cronjob-removal-validation.md` | Validation | Complete (commit 5b85d59e) |
| `context-tool-output-summary-schema.md` | Schema design | Complete (commit eee66c6e) |
| `context-tool-output-artifact-pointer.md` | Schema design | Complete (commit 1ad95362) |

## Completed optimizations

- **cronjob removal from _HERMES_CORE_TOOLS:** −1,652 tokens/session confirmed.
  Standalone `"cronjob"` toolset remains available for opt-in.

## Active workstreams

- **Tool output summarization** — schema designed (Task 5G-1), next: artifact pointer format (Task 5G-2)
- **Cronjob opt-in policy** — decision pending per platform (Task 5F)

## Branch and commit tracking

- Branch: `context-input-baseline`
- Base commit for current work: `5b85d59e` (cronjob removed from core)
- All docs under `docs/` in this branch; analyzer at `scripts/analyze_context_overhead.py`
- Baseline reports: `/tmp/hermes_context_baseline.md` + `.json`

## Navigation for future sessions

To continue this program:

1. `read_file docs/context-optimization-plan.md` — master plan with all stages
2. `read_file docs/context-tool-output-summary-schema.md` — latest schema design
3. Check `docs/` for any new docs created since this reference was written
4. Verify branch: `git log -3 --oneline` and `git status --short --branch`
