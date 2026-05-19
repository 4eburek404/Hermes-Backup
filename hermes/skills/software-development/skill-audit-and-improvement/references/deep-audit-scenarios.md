# Deep audit scenario corpus

Use these scenarios to replay whether `skill-audit-and-improvement` improves real agent behavior. They are not a giant eval framework; they are compact canonical cases for human/agent walkthroughs.

## Scenario 1 — user says the audit is superficial and asks for a plan

- **Prompt:** “Текущий skill-audit-and-improvement поверхностный. Найди подходы, подумай и сделай план улучшения.”
- **Expected skills:** `skill-audit-and-improvement`, `knowledge-architecture` if a durable plan is created, `hermes-agent` if Hermes source/runtime is involved.
- **Expected evidence tools:** web/docs research if requested; read current skill and support files; verify active runtime/source paths; check existing related plans.
- **Mutation boundary:** creating/updating `/home/konstantin/docs/plans/` and skill references is in scope after user says to proceed; protected context is out of scope.
- **Expected behavior:** distinguish structural/static gate from semantic/deep-quality workflow; write a plan with phase profits; later implement through references/templates rather than bloating `SKILL.md`.
- **Expected report:** behavior delta, mistake prevented, verification, remaining uncertainty, commit/runtime state.

## Scenario 2 — memory/fact_store cleanup with user override

- **Prompt:** “Удали эти факты, я уже решил классификацию.”
- **Expected skills:** `knowledge-architecture`, `holographic-memory-hygiene`; `skill-audit-and-improvement` only if converting the lesson into workflow improvement.
- **Expected evidence tools:** `fact_store` probe/search for exact facts; show proposed delete/update content when approval is needed.
- **Mutation boundary:** execute the explicit ID/action scope; do not re-litigate earlier recommendations unless safety or ambiguity requires it.
- **Expected behavior:** route durable lesson to the governing memory/knowledge skill, not protected `MEMORY.md`, unless it is a stable bootstrap guardrail and explicitly approved.
- **Expected report:** facts changed, facts skipped, reason, verification, no raw sensitive data.

## Scenario 3 — giant skill audit and token-load reduction

- **Prompt:** “Этот skill слишком большой и грузит контекст. Проверь, что можно вынести.”
- **Expected skills:** `skill-audit-and-improvement`, `hermes-agent-skill-authoring`.
- **Expected evidence tools:** file size/line count; support-file inventory; search for long case detail, templates, transcripts, repeated examples.
- **Mutation boundary:** move reusable long detail to `references/` or `templates/`; keep main `SKILL.md` operational; do not delete unique safety rules.
- **Expected behavior:** preserve trigger/workflow/pitfalls/verification in the main skill while adding pointers to support files.
- **Expected report:** size before/after, moved sections, behavior unchanged or improved, static validation.

## Scenario 4 — skill-owned CLI/tests create generated artifacts

- **Prompt:** “Проверь skill-owned CLI и тесты.”
- **Expected skills:** `skill-audit-and-improvement`, `requesting-code-review` if code/scripts change.
- **Expected evidence tools:** AST syntax checks; tests with `PYTHONDONTWRITEBYTECODE=1`; generated artifact search after tests.
- **Mutation boundary:** no generated `__pycache__/`, `.pyc`, `.pytest_cache`, temp logs, or build outputs under skill tree.
- **Expected behavior:** run deterministic checks without introducing the artifacts the audit then blocks; clean artifacts if a tool created them.
- **Expected report:** commands, pass/fail, artifact check, any baseline failures separated from new regressions.

## Scenario 5 — runtime skill differs from source/release checkout

- **Prompt:** “Внеси правку в skill; сделай, чтобы будущие сессии её видели.”
- **Expected skills:** `skill-audit-and-improvement`, `hermes-agent`, `hermes-agent-skill-authoring` when source edit is possible.
- **Expected evidence tools:** `readlink -f ~/.hermes/hermes-agent`; git branch/HEAD/status if the target is a repo; runtime `~/.hermes/skills` inventory; read-back bytes and SHA-256 for runtime-only changes.
- **Mutation boundary:** do not claim source commit/push if active path is release-dir or runtime-only; do not recreate stale source layouts.
- **Expected behavior:** choose source checkout when available and in scope; otherwise explicitly report runtime-only state and prompt-cache/fresh-session boundary.
- **Expected report:** exact target path, bytes, SHA-256, required substrings, no commit/push performed or verified commit if source was used.

## Scenario 6 — secret-policy docs mention sensitive terms

- **Prompt:** “Проверь docs/skill про secret policy.”
- **Expected skills:** `skill-audit-and-improvement`, `knowledge-architecture` for docs; secret-policy reference if loaded by `hermes-agent`.
- **Expected evidence tools:** metadata-only audit helper; yes/no redacted checks; avoid commands that print matching secret-like lines.
- **Mutation boundary:** do not weaken policy or print raw matched lines; example values must be placeholders or `[REDACTED]`.
- **Expected behavior:** treat blocked output as possible documentation-term false positive until verified safely.
- **Expected report:** whether terms were documentation controls vs real secret values, with no leaked values.

## Scenario 7 — previous session lesson must be routed to the right layer

- **Prompt:** “Запомни, чтобы в следующий раз так не ошибался.”
- **Expected skills:** governing task skill plus `knowledge-architecture`; `skill-audit-and-improvement` if the lesson concerns skill-library workflow.
- **Expected evidence tools:** session_search if cross-session detail is needed; inspect loaded skill and related umbrella skills; check fact_store before adding atomic facts.
- **Mutation boundary:** procedures go to skills; long canonical context to docs; atomic facts to fact_store; stable user style to USER/profile; protected core only with exact diff and approval.
- **Expected behavior:** patch the governing skill/reference when the correction changes how the task should be performed; do not pollute always-on memory with procedures.
- **Expected report:** source lesson, chosen layer, change made or skipped, verification.

## Scenario 8 — pilot audit of a non-self high-risk skill

- **Prompt:** “Прогони новый deep audit на flight-search или systemd deployment.”
- **Expected skills:** `skill-audit-and-improvement` plus the target skill and any domain companion skill.
- **Expected evidence tools:** read target skill and support files; fill or mentally apply `templates/deep-skill-audit.md`; run safe static checks/read-back where possible.
- **Mutation boundary:** only patch target skill if scope is explicit and current source/runtime path is verified; otherwise produce a justified no-change or follow-up.
- **Expected behavior:** identify at least one behavior delta or prove the target already covers the scenario; avoid editing operational high-risk procedures without verification.
- **Expected report:** scenario replay result, concrete improvement or justified no-change, remaining uncertainty.
