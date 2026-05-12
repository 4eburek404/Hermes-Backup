# Flight-search Coverage / Route Graph / Frontier Plan

> **For Hermes:** Use `subagent-driven-development` if implementing this plan task-by-task. Keep changes small, test-first, and offline by default.

**Status:** planned

**Created:** 2026-05-09

**Goal:** Fix the `flight-search` CLI design gap where `route live-assemble` relies on static route families and scalar ranking, so it can hide or mis-rank decision-critical controls.

**Scope:** User-approved items 1–7 only:
1. Coverage mode / targeted coverage controls.
2. Route graph instead of fixed route families.
3. Domestic-RU strategy.
4. Dubai airport scope = DXB primary + DWC secondary; SHJ out of default.
5. Ranking frontier.
6. Provider aggregate offers as explicitly labeled candidates.
7. Coverage diagnostics in `agent_report`.

**Out of scope for this plan:** cache/rate-limit implementation. Because expanded live probes can multiply upstream calls, this plan must keep new coverage behavior testable offline and avoid enabling unbounded automatic live fan-out by default until a separate cache/rate-limit phase is approved.

**Primary repo:** `/home/konstantin/.hermes/hermes-agent`

**CLI root:** `/home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli`

**Primary files likely touched:**
- `skills/productivity/flight-search/cli/flights_cli/orchestrators/route_plan.py`
- `skills/productivity/flight-search/cli/flights_cli/orchestrators/kb_assemble.py`
- `skills/productivity/flight-search/cli/flights_cli/services/assembly.py`
- `skills/productivity/flight-search/cli/flights_cli/services/agent_report.py`
- `skills/productivity/flight-search/cli/flights_cli/services/ranking.py`
- `skills/productivity/flight-search/cli/flights_cli/domain/airports.py`
- `skills/productivity/flight-search/cli/flights_cli/domain/hubs.py`
- `skills/productivity/flight-search/cli/flights_cli/contracts/agent_report.v1.schema.json` if present / equivalent contract file if schema location differs
- `skills/productivity/flight-search/SKILL.md`
- `skills/productivity/flight-search/references/dubai-city-airports.md`
- new or updated reference: `skills/productivity/flight-search/references/coverage-controls.md`

**Primary tests likely touched/created:**
- `skills/productivity/flight-search/cli/tests/test_route_workflows.py`
- `skills/productivity/flight-search/cli/tests/test_agent_report_contract.py`
- `skills/productivity/flight-search/cli/tests/test_agent_report_p1_moscow_control.py`
- `skills/productivity/flight-search/cli/tests/test_agent_report_p0_completeness.py`
- create `skills/productivity/flight-search/cli/tests/test_route_graph.py`
- create `skills/productivity/flight-search/cli/tests/test_coverage_controls.py`
- create `skills/productivity/flight-search/cli/tests/test_domestic_routing_strategy.py`
- create `skills/productivity/flight-search/cli/tests/test_dubai_airport_scope.py`
- create `skills/productivity/flight-search/cli/tests/test_ranking_frontier.py`
- create `skills/productivity/flight-search/cli/tests/test_provider_aggregate_candidates.py`
- create `skills/productivity/flight-search/cli/tests/test_coverage_diagnostics.py`

---

## Current evidence / root cause

Verified working assumptions from the prior analysis:

- `route live-assemble` is not proof that a direct flight, carrier route, or best practical option does not exist.
- Current `ru-priority` behavior is too static: direct, IST, SVO→IST, DXB fallback.
- SVO is not modeled as an independent gateway to the final destination; it is often only a step toward IST.
- Gulf/Middle East routes need their own regional logic; they are not adequately covered by the existing Asia/Oceania profile.
- Domestic Russian routes can be polluted by international hub routes through IST/DXB.
- Ranking mixes practical risk and preferred-carrier bias; carrier preference can promote worse routes.
- Aggregate controls exist but are closer to appendix/control data than first-class frontier candidates.
- Dubai city scope must be **DXB + DWC**, not SHJ by default.

---

## Implementation principles

