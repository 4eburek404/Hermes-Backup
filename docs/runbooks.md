# Runbooks

Назначение: короткие проверенные процедуры. Если процедура длинная или часто повторяется — перенести в skill, оставить здесь ссылку.

## Before changing Hermes setup

1. Read relevant file: `infrastructure.md` (paths/providers/cron), `user-context.md` (preferences).
2. Check current state: `hermes --version`, `hermes memory status`, `date '+%Z %z'`.
3. No secrets in output.
4. Small reversible changes.
5. Verify after change.

## Searcharvester-derived research/delegation guardrails

Use these as the cross-skill contract for web/API/news/flight/research/delegate workflows.

1. **Date/current-context in delegation:** every `delegate_task` context starts with a current date/time line from `date` plus explicit scope/language/task boundaries. For current web/API/flight/news/version facts, tell subagents not to rely on stale training-memory.
2. **Grounding artifacts:** URL/API/search/CLI/browser-backed claims should have side-effect evidence: `./extracts/`, `./api_responses/`, `./queries/`, or a skill-specific equivalent. Missing artifact/tool evidence → label the claim ungrounded or re-check.
3. **Progress artifacts:** for multi-step/delegate workflows, use lightweight `plan.md → notes.md → report.md` so state is recoverable after truncation, `(empty)` summaries, or context loss. Skip this overhead for simple one-shot lookups.
4. **Verifier escalation:** use full `researcher → verifier/critic/fact-checker` only for high-stakes decisions: money/purchase/non-refundable fares, production/security, dates/deadlines, airport/visa/self-transfer/baggage risk, conflicting sources, incomplete cache/API, or explicit user request. Round 2 must receive `researcher_summary`, `facts_to_verify`, and artifact paths; blind critic alone is not verification.
5. **Scope boundary:** these guardrails live in user-layer skills/docs. They do not require Hermes core repo changes unless a separate UI/ACP/orchestration project is opened.

## Add Ollama cloud model to Hermes `/model`

1. Verify exact tag: `ollama list` → `ollama show <model>:<tag>-cloud`.
2. Edit `~/.hermes/config.yaml` → `providers.ollama-local.models.<exact-tag>: {}`.
3. Verify YAML parses; restart gateway/new session for `/model` refresh.

Pitfalls:
- Tag format varies: `gemma4:cloud` invalid, `gemma4:31b-cloud` valid; `gpt-oss:20b-cloud` valid before appearing in `ollama list`.

## Import Codex CLI OAuth credentials into Hermes

Source: `~/.codex/auth.json` → Dest: `~/.hermes/auth.json`.

Dest shape: `{"providers":{"openai-codex":{"tokens":{"access_token":"***","refresh_token":"***","id_token":"***"},"auth_mode":"chatgpt","last_refresh":"..."}}}`

Verify: only check provider names, token key names, `auth_mode`, key presence — never print values.

Known failure: credentials under top-level `openai-codex` instead of `providers.openai-codex`.

## Create timezone-aware cron job

1. Check host timezone: `date '+%Z %z'`.
2. Convert requested user time → host local time.
3. Create/update cron.
4. Verify `next_run_at` or run a test job.

Reference: user UTC+5. Host may differ (observed CEST UTC+2 earlier). 06:00 user = 03:00 host → `0 3 * * *`.

## Repair GitHub CLI PR/API authentication

Use when `git push` works but `gh pr` fails with 403/401.

1. `git push` success ≠ PR API access.
2. Never print/store/reuse pasted tokens; treat as compromised → advise revocation.
3. This host: classic PAT with scopes `repo`, `workflow`, `read:org`.
4. Check env shadowing: report only whether `GH_TOKEN`/`GITHUB_TOKEN` present, not values.

```bash
read -rsp "GitHub token: " GH_PAT; echo; printf '%s\n' "$GH_PAT" | gh auth login --with-token && unset GH_PAT && gh auth setup-git
```

Verify: `gh auth status` + `gh api user --jq .login` + `gh pr list --repo <repo> --limit 3 --json number,title,state`.

## Google Calendar write/datetime safety

