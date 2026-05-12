# Master Plan Synthesis Pattern — 2026-05-08

Use this reference when a skill-audit task has multiple overlapping plans and the user asks to decompose, analyze, synthesize, or justify the path to maturity.

## Trigger

The session produced a synthesized master plan for maturing `skill-audit-and-improvement` from a structural checker into an enforced quality gate. The user asked for deep decomposition, then explicitly asked to save the plan and list the profit for each point.

## Reusable pattern

1. Load `skill-audit-and-improvement`, `writing-plans`, `hermes-agent-skill-authoring`, and `knowledge-architecture`/plan governance when the work touches Hermes skills and durable plans.
2. Re-check live state before synthesizing: branch, HEAD, dirty status, target skill files, current CLI flags, current audit output, generated artifacts, and plan statuses.
3. Treat existing plans as inputs, not as automatically current truth. Reconcile them into one master execution map when they overlap.
4. Preserve companion plans unless the user explicitly approves lifecycle changes such as `superseded` or archive moves.
5. For each phase, include the practical profit/benefit, not only tasks. Konstantin uses this to judge sequencing, trade-offs, and why a gate is worth implementing.
6. Save durable multi-step synthesized plans under `/home/konstantin/docs/plans/` with machine-readable status.
7. Verify after saving: file exists, `Current status: ...` is present, code fences are balanced, no secret-like values are present, and `knowledge --json plans audit` can detect the plan.

## Useful commands

```bash
cd /home/konstantin/.hermes/hermes-agent
git branch --show-current
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --skill skill-audit-and-improvement --json
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --changed --json
```

For plan governance validation, direct subprocess parsing of `knowledge --json plans audit` can be more reliable than wrapper output if the wrapper renders control characters into an invalid JSON string:

```python
import json, subprocess
p = subprocess.run(['knowledge', '--json', 'plans', 'audit'], capture_output=True, text=True, timeout=120)
data = json.loads(p.stdout)
```

## Master-plan shape that worked

- Goal: what maturity means in operational terms.
- Context: live branch/HEAD/status, current tool flags, missing capabilities, related plans.
- Architecture decision: e.g. `schema → audit_skill.py → baseline/no-regression compare → CI required check → branch protection → blocker-only review`.
- Non-goals: especially no mutation, no secrets, no generated artifacts, and no premature SARIF/CLI/per-skill JSON.
- Phases:
  1. stabilize dirty/generated state;
  2. add tests and negative fixtures;
  3. define stable JSON contract;
  4. harden resolver and exit codes;
  5. implement deterministic rule engine;
  6. improve `--changed` as the practical gate mode;
  7. add baseline/no-regression;
  8. enforce with CI;
  9. protect with CODEOWNERS/branch protection;
  10. update the skill as procedural source of truth;
  11. defer SARIF/CLI/policy-as-code until the core contract is stable.
- Profit section under each phase.
- Verification and Definition of Done.
- Risks/pitfalls.
- `## Status` with `Current status: planned|in_progress|blocked`.

## Pitfalls captured

- Do not collapse multiple existing plans silently; name the companion plans and say whether they remain active.
- Do not claim plan state from memory; verify live repo and plan inventory first.
- Do not omit the benefit rationale when the user asks for decomposition/synthesis; phases without profit are harder to prioritize.
- Do not archive/supersede companion plans unless explicitly asked.
- Do not use raw `grep`-style secret scans that may print secret values into the transcript.
