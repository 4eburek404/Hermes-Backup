# Git commits touching subagents/delegation

Repo: /home/konstantin/.hermes/hermes-agent
HEAD: c829460ab2f0
Branch: skills-improvements
Total relevant commits collected: 469

## 2026-05-07 fb1ce793e6ad — feat(security): enable secret redaction by default (#17691, #20785) (#21193)
paths: hermes_cli/config.py
sources: path

## 2026-05-07 af9336d575ef — feat(gateway): generic plugin hooks for env enablement + cron delivery
paths: hermes_cli/config.py
sources: path

## 2026-05-07 90186c04fb56 — dev: make repo skills the runtime source
sources: S:delegate_task

## 2026-05-07 80717a157f9c — fix(discord): route DM role-auth opt-in through config.yaml (not env var)
paths: hermes_cli/config.py
sources: path

## 2026-05-07 69d025e4a744 — feat(gateway): add allowed_{chats,channels,rooms} whitelist to Telegram, Mattermost, Matrix, DingTalk
paths: hermes_cli/config.py
sources: path

## 2026-05-07 51f9953e69d3 — feat(profiles): --no-skills flag for empty profile creation (#20986)
sources: grep:orchestrator

## 2026-05-07 40b51c93a2d9 — fix(kanban): heartbeat tool extends claim TTL, not just last_heartbeat_at
sources: grep:heartbeat

## 2026-05-06 cd2cbc73b7c5 — refactor(web): per-capability backend selection for search/extract split
paths: hermes_cli/config.py
sources: path

## 2026-05-06 ad7aad251c60 — feat(skills/linear): add Documents support + Python helper script (#20752)
paths: hermes_cli/config.py
sources: path

## 2026-05-06 a0fedfbb1b7e — feat(checkpoints): v2 single-store rewrite with real pruning + disk guardrails (#20709)
paths: hermes_cli/config.py
sources: path

## 2026-05-06 8308611b6734 — feat(profiles): --no-skills flag for empty profile creation
sources: grep:orchestrator

## 2026-05-06 81d4316b4a6f — Merge origin/main into bb/gui — resolve server + docs navbar conflicts
paths: hermes_cli/config.py
sources: path

## 2026-05-06 5c906d70266c — feat(web): add SearXNG as a native search-only backend
paths: hermes_cli/config.py
sources: path

## 2026-05-06 49c3c2e0d37c — docs(kanban): fix worker skill setup instructions too (#20960)
sources: grep:orchestrator

## 2026-05-06 45cbf93899a9 — docs(kanban): fix orchestrator skill setup instructions (#20958)
sources: grep:orchestrator

## 2026-05-06 411cfa26e31d — fix: auto-block repeated kanban retries
paths: hermes_cli/config.py
sources: path

## 2026-05-06 33bf5f6292f4 — fix(auth): fall back to global-root auth.json for providers missing in profile
sources: grep:subagent

## 2026-05-05 de9238d37e77 — feat(kanban): hallucination gate + recovery UX for worker-created-card claims (#20232)
sources: grep:orchestrator

## 2026-05-05 dda389452343 — Merge branch 'main' of github.com:NousResearch/hermes-agent into bb/gui
paths: hermes_cli/config.py
sources: path

## 2026-05-05 c4b287ba539d — feat(i18n): add Ukrainian locale
paths: hermes_cli/config.py
sources: path

## 2026-05-05 bf4e502147df — refactor(web): per-capability backend selection for search/extract split
paths: hermes_cli/config.py
sources: path

## 2026-05-05 b7bd17710598 — docs(AGENTS.md): add curator/cron/delegation/toolsets, fix plugin tree (#20226)
sources: S:child_timeout_seconds, S:delegate_task, S:max_concurrent_children, S:max_spawn_depth, S:subagent_auto_approve, grep:delegate_task, grep:delegation, grep:orchestrator

## 2026-05-05 abce1a5d087e — feat: provider modules — ProviderProfile ABC, 33 providers, fetch_models, transport single-path
paths: hermes_cli/config.py
sources: path

## 2026-05-05 7de3c86c5a79 — feat(i18n): add display.language for static message translation (zh/ja/de/es) (#20231)
paths: hermes_cli/config.py
sources: path

## 2026-05-05 76074d9ee6e4 — fix(cli): recover classic CLI output after resize
paths: hermes_cli/config.py
sources: path

## 2026-05-05 6ebc3014795f — fix(terminal): recover from deleted cwd instead of crashing all sessions
sources: grep:subagent

