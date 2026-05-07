# Plan: universal flight routing skill

## Goal
Refactor the latest flight-search distillation from a route-specific London/U6 lesson into a reusable, universal routing skill pattern: multi-objective/frontier ranking that preserves materially different options before price-based truncation.

## Context
Konstantin corrected the previous update: it was too attached to the SVX→London/U6/TK case. The durable skill should generalize across routes and use the case only as an example/reference.

Relevant durable surfaces:
- `~/.hermes/skills/productivity/flight-search-routing/SKILL.md`
- `~/.hermes/skills/productivity/flight-search-routing/references/*.md`
- `/home/konstantin/code/clis/flights/` CLI docs/help/tests if current wording is too case-specific
- holographic `fact_store` if the stored preference is too narrow

## Non-goals
- Do not re-run live airfare searches.
- Do not change route search algorithms beyond wording/defaults/tests needed for universal behavior.
- Do not store raw flight prices/logs as durable knowledge.
- Do not touch secrets or credentials.

## Steps
- [x] Identify overly route-specific wording in skill, references, CLI help, and tests.
- [x] Rewrite core skill rule as a universal multi-objective/frontier ranking protocol.
- [x] Keep London/U6/TK as an example/reference, not the main rule.
- [x] Generalize CLI help/test naming if needed.
- [x] Update fact_store preference from specific case to general expectation if needed.
- [x] Verify skill loads, CLI tests pass, and final wording no longer frames the rule as London-only.

## Verification
- `skill_view(flight-search-routing)` shows version `2.0.3` with universal multi-objective/frontier protocol in the core skill.
- London-specific example is in `references/business-trip-london-airport-ranking.md` and explicitly labeled as a route-specific application/regression example.
- `flights route assemble --help` says `--limit-per-pair 10` is for complex routes/frontier-relevant options, not only London/business.
- `python -m pytest -q` in `/home/konstantin/code/clis/flights`: `30 passed, 4 subtests passed in 1.98s`.
- `flights --version`: `flights 0.7.2`.

## Risks / pitfalls
- Over-generalizing until the skill becomes vague and non-actionable. Mitigated by adding concrete axes and trade-off buckets.
- Losing the concrete example that prevents the same London mistake from recurring. Mitigated by keeping London as a regression/example reference.
- Editing CLI behavior unnecessarily instead of only generalizing wording. Behavior stayed the same as 0.7.1; 0.7.2 generalizes help/test wording.

## Status
Current status: done

## Notes
Outcome: `flight-search-routing` now teaches a universal rule: preserve route-relevant frontier representatives across price, schedule, duration, connection safety, airport/carrier quality, visa exposure, ticketing and baggage/self-transfer risk. Specific routes such as SVX→London are examples/regression cases, not the core rule.
