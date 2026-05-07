# Skill evolution / self-improvement experiment lessons

Use this reference when designing or evaluating Hermes skill/prompt/self-improvement workflows.

## Session lesson

A sandbox test of a standalone skill-evolution repo showed that a "rewrite SKILL.md with an optimizer" approach can pass dry-runs and unit tests while still producing no evolved artifact. Treat that as a warning about evaluating self-improvement systems by outputs and traces, not by repository claims.

## Practical requirements for future evolution experiments

- Never mutate a production skill directly. Copy the target skill into a sandbox tree and rename it to avoid collisions.
- Define the artifact contract before running: every run must produce at least a patch/diff, scorecard, rationale, and eval log. If no artifact exists, do not call the experiment successful.
- Run a dry-run and dependency/import checks before any expensive optimizer run.
- Do not require hidden standalone provider credentials unless the experiment explicitly declares them. Check key presence without printing secrets.
- Fitness must be deterministic first: structure validation, required/forbidden behaviors, trace/tool-use checks, output existence, and regression cases. LLM judging can be secondary, not the sole gate.
- Validate the exact object passed to validators. If a loader strips YAML frontmatter, do not run a validator that expects a full `SKILL.md` against body-only text.
- Version/API drift is common in optimizer stacks. Inspect installed optimizer signatures before assuming documented parameters work.

## Better substrate than raw prompt rewriting

Prefer **behavioral policy evolution** over wholesale prompt rewriting:

```text
real tasks + traces
  -> small behavioral genomes/policies
  -> sandboxed agent runs
  -> deterministic trace/side-effect/verification scoring
  -> manual promotion into skills/docs/SOUL/routing rules
```

Candidate genes:

- routing order: skills first, fact_store first, session_search first, docs first;
- verification policy: require artifact before "done", read back after writes, checksum before/after;
- risk policy: sandbox before mutation, diff before patch, no production write without scope;
- communication policy: status first, evidence before interpretation, commands as copyable blocks;
- memory policy: built-in memory vs fact_store vs docs vs skills.

Score traces, not prose aesthetics. A variant is better only if it reduces concrete failures: missed skill load, stale fact use, unsupported success claims, skipped verification, unsafe side effects, or inability to produce the promised artifact.

## Terminology/autocorrect pitfall

When the user has an obvious typo or iPhone autocorrect artifact, normalize to the likely intended term and proceed. Do not build a metaphor or technical taxonomy around the mistaken word. A brief clarification like "читаю это как 'промптов'" is enough when needed.
