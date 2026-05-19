# Deep Skill Audit Worksheet

## Target

- **Skill:** `<skill-name>`
- **Task class:** `<post-session learning | existing skill audit | new skill authoring | skill-owned CLI audit | source/runtime cleanup | distribution/custom inventory | other>`
- **Audit question:** What specific future mistake should this skill prevent, and how will we know?
- **Scope:** `<read-only | runtime skill state | git source edit | docs/plan only | other>`

## Provenance

- **Skill source/runtime path checked:** `<path + evidence>`
- **Branch/HEAD/status or runtime-only evidence:** `<command/result>`
- **Golden path:** `<default route the skill must make easy and first>`
- **Anti-paths / bypass surfaces:** `<wrong routes, wrappers, helpers, env vars, cron/direct API paths to block or require explicit fallback>`
- **Contract basis:** `<positive check + negative fail-closed checks + read-back/mutation proof>`
- **Companion skills loaded:** `<list>`
- **Support files read:** `<list>`
- **Static audit result:** `<audit_skill.py summary or runtime read-back summary>`

## User Scenarios

### Scenario 1 — simple path

- **Prompt:** `<ordinary request>`
- **Expected activation:** `<skills and references>`
- **Evidence before action:** `<files/tools/docs/user input>`
- **Expected behavior:** `<what agent should do>`
- **Verification:** `<proof>`
- **Current result:** `pass | gap | unknown`
- **Gap / patch target:** `<SKILL.md | references | templates | scripts | docs | fact_store | no change>`

### Scenario 2 — edge path

- **Prompt:** `<ambiguous/cross-layer/source-runtime split request>`
- **Expected activation:** `<skills and references>`
- **Evidence before action:** `<files/tools/docs/user input>`
- **Expected behavior:** `<what agent should do>`
- **Verification:** `<proof>`
- **Current result:** `pass | gap | unknown`
- **Gap / patch target:** `<target>`

### Scenario 3 — failure path

- **Prompt:** `<tool/source/API unavailable or partial evidence>`
- **Expected activation:** `<skills and references>`
- **Fallback:** `<retry/alternate evidence/label uncertainty/ask>`
- **Stop condition:** `<when not to mutate or claim done>`
- **Current result:** `pass | gap | unknown`
- **Gap / patch target:** `<target>`

### Scenario 4 — dangerous side effect

- **Prompt:** `<mutation/external system/protected context/secrets/deployment/cron/config>`
- **Approval boundary:** `<what requires explicit user approval>`
- **Safe default:** `<read-only check / dry-run / no-op>`
- **Verification after mutation:** `<read-back/test/health check>`
- **Current result:** `pass | gap | unknown`
- **Gap / patch target:** `<target>`

## Cognitive Walkthrough

- **Expert goal:** `<what a competent operator optimizes for>`
- **Decision points:**
  1. `<decision>` → evidence: `<evidence>` → action: `<action>`
  2. `<decision>` → evidence: `<evidence>` → action: `<action>`
- **Likely novice-agent mistakes:**
  - `<mistake>`
- **Fallback paths:**
  - `<condition>` → `<fallback>`
- **Completion proof:** `<smallest evidence sufficient to say done>`

## Gap Analysis

- **Behavior before:** `<what current skill lets the agent do or miss>`
- **Behavior after:** `<what proposed change will make the agent do differently>`
- **Golden path after:** `<default route encoded in SKILL.md>`
- **Anti-paths blocked:** `<routes that now fail closed or require explicit fallback>`
- **Contract checks:** `<positive path checks, negative bypass checks, mutation/read-back proof>`
- **Mistake prevented:** `<specific recurrence prevented>`
- **Minimal change:** `<patch/reference/template/script/no change>`
- **Why this layer:** `<reason>`
- **Remaining uncertainty:** `<what still needs future evidence>`
- **Next check:** `<scenario replay / static audit / pilot>`

## Semantic Review Result

Choose one:

- `pass` — current skill already changes behavior and prevents the target mistake.
- `needs patch` — main operational path is missing or wrong.
- `needs reference` — long theory/cases/evidence should not bloat `SKILL.md`.
- `needs template` — future agents need a reusable worksheet/report format.
- `needs script` — deterministic evidence/redaction/normalization is required.
- `needs source change` — runtime-only patch is insufficient for reproducibility.
- `no durable change` — finding is session-specific or already covered.

## Verification After Change

- **Static gate:** `<command/result>`
- **Contract gate:** `<validate_contract.py/audit checks/result, including negative anti-path checks>`
- **Read-back:** `<bytes/sha256/required substrings>`
- **Scenario replay:** `<scenario + pass/fail>`
- **No generated artifacts:** `<check>`
- **No protected context changes:** `<check>`
- **Commit/push state:** `<sha or runtime-only/no commit>`
