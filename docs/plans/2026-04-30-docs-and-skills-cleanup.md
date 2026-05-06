# Plan: Docs and skills cleanup

## Goal
Bring `/home/konstantin/docs/` and local high-impact skills back to curated operational shape: less duplicated policy text, clearer source-of-truth boundaries, active plans root cleaned up, and executable procedures kept in skills/runbooks without long philosophical overgrowth.

## Context
A read-only audit in the 2026-04-30 Telegram session found that the knowledge base is useful but starting to sprawl:

- `/home/konstantin/docs/infrastructure.md` is 354 lines / ~15.4k chars and now mixes stable infrastructure map with detailed dashboard feature history.
- `/home/konstantin/docs/runbooks.md` is 310 lines / ~12.9k chars and mixes short procedures with benchmark policy, distillation policy, GitHub auth repair, Holographic hygiene, Himalaya details, etc.
- `plans/README.md` is 206 lines / ~7.6k chars; acceptable but heavy.
- Active plan root contains `2026-04-30-server-monitor-auth.md` with completed status; it should be archived under `archive/2026/done/`.
- Large local skills include `daily-knowledge-distillation` (~365 lines / ~22.7k chars) and `docs-review` (~317 lines / ~15.8k chars); both contain valuable policy but are too verbose for frequent loading.
- `github-auth` was corrected after the GitHub token repair: keep the right token-based login command, avoid sprawling meta-rules.
- No direct GitHub-token-like secret was found in docs/skill during the quick scan; earlier hits were false positives around ordinary words such as `task-progress`.

Relevant skills/docs to load before executing:

- `docs-review`
- `konstantin-plan-governance`
- `/home/konstantin/docs/README.md`
- `/home/konstantin/docs/plans/README.md`

## Non-goals
- Do not rewrite all docs from scratch.
- Do not delete archived plans just because they are old.
- Do not mutate credentials, cron jobs, Hermes config, GitHub auth, or production services.
- Do not compact built-in memory unless a separate explicit need appears.
- Do not remove useful operational facts; move/condense them to the right layer.

## Steps
- [x] Re-run read-only inventory: file sizes, headings, active/root plans, duplicate-with-skill candidates, secret-risk scan.
- [x] Archive completed root plans `2026-04-30-server-monitor-auth.md` and `2026-05-01-cron-fact-store-deepseek-root-cause.md` after confirming done/completed statuses.
- [ ] Compact `runbooks.md`: keep short procedures and pointers; move/leave detailed executable procedures in skills where appropriate.
- [ ] Compact `infrastructure.md`: keep stable system map/current invariants; remove one-off implementation history or point to archived plans/session history.
- [ ] Review `github-auth` skill and ensure it contains the correct token login command and concise troubleshooting, not extra “rails” prose.
- [ ] Review `daily-knowledge-distillation` skill for policy bloat; propose or apply targeted compaction while preserving hard-learned pitfalls.
- [ ] Review `docs-review` skill for policy bloat; propose or apply targeted compaction while preserving the read-only-first audit workflow.
- [x] Audit custom runtime skills absent from Hermes repo and separate instruction core from inline scripts/code into `scripts/` or `references/` where not already done.
- [x] Verify no secrets/token-like values and no raw logs were introduced.
- [ ] Re-read changed sections and report exact files/sections changed.

## Verification
- Root `/home/konstantin/docs/plans/` contains only `README.md` plus active `planned|in_progress|blocked` plans.
- `runbooks.md` is shorter or at least better layered: repeatable procedures only, long policy moved to skills or shortened to pointers.
- `infrastructure.md` distinguishes current stable facts from historical/session detail.
- `github-auth` contains the canonical token login command:
  `read -rsp "GitHub token: " GH_PAT; echo; printf '%s\n' "$GH_PAT" | gh auth login --with-token && unset GH_PAT && gh auth setup-git`
- Secret scan for GitHub-token-like strings returns no real secrets.
- Final report separates: changed, skipped, needs decision.

## Risks / pitfalls
- Over-cleaning can delete useful recovery knowledge. Prefer compaction and pointers over deletion.
- Skills may be plugin-provided or archived; verify paths and whether a skill is writable before patching.
- Some “secret-like” regex hits can be false positives; inspect context without reproducing secret values.
- Avoid turning cleanup into another layer of meta-policy. If a section needs a rule, prefer a short command/procedure over an essay.

## Status
Current status: in_progress


## Notes
2026-05-05: active-plan audit — **не закрыт**. Read-only inventory re-run:
- `runbooks.md`: 10,193 chars / 177 lines / 18 H1-H3 headings.
- `infrastructure.md`: 8,078 chars / 180 lines / 22 H1-H3 headings.
- `github-auth` skill contains canonical `gh auth login --with-token` command, but still large: 8,702 chars / 253 lines.
- Heavy archived skills still large: `daily-knowledge-distillation` 26,259 chars; `docs-review` 17,311 chars.
- Secret-risk scan over `/home/konstantin/docs`: 0 hits.
Remaining blockers are the actual compaction/review steps for `runbooks.md`, `infrastructure.md`, `github-auth`, `daily-knowledge-distillation`, and `docs-review`.

Starting point from prior session: likely cleanup order is root plans → `runbooks.md` → `infrastructure.md` → `github-auth` → heavy skills (`daily-knowledge-distillation`, `docs-review`).

2026-04-30: compacted `/home/konstantin/docs/plans/README.md` from ~205 lines / ~11.5k chars to 153 lines / ~5.1k chars. Kept root/archive policy, statuses, minimal template, lifecycle, forbidden content, hygiene checklist, and anti-patterns; removed repeated rationale/meta-policy.

2026-05-05: plan-root canonical cleanup archived completed root plans `2026-04-30-server-monitor-auth.md` and `2026-05-01-cron-fact-store-deepseek-root-cause.md`; normalized active plan statuses/sections so root contains only active `planned|in_progress|blocked` plans.

2026-05-05: started custom-skill instruction/code split audit. Runtime-vs-repo comparison found 11 custom skills absent from Hermes repo; initial scan shows several already have support files, but `hh-ru`, `web-article-reader`, `news-search`, `ollama`, `systemd-web-service-deployment`, and `holographic-memory-hygiene` still contain executable/script-like blocks in `SKILL.md` that should be extracted or reduced to pointers.

2026-05-05: completed custom-skill instruction/code split for the 11 skills absent from Hermes repo. Moved executable snippets/helpers into support files for `web-article-reader`, `news-search`, `hh-ru`, `ollama`, `systemd-web-service-deployment`, and `holographic-memory-hygiene`; additionally split `hh-ru` API/auth reference out of the core into `references/api-reference.md`; removed generated `__pycache__/*.pyc` artifacts from custom skill `scripts/`. Verification: all 11 custom `SKILL.md` files have valid frontmatter; custom skill cores now have 0 bash/python fenced code blocks; `hh-ru/SKILL.md` is now 7,535 chars with 0 fenced blocks; new Python helpers passed `python3 -m py_compile`; secret-risk scan over changed/plan files returned 0 hits; `ollama` core no longer contains stale `ollama pull/run <model>:cloud` smoke-test text.