1. **TDD first.** Every behavioral change starts with an offline failing test.
2. **No live fan-out by default.** Until cache/rate-limit work is approved, expanded coverage controls must be deterministic/offline-testable and gated behind explicit CLI/report behavior rather than silently multiplying provider calls.
3. **Frontier, not scalar winner.** The report must preserve materially non-dominated options: best practical, fastest acceptable, cheapest acceptable, direct/nonstop, same-carrier/protected-looking, Moscow gateway, aggregate candidate.
4. **Negative evidence typed.** `cached 0`, schedule-index absence, provider unsupported, provider failure, and live fare 0 are different signals. None should be collapsed into “flight does not exist” without a stronger source.
5. **Airport scope explicit.** DXB/DWC/SHJ must not be blurred.
6. **Agent-facing report first.** Human answer quality depends on `agent_report`; do not bury crucial controls only in raw candidates.

---

## Phase 0 — Baseline and safety gate

### Task 0.1: Record baseline status

**Objective:** Capture source/runtime provenance before changing behavior.

**Commands:**

```bash
cd /home/konstantin/.hermes/hermes-agent
git branch --show-current
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all -- skills/productivity/flight-search
```

**Expected:** Current branch and dirty state are explicit. Do not overwrite existing uncommitted skill/reference changes.

### Task 0.2: Run current offline health checks

**Objective:** Confirm the current test baseline before adding route logic.

**Commands:**

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json doctor
```

**Expected:** Existing suite and doctor pass, or failures are documented as baseline and separated from this plan.

---

## Phase 1 — Coverage controls contract

### Task 1.1: Define coverage-control data contract

**Objective:** Add a typed internal contract for controls that the agent can trust.

**Files:**
- Create or modify: `flights_cli/services/coverage_controls.py`
- Modify: `flights_cli/services/agent_report.py`
- Modify schema/contract: `flights_cli/contracts/agent_report.v1.schema.json` if this file exists
- Test: `tests/test_coverage_controls.py`

**Contract fields:**

```python
{
    "control_id": "direct_exact_airport|direct_city_code|full_route_aggregate|carrier_direct|carrier_aggregate|alternate_airport|moscow_gateway",
    "scope": "outbound|return|round_trip|route",
    "origin": "SVX",
    "destination": "DXB",
    "date": "2026-08-16",
    "provider_policy": "auto|kupibilet|fli|both",
    "status": "searched|skipped|failed|not_applicable",
    "negative_evidence_type": "none|live_fare_zero|cached_zero|schedule_absence|provider_unsupported|provider_failure",
    "decision_critical": True,
    "summary": "short human-readable reason"
}
```

**Test first:** Add tests proving:
- skipped controls carry a reason;
- negative evidence type is explicit;
- absence from `live-assemble` is not rendered as “no flight”.

### Task 1.2: Add explicit coverage modes without extra live calls yet

**Objective:** Surface which controls should be run, without automatically increasing provider traffic.

**Files:**
- Modify: `flights_cli/orchestrators/kb_assemble.py`
- Modify: `flights_cli/orchestrators/route_plan.py`
- Test: `tests/test_coverage_controls.py`

**Behavior:**
- `live-assemble` should compute a `coverage_plan` from route context.
- For this plan phase, controls may be marked `not_executed_auto_fanout_disabled` or similar unless already covered by existing calls.
- This preserves correctness in the report without adding cache/rate-limit work.

**Acceptance:** The agent can see “this plausible control was not searched” rather than infer absence.

---

## Phase 2 — Route graph foundation

### Task 2.1: Introduce route graph model

**Objective:** Replace hardcoded route-family generation with a composable graph abstraction.

**Files:**
- Create: `flights_cli/orchestrators/route_graph.py` or `flights_cli/domain/route_graph.py`
- Modify: `flights_cli/orchestrators/route_plan.py`
- Test: `tests/test_route_graph.py`

**Core model:**

```python
@dataclass(frozen=True)
class AirportNode:
    code: str
    role: str  # origin, destination, hub, metro_alternate, pseudo_excluded