1. Calendar ACL share role ≠ OAuth/API scope; `calendar.readonly` scope ≠ lack of write ACL.
2. Prefer service-account path (see infrastructure.md); OAuth helpers = generic compatibility.
3. Event datetimes must include timezone: `2026-05-25T12:00:00+05:00`, never naive local.
4. Verify after mutation; confirm destructive changes before executing.

## Flight search / booking assistance

Use `flight-search-routing` skill and Travelpayouts plugin as advisory inputs, not as a booking authority.

1. Gather requirements: exact passengers, dates, luggage, cabin, airport constraints, visa/passport constraints, payment/booking owner.
2. Search market/options, then build a 3–5 route shortlist with trade-offs, risks, and recheck points.
3. Treat the agent as quality controller, not auto-clicker: never book/pay without explicit human confirmation of names, dates, airports, tariff, baggage, refund/exchange rules, and final price.
4. For London, query specific airports (`LHR`, `LGW`, `STN`, `LTN`) rather than city code `LON`; Travelpayouts cache may return empty for `LON`.
5. Keep airport systems separate: `IST`≠`SAW`, `SVO`≠`DME`≠`VKO`, `LHR`≠`LGW`≠`STN`≠`LTN`. Cross-airport self-connections on separate tickets are high risk.
6. Travelpayouts prices are cached/advisory; recheck final fare and availability on aggregator/airline site before purchase.

## Repair n8n after reboot

Use when the n8n container restarts but fails with `EACCES: permission denied, open '/home/node/.n8n/config'`.

1. Inspect the container mount: host data directory should be mounted to `/home/node/.n8n`.
2. Check host directory ownership. n8n runs as UID 1000; the host data directory must be owned by `1000:1000`.
3. Fix ownership, then restart/verify the container.

Pitfall: after an external VPS reboot or recreated bind-mount directory, Docker may leave/create the host data directory as `root:root`, causing a crash loop even though the container image and port mapping are unchanged.

## Use hh.ru API skill

Load `hh-ru` skill for vacancy, employer, salary-statistics, OAuth, and API parameter details.

Pitfalls:
- Public `/vacancies` calls can hit rate limits quickly; on 403, back off instead of looping.
- Use `professional_role` for modern vacancy filtering; `specialization` is legacy.
- Salary-statistics region IDs are macro-area IDs, not ordinary `/areas` IDs.

## Interpreting "do not edit files"

- Broad: no edits to docs, plans/, skills, config, memory, cron, credentials, or target project files unless explicitly exempted.
- Plans not exempt. If plan needed but edits forbidden → output in chat or `/tmp` scratch.
- Benchmark/dry-run: candidates propose only; controller must not apply.

### Pitfall: рестарт при незавершённых изменениях

Агент не должен вызывать `/restart` или `/reset`, пока в текущей сессии есть незавершённые write-операции (файлы, memory, fact_store, cron, config). Вместо рестарта — отчёт о сделанном и запрос подтверждения пользователя. Внешний краш (OOM, сигнал ОС, таймаут провайдера) — исключение.

## Benchmark models (unified)

Use before pinning a model to any cron job (weather, distillation, reports).

Method:
1. Fetch one fixed input payload.
2. Run every candidate on same payload + prompt.
3. Collect: raw output, latency, output length, token usage, factual issues, Telegram suitability (or distillation-specific behavior — see below).
4. Show raw outputs + analysis.
5. Pin selected model.

**For distillation benchmarks**, additionally:
- Use a fixed packet resembling real task: current docs/rules, recent-session facts, duplicates, low-durability progress, credential-like material, ≥1 durable candidate.
- Require `add/update/remove/skip`, destination, evidence, confidence, rationale.
- Score distillation behavior: separates facts/hypotheses, prefers updates over duplicates, explains skips, avoids secrets/raw logs/task-progress, routes correctly, doesn't invent infrastructure.
- Run models in isolated invocations with separate timeout/result file. Parallel OK only when no model can edit target files.
- Report raw outputs, metrics, interpretation, confidence, limitations. One synthetic packet is not enough.
- **Pitfall:** polished answer with speculative additions = distillation failure. Mini-prompt success ≠ override full real-prompt timeout.

**Known outcomes:**

