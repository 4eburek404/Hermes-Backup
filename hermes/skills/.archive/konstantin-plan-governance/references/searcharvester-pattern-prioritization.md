# Searcharvester pattern prioritization example

Use this reference when reviewing a Konstantin plan that imports patterns from another system and asks for "usefulness here and now" rather than a generic architecture assessment.

## Context

Plan reviewed: `/home/konstantin/docs/plans/searcharvester-patterns.md`.

Source patterns came from Searcharvester:

- date/current-context injection into delegated work;
- filesystem/API grounding via artifacts such as `extracts/`;
- two-round `researcher → critic/fact-checker` verification;
- progress artifacts such as `plan.md → notes.md → report.md`;
- session-file recovery, `cwd=job_dir`, flat event schema, ACP middleware.

Relevant current Hermes consumer: `flight-search-routing`, where mistakes can be materially harmful: wrong airport, unsafe connection, stale/cached price, self-transfer/visa/baggage risk, API returning a different airport than queried.

## Ranking pattern

Prefer this reasoning shape:

- **P0** — cheap, high-frequency guardrails that prevent common failures immediately.
  - Date/current-context injection.
  - Grounding through filesystem/API side effects.
  - Minimal verifier-gate for `flight-search-routing`.
- **P1** — valuable but conditional escalation / observability.
  - Two-round verification only for high-stakes tasks.
  - Progress artifacts for multi-step/delegate workflows.
- **P2** — implement when touching the relevant skill or orchestration surface.
  - Methodology/scripts split, session-file recovery, `cwd=job_dir`.
- **P3** — defer until there is a real UI/orchestration project.
  - Flat event schema, custom ACP Client middleware.

## P1 usefulness conclusion

P1 is useful, but should not become the default path for every request.

### P1.1 two-round verification

High value when the cost of being wrong is high:

- money/purchase/non-refundable ticket;
- dates, deadlines, transfers, minimum connection time;
- visa/border/self-transfer/baggage risk;
- explicit user request to verify carefully;
- conflicting sources or cached/incomplete API results.

Do not use by default for simple lookups: it adds latency, token cost, and orchestration complexity. Blind critics are not real verification; round 2 must receive `researcher_summary` and `facts_to_verify`.

### P1.2 progress artifacts

Often closer to `P0.5` than full P1 because it is cheaper and improves auditability/recovery:

- useful for multi-step/delegate workflows;
- makes progress checkable through files instead of reasoning summaries;
- helps after truncated/empty delegate output or cross-session handoff;
- too much overhead for single-shot answers.

Practical recommendation: implement progress artifacts before full two-round verification where the workflow is already multi-step. Keep full two-round verification as a high-stakes escalation gate.

## Communication pattern

When Konstantin asks "analyze usefulness" or "show conclusions":

1. Start with the verdict.
2. Separate checked facts from interpretation.
3. Compare the item against cheaper alternatives, not just against doing nothing.
4. State trigger conditions / kill criteria.
5. Do not mutate the plan unless the user explicitly asks to update it.
