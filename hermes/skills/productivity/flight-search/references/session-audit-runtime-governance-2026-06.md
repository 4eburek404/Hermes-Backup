# Session audit note: runtime governance and CLI bypass surfaces (2026-06)

Use this as a condensed checklist when maintaining or auditing `flight-search`. It captures durable lessons from a read-only audit session; do not treat it as a task log.

## Durable findings

- **Check runtime/source provenance from the canonical source repo, not only from the installed runtime copy.** A maintenance check launched from runtime can collapse source and runtime into the same path and miss drift. Prefer comparing the canonical git source tree with the installed skill runtime copy.
- **Treat runtime-only audit/proposal files as a smell.** The skill itself says durable rules should be distilled into existing references/tests rather than left as standalone one-session audit files. If an audit note survives, either merge it into a durable reference/test or explicitly mark it as temporary.
- **Avoid active examples for commands that are not implemented.** If a reference mentions an unimplemented command such as a future `route direct-window`, do not leave it in a copy-pasteable command block. Provide only implemented alternatives and move future commands to backlog prose.
- **Golden path should dominate the broad CLI surface.** Provider probes, raw route internals, debug flags, and cache-control knobs are useful for diagnosis, but user-facing answers should flow through `route live-assemble`, `data.agent_report`, and `user_answer.rendered_text` when available.
- **Read-only searches need explicit cache discipline.** Default live search may refresh static catalogs or write live-search cache. For a true read-only/provenance audit, use explicit no-refresh/no-cache flags where the command supports them.
- **Do not infer round-trip ticketing guarantees from directional/date-price evidence.** Provider surfaces differ: date-price or directional evidence is not enough to claim single PNR, through baggage, or protected connection.
- **Strengthen semantic contract tests around catalog answers.** JSON Schema validates structure, but tests should also cover empty catalog, numbering gaps, zero-based numbering, duplicate numbers, item limits, missing detail status, and incomplete round-trip directions.
- **Keep airport policy as a single-source-of-truth.** If airport/city expansion policy appears in several references, reconcile it back to the provider-aware airport priority reference and keep other docs as pointers.

## Maintenance checklist

1. Run provenance checks from canonical source and compare against installed runtime.
2. Inspect `SKILL.md` and references for stale audit/proposal files or copy-pasteable future commands.
3. Confirm the documented golden path still routes through `route live-assemble` and final answer contracts.
4. Verify read-only examples use explicit cache/no-refresh controls when appropriate.
5. Add/extend tests before relaxing contract semantics or adding new answer modes.