@dataclass(frozen=True)
class RoutePath:
    path_id: str
    airports: tuple[str, ...]
    family: str
    purpose: str  # primary, control, fallback
    enabled_by_default: bool
    requires_explicit_live_probe: bool = False
```

**Required generated paths:**
- Direct exact airport.
- Destination airport group.
- Moscow gateway group.
- Regional hub group.
- Provider-discovered aggregate candidate group later in Phase 6.

### Task 2.2: Keep `route plan` and `live-assemble` aligned

**Objective:** Prevent plan/live route-family drift.

**Files:**
- Modify: `flights_cli/orchestrators/route_plan.py`
- Modify: `flights_cli/orchestrators/kb_assemble.py`
- Test: `tests/test_route_graph.py`
- Test: `tests/test_architecture.py`

**Acceptance:**
- Both `route plan` and `route live-assemble` use the same route graph builder.
- A test proves both commands expose equivalent route families for the same route context.

---

## Phase 3 — Domestic-RU strategy

### Task 3.1: Add domestic-RU classifier

**Objective:** Detect routes where origin and destination are both Russian airports/cities.

**Files:**
- Modify: `flights_cli/domain/airports.py`
- Modify or create: `flights_cli/orchestrators/route_graph.py`
- Test: `tests/test_domestic_routing_strategy.py`

**Behavior:**
- If `origin_country == RU` and `dest_country == RU`, strategy is `domestic_ru`.
- International hubs IST/DXB/DWC/SAW must be excluded by default.
- Allowed strategy: direct first, then Russian hubs when practical: SVO/DME/VKO/LED/OVB, but only if route graph says they are useful.

### Task 3.2: Make domestic direct options dominate international detours

**Objective:** Prevent business profile from leading with IST/DXB domestic nonsense.

**Files:**
- Modify: `flights_cli/services/ranking.py`
- Modify: `flights_cli/services/agent_report.py`
- Test: `tests/test_domestic_routing_strategy.py`

**Acceptance cases:**
- SVX→KUF and SVX→OVB test fixtures should not present IST/DXB as best practical when direct domestic options exist.
- If an international detour is present, it appears only as low-priority diagnostic/oddity with reason.

---

## Phase 4 — Dubai airport scope

### Task 4.1: Encode Dubai airport policy

**Objective:** Make Dubai city semantics match Konstantin’s preference: DXB primary, DWC secondary, SHJ out of default.

**Files:**
- Modify: `flights_cli/domain/airports.py`
- Modify: `flights_cli/orchestrators/route_graph.py`
- Test: `tests/test_dubai_airport_scope.py`
- Docs: `skills/productivity/flight-search/references/dubai-city-airports.md`

**Behavior:**
- Query “Dubai” → airport group `[DXB, DWC]` by default.
- SHJ is excluded unless user explicitly asks for SHJ/Sharjah/Air Arabia/G9/cheapest UAE-wide scope, or provider returns SHJ and report labels it as out-of-default.
- Pseudo/non-flight codes such as XEU/XMB/XNB/ZXZ are excluded from airport groups by default.

### Task 4.2: Add report labels for airport-scope decisions

**Objective:** Ensure the user sees which Dubai airport was searched.

**Files:**
- Modify: `flights_cli/services/agent_report.py`
- Test: `tests/test_dubai_airport_scope.py`

**Acceptance:**
- Agent report says `airport_scope: DXB+DWC` for Dubai.
- SHJ is never silently presented as Dubai.

---

## Phase 5 — Regional route graph: Moscow and Gulf/Middle East

### Task 5.1: Add Gulf/Middle East destination profile

**Objective:** Ensure routes like SVX→MCT can consider Moscow as gateway to final destination, not only SVO→IST.

**Files:**
- Modify: `flights_cli/orchestrators/route_graph.py`
- Modify: `flights_cli/domain/hubs.py`
- Test: `tests/test_route_graph.py`

**Behavior:**
- Gulf/Middle East profile includes MCT, DXB, DWC, AUH, DOH, and comparable airports as region destinations.
- Moscow gateway group can connect to final destination when plausible.
- Generated path example: `SVX→SVO→MCT` as a control path, not only `SVX→SVO→IST→MCT`.

### Task 5.2: Make Moscow gateway a first-class control

**Objective:** Preserve Moscow gateway comparisons for Russian-origin international business routes.

**Files:**
- Modify: `flights_cli/orchestrators/route_graph.py`
- Modify: `flights_cli/services/agent_report.py`
- Test: `tests/test_agent_report_p1_moscow_control.py`

**Acceptance:**
- For plausible international routes from SVX, report includes a Moscow gateway control path or an explicit skipped/not-searched diagnostic.
- SVO is preferred; DME/VKO only when same-airport/practical.

---

## Phase 6 — Ranking frontier

### Task 6.1: Separate carrier preference from safety risk

**Objective:** Stop preferred-carrier bias from hiding faster/shorter/safer options.

**Files:**
- Modify: `flights_cli/services/ranking.py`
- Test: `tests/test_ranking_frontier.py`

**Behavior:**
- Keep `carrier_preference_score` as a separate field.
- Do not treat “has preferred carrier” as a safety-risk substitute.
- Ranking can still prefer SU/U6/TK as tie-breakers or business preference, but cannot override direct/faster/safer options without explicit trade-off.

### Task 6.2: Build material frontier categories

**Objective:** Preserve non-dominated options, not only scalar rank #1.

**Files:**
- Modify: `flights_cli/services/assembly.py`
- Modify: `flights_cli/services/agent_report.py`
- Test: `tests/test_ranking_frontier.py`
- Test: `tests/test_agent_report_contract.py`

**Frontier categories:**
- `best_practical`
- `fastest_acceptable`
- `cheapest_acceptable`
- `direct_or_nonstop`
- `same_carrier_or_protected_looking`
- `moscow_gateway_control`
- `provider_aggregate_candidate`

**Acceptance:**
- Each category retains segment details when available.
- If segment details are unavailable, `detail_status` is explicit.
- `answer_lines` can explain why a lower-ranked frontier option matters.

---

## Phase 7 — Provider aggregate candidates

### Task 7.1: Normalize aggregate offers as labeled candidates

**Objective:** Let provider-assembled full-route offers enter the frontier without pretending they are verified through fares.

**Files:**
- Modify: `flights_cli/orchestrators/kb_assemble.py`
- Modify: `flights_cli/services/assembly.py`
- Test: `tests/test_provider_aggregate_candidates.py`

**Candidate shape:**

```python
{
    "candidate_type": "provider_aggregate",
    "provider": "kupibilet|fli|travelpayouts",
    "ticketing_protection": "unknown",
    "requires_purchase_screen_verification": True,
    "source_boundary": "provider aggregate offer; not proof of airline/GDS through fare"
}
```

**Acceptance:**
- Aggregate offer can appear in frontier if materially cheaper, faster, direct, same-carrier, or fills a coverage gap.
- Report never states it is a protected through-fare unless provider data explicitly supports that.

### Task 7.2: Add source-boundary wording for aggregate candidates

**Objective:** Prevent user-facing overclaiming.

**Files:**
- Modify: `flights_cli/services/agent_report.py`
- Modify: `skills/productivity/flight-search/references/source-boundaries.md`
- Test: `tests/test_provider_aggregate_candidates.py`

**Acceptance:**
- Report says “verify on purchase screen” for provider aggregate candidates.
- Separate-segment assembled prices are not described as airline/GDS through fares.

---

## Phase 8 — Coverage diagnostics in agent_report

### Task 8.1: Add compact diagnostics block

**Objective:** Make missing controls visible to the agent without creating a long chat dump.

**Files:**
- Modify: `flights_cli/services/agent_report.py`
- Modify schema/contract: `flights_cli/contracts/agent_report.v1.schema.json` if present
- Test: `tests/test_coverage_diagnostics.py`

**Contract:**

```python
"coverage_diagnostics": {
    "searched_controls": [...],
    "skipped_controls": [...],
    "provider_coverage_by_leg": [...],
    "negative_evidence_summary": [...],
    "decision_critical_gaps": [...]
}
```

**Acceptance:**
- Agent can distinguish searched, skipped, failed, and not-applicable controls.
- Agent can say “this was not searched” instead of inventing absence.

### Task 8.2: Keep user-facing output compact

**Objective:** Ensure diagnostics improve answers without flooding Telegram.

**Files:**
- Modify: `flights_cli/services/agent_report.py`
- Modify: `skills/productivity/flight-search/SKILL.md`
- Create/update: `skills/productivity/flight-search/references/coverage-controls.md`
- Test: `tests/test_coverage_diagnostics.py`

**Behavior:**
- `answer_lines` mention only decision-critical diagnostics.
- Raw diagnostic arrays stay in JSON for agent reasoning/debug.

---

## Phase 9 — Documentation and skill alignment

### Task 9.1: Add `coverage-controls.md`

**Objective:** Give future agents a durable checklist for direct/carrier/city/aggregate/domestic surprises.

**Files:**
- Create: `skills/productivity/flight-search/references/coverage-controls.md`
- Modify: `skills/productivity/flight-search/SKILL.md`

**Checklist sections:**
- Surprising top rank.
- Direct/nonstop claim.
- Carrier-route question.
- City-name request.
- Domestic-RU route.
- Aggregate control much cheaper/faster.
- Moscow gateway control.
- Dubai DXB/DWC scope.

### Task 9.2: Update report contract docs

**Objective:** Keep skill docs aligned with CLI JSON.

**Files:**
- Modify: `skills/productivity/flight-search/references/report-contract.md`
- Modify: `skills/productivity/flight-search/references/source-boundaries.md`

**Acceptance:** Docs describe new fields and source boundaries without adding cache/rate-limit promises.

---

## Verification bundle

Run after each phase that touches code:

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json doctor
```