## 2026-05-05 6d302b340e99 — fix(kanban): accept created_cards linked as child of completing task
sources: grep:orchestrator

## 2026-05-05 401aadb5b892 — docs(security): rewrite policy around OS-level isolation as the boundary
sources: S:delegate_task

## 2026-05-05 39f451f5ada6 — fix: add Turkish locale references in config, tests, and docs
paths: hermes_cli/config.py
sources: path

## 2026-05-05 20a4f79ed11d — feat: provider modules — ProviderProfile ABC, 33 providers, fetch_models, transport single-path
paths: hermes_cli/config.py
sources: path

## 2026-05-05 0dc677f0718b — docs(skill/hermes-agent): sync slash commands + add durable-systems section
sources: S:delegate_task, S:max_concurrent_children, S:max_spawn_depth, grep:delegation

## 2026-05-04 ff3d2773e2a3 — feat(kanban): auto-subscribe gateway chat on tool-driven kanban_create (#19718)
sources: grep:orchestrator

## 2026-05-04 e795b7e3ab1d — fix(delegate): expand composite toolsets before intersection in delegate_task
paths: tools/delegate_tool.py
sources: S:delegate_task, grep:delegate_task, path

## 2026-05-04 d3b22b76d8b6 — fix(kanban): enforce worker task-ownership on destructive tool calls (#19713)
sources: grep:heartbeat, grep:orchestrator

## 2026-05-04 ca8f2c7907e4 — Merge branch 'main' of github.com:NousResearch/hermes-agent into bb/gui
paths: hermes_cli/config.py
sources: path

## 2026-05-04 b2b479b40ece — docs(kanban): backfill multi-board refs in reference docs (#19704)
sources: grep:orchestrator

## 2026-05-04 a1bed18194ff — docs: clarify that the Docker terminal backend is a single persistent container (#20003)
sources: S:delegate_task, grep:delegate_task, grep:subagent

## 2026-05-04 a11aed1accc7 — fix(cli): local backend CLI always uses launch directory, stops .env sync of TERMINAL_CWD (#19334)
paths: hermes_cli/config.py
sources: path

## 2026-05-04 9eaddfafa300 — fix(cli): CLI/TUI on local backend always uses launch directory, ignores terminal.cwd (#19242)
sources: grep:delegation

## 2026-05-04 986ec04048b3 — docs: document /kanban slash command (#19584)
sources: grep:heartbeat, grep:orchestrator

## 2026-05-04 8163d3719227 — fix(skill): reference built-in video_analyze/vision_analyze tools in kanban-video-orchestrator (#19562)
sources: grep:orchestrator

## 2026-05-04 3fb35520c6f5 — revert: auto-subscribe gateway chat on tool-driven kanban_create (#19718) (#19721)
sources: grep:orchestrator

## 2026-05-04 395dbcc873c8 — feat(browser): add Lightpanda engine support with automatic Chrome fallback
paths: hermes_cli/config.py
sources: path

## 2026-05-04 1c7c7c3c5f48 — feat(kanban-dashboard): per-platform home-channel notification toggles (#19864)
sources: grep:orchestrator

## 2026-05-04 1bd5ac7f2f83 — fix(self-improvement-loop): bump background-review budget to 16 and suppress status leaks (#19710)
sources: grep:max_iterations

## 2026-05-04 12307a66e0b0 — Merge branch 'main' of github.com:NousResearch/hermes-agent into bb/gui
paths: hermes_cli/config.py
sources: path

## 2026-05-03 f41ebf778572 — feat(tools): add TinyFish cloud browser provider
paths: hermes_cli/config.py
sources: path

## 2026-05-03 9faaa292b460 — fix(delegate): inherit parent fallback_chain in _build_child_agent
paths: tests/tools/test_delegate.py, tools/delegate_tool.py
sources: grep:subagent, path

## 2026-05-03 9ca5ea137524 — Merge branch 'main' of github.com:NousResearch/hermes-agent into bb/gui
paths: hermes_cli/config.py
sources: path

## 2026-05-03 739b30bc021f — fix: follow-up fixes for TinyFish browser provider salvage
paths: hermes_cli/config.py
sources: path

## 2026-05-03 69692039e916 — fix(delegate): correct ACP docs — Claude Code CLI has no --acp flag
paths: tools/delegate_tool.py
sources: grep:delegate_task, path

## 2026-05-03 511add724987 — feat(skill): add video-orchestrator optional creative skill
sources: grep:orchestrator

