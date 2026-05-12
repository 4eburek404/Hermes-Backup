# Notes: strict subagent contract investigation

## Session-history evidence

- `2026-05-05 searcharvester-patterns`: identified subagent/delegate reliability issues: stale dates, hallucinated URLs, missing grounding artifacts, absent verifier handoff. Proposed P0/P1 guardrails: current-context line, artifacts, progress files, two-round verifier with `researcher_summary` + `facts_to_verify`.
- `2026-05-05 P1 analysis`: found explicit preference/rule: do not delegate search/news; parent should search directly with tools and artifacts. `delegate_task` is mainly for coding/reasoning work.
- `2026-04-29 distillation`: decided direct HTTP workers are better than `delegate_task` for single-shot extraction workers; `delegate_task` was appropriate for research, not mechanical worker extraction.

## Fact-store evidence used

- Fact 116: Konstantin prefers news/search work to be done directly by the main agent, not delegated to subagents.
- Fact 132: existing guardrail pointer says delegated contexts need current-date/current-context preamble, artifacts, progress files, and verifier handoff.

## Web/source evidence

- `extracts/hermes_delegation.md`: Hermes docs say child agents have isolated context, only final summary enters parent context, subagents know nothing except `goal` + `context`, some tools are blocked, and `delegate_task` is synchronous/not durable.
- `extracts/microsoft_orchestrator_subagent.md`: Microsoft pattern says orchestrator owns high-level user conversation/decisions, subagents execute specialized work; not suited when consistent success rate, tight time, strong hierarchical dependencies, or long response windows make failures costly.

## Source-layer check

- Source model: active skills source is `/home/konstantin/.hermes/hermes-agent/skills/`; `~/.hermes/skills` is runtime state only.
- Current branch before patch: `skills-improvements`, HEAD `c829460ab2f0`.
- Current `subagent-driven-development` source was v1.1.0 and lacked `CURRENT CONTEXT`, strict return schema, progress artifacts, stale-training-memory guardrail, and empty-result recovery.
- Existing unrelated dirty files were present before this patch: `hermes-agent-skill-authoring/SKILL.md`, `skill-audit-and-improvement/SKILL.md`, and `skill-audit-and-improvement/references/audit-protocol-contract.md`.

## Implemented patch

- Patched `skills/software-development/subagent-driven-development/SKILL.md` to v1.2.0.
- Added strict parent ↔ subagent contract:
  - parent pre-flight gate;
  - required `CURRENT CONTEXT` line;
  - exact `SUBAGENT_RESULT` schema;
  - parent acceptance gate;
  - recovery path for empty/interrupted/timed-out/truncated/unverifiable child result;
  - progress artifacts `plan.md → notes.md → report.md`;
  - high-stakes `researcher_summary` + `facts_to_verify` verifier escalation;
  - explicit ban on silent parent fallback.

## Working conclusion

Root cause is not only model behavior. It is a contract/layer problem: subagents are isolated, only final summaries enter parent context, and the active source skill lacked a mandatory return/evidence/acceptance contract despite earlier plans documenting the need. Without that contract, the parent can treat empty/vague child results as context loss and continue manually without provenance.