Run from repo root before reporting done:

```bash
cd /home/konstantin/.hermes/hermes-agent
git diff --check -- skills/productivity/flight-search
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --skill flight-search --json
```

Clean generated artifacts before final audit if tests created them:

```bash
cd /home/konstantin/.hermes/hermes-agent
find skills/productivity/flight-search -type d -name '__pycache__' -prune -exec rm -rf {} +
find skills/productivity/flight-search -type f -name '*.pyc' -delete
find skills/productivity/flight-search -type d -name '*.egg-info' -prune -exec rm -rf {} +
```

---

## Rollout order

Recommended order to reduce risk:

1. Phase 1: coverage contract and non-executed diagnostics.
2. Phase 2: shared route graph builder.
3. Phase 4: Dubai DXB/DWC scope, because it is bounded and user-corrected.
4. Phase 3: domestic-RU strategy.
5. Phase 5: Gulf/Middle East + Moscow gateway controls.
6. Phase 6: ranking frontier.
7. Phase 7: provider aggregate candidates.
8. Phase 8: diagnostics polish.
9. Phase 9: docs/skill alignment.

---

## Explicit non-goals / deferrals

- No provider-aware TTL cache in this plan.
- No request de-duplication layer in this plan.
- No bounded concurrency/backoff implementation in this plan.
- No broad live-search fan-out enabled by default until cache/rate-limit design is approved.
- No SHJ default for Dubai.
- No claim that aggregate provider offers are protected through-fares without purchase-screen evidence.

---

## Done criteria

- Offline tests cover all 7 approved behavior areas.
- `route plan` and `route live-assemble` share route graph logic.
- Domestic-RU routes do not lead with international detours when practical direct options exist.
- Dubai city scope is DXB/DWC by default, SHJ excluded unless explicit/out-of-default.
- Frontier report preserves materially important controls with detail status.
- Aggregate candidates are labeled with ticketing/source boundaries.
- `agent_report` exposes searched/skipped/failed/not-applicable coverage diagnostics.
- `flight-search` skill and references reflect the new contract.
- Full test suite, `doctor`, `git diff --check`, and `audit_skill.py --skill flight-search --json` pass after pycache cleanup.