| Use case | Selected | Alternatives considered |
|---|---|---|
| Weather morning report | `gemma4:31b-cloud` | `gpt-oss:20b-cloud` fast but dry; `gpt-oss:120b-cloud` too long |
| Distillation curator | `gpt-5.5` (OpenAI Codex) | `glm-5.1:cloud` usable fallback; `deepseek-v4-pro:cloud` timeout on full prompt; `kimi-k2.6` unreliable JSON |

## Evaluate external memory provider

1. No auto-extract by default.
2. Backup config first.
3. Prefer local (`holographic`).
4. Confirm storage path + DB schema before relying.
5. Test with non-sensitive facts.
6. Verify retrieval.
7. Document rollback.

Target: `memory.provider: holographic`, `plugins.hermes-memory-store.auto_extract: false`. Apply after explicit approval.

## Maintain daily knowledge distillation cron

1. Write plan in `plans/` before multi-step changes.
2. Check host timezone; convert user time → cron time.
3. Keep toolsets minimal: `session_search`, `file`, `terminal`, `memory`; add `web` only if source gathering needs it and `delegation` only if parallel subagents are explicitly enabled.
4. Attach `daily-knowledge-distillation` skill; keep cron prompt short, doctrine in skill.
5. Record metadata in `infrastructure.md`: job name/ID/schedule/user-time/toolsets/skill/model.
6. After first real run, review Telegram audit. If issues → patch skill, don't bloat prompt.

## Structured JSON from Ollama Cloud models

1. Endpoint matters. `ollama-local` uses OpenAI-compatible `/v1/chat/completions`; `ollama-native` uses native `/api/chat` with Hermes `api_mode: ollama_native_chat`.
2. Compatibility path: no `json_schema` strict mode — not enforced by remote proxy. Use `response_format: {"type":"json_object"}` + explicit enum values in system prompt.
3. Native path: use top-level `format:"json"`, `think:false` for reasoning models when hidden reasoning is not wanted, `options.num_predict` for visible output budget, and `stream:false` for non-stream JSON responses. Parse content from native `message.content`; usage is Ollama prompt/eval counts, not OpenAI `usage`.
4. Parse defensively: JSON parse → strip ```json fences → extract first `{...}`.
5. `glm-5.1:cloud`: system prompt in English; Russian system prompt + compatibility `json_object` produced empty content. Russian claim/reason fields OK.
6. Reasoning models (`deepseek-v4-pro`): reasoning tokens count toward limit and may be returned as `message.reasoning`, not `reasoning_content`. Cron-shaped distillation repro on 2026-05-01: `deepseek-v4-pro:cloud` through compatibility `/v1` exited in ~93–113s but spent the 3000-token budget on reasoning and produced only 127 chars of incomplete JSON. Native `/api/chat` with `think:false` removes that hidden-reasoning budget issue, but production use still needs the compact output contract and fresh task-shaped benchmark.
7. `kimi-k2.6`: not recommended — excessive reasoning tokens on trivial prompts, unreliable/truncated JSON.

## Holographic memory hygiene

Canonical protocol: Hermes skill `holographic-memory-hygiene`. Load before auditing/cleaning/mutating `fact_store`.

Guardrails:
1. Before `fact_store add`, search for similar; update similar instead of duplicate add.
2. Situation changed → update/remove old fact, don't add contradicting one.
3. `memory add` auto-mirrored into holographic via `on_memory_write()` hook — additional `fact_store add` creates duplicates.
4. `fact_store update/remove/add` = long-term mutation: audit first, act after explicit instruction.

## Use Himalaya CLI for Gmail

Auth: Gmail App Password; config at `~/.config/himalaya/config.toml`.

Pitfalls:
1. `himalaya message delete` fails on Trash/Spam — Gmail `NO: No folder Trash`. Fix: `himalaya flag add --folder "[Gmail]/Корзина" ID deleted` then `himalaya folder expunge "[Gmail]/Корзина"`.
2. `himalaya message move` — target folder FIRST: `himalaya message move "FolderName" ID1 ID2...`. Folder after IDs → `invalid digit`.
3. Russian locale folder names: Trash = `[Gmail]/Корзина`, Spam = `[Gmail]/Спам`. Verify with `himalaya folder list`.
4. Batch: 20–30 IDs per command. Single-ID loops too slow for bulk.