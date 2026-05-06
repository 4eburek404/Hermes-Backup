---
name: hermes-agent
description: "Configure, extend, or contribute to Hermes Agent."
version: 2.0.0
author: Hermes Agent + Teknium
license: MIT
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent

Hermes Agent is an open-source AI agent framework by Nous Research that runs in your terminal, messaging platforms, and IDEs. It belongs to the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Hermes works with any LLM provider (OpenRouter, Anthropic, OpenAI, DeepSeek, local models, and 15+ others) and runs on Linux, macOS, and WSL.

What makes Hermes different:

- **Self-improving through skills** — Hermes learns from experience by saving reusable procedures as skills. When it solves a complex problem, discovers a workflow, or gets corrected, it can persist that knowledge as a skill document that loads into future sessions. Skills accumulate over time, making the agent better at your specific tasks and environment.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends (built-in, Honcho, Mem0, and more) let you choose how memory works.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Email, and 10+ other platforms with full tool access, not just chat.
- **Provider-agnostic** — swap models and providers mid-workflow without changing anything else. Credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Hermes instances with isolated configs, sessions, skills, and memory.
- **Extensible** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, and the full Python ecosystem.

People use Hermes for software development, research, system administration, data analysis, content creation, home automation, and anything else that benefits from an AI agent with persistent context and full system access.

**This skill helps you work with Hermes Agent effectively** — setting it up, configuring features, spawning additional agent instances, troubleshooting issues, finding the right commands and settings, and understanding how the system works when you need to extend or contribute to it.

**Docs:** https://hermes-agent.nousresearch.com/docs/

## Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Interactive chat (default)
hermes

# Single query
hermes chat -q "What is the capital of France?"

# Setup wizard
hermes setup

# Change model/provider
hermes model

# Check health
hermes doctor
```

---

## CLI Reference

### Global Flags

```
hermes [flags] [command]

  --version, -V             Show version
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --pass-session-id         Include session ID in system prompt
```

No subcommand defaults to `chat`.

### Chat

```
hermes chat [flags]
  -q, --query TEXT          Single query, non-interactive
  -m, --model MODEL         Model (e.g. anthropic/claude-sonnet-4)
  -t, --toolsets LIST       Comma-separated toolsets
  --provider PROVIDER       Force provider (openrouter, anthropic, nous, etc.)
  -v, --verbose             Verbose output
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --source TAG              Session source tag (default: cli)
```

### Configuration

```
hermes setup [section]      Interactive wizard (model|terminal|gateway|tools|agent)
hermes model                Interactive model/provider picker
hermes config               View current config
hermes config edit          Open config.yaml in $EDITOR
hermes config set KEY VAL   Set a config value
hermes config path          Print config.yaml path
hermes config env-path      Print .env path
hermes config check         Check for missing/outdated config
hermes config migrate       Update config with new options
hermes login [--provider P] OAuth login (nous, openai-codex)
hermes logout               Clear stored auth
hermes doctor [--fix]       Check dependencies and config
hermes status [--all]       Show component status
```

### Tools & Skills

```
hermes tools                Interactive tool enable/disable (curses UI)
hermes tools list           Show all tools and status
hermes tools enable NAME    Enable a toolset
hermes tools disable NAME   Disable a toolset

