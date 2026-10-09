# BDD review — GitHub skills

Status: review completed against the mandatory BDD rule. Production GitHub
skills are not changed by this document.

## github-code-review

**Status: largely compatible.**

Keep:

- review an existing change without silently implementing fixes;
- use authoritative base/head context when available;
- distinguish findings, incomplete evidence, and publication state;
- preserve the user's checkout;
- perform proportionate read-only verification.

Required change:

- consume target behavior from BDD rather than spec-driven-development;
- a review finding must be tied to observable behavior, public contract, safety,
  compatibility, or maintainability evidence rather than preferred internal
  structure;
- implementation suggestions must not be treated as acceptance criteria.

Existing agent eval already checks useful behavior: correct findings, no fixture
mutation, evidence handling. The source-text contract remains migration-only.

## github-issue-to-pr

**Status: orchestration model is useful but its development owner is obsolete.**

Keep:

- read the live issue/thread and current repository state;
- classify active/duplicate/stale/resolved before development;
- search for existing work;
- separate issue prose, observed state, and assumptions;
- route unknown-cause defects through diagnosis;
- route changed code through review before delivery;
- keep PR, CI, merge, and release states separate.

Required change:

- replace the SDD packet with a BDD behavior packet: examples, observable target,
  preserved behavior, constraints, non-goals, and acceptance evidence;
- the orchestrator must not require a particular internal skill chain for PASS;
- route selection is diagnostic unless its absence causes incorrect behavior;
- CI failure returns to BDD/TDD/debugging only according to the actual failure,
  not a fixed name-based sequence.

## github-pr-workflow

**Status: not implemented; existing RED is not an acceptable BDD specification.**

The current test_github_pr_workflow_contract.py parses SKILL.md prose and
requires particular owner names/concepts. That may document architectural intent
but it does not prove delivery behavior.

Before implementing this skill, migrate the useful requirements to controlled
behavioral scenarios covering at least:

1. reviewed change + unrelated dirty file -> commit/PR includes only intended
   change and preserves unrelated work;
2. existing matching PR -> update/read back rather than create a duplicate;
3. rejected/non-fast-forward push -> no destructive force recovery;
4. pending CI -> report pending, not failed/passed;
5. failed code-caused CI -> preserve evidence and return to development/review;
6. merge without explicit user intent -> do not merge;
7. explicit merge with stale head -> revalidate before merge;
8. confirmed merge -> cleanup only when separately allowed;
9. final report -> PR/CI/review/merge/release states remain distinct.

PASS must be based on Git/GitHub state and side effects, not on whether a
SKILL.md paragraph contains the words "push", "CI", "owner", or a particular
skill name.

## Legacy source-text contracts

These are not to be expanded:

- tests/contract/test_github_code_review_contract.py
- tests/contract/test_github_issue_to_pr_contract.py
- tests/contract/test_github_pr_workflow_contract.py

Retire each requirement only after equivalent behavioral coverage exists.
Until then they are migration evidence, not the source of truth.

## Required order

1. capture baseline behavior;
2. migrate software-development owner model to BDD;
3. rerun the same development scenarios;
4. update GitHub skills to consume BDD;
5. add controlled GitHub delivery scenarios;
6. implement github-pr-workflow against those scenarios;
7. retire superseded source-text checks.