## 2026-05-03 457c7b76cd69 — feat(openrouter): add response caching support (#19132)
paths: hermes_cli/config.py
sources: path

## 2026-05-03 0dd8e3f8d876 — rename: video-orchestrator → kanban-video-orchestrator
sources: grep:orchestrator

## 2026-05-02 e444d8f29cea — fix(gateway): config.yaml wins over .env for agent/display/timezone settings (#18764)
sources: grep:max_iterations

## 2026-05-02 deb59eab727c — fix: allow kanban tools for orchestrator profiles with kanban toolset
sources: grep:orchestrator

## 2026-05-02 db884f464683 — chore: uptick
paths: hermes_cli/config.py
sources: S:delegate_task, path

## 2026-05-02 72c8037a24b5 — fix(acp): polish common tool rendering
sources: S:delegate_task

## 2026-05-02 5d3be898a867 — docs(tts): mention xAI custom voice support (#18776)
paths: hermes_cli/config.py
sources: path

## 2026-05-02 2791ba8ad53f — fix(acp): polish common tool rendering
sources: S:delegate_task

## 2026-05-02 1dce90893016 — fix(gateway): shutdown + restart hygiene (drain timeout, false-fatal, success log) (#18761)
paths: hermes_cli/config.py
sources: grep:max_iterations, path

## 2026-05-02 10297fa23c98 — fix(discord): `/reload-skills` now refreshes the `/skill` autocomplete live (#18754)
sources: grep:orchestrator

## 2026-05-01 d5d7b5c6dc72 — feat: lots of speech stuff
paths: hermes_cli/config.py
sources: path

## 2026-05-01 9f3d393a4d03 — feat(desktop): polish chat voice and loading states
paths: hermes_cli/config.py
sources: S:child_timeout_seconds, S:max_concurrent_children, path

## 2026-05-01 7b61f86529cf — feat(desktop): add structured desktop chat app
sources: S:child_timeout_seconds, S:max_concurrent_children

## 2026-05-01 77c0bc6b13c8 — fix(curator): defer first run and add --dry-run preview (#18373) (#18389)
paths: hermes_cli/config.py
sources: path

## 2026-05-01 4a3eac5fe140 — feat: add /recap slash command — summarize recent session activity
sources: S:delegate_task

## 2026-04-30 fc78e708ed0c — fix(update): don't crash hermes update if skill config scan fails (#18257)
paths: hermes_cli/config.py
sources: path

## 2026-04-30 e8e5985ce6ad — fix(curator): seed defaults on update, create logs/curator dir, defer fire import (#17927)
paths: hermes_cli/config.py
sources: path

## 2026-04-30 c86842546750 — feat(kanban): durable multi-profile collaboration board (#17805)
paths: hermes_cli/config.py
sources: S:delegate_task, grep:heartbeat, grep:orchestrator, path

## 2026-04-30 b50bc13ef99d — fix(config): preserve YAML lists in hermes config set (#17876)
paths: hermes_cli/config.py
sources: path

## 2026-04-30 8d302e37a896 — feat(tts): add Piper as a native local TTS provider (closes #8508) (#17885)
paths: hermes_cli/config.py
sources: path

## 2026-04-30 7c6c5619a7b8 — docs(sidebar): collapse exploding skills tree to a single Skills node (#18259)
sources: S:delegate_task, grep:orchestrator

## 2026-04-30 73bf3ab1b223 — chore: release v0.12.0 (2026.4.30) (#18057)
sources: S:child_timeout_seconds

## 2026-04-30 52be0f23367a — merge
paths: hermes_cli/config.py
sources: path

## 2026-04-30 4caad285a602 — feat(gateway): auto-delete slash-command system notices after TTL (#18266)
paths: hermes_cli/config.py
sources: path

## 2026-04-30 265bd59c1d9f — feat: /goal — persistent cross-turn goals (Ralph loop) (#18262)
paths: hermes_cli/config.py
sources: path

## 2026-04-30 2470434d6099 — fix(telegram): probe polling liveness after reconnect to detect wedged Updater
sources: grep:heartbeat

## 2026-04-30 0da968e521f3 — fix(curator): unify under auxiliary.curator (hermes model, dashboard) (#17868)
paths: hermes_cli/config.py
sources: path

## 2026-04-29 e3624e00db6d — fix: enforce strictly subtractive toolset filtration
paths: hermes_cli/config.py
sources: path
