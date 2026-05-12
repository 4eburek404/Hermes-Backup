# Subagent runtime deep analysis

Current status: completed
Started: 2026-05-07 22:21:37 CEST +0200
Completed: 2026-05-07
Repo: /home/konstantin/.hermes/hermes-agent
Branch/HEAD at start: skills-improvements @ c829460ab2f0
Primary findings artifact: /home/konstantin/docs/research/subagent-runtime-deep-analysis/final_findings.md

## Goal

Find why `delegate_task` / subagents sometimes disappear, return insufficient information, or cause the parent to redo work; identify better configuration and code-level guardrails around timeouts, max iterations, concurrency, spawn depth, model/provider selection, and result contracts.

## Scope

- Inspect local Hermes source for delegation implementation and config defaults.
- Search git history/branches for commits touching delegation/subagent behavior.
- Fetch public docs/source where available for current external reference.
- Produce concrete recommendations split into:
  - safe config changes;
  - skill/process changes;
  - code changes needing patch/PR;
  - hypotheses needing repro.

## Evidence artifacts

- notes.md: command/web findings and source excerpts.
- report.md: final synthesis and recommendations.

## Verification plan

- Every config recommendation must cite actual config key/default/source.
- Every code recommendation must cite file/function/commit evidence.
- Any web claim must cite URL or fetched artifact.
- Do not accept subagent review output unless path and evidence are verified by parent.
