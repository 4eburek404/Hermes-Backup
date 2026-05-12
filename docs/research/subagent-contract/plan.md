# Plan: strict subagent contract

## Goal

Investigate recurring Hermes `delegate_task` / subagent failures where the parent launches children but does not receive/use their information, then establish a durable strict parent-child contract.

## Scope

- Search session history for prior subagent/delegation incidents and decisions.
- Use web/source acquisition with artifacts.
- Check current Hermes skill/source layer for drift.
- Patch the governing skill if it is missing the contract.
- Verify the patch.

## Gates

- Pre-flight: load relevant skills (`subagent-driven-development`, `web-content-acquisition`, `hermes-agent`, `skill-audit-and-improvement`, `hermes-agent-skill-authoring`) and check source path/branch/status.
- Evidence: keep extracted web docs under `extracts/` and query under `queries/`.
- Revision: patch `subagent-driven-development` only if current source lacks strict contract.
- Verification: `git diff --check` and `audit_skill.py --skill subagent-driven-development --json`.

## Non-goals

- Do not change Hermes core delegation code in this pass.
- Do not edit protected context files (`MEMORY.md`, `USER.md`, `SOUL.md`).
- Do not delegate the web/history search itself; prior preference says direct search is preferred for search/news/source tasks.