hermes skills list          List installed skills
hermes skills search QUERY  Search the skills hub
hermes skills install ID    Install a skill (ID can be a hub identifier OR a direct https://…/SKILL.md URL; pass --name to override when frontmatter has no name)
hermes skills inspect ID    Preview without installing
hermes skills config        Enable/disable skills per platform
hermes skills check         Check for updates
hermes skills update        Update outdated skills
hermes skills uninstall N   Remove a hub skill
hermes skills publish PATH  Publish to registry
hermes skills browse        Browse all available skills
hermes skills tap add REPO  Add a GitHub repo as skill source
```

### MCP Servers

```
hermes mcp serve            Run Hermes as an MCP server
hermes mcp add NAME         Add an MCP server (--url or --command)
hermes mcp remove NAME      Remove an MCP server
hermes mcp list             List configured servers
hermes mcp test NAME        Test connection
hermes mcp configure NAME   Toggle tool selection
```

### Gateway (Messaging Platforms)

```
hermes gateway run          Start gateway foreground
hermes gateway install      Install as background service
hermes gateway start/stop   Control the service
hermes gateway restart      Restart the service
hermes gateway status       Check status
hermes gateway setup        Configure platforms
```

Supported platforms: Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Matrix, Mattermost, Home Assistant, DingTalk, Feishu, WeCom, BlueBubbles (iMessage), Weixin (WeChat), API Server, Webhooks. Open WebUI connects via the API Server adapter.

Platform docs: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
hermes sessions list        List recent sessions
hermes sessions browse      Interactive picker
hermes sessions export OUT  Export to JSONL
hermes sessions rename ID T Rename a session
hermes sessions delete ID   Delete a session
hermes sessions prune       Clean up old sessions (--older-than N days)
hermes sessions stats       Session store statistics
```

### Cron Jobs

```
hermes cron list            List jobs (--all for disabled)
hermes cron create SCHED    Create: '30m', 'every 2h', '0 9 * * *'
hermes cron edit ID         Edit schedule, prompt, delivery
hermes cron pause/resume ID Control job state
hermes cron run ID          Trigger on next tick
hermes cron remove ID       Delete a job
hermes cron status          Scheduler status
```

#### Auditing existing cron jobs

Use this when a cron job has a skill attached, was recently reworked, uses delegation, or may have a stale prompt/model/toolset. **Also use this when ANY cron job fails with a provider/auth error** — check ALL jobs for the same stale provider, because config migrations and provider renames often affect multiple jobs simultaneously.

1. Start with `cronjob(action="list")` or `hermes cron list` to verify job id, schedule, enabled state, delivery, model/provider pinning, attached skills, and enabled toolsets.
2. `cronjob list` only returns a prompt preview. For full prompt audits, read `~/.hermes/cron/jobs.json` and inspect the target job's `prompt` field. Do not rely on preview when checking model names, delegate_task instructions, safety rules, or fallback paths.
3. Compare three sources separately: (a) cron metadata (`model`, `provider`, `enabled_toolsets`, `schedule`), (b) embedded cron prompt, and (c) the referenced skill/SKILL.md. Skill changes do **not** automatically rewrite existing cron prompts; stale instructions can remain embedded in the job.
4. Explicitly distinguish runtime chat model, cron entry/orchestrator model, worker models, delegated curator/subagent models, and fallback models. A model switch in the current chat does not prove the scheduled job prompt was updated.
5. Validate model/provider pins against the **current** Hermes runtime, not just historical cron success:
   - Check `~/.hermes/cron/jobs.json` for the stored `provider`/`model`.
   - Check `~/.hermes/config.yaml` provider keys and `hermes chat --help` provider choices; CLI/provider names can change across Hermes versions.
   - Check the scheduler's actual resolver before declaring a cron provider invalid. Cron execution uses `hermes_cli.runtime_provider.resolve_runtime_provider(requested=<job provider>)`, so configured aliases such as `ollama-local` or `custom` can resolve to runtime `provider: custom` with a local `base_url` even when `hermes chat --provider <alias>` is not accepted by argparse.
   - Smoke-test the pinned model through the actual resolved provider path: either `hermes chat -q 'OK' --provider <currently-valid-cli-provider> --model <model> -t '' -Q` or a direct OpenAI-compatible call to the resolved `base_url` (for example `http://127.0.0.1:11434/v1/chat/completions`).
   - If a cron entry still says a legacy provider such as `custom`, distinguish two cases: (a) resolver/config still maps it to a working endpoint — not an immediate break; (b) resolver/config no longer maps it, while an equivalent current provider works (for example `ollama-cloud` for Ollama cloud models) — report provider-name drift and update only after preserving schedule/delivery/origin/toolsets.
6. Before changing any cron job, report expected vs actual and preserve unrelated fields: schedule, delivery, origin, attached skills, enabled toolsets, workdir, and model/provider unless the change explicitly targets them.
7. When the user corrects or redefines a cron job's model architecture, treat the role mapping as the source of truth and update every affected layer together: cron metadata (`model`/`provider`), embedded prompt, referenced skill/SKILL.md, helper scripts/docstrings/config constants, and any active plan file. Then verify by searching for stale model names, stale role labels (entry/orchestrator/worker/curator/fallback), old timeouts, and obsolete delegation instructions. Do not leave the job in a split-brain state where metadata says one model but the prompt delegates primary work to another.

#### Testing triggered cron jobs

Use this when the user asks to “run/test the cron job now” after creating or modifying a job.

1. Trigger explicitly with `cronjob(action="run", job_id="...")` or `hermes cron run <id>`. This only sets `next_run_at` to “now”; it runs on the next scheduler tick, not synchronously in the command/tool call.
2. Verify the scheduler is alive with `hermes cron status` and note that gateway-hosted cron execution may take several minutes for model-heavy jobs.
3. Poll both metadata and output:
   - `cronjob(action="list")` / `hermes cron list` for `last_run_at`, `last_status`, `last_error`, `last_delivery_error`, and `next_run_at`.
   - `~/.hermes/cron/output/<job_id>/` for a new timestamped `.md` output file.
4. If `next_run_at` is in the past but `last_run_at` has not changed, check whether another scheduler tick is already running before re-triggering:
   ```bash
   lsof ~/.hermes/cron/.tick.lock || fuser -v ~/.hermes/cron/.tick.lock
   ```
   A gateway process holding `.tick.lock` usually means the job is currently executing. Do not assume failure just because `cron list` has not updated; `last_run_at` and the output file are written only after the job finishes.
5. For long jobs, wait at least the job’s expected model/tool timeout window before declaring failure. For multi-worker LLM cron jobs, the slowest worker timeout plus curator time can be several minutes.
6. After completion, read the new output file and verify the report content, delivery status (`last_delivery_error: null`), and any side effects the job claims it made.
7. If the test follows prompt/config hardening or a bug fix, validate the specific regression, not just `last_status: ok`: search the output and touched files for known-bad phrases/patterns, verify expected guardrail text actually appeared in the run prompt/output, and run any relevant secret/stale-claim scans before declaring the fix proven.

Cron schedules are evaluated in the host's local timezone unless configured otherwise. For user-facing reminders in another timezone, check the host timezone (`date '+%Z %z'`) and convert the requested local time before creating the cron expression. Example: a daily 06:00 reminder for a UTC+5 user on a UTC+2 host should use `0 3 * * *`. Use the cron tool's returned `next_run_at` to verify the conversion.

#### Manually updating from git source

When `hermes update` is blocked or unavailable, update from the local git checkout:

```bash
# 1. Switch remote to HTTPS if SSH fails (common after fresh install)
cd ~/.hermes/hermes-agent
git remote set-url origin https://github.com/NousResearch/hermes-agent.git
git pull --ff-only

# 2. Reinstall into the venv (pip may be missing after some updates)
venv/bin/python -m ensurepip --default-pip 2>/dev/null
venv/bin/python -m pip install -e .

# 3. Verify
hermes --version
git log --oneline -1
```

If `pip` is missing from the venv, `ensurepip` restores it. After reinstall, `/restart` the gateway or start a new session for changes to take effect.

### Discovering new Ollama cloud models

Use `ollama show <model>:<tag>-cloud` to probe whether a cloud variant exists (returns architecture metadata on success, `Error: model not found` on failure). Do NOT use `ollama run` or `ollama pull` — those download multi-GB blobs. The `/v1/models` endpoint returns `null` for cloud-proxied models and is not a reliable discovery mechanism. Instead, check `https://ollama.com/library/<model>/tags` for available tags including `cloud` variants. Ollama v0.23 (May 2026) adds `ollama launch claude-desktop` for built-in third-party inference inside Claude Desktop (Cowork + Code).

Known cloud models (May 2026): `deepseek-v4-flash:cloud`, `deepseek-v4-pro:cloud`, `deepseek-v3.1:671b-cloud`, `glm-5.1:cloud`, `glm-5:cloud`, `glm-4.7:cloud`, `glm-4.6:cloud`, `kimi-k2.6:cloud`, `kimi-k2.5:cloud`, `kimi-k2:1t-cloud`, `nemotron-3-super:cloud`, `qwen3-coder-next:cloud`, `qwen3-coder:480b-cloud`, `qwen3.5:cloud`, `qwen3.5:397b-cloud`, `qwen3-vl:235b-cloud`, `qwen3:480b-cloud`, `minimax-m2.5:cloud`, `minimax-m2.1:cloud`, `minimax-m2:cloud`, `gpt-oss:120b-cloud`, `gpt-oss:20b-cloud`, `gemma4:31b-cloud`, `devstral-small-2:24b-cloud`, `ministral-3:14b-cloud`, `ministral-3:8b-cloud`, `ministral-3:3b-cloud`. No `:cloud` tags for: mistral-medium-3.5, nemotron3 (only local 33b), granite4.1 (only local 30b), phi4, llama4, gemma3n, lfm2, laguna-xs.2, medgemma.

### Choosing and pinning a model for cron jobs

When a cron job generates a recurring user-facing message (weather, briefing, reports), benchmark candidate models on the exact same source data and prompt before pinning one. Prefer showing raw model outputs to the user when comparing quality. See `references/model-comparison-reasoning-cost-framing-2026-05-06.md` for the Konstantin-specific correction on treating reasoning/cost/latency as trade-offs rather than negative labels.

Workflow:

1. Fetch or prepare one fixed input payload (for weather, call the weather API once and reuse the same JSON for all models).
2. Run each candidate with the same prompt, temperature, and token limit.
   - Run one model per isolated command/script with its own timeout and result file. Do not benchmark multiple slow models inside one shared sequential timeout; the first timeout can mask later results.
   - For Ollama/OpenAI-compatible local endpoints, direct calls to `http://127.0.0.1:11434/v1/chat/completions` are faster and give usage metrics.
   - For Ollama native `/api/chat`, save a JSON result with at least: model, prompt path/chars, ok, latency, error, output chars, and token/eval counts if returned.
   - Thinking models may spend `max_tokens` on reasoning and return empty `content`; retry with a larger `max_tokens` and prompt them to answer directly if needed.
   - If a full real-task prompt times out, optionally run a smaller real-data mini prompt to distinguish “model unavailable” from “usable only for small batches”; do not let a mini-pass override a full-prompt timeout for cron-primary selection.
3. Compare metrics that match the actual task, not a proxy task. At minimum: latency, output length, token usage if available, factual accuracy, formatting, and whether the result is suitable for Telegram.
   - Treat reasoning tokens, hidden reasoning length, latency, and cost as **trade-off metrics**, not as quality labels. A model that is slower or uses more reasoning can be the right choice if it returns more useful facts, stronger analysis, better coverage, or fewer mistakes for that task. Do not describe a model as merely “прожорливый”/wasteful without evaluating value per task.
   - Conversely, a model succeeding on a deep-analysis task does not overturn a failure on a cron-shaped structured-extraction task; compare by task shape, prompt, token budget, endpoint/provider path, and output contract.
   - For knowledge-distillation or memory-curation cron jobs, add a stricter rubric: the model must propose add/update/remove/skip decisions, include skipped items, avoid secrets/raw logs/task-progress, deduplicate existing docs, distinguish checked facts from hypotheses, and avoid inventing infrastructure or thresholds.
   - Do not present a model as “best” for a task based only on a benchmark from another task; label that as a hypothesis and run a direct task-specific benchmark before pinning.
4. Show raw outputs when the user asks to compare “with eyes,” not just a summary. Separate measured facts from interpretation, confidence, and remaining limitations.
5. Pin the chosen model on the cron job:

```python
cronjob(
    action="update",
    job_id="<job_id>",
    model={"provider": "<validated-provider>", "model": "<validated-model>"},
)
```

For Ollama/Ollama-cloud models, do not assume old examples such as `provider: custom` are still valid. Verify the provider name against the current Hermes CLI/provider registry and config before pinning. Examples that may be valid in different installs include `ollama-cloud`, `ollama-local`, or another configured provider key; use the exact currently working provider, then run a smoke test before declaring the cron fixed.

### Webhooks

```
hermes webhook subscribe N  Create route at /webhooks/<name>
hermes webhook list         List subscriptions
hermes webhook remove NAME  Remove a subscription
hermes webhook test NAME    Send a test POST
```

### Auditing installed plugins by topic/keyword

Use this when the user asks whether Hermes plugins contain a feature, phrase, domain, or suspicious behavior.

1. Check enabled/available plugins first:
   ```bash
   hermes plugins list
   ```
2. Search both user and bundled plugin trees; user plugins alone are not enough:
   ```text
   ~/.hermes/plugins/
   ~/.hermes/hermes-agent/plugins/
   ```
   If a guest/profile instance is relevant, use its actual mounted Hermes home rather than guessing `data/plugins` exists.
3. Search metadata and source/docs separately: `plugin.yaml`, `*.py`, `*.md`, and config files. For fuzzy user wording, include likely typo/translation variants (for example `аромат` as an iPhone autocorrect artifact for `prompt/промпт`, or English/Russian synonyms). **Do not overfit the answer to the typo**: if intent is obvious from context, normalize to the intended term and optionally say once “читаю это как …”; do not build analysis, metaphors, or repeated terminology around the mistaken word.
4. Treat cache/data files as a separate class. Large JSON reference caches can produce substring false positives inside unrelated names (for example `scent` inside `Crescent`). If a hit comes from cache JSON, parse the records and rerun with stricter word/domain patterns before presenting it as evidence.
5. Report evidence by path + line + interpretation. Separate exact domain matches from incidental words such as code comments about UI rewrites, provider `revised_prompt` fields, or changelog text saying an implementation was rewritten.

### Designing Hermes self-improvement / skill-evolution experiments

Use `references/skill-evolution-sandbox-lessons.md` before testing any “self-evolution”, prompt/skill rewriting, behavioral optimization, or agent-policy evolution workflow.

Core rule: require an artifact contract and deterministic fitness before running optimizers. A valid run must produce inspectable artifacts (`candidate.patch`/diff, `score.json`, rationale, eval log) and pass sandbox verification before any production promotion. Prefer evolving small behavioral policies and trace-scored strategies over wholesale `SKILL.md` prompt rewriting.

### Profiles

```
hermes profile list         List all profiles
hermes profile create NAME  Create (--clone, --clone-all, --clone-from)
hermes profile use NAME     Set sticky default
hermes profile delete NAME  Delete a profile
hermes profile show NAME    Show details
hermes profile alias NAME   Manage wrapper scripts
hermes profile rename A B   Rename a profile
hermes profile export NAME  Export to tar.gz
hermes profile import FILE  Import from archive
```

### Credential Pools

```
hermes auth add             Interactive credential wizard
hermes auth list [PROVIDER] List pooled credentials
hermes auth remove P INDEX  Remove by provider + index
hermes auth reset PROVIDER  Clear exhaustion status
```

### Other

```
### Plugins

```
hermes plugins list/install/remove  Plugin management
hermes honcho setup/status  Honcho memory integration (requires honcho plugin)
hermes memory setup/status/off  Memory provider config
hermes completion bash|zsh  Shell completions
hermes acp                  ACP server (IDE integration)
hermes claw migrate         Migrate from OpenClaw
hermes uninstall            Uninstall Hermes
```

#### Auditing and curating Hermes long-term memory

When the user asks to understand, clean up, or configure Hermes long-term memory, treat it as a memory-architecture task rather than immediately enabling a provider.

Recommended workflow:

1. Check current state first:
   ```bash
   hermes memory status
   hermes config | grep -A20 '^memory:'
   ```
   Or inspect `~/.hermes/config.yaml` for `memory.memory_enabled`, `memory.user_profile_enabled`, `memory.provider`, `memory_char_limit`, and `user_char_limit`.
2. Explain the built-in layers clearly:
   - `~/.hermes/memories/USER.md` — user identity, preferences, communication style; ~1,375 chars by default.
   - `~/.hermes/memories/MEMORY.md` — stable environment facts, tool quirks, conventions; ~2,200 chars by default.
   - `session_search` — SQLite/FTS5 search over past sessions, for detailed history rather than always-in-context facts.
   - Skills — reusable procedures/workflows; do not store procedures as ordinary memory entries.
3. Before adding memory, consolidate duplicates and keep entries declarative, compact, and durable. Avoid diary entries, task progress, raw logs, secrets, and facts that are easy to rediscover.
4. For users who dislike memory bloat, prefer curated built-in memory + `session_search` + skills as the baseline. Do not enable automatic fact extraction unless explicitly requested.
5. If evaluating external providers, compare them by locality, API-key requirements, automatic extraction behavior, storage path, retrieval mechanism, and rollback plan. In a local/privacy-first setup, `holographic` is the first provider to investigate because it is local SQLite/FTS5 and its `auto_extract` default is false; still verify config and behavior before enabling.
6. If enabling a provider, make a config backup, set the provider explicitly, keep auto-extraction disabled for cautious users, run `hermes memory status`, perform a small test add/search, and document how to revert (`hermes memory off` or reset `memory.provider`).

Remember: built-in memory updates persist immediately but are injected into the prompt as a frozen snapshot at session start, so changes may require `/reset` or a new session to appear in the system prompt.

#### Enabling the Holographic memory provider

When the user wants to activate `holographic` as the external memory provider, follow this workflow (plan-only unless the user explicitly asks to execute):

1. **Check NumPy in the Hermes venv** (not system Python). The plugin lives in the Hermes process — if `numpy` is only installed system-wide, HRR algebra silently degrades to FTS5 fallback.
   ```bash
   <hermes_home>/hermes-agent/venv/bin/python3 -c "import numpy; print(numpy.__version__)"
   ```
   If missing: install into the venv, not the system. System `pip`/`apt` won't help.

2. **Backup config:**
   ```bash
   cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-$(date +%Y%m%d-%H%M%S)
   ```

3. **Set the provider:**
   ```bash
   hermes config set memory.provider holographic
   ```
   The provider becomes available immediately for `hermes memory status`, but its tools (`fact_store`, `fact_feedback`) and SQLite DB are **lazy** — they appear only after a new session (`/reset`).

4. **Ensure auto_extract is off** (cautious users):
   ```bash
   hermes config set plugins.hermes-memory-store.auto_extract false
   ```

5. **Verify:**
   ```bash
   hermes memory status
   ```
   Expected: `Provider: holographic` with `(local) ← active`.

6. **Test after `/reset`** — in a new session, `fact_store` and `fact_feedback` tools appear. Verify: add → search → list → feedback round-trip. The DB file (`memory_store.db`) is created on first `initialize()` call at session start, not at config time.

7. **Rollback:**
   ```bash
   hermes config set memory.provider ''
   ```
   Then `/reset`. The DB file remains on disk; delete it manually if desired.

Pitfalls:
- `hermes config set plugins.hermes-memory-store.auto_extract false` is a **plugin** config path, not a top-level `memory` key. The plugin reads `plugins.hermes-memory-store` from `config.yaml`.
- The plugin **mirrors** built-in `memory(action='add')` calls via `on_memory_write()` — facts created with the ordinary `memory` tool also land in holographic. This is by design, not a bug.
- **FTS5 AND/OR fallback**: As of May 2026, `_fts_candidates` in `retrieval.py` was patched with OR fallback for multi-word queries. Without this fix, `fact_store search` with 2+ words returns 0 unless a single fact contains ALL words. If search returns 0 unexpectedly on multi-word queries, check `retrieval.py` for the OR retry block. See `holographic-memory-hygiene` skill → `references/fts5-or-fallback-and-cyrillic-entities.md`.
- **Cyrillic entity extraction**: As of May 2026, `_extract_entities` in `store.py` was patched to support Cyrillic Title-case, single-word entities, backtick-quoted terms, and a stop list. Without this fix, `probe('Konstantin')` misses most preference facts; `reason()` cross-entity queries are incomplete. After patching, run `store.rebuild_all_vectors()` to reindex. See `holographic-memory-hygiene` skill → `references/fts5-or-fallback-and-cyrillic-entities.md`.
- If `fact_store`/`fact_feedback` returns `database is locked`, do not repeatedly retry writes or assume DB corruption. Use `references/holographic-memory-sqlite-locks.md`: check `hermes memory status`, WAL/SHM files, `lsof`/`fuser`, `/proc/locks`, read-only `PRAGMA integrity_check`, and a rollback-only `BEGIN IMMEDIATE` probe. If the gateway process holds the WAL write lock, restart the gateway only after confirming no writes are in progress, then verify the lock cleared.
- Protected built-in memory writes must not be bypassed through holographic memory. If `memory(add target=user)` is denied because `USER.md` requires explicit approval or times out as a protected context-file write, do not silently write the same user preference to `fact_store` as a fallback. Report that `USER.md` was not changed, give the exact proposed text or retry path, and use `fact_store` only if the user explicitly approves that alternate store/scope.

#### Backing up the personal Hermes overlay

Use this when the user asks to back up Hermes Agent settings, memory, skills, plugins, cron, or custom docs that live on top of the upstream `~/.hermes/hermes-agent` repo. See `references/hermes-personal-overlay-backup-2026-05-06.md` for Konstantin's session-specific scope and inventory. For the hybrid retention design that emerged later (daily plaintext/redacted diff + weekly/on-change encrypted refresh), see `references/hermes-hybrid-backup-retention-2026-05-06.md`.

For backup design recommendations to Konstantin, lead with a short actionable recommendation before any rationale. If he asks for a recommendation specifically, keep it concise: decision, 3–4 actions, final next step. Do not repeat the full storage-model explanation unless requested.

Hybrid retention default for this repo class: keep `main` as the latest restoreable snapshot; update plaintext/redacted overlay daily; refresh heavy `age` encrypted state/session bundles weekly and secrets weekly plus on safe metadata change; verify freshness and require a single active encrypted generation in HEAD. Do not use daily branch-per-backup, binary diffs of encrypted archives, or plaintext secret/state diffs.

Workflow:

1. Treat `~/.hermes/hermes-agent/` as upstream source code and do not vendor the full repo into a personal backup. If Konstantin asks for “CLI backup” or source patches, capture reproducible state instead: git remote/branch/HEAD manifest, tracked `git diff --binary --full-index`, and safe untracked source/test files. Also include local skill-related CLIs from `/home/konstantin/code/clis` as safe source snapshots when they are part of the requested scope.
2. Inventory `~/.hermes` without printing secret values. Classify paths as: plaintext include, redacted transform, encrypted-only, optional encrypted archive, or exclude.
3. For plaintext backup, prefer durable overlay state: `SOUL.md`, `memories/USER.md`, `memories/MEMORY.md`, `skills/`, `plugins/`, `cron/jobs.json`, local docs/plans, and redacted config/env inventories.
4. For holographic/local SQLite memory, create a consistent SQLite snapshot with backup API or `sqlite3 .backup`; do not copy live `*-wal`/`*-shm` files. Verify the copied DB with `PRAGMA integrity_check`.
5. Never commit raw `.env`, OAuth `auth.json`, service-account JSON, app passwords, private keys, or credential files in plaintext, even if the GitHub repo is private. Use encrypted bundles only after the user chooses GPG/age/passphrase policy. For Konstantin's proven bootstrap, `age` SSH-recipient encryption was used; see the reference file for the exact restore assumptions.
6. Exclude runtime noise and privacy-heavy history by default: `state.db`, raw sessions, logs, caches, media, locks, pids, update markers, and model caches. Include `state.db` and raw sessions only when explicitly requested, and then encrypted-only. For live SQLite state, create a consistent backup before archiving.
7. Before clone/push/commit, write a durable plan if the work is multi-step or changes Konstantin's operational Hermes state. Include include/exclude rules, secret handling, verification criteria, and machine-readable `Current status:`. Update and archive the plan after completion.
8. Build a deny-by-default `.gitignore` in the backup repo: block raw secrets, raw sessions, raw DBs, caches, logs, temp files, and credential sidecars; explicitly allow approved plaintext overlay paths plus encrypted artifacts/manifests.
9. Sanitize plaintext copies before scanning/committing. Docs and skill examples can contain token-shaped placeholders (for example GitHub-token-looking examples) that are not real secrets but still trigger scanners; replace high-risk token-shaped literals in the backup copy rather than weakening the scanner.
10. Verify before commit/push with: manifest checksums, `age` test-decrypt/listing for each encrypted artifact, SQLite `PRAGMA integrity_check`, raw-denied-filename scan, high-risk secret regex scan, GitHub hard file-limit check, and `git status`.
11. If encrypted artifacts approach GitHub limits, split below the hard 100 MB limit. GitHub may still warn above the recommended 50 MB; for long-term hygiene, prefer chunks under ~49 MB or Git LFS if installed/configured.

Pitfalls:
- Private GitHub is not a substitute for encryption of raw credentials. The safe default is redacted plaintext + optional encrypted archives, not raw dotfiles.
- `age` can encrypt to an SSH public key without exposing passphrases in chat/tool output, but restore/test-decrypt requires the matching private key to remain locally available.
- A successful `git push` with large-file warnings is still a valid push, but report the warning separately from verification success.

#### File-backed long-term memory docs

When built-in `USER.md`/`MEMORY.md` is too small but a full external memory provider would be overkill, use a file-backed curated knowledge base and keep built-in memory as an index.

Class trigger: use this pattern when a user wants durable, auditable long-term context for Hermes without automatic semantic memory extraction, especially after memory-bloat concerns.

Pattern:

1. Create a stable docs directory, e.g. `/home/<user>/docs/` or another user-approved path.
2. Do **not** just copy current memory entries into several files. Design the files around future retrieval questions: “who is the user?”, “how is the system wired?”, “how do I repeat a known operation?”, and “how do I maintain this knowledge base?”
3. A practical starter structure:
   - `README.md` — index, when to read which file, what belongs in docs vs session_search/skills/memory, and formatting rules.
   - `user-context.md` — expanded user/work context, communication contract, irritants, useful hypotheses, open questions; not a duplicate of compact `USER.md`.
   - `infrastructure.md` — system map, stable paths, providers/models, auth invariants, cron automations, memory architecture, operational risks.
   - `runbooks.md` — verified procedures and checklists; promote large/repeated procedures to skills.
   - `plans/` — written plans for multi-step work: goals, scope, steps, verification, risks, and status. Treat it as an intent ledger for agents; if a non-trivial step is not written in the plan, do not assume it will happen.
4. Put only a short pointer in built-in `MEMORY.md`, for example:
   ```text
   Long-term docs live in /home/<user>/docs/: README.md, user-context.md, infrastructure.md, runbooks.md, plans/. Read relevant file before changing Hermes/memory/cron/Codex/Ollama setup. Multi-step work needs a plan in plans/.
   ```
5. Move detailed environment facts out of `MEMORY.md` into the appropriate Markdown file, leaving only critical warnings or pointers in built-in memory.
6. For users who rely on explicit planning with AI agents, create `plans/README.md` with triggers, naming convention (`YYYY-MM-DD-short-topic.md`), a template (`Goal`, `Context`, `Non-goals`, `Steps`, `Verification`, `Risks / pitfalls`, `Status`, `Notes`), and rules to update the plan as scope changes.
7. If the first structure feels like a mechanical memory dump, revise it: add an index, separate facts from rationale/pitfalls/open questions, rename generic `procedures.md` to `runbooks.md`, add `plans/` as the intent layer, and remove metaprocess files that only duplicate built-in memory policy.
8. Verify files exist and sample-read at least one created/updated file before reporting success.

Use this pattern for cautious users who prefer compact curated memory, dislike automatic extraction, or want auditable long-term context without enabling a semantic memory provider.

---

## Slash Commands (In-Session)

Type these during an interactive chat session.

### Session Control
```
/new (/reset)        Fresh session
/clear               Clear screen + new session (CLI)
/retry               Resend last message
/undo                Remove last exchange
/title [name]        Name the session
/compress            Manually compress context
/stop                Kill background processes
/rollback [N]        Restore filesystem checkpoint
/background <prompt> Run prompt in background
/queue <prompt>      Queue for next turn
/resume [name]       Resume a named session
```

### Configuration
```
/config              Show config (CLI)
/model [name]        Show or change model
/personality [name]  Set personality
/reasoning [level]   Set reasoning (none|minimal|low|medium|high|xhigh|show|hide)
/verbose             Cycle: off → new → all → verbose
/voice [on|off|tts]  Voice mode
/yolo                Toggle approval bypass
/skin [name]         Change theme (CLI)
/statusbar           Toggle status bar (CLI)
```

### Tools & Skills
```
/tools               Manage tools (CLI)
/toolsets            List toolsets (CLI)
/skills              Search/install skills (CLI)
/skill <name>        Load a skill into session
/cron                Manage cron jobs (CLI)
/reload-mcp          Reload MCP servers
/plugins             List plugins (CLI)
```

### Gateway
```
/approve             Approve a pending command (gateway)
/deny                Deny a pending command (gateway)
/restart             Restart gateway (gateway)
/sethome             Set current chat as home channel (gateway)
/update              Update Hermes to latest (gateway)
/platforms (/gateway) Show platform connection status (gateway)
```

### Utility
```
/branch (/fork)      Branch the current session
/fast                Toggle priority/fast processing
/browser             Open CDP browser connection
/history             Show conversation history (CLI)
/save                Save conversation to file (CLI)
/paste               Attach clipboard image (CLI)
/image               Attach local image file (CLI)
```

### Info
```
/help                Show commands
/commands [page]     Browse all commands (gateway)
/usage               Token usage
/insights [days]     Usage analytics
/status              Session info (gateway)
/profile             Active profile info
```

### Exit
```
/quit (/exit, /q)    Exit CLI
```

---

## Key Paths & Config

```
~/.hermes/config.yaml       Main configuration
~/.hermes/.env              API keys and secrets
$HERMES_HOME/skills/        Installed skills
~/.hermes/sessions/         Session transcripts
~/.hermes/logs/             Gateway and error logs
~/.hermes/auth.json         OAuth tokens and credential pools
~/.hermes/hermes-agent/     Source code (if git-installed)
```

Profiles use `~/.hermes/profiles/<name>/` with the same layout.

### Config Sections

Edit with `hermes config edit` or `hermes config set section.key value`.

| Section | Key options |
|---------|-------------|
| `model` | `default`, `provider`, `base_url`, `api_key`, `context_length` |
| `agent` | `max_turns` (90), `tool_use_enforcement` |
| `terminal` | `backend` (local/docker/ssh/modal), `cwd`, `timeout` (180) |
| `compression` | `enabled`, `threshold` (0.50), `target_ratio` (0.20) |
| `display` | `skin`, `tool_progress`, `show_reasoning`, `show_cost` |
| `stt` | `enabled`, `provider` (local/groq/openai/mistral) |
| `tts` | `provider` (edge/elevenlabs/openai/minimax/mistral/neutts) |
| `memory` | `memory_enabled`, `user_profile_enabled`, `provider` |
| `security` | `tirith_enabled`, `website_blocklist` |
| `delegation` | `model`, `provider`, `base_url`, `api_key`, `max_iterations` (50), `reasoning_effort` |
| `checkpoints` | `enabled`, `max_snapshots` (50) |

Full config reference: https://hermes-agent.nousresearch.com/docs/user-guide/configuration

### Providers

20+ providers supported. Set via `hermes model` or `hermes setup`.

| Provider | Auth | Key env var |
|----------|------|-------------|
| OpenRouter | API key | `OPENROUTER_API_KEY` |
| Anthropic | API key | `ANTHROPIC_API_KEY` |
| Nous Portal | OAuth | `hermes auth` |
| OpenAI Codex | OAuth | `hermes auth` |
| GitHub Copilot | Token | `COPILOT_GITHUB_TOKEN` |
| Google Gemini | API key | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| DeepSeek | API key | `DEEPSEEK_API_KEY` |
| xAI / Grok | API key | `XAI_API_KEY` |
| Hugging Face | Token | `HF_TOKEN` |
| Z.AI / GLM | API key | `GLM_API_KEY` |
| MiniMax | API key | `MINIMAX_API_KEY` |
| MiniMax CN | API key | `MINIMAX_CN_API_KEY` |
| Kimi / Moonshot | API key | `KIMI_API_KEY` |
| Alibaba / DashScope | API key | `DASHSCOPE_API_KEY` |
| Xiaomi MiMo | API key | `XIAOMI_API_KEY` |
| Kilo Code | API key | `KILOCODE_API_KEY` |
| AI Gateway (Vercel) | API key | `AI_GATEWAY_API_KEY` |
| OpenCode Zen | API key | `OPENCODE_ZEN_API_KEY` |
| OpenCode Go | API key | `OPENCODE_GO_API_KEY` |
| Qwen OAuth | OAuth | `hermes login --provider qwen-oauth` |
| Custom endpoint | Config | `model.base_url` + `model.api_key` in config.yaml |
| GitHub Copilot ACP | External | `COPILOT_CLI_PATH` or Copilot CLI |

Full provider docs: https://hermes-agent.nousresearch.com/docs/integrations/providers

### Toolsets

Enable/disable via `hermes tools` (interactive) or `hermes tools enable/disable NAME`.

| Toolset | What it provides |
|---------|-----------------|
| `web` | Web search and content extraction |
| `browser` | Browser automation (Browserbase, Camofox, or local Chromium) |
| `terminal` | Shell commands and process management |
| `file` | File read/write/search/patch |
| `code_execution` | Sandboxed Python execution |
| `vision` | Image analysis |
| `image_gen` | AI image generation |
| `tts` | Text-to-speech |
| `skills` | Skill browsing and management |
| `memory` | Persistent cross-session memory; also exposes holographic `fact_store` / `fact_feedback` tools when that provider is active. For cron jobs, add `memory` to `enabled_toolsets`—there is no separate `fact_store` toolset. |
| `session_search` | Search past conversations |
| `delegation` | Subagent task delegation |
| `cronjob` | Scheduled task management |
| `clarify` | Ask user clarifying questions |
| `messaging` | Cross-platform message sending |
| `search` | Web search only (subset of `web`) |
| `todo` | In-session task planning and tracking |
| `rl` | Reinforcement learning tools (off by default) |
| `moa` | Mixture of Agents (off by default) |
| `homeassistant` | Smart home control (off by default) |

Tool changes take effect on `/reset` (new session). They do NOT apply mid-conversation to preserve prompt caching.

---

## Security & Privacy Toggles

Common "why is Hermes doing X to my output / tool calls / commands?" toggles — and the exact commands to change them. Most of these need a fresh session (`/reset` in chat, or start a new `hermes` invocation) because they're read once at startup.

### Secret redaction in tool output

Hermes auto-redacts strings that look like API keys, tokens, and secrets in all tool output (terminal stdout, `read_file`, web content, subagent summaries, etc.) so the model never sees raw credentials. If the user is intentionally working with mock tokens, share-management tokens, or their own secrets and the redaction is getting in the way:

```bash
hermes config set security.redact_secrets false      # disable globally
```

**Restart required.** `security.redact_secrets` is snapshotted at import time — setting it mid-session (e.g. via `export HERMES_REDACT_SECRETS=false` from a tool call) will NOT take effect for the running process. Tell the user to run `hermes config set security.redact_secrets false` in a terminal, then start a new session. This is deliberate — it prevents an LLM from turning off redaction on itself mid-task.

Re-enable with:
```bash
hermes config set security.redact_secrets true
```

### PII redaction in gateway messages

Separate from secret redaction. When enabled, the gateway hashes user IDs and strips phone numbers from the session context before it reaches the model:

```bash
hermes config set privacy.redact_pii true    # enable
hermes config set privacy.redact_pii false   # disable (default)
```

### Command approval prompts

By default (`approvals.mode: manual`), Hermes prompts the user before running shell commands flagged as destructive (`rm -rf`, `git reset --hard`, etc.). The modes are:

- `manual` — always prompt (default)
- `smart` — use an auxiliary LLM to auto-approve low-risk commands, prompt on high-risk
- `off` — skip all approval prompts (equivalent to `--yolo`)

```bash
hermes config set approvals.mode smart       # recommended middle ground
hermes config set approvals.mode off         # bypass everything (not recommended)
```

Per-invocation bypass without changing config:
- `hermes --yolo …`
- `export HERMES_YOLO_MODE=1`

Note: YOLO / `approvals.mode: off` does NOT turn off secret redaction. They are independent.

### Shell hooks allowlist

Some shell-hook integrations require explicit allowlisting before they fire. Managed via `~/.hermes/shell-hooks-allowlist.json` — prompted interactively the first time a hook wants to run.

### Disabling the web/browser/image-gen tools

To keep the model away from network or media tools entirely, open `hermes tools` and toggle per-platform. Takes effect on next session (`/reset`). See the Tools & Skills section above.

---

## Voice & Transcription

### STT (Voice → Text)

Voice messages from messaging platforms are auto-transcribed.

Provider priority (auto-detected):
1. **Local faster-whisper** — free, no API key: `pip install faster-whisper`
2. **Groq Whisper** — free tier: set `GROQ_API_KEY`
3. **OpenAI Whisper** — paid: set `VOICE_TOOLS_OPENAI_KEY`
4. **Mistral Voxtral** — set `MISTRAL_API_KEY`

Config:
```yaml
stt:
  enabled: true
  provider: local        # local, groq, openai, mistral
  local:
    model: base          # tiny, base, small, medium, large-v3
```

### TTS (Text → Voice)

| Provider | Env var | Free? |
|----------|---------|-------|
| Edge TTS | None | Yes (default) |
| ElevenLabs | `ELEVENLABS_API_KEY` | Free tier |
| OpenAI | `VOICE_TOOLS_OPENAI_KEY` | Paid |
| MiniMax | `MINIMAX_API_KEY` | Paid |
| Mistral (Voxtral) | `MISTRAL_API_KEY` | Paid |
| NeuTTS (local) | None (`pip install neutts[all]` + `espeak-ng`) | Free |

Voice commands: `/voice on` (voice-to-voice), `/voice tts` (always voice), `/voice off`.

---

## Spawning Additional Hermes Instances

Run additional Hermes processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `hermes` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### One-Shot Mode

```
terminal(command="hermes chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="hermes chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Hermes uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'hermes'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'hermes --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'hermes --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `hermes chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **For scheduled tasks**, use the `cronjob` tool instead of spawning — handles delivery and retry

---

### Updating Hermes manually

When `hermes update` is blocked or unavailable, update from the git checkout:

```bash
cd ~/.hermes/hermes-agent
git remote set-url origin https://github.com/NousResearch/hermes-agent.git  # if SSH fails
git pull --ff-only
source venv/bin/activate  # or .venv
python -m ensurepip 2>/dev/null  # pip may be missing from the venv
python -m pip install -e .
hermes --version  # verify
```

After updating, restart the gateway (`/restart` in a Telegram session) or wait for the next session — config changes and code updates take effect on restart.

Pitfalls:
- `git pull` over SSH (`git@github.com`) fails if no SSH key for the repo; switch to HTTPS.
- The venv may not have `pip` installed — `python -m ensurepip` restores it.
- `hermes update` may be blocked by approval settings; manual `pip install -e .` bypasses that.

### Troubleshooting

### Voice not working
1. Check `stt.enabled: true` in config.yaml
2. Verify provider: `pip install faster-whisper` or set API key
3. In gateway: `/restart`. In CLI: exit and relaunch.

### Tool not available
1. `hermes tools` — check if toolset is enabled for your platform
2. Some tools need env vars (check `.env`)
3. `/reset` after enabling tools

### Model/provider issues
1. `hermes doctor` — check config and dependencies
2. `hermes login` — re-authenticate OAuth providers
3. Check `.env` has the right API key
4. **Copilot 403**: `gh auth login` tokens do NOT work for Copilot API. You must use the Copilot-specific OAuth device code flow via `hermes model` → GitHub Copilot.

### Changes not taking effect
- **Tools/skills:** `/reset` starts a new session with updated toolset
- **Config changes:** In gateway: `/restart`. In CLI: exit and relaunch.
- **Code changes:** Restart the CLI or gateway process
- **SOUL.md / system-prompt behavior:** `~/.hermes/SOUL.md` is read when Hermes builds the system prompt snapshot. The prompt is cached per session, and gateway continuations may reuse the stored `system_prompt` from SessionDB instead of rereading SOUL from disk each turn. After editing SOUL, verify in a fresh session/reset/restart before claiming the new constitution is active.

### Skills not showing
1. `hermes skills list` — verify installed
2. `hermes skills config` — check platform enablement
3. Load explicitly: `/skill name` or `hermes -s name`

### Gateway issues
Check logs first:
```bash
grep -i "failed to send\|error" ~/.hermes/logs/gateway.log | tail -20
```

Common gateway problems:
- **Gateway dies on SSH logout**: Enable linger: `sudo loginctl enable-linger $USER`
- **Gateway dies on WSL2 close**: WSL2 requires `systemd=true` in `/etc/wsl.conf` for systemd services to work. Without it, gateway falls back to `nohup` (dies when session closes).
- **Gateway crash loop**: Reset the failed state: `systemctl --user reset-failed hermes-gateway`

#### SOUL.md missing, shortened, or changed

Use `references/soul-md-audit-recovery.md` when a user asks where `SOUL.md` went, why behavior rules disappeared, or whether the Hermes persona/behavior constitution changed. Check the live main `~/.hermes/SOUL.md`, distinguish it from guest instance files, compare against backups, and report paths/sizes/timestamps/diff before proposing restoration. `SOUL.md` is a DO-NOT-EDIT file for Konstantin: do not restore or rewrite it without explicit approval.

#### Stale SessionDB “open sessions”

Use `references/sessiondb-stale-open-sessions.md` when a dashboard, monitor, or direct SQLite query reports many Hermes `open sessions` from `~/.hermes/state.db`.

Use `references/guest-docker-dashboard-telemetry.md` when adding or troubleshooting dashboard telemetry for a separate guest Hermes Agent instance running in Docker; keep it separate from the primary local gateway status.

Key rule: `sessions.ended_at IS NULL` is a logical SessionDB state, not proof of live stuck processes. First distinguish live processes from stale DB rows, then separate `open`, `recent/active`, and `stale_open` counts. If cleanup is approved, back up the DB and close only clearly stale rows with an explicit audit reason such as `end_reason='stale_cleanup'` rather than deleting them.

For monitoring/dashboard code, do not label raw `COUNT(*) WHERE ended_at IS NULL` as active work. Prefer last-activity logic based on `COALESCE(MAX(messages.timestamp), sessions.started_at)` and a configurable recency window. If the user asks “why did this happen,” correlate stale rows with gateway restarts, drain timeouts, compression/session splits, provider/model errors, ENOSPC, and SessionStore-vs-SessionDB lifecycle before declaring the issue fixed.

### Platform-specific issues
- **Discord bot silent**: Must enable **Message Content Intent** in Bot → Privileged Gateway Intents.
- **Slack bot only works in DMs**: Must subscribe to `message.channels` event. Without it, the bot ignores public channels.
- **Windows HTTP 400 "No models provided"**: Config file encoding issue (BOM). Ensure `config.yaml` is saved as UTF-8 without BOM.

### Adding models to a custom provider (e.g., ollama-local)

Edit `~/.hermes/config.yaml` and add model entries under the provider's `models` key:

```yaml
providers:
  ollama-local:
    base_url: http://127.0.0.1:11434/v1
    model: glm-5.1:cloud
    models:
      glm-5.1:cloud: {}
      deepseek-v4-flash:cloud: {}
      kimi-k2.6:cloud: {}
```

Available models can be discovered with `ollama list`. For cloud models that are not already listed locally, probe exact tags with `ollama show <model>:<tag>-cloud` or inspect `https://ollama.com/library/<model>` for `*-cloud` tags. Example: `gemma4:cloud` is invalid; the cloud tag is `gemma4:31b-cloud`. `gpt-oss:20b-cloud` can be validated with `ollama show gpt-oss:20b-cloud` even before it appears in `ollama list`. DeepSeek V4 Pro's verified Ollama cloud tag is `deepseek-v4-pro:cloud` (not `deepseek-v4pro:cloud` or `deepseek-v4:cloud`).

For reasoning/thinking cloud models, prefer `ollama show <model>` as the availability check. A quick `ollama run` smoke test can hang or spend minutes in `Thinking...` even when the model is valid.

**BLOCKED PATH — `ollama run` for cloud models:** Never use `ollama run <model>:<tag>-cloud` for cloud-tagged models in `execute_code` or the terminal tool. Cloud models are remote proxies; `ollama run` treats them as local and pulls all blob layers (~5–7 GB per model), filling the disk. Three models × partial pull = disk full (ENOSPC, April 29 2026: `ollama run` for ensemble workers filled 19 GB, crashed Hermes gateway). Use the Ollama HTTP API (`http://127.0.0.1:11434/v1/chat/completions`) or Hermes' built-in provider (`ollama-local`) to call cloud models without local blob downloads. If an ensemble or batch calls multiple Ollama models, always use the API path, never `ollama run`.

**Provider name migration — `ollama-cloud` → custom provider:** Older cron jobs or configs may reference `ollama-cloud` as a provider name. If the runtime config only defines `ollama-local` (or another custom provider key), `ollama-cloud` will fail with `RuntimeError: Provider 'ollama-cloud' is set in config.yaml but no API key was found`. Fix: update the cron job's provider to the working config key (e.g., `ollama-local`). Always audit ALL cron jobs after a provider rename — a single missed job will silently fail. Use `cronjob(action="list")` and check every job's `provider` field against `~/.hermes/config.yaml` providers.

Key nuance: `ollama-local` (localhost endpoint `http://127.0.0.1:11434/v1`) does **not** require an API key. Models routed through `ollama-local` work even when `OLLAMA_API_KEY` is unset or commented out in `.env`. The `RuntimeError` about missing API keys only fires for providers that expect one (like `ollama-cloud` or cloud proxies). When migrating a cron job from a broken provider to `ollama-local`, smoke-test with `cronjob(action="run", job_id="...")` to confirm the fix before declaring success — `last_status: ok` and `last_delivery_error: null` are the definitive signals.

Models will appear in `/model` menu after `/restart` (gateway) or new session (CLI).

### Importing Codex CLI OAuth tokens

If Codex CLI is installed and authenticated (`~/.codex/auth.json` exists), but Hermes shows "codex_auth_missing", import tokens into Hermes' provider store. Hermes expects provider credentials under `providers.openai-codex`, not at the auth file top level.

```python
import json
from pathlib import Path

with open(Path.home() / '.codex' / 'auth.json') as f:
    codex = json.load(f)

auth_path = Path.home() / '.hermes' / 'auth.json'
if auth_path.exists():
    with open(auth_path) as f:
        hermes_auth = json.load(f)
else:
    hermes_auth = {}

providers = hermes_auth.setdefault('providers', {})
providers['openai-codex'] = {
    'tokens': {
        'access_token': codex['tokens']['access_token'],
        'refresh_token': codex['tokens']['refresh_token'],
        'id_token': codex['tokens']['id_token'],
    },
    'last_refresh': codex.get('last_refresh'),
    'auth_mode': 'chatgpt',
}
hermes_auth['active_provider'] = 'openai-codex'

# Clean up the common wrong shape from manual imports, if present.
hermes_auth.pop('openai-codex', None)

with open(auth_path, 'w') as f:
    json.dump(hermes_auth, f, indent=2)
```

Verify without printing secrets:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / '.hermes' / 'auth.json'
d = json.load(open(p))
state = d.get('providers', {}).get('openai-codex', {})
print('providers:', list(d.get('providers', {})))
print('token keys:', list(state.get('tokens', {})))
print('auth_mode:', state.get('auth_mode'))
PY
```

Or simply run `hermes login --provider openai-codex` to authenticate via the browser OAuth flow directly.

### Auxiliary models not working
If `auxiliary` tasks (vision, compression, session_search) fail silently, the `auto` provider can't find a backend. Either set `OPENROUTER_API_KEY` or `GOOGLE_API_KEY`, or explicitly configure each auxiliary task's provider:
```bash
hermes config set auxiliary.vision.provider <your_provider>
hermes config set auxiliary.vision.model <model_name>
```

---

## Where to Find Things

| Looking for... | Location |
|----------------|----------|
| Config options | `hermes config edit` or [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) |
| Available tools | `hermes tools list` or [Tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference) |
| Slash commands | `/help` in session or [Slash commands reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands) |
| Skills catalog | `hermes skills browse` or [Skills catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `hermes model` or [Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers) |
| Platform setup | `hermes gateway setup` or [Messaging docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) |
| MCP servers | `hermes mcp list` or [MCP guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) |
| Profiles | `hermes profile list` or [Profiles docs](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) |
| Cron jobs | `hermes cron list` or [Cron docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Memory | `hermes memory status` or [Memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) |
| Env variables | `hermes config env-path` or [Env vars reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) |
| CLI commands | `hermes --help` or [CLI reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands) |
| Gateway logs | `~/.hermes/logs/gateway.log` |
| Session files | `~/.hermes/sessions/` or `hermes sessions browse` |
| Source code | `~/.hermes/hermes-agent/` |

---

## Contributor Quick Reference

For occasional contributors and PR authors. Full developer docs: https://hermes-agent.nousresearch.com/docs/developer-guide/

### Project Layout

```
hermes-agent/
├── run_agent.py          # AIAgent — core conversation loop
├── model_tools.py        # Tool discovery and dispatch
├── toolsets.py           # Toolset definitions
├── cli.py                # Interactive CLI (HermesCLI)
├── hermes_state.py       # SQLite session store
├── agent/                # Prompt builder, context compression, memory, model routing, credential pooling, skill dispatch
├── hermes_cli/           # CLI subcommands, config, setup, commands
│   ├── commands.py       # Slash command registry (CommandDef)
│   ├── config.py         # DEFAULT_CONFIG, env var definitions
│   └── main.py           # CLI entry point and argparse
├── tools/                # One file per tool
│   └── registry.py       # Central tool registry
├── gateway/              # Messaging gateway
│   └── platforms/        # Platform adapters (telegram, discord, etc.)
├── cron/                 # Job scheduler
├── tests/                # ~3000 pytest tests
└── website/              # Docusaurus docs site
```

Config: `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys).

### Planning a User Plugin for an External API

Use this when designing a Hermes **user plugin** that wraps an external API or reuses code from another local project.

Prefer a user plugin under `~/.hermes/plugins/<plugin-name>/` when the integration is personal/local and does not need to modify Hermes core. Use a core tool only when the integration belongs in Hermes itself.

Recommended workflow:

1. **Survey existing code and dependencies first — map the functional dependency chain, not just files.** If reusing another project's module, inspect its import chain and configuration requirements. Avoid direct imports when they pull unrelated settings, credentials, framework startup, Telegram/WebApp auth, database connections, or other side effects into Hermes startup. **Critically: do not copy a layer without the infrastructure that keeps it alive.** A cache without its refresh/fetch mechanism is dead data. An enrichment pipeline without its reference data lookups produces raw codes. Map the chain: data source (REST/GraphQL endpoints) → persistence/refresh (cache TTL, file storage, API fetch) → domain models (reference data models, not just transaction models) → enrichment/resolution (name lookups, airport→city chains, duration calculations) → enriched output contract (DTOs with human-readable names, not just IATA codes). Each layer depends on the previous; skipping one breaks everything downstream. Also analyze the UI/WebApp layer functionally (city search by name, sorting, filtering, popular routes) — these are capabilities, not just rendering, and may belong in the plugin as tool parameters or post-processing.
2. **Choose self-contained reuse by default.** Copy or extract the minimal domain layer needed by the plugin (models, parsers, API queries, small helpers) rather than importing an application package that requires unrelated env vars. Keep the plugin independent from UI/web handlers and app lifecycle code.
3. **Use plugin conventions:**
   ```text
   ~/.hermes/plugins/<name>/
   ├── plugin.yaml
   ├── __init__.py      # register(ctx)
   ├── schemas.py       # tool schemas shown to the model
   └── tools.py/client.py
   ```
4. **Gate credentials explicitly.** Put secrets in `~/.hermes/.env` via `requires_env`; put non-secret settings in config or documented env vars. Prefer auth headers over query parameters for API tokens because URLs are commonly logged. If migrating a credential from another local project, require an explicit user choice, copy without printing the value, preserve `.env` permissions, verify exact key counts/lengths only, and do not keep the old project as a runtime dependency.
5. **Design the tool contract for model use.** Keep the first tool narrow and deterministic: one clear operation, strict JSON-schema-style guidance, bounded `limit`, explicit date/enum formats, and output that includes `success`, `error`/`warnings`, source, and enough normalized data for a concise answer. Treat the schema as guidance, not a security boundary: perform real validation/clamping in Python, especially when the active model/provider may be an Ollama cloud model where `json_schema` enforcement is unreliable or unavailable. Prefer `json_object`-style outputs plus enums/descriptions in prompts/schemas and a robust handler that tolerates malformed/missing args.
6. **Harden external API calls.** Add explicit timeout, structured handling for 4xx/5xx, `429 Retry-After`, malformed JSON, and upstream semantic errors. Return JSON error strings instead of raising. Do not log secrets or full auth headers.
7. **Protect against LLM-driven resource abuse.** Add request bounds, local TTL cache/deduplication for repeated identical calls, and avoid broad/range/batch searches in the first version unless specifically needed.
8. **Preserve source-of-truth boundaries.** External API data may be cached/stale; include actuality/expiry warnings in tool output when the upstream docs imply it. Do not let the agent present advisory data as guaranteed facts or perform irreversible actions such as purchases.
9. **Activation and verification:** plugins are opt-in. After writing files, run `hermes plugins list`, `hermes plugins enable <name>`, then start a new session or restart the gateway. Also check `hermes tools list` for the plugin toolset: enabled plugin status and enabled toolset status are separate useful signals. Verify `/plugins` and run one smoke prompt/tool call. Tool/schema/plugin changes do not reliably apply mid-session.
10. **Testing:** test handlers return JSON strings on success and failure; mock 200/429/500/malformed responses; test plugin discovery under a temp `HERMES_HOME`; verify no token-like strings appear in output/logs. For user plugin directories with hyphenated names (for example `~/.hermes/plugins/my-plugin`), do not assume plain `pytest <plugin-dir>` can import `__init__.py` correctly as a normal Python package. Hermes loads plugins under a synthetic `hermes_plugins.<slug>` namespace with `spec_from_file_location(..., submodule_search_locations=[plugin_dir])`; mirror that loader in an ad-hoc test runner or place tests outside the plugin package to avoid false `attempted relative import with no known parent package` failures. For direct handler smoke tests before a new session/gateway restart, import the plugin with the same namespace-loader pattern and load only the intended Hermes `.env` keys into the test process, then print redacted summaries rather than full tool outputs when URLs or markers may be present.

### Reference data caches and enrichment pipelines

When the external API returns raw codes (IATA, carrier codes, equipment codes) and the source application has a reference data layer (Data API JSON dictionaries, airport/airline/city caches), port that layer to the plugin:

1. **Pydantic models for reference data** — model_validate from JSON responses; use `alias` fields where Data API uses non-Pythonic keys (e.g., `"code"` → `iata` for airlines).
2. **BaseCache with lazy loading** — `ensure_loaded()` called at first use, not at plugin import. Include: asyncio lock (prevent thundering herd), TTL (7+ days for stable dictionaries), file-system persistence (load from disk if fresh, fetch from API if stale), and graceful degradation (empty data on first fetch failure, not a crash).
3. **Singleton getters** — one cache instance per process, created on first call. This avoids re-initialization across tool calls within a session.
4. **Enrichment pipeline as a separate module** — `enrichment.py` takes raw API objects + cache lookups → enriched DTOs (`FlightOut`, `LegOut`, etc.) with human-readable names (`carrier_name`, `origin_name`, `aircraft_name`, `duration_min`). Do not embed enrichment logic in the tool handler; keep it testable in isolation.
5. **City name resolution with disambiguation** — if the API requires IATA codes but users type city names, add a `_resolve_location()` function that: (a) passes through valid IATA codes, (b) searches cache by name (including translations), (c) on unique match returns the code, (d) on multiple matches returns a structured suggestion list for the model to disambiguate, (e) on no match returns a clear error with usage hints.
6. **Parallel cache preloading** — when the tool handler needs multiple caches, load them concurrently with `asyncio.gather()` on first call rather than sequentially.

### Tool output formatting for human-facing plugins

When a plugin tool returns data that an end user will read (flights, weather, schedules, prices), the tool must return **pre-formatted text as the primary response** — not a JSON blob with a `formatted` field inside it. LLMs cannot reliably relay embedded `formatted` fields; they read the JSON and reformat manually, producing inconsistent output.

**Architecture: formatted text as primary response + compact JSON summary**

1. **Primary response: formatted HTML/Markdown string** — the tool returns the ready-to-deliver text directly as its string result. The LLM relay it as-is. This is deterministic ("на рельсах").
2. **Compact JSON summary appended after `---`** — a minimal JSON block with key fields (price, transfers, times, booking_url) for the model to answer follow-up questions without re-calling the tool. No verbose nested objects.
3. **Companion `_formatted` fields in nested DTOs** — `departure_formatted` alongside `departure_at` (ISO), `duration_formatted` alongside `duration_min`, `price_formatted` alongside `price`. These support the formatter and are available if the model parses the JSON.
4. **Structural hints** — boolean flags like `direct_not_available` + text warnings in `warnings[]` so the model can explain gaps proactively.
5. **Emoji indicators** — `🌙 ночная`, `⚠️ виза` in transfer descriptions; pre-built in the formatted string so the model doesn't need to infer meaning from boolean flags.

**Return pattern:**
```python
return formatted_html + "\n\n---\n" + json.dumps({"success": True, "count": N, "flights": [compact_summary...]})
```

The model sees the HTML first, relays it to the user, and can query the JSON section for follow-ups ("which is cheapest?", "what time does flight 3 arrive?").

**Implementation pattern:**
- `formatters.py` — pure functions for localization (`format_time`, `format_date`, `format_duration`, `format_price`, `format_transfers_count`) plus a top-level `format_flight_results()` producing full Telegram-HTML.
- `schemas_enriched.py` — Pydantic models with both machine (`departure_at: str`) and human (`departure_formatted: str = ""`) fields; `default=""` keeps backward compatibility.
- `enrichment.py` — calls formatters to fill `_formatted` fields during the enrichment pipeline.
- `tools.py` — assembles formatted HTML as primary return + compact JSON summary after `---`.

**Key principle:** formatted text is the primary output for deterministic delivery; JSON summary is secondary for model reasoning. Do NOT put the formatted string inside a JSON field — the model will ignore it and reformat.

**Learned pitfall (April 2026):** Returning `{"success": true, "flights": [...], "formatted": "<html>..."}` does NOT work reliably. Models see the JSON envelope and reformat the data manually instead of relaying the `formatted` field. The fix is to make the HTML the top-level string return value, with JSON as a secondary appendix.

**Other pitfalls:**
- A plugin file existing on disk is not enough; it must be enabled and loaded in a fresh session.
- Project plugins under `./.hermes/plugins/` require `HERMES_ENABLE_PROJECT_PLUGINS=true`; use user plugins for trusted personal integrations.
- Directly importing an existing app's API client can break Hermes startup if that app validates unrelated required environment variables at import time.
- For user-facing data like prices, schedules, weather, or inventory, explicitly distinguish cached/upstream data from guaranteed current state.
- **Hyphenated plugin directory names break Python relative imports** for ad-hoc CLI testing. Hermes loads plugins via `importlib.import_module("plugin-name")` with a synthetic `hermes_plugins.<slug>` namespace; direct `python3 -c "from cache import X"` fails. For smoke tests, mirror the Hermes loader: `pkg = importlib.import_module("plugin-name"); City = pkg.cache.models.City`.
- **Aviasales/affiliate fallback URLs** — when the API returns no `ticket_link` but the source app builds a fallback search URL (e.g., `aviasales.ru/{origin}.{destination}.{date}`), port that logic to the enrichment pipeline so the tool always returns a clickable link.

### Adding a Tool (3 files)

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(
        param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add to `toolsets.py`** → `_HERMES_CORE_TOOLS` list.

Auto-discovery: any `tools/*.py` file with a top-level `registry.register()` call is imported automatically — no manual list needed.

All handlers must return JSON strings. Use `get_hermes_home()` for paths, never hardcode `~/.hermes`.

### Adding a Slash Command

1. Add `CommandDef` to `COMMAND_REGISTRY` in `hermes_cli/commands.py`
2. Add handler in `cli.py` → `process_command()`
3. (Optional) Add gateway handler in `gateway/run.py`

All consumers (help text, autocomplete, Telegram menu, Slack mapping) derive from the central registry automatically.

### Agent Loop (High Level)

```
run_conversation():
  1. Build system prompt
  2. Loop while iterations < max:
     a. Call LLM (OpenAI-format messages + tool schemas)
     b. If tool_calls → dispatch each via handle_function_call() → append results → continue
     c. If text response → return
  3. Context compression triggers automatically near token limit
```

### Testing

```bash
python -m pytest tests/ -o 'addopts=' -q   # Full suite
python -m pytest tests/tools/ -q            # Specific area
```

- Tests auto-redirect `HERMES_HOME` to temp dirs — never touch real `~/.hermes/`
- Run full suite before pushing any change
- Use `-o 'addopts='` to clear any baked-in pytest flags

### Commit Conventions

```
type: concise subject line

Optional body.
```

Types: `fix:`, `feat:`, `refactor:`, `docs:`, `chore:`

### Key Rules

- **Never break prompt caching** — don't change context, tools, or system prompt mid-conversation
- **Message role alternation** — never two assistant or two user messages in a row
- Use `get_hermes_home()` from `hermes_constants` for all paths (profile-safe)
- Config values go in `config.yaml`, secrets go in `.env`
- New tools need a `check_fn` so they only appear when requirements are met
