---
name: tool-output-summarization
description: Use when designing, implementing, or testing tool output summarization policies — compact summaries, secret scanning, artifact pointers, dedup, and protected tails for LLM context compression.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [summarization, context-compression, secret-scanning, redaction, testing, policy]
    related_skills: [test-driven-development, systematic-debugging]
---

# Tool Output Summarization

## Overview

Design and implement compact summarization of tool outputs (terminal, file reads, etc.) for LLM context compression. Core concerns: reduce token count while preserving actionable information, scan for secrets, provide artifact pointers for on-demand restoration.

## When to Use

- Implementing or extending a summarization policy for tool outputs
- Writing secret-scanning regex patterns for redaction/blocking
- Designing test fixtures for clean/redacted/blocked contract tiers
- Building artifact pointer or dedup logic
- Debugging regex span overlap or word-boundary issues in secret scanning
- Creating local synthetic smoke harnesses for terminal compaction without real LLM/API calls or user config changes
- Building Docker-isolated sandbox validation for compaction after an incident, before any production rollout
- Auditing production raw-leak suspects after rollout, including pre-activation carry-over classification, artifact aggregate checks, and fresh compaction-error filtering
- Classifying blocked secret-heavy outputs for false-positive risk without revealing raw content, using sanitized metadata, pattern categories, and SHA prefixes only

Don't use for: general text summarization, LLM prompt compression (broader), or log rotation.

## Contract Tiers

The summary policy has three tiers based on secret match count:

| Matches | Tier     | Behavior                                    | `artifact_ref` |
|---------|----------|---------------------------------------------|----------------|
| 0       | Clean    | No redaction, full summary                  | Present        |
| 1–5     | Redacted | `[REDACTED]` replaces secrets in summary   | Present        |
| ≥6      | Blocked  | Empty output, `BLOCKED: …` message only    | `None`         |

Each tier must have **separate test fixtures**. Never reuse a fixture across redacted and blocked assertions.

## Key Design Decisions

### Summary Schema Fields

Every `SummaryResult` carries:
- `compact_summary` — truncated, optionally redacted text
- `artifact_ref` — `artifact:{session_id}:{message_index}:{tool_call_id}` or `None`
- `is_blocked` — `True` only for ≥6 secret matches
- `redacted_ranges` — `[(start, end), …]` of redacted spans
- `sha256`, `size`, `line_count` — raw output metadata (always computed, even when blocked)

### Protected Tail

`TAIL_PROTECT_LINES` (default 20) lines from the end are never truncated aggressively. Head lines fill remaining `MAX_SUMMARY_LINES` budget. A `…` separator marks the gap.

### Repeated Output Dedup

If `previous_hashes` dict contains the current output's `sha256`, return a `Repeated output (same as {call_id})` marker with `artifact_ref=None`. First occurrence gets full summary + artifact pointer.

## Common Pitfalls

1. **Regex word-boundary + suffixes.** `\bAPI_KEY\b` won't match `API_KEY_0` because `_0` follows and `\b` requires a non-word char. Fix: use `\bAPI_KEY\w*` or match the full identifier pattern, not just the prefix.

2. **Span overlap inflates count.** `DATABASE_URL=postgres://user:pass@host/db` matches both key=value and postgres:// patterns at different (overlapping) spans. Always merge overlapping/nested spans before counting. See `references/secret-scanning-pitfalls.md`.

3. **Same fixture for redacted and blocked.** A fixture with ~6 ambiguous secrets can flip between redacted and blocked depending on pattern changes. Use exactly 5 clearly-matching secrets for redacted tests, and ≥10 for blocked tests.

4. **PYTHONPATH in pytest.** `from scripts.module import ...` requires `PYTHONPATH=/repo/root` or a proper `pyproject.toml` package config. In isolated repos, always set it explicitly.

5. **Tail expectations.** With `MAX_SUMMARY_LINES=20` and `TAIL_PROTECT_LINES=20`, a 100-line file shows lines 1 (head) + lines 81-100 (tail), not line 20. Adjust test expectations to the actual tail window.

6. **Working directory vs repo root.** Always verify `pwd` and `git rev-parse --show-toplevel` before creating files. Session repos may be in `/tmp/`, not `~/`. The `write_file` tool uses an absolute path default that may not match the repo — always use the full repo path.

7. **pytest + xdist + PYTHONPATH.** When `pyproject.toml` sets `addopts = "-n auto"`, bare `pytest tests/test_file.py` can fail to find imports (xdist workers start before collection). Fix: `python3 -m pytest tests/test_file.py -o addopts=""` or set `PYTHONPATH=/repo/root` explicitly.

8. **Parameter name shadows function.** If a function parameter has the same name as an imported/calling function (e.g., `simulate_tool_output_summarization: bool = False` inside `summarize()` which calls `simulate_tool_output_summarization()`), the parameter *shadows* the function name in that scope. When the flag is `True`, calling the function produces `TypeError: 'bool' object is not callable`. **Fix:** use a distinct parameter name (e.g., `run_tool_output_summarization_sim`) so the function reference stays reachable. This is easy to miss because the code reads naturally despite the bug.

9. **Short outputs have negative savings.** Compact summaries include metadata overhead (artifact ref, headers, section markers) that exceeds the raw content for short outputs. On real session data the top savings come from dedup of repeated large outputs (~99.9%), but the aggregate hides a long tail of small outputs where `compact_tokens > raw_tokens`. **Test assertions** must not assume `compact_tokens <= raw_tokens` or `savings_tokens >= 0` globally — only assert it for outputs known to be long. The aggregate metric (savings_percent) is positive because large-output dedup dominates.

10. **git track vs write_file path divergence.** When `write_file` creates a file outside the repo root (e.g., `/home/konstantin/tests/file.py` instead of `/tmp/repo/tests/file.py`), `git status` shows the repo copy as deleted (`D`) because the working-tree version no longer exists. Running `git checkout HEAD -- path` restores the last-committed version, but any new changes must then be re-applied. **Always verify** with `git status --short` + `ls -la` that the file is physically in the repo before running tests.

11. **write_file + git checkout HEAD race condition.** If `write_file` creates a new untracked file and the session compacts before `git add`, the next turn may find the file missing from the working tree (context compaction drops the write). `git checkout HEAD -- path` restores the last-committed version but discards uncommitted content. Always `git add` + `git commit` promptly after creating new test/utility files, or be prepared to reconstruct them.

12. **Blocked test fixtures need real SECRET_PATTERNS matches.** Generic `SECRET_0=value_0_with_enough_chars` does NOT match any pattern in `SECRET_PATTERNS`. Use patterns that actually trigger: `password=verysecretvalue_0_extracharshere`, `API_KEY=[REDACTED_TOKEN_LIKE_LITERAL]`, `Bearer eyJ...`, `postgres://user:pass@host/db`. Always verify fixture match count with `scan_secrets()` before asserting blocked/redacted behavior.

13. **Path validation must precede early returns in wrappers.** In `compact_tool_output_with_artifact()`, `_sanitize_path_component()` is called before the blocked-path early return. Otherwise, blocked outputs with path-traversal `session_id` would silently succeed (no file written to validate against). Call validation early and consistently for all code paths.

14. **Subprocess sys.path for scripts imports.** When `analyze_context_overhead.py` is invoked as `python scripts/analyze_context_overhead.py`, the repo root is NOT on `sys.path` by default, so lazy imports like `from scripts.tool_output_summarizer import ...` fail silently, returning `available: False`. Fix: add `_ensure_scripts_importable()` that inserts `Path(__file__).resolve().parent.parent` at `sys.path[0]` before any lazy imports. This must be called at the top of `simulate_tool_output_summarization()`.

15. **Dedup hash ordering — current hash must NOT be in previous_hashes.** When integrating `compact_tool_output_with_artifact()` into a loop that also calls `summarize_tool_output()`, the `seen_hashes` dict is updated with the current output's sha256 *after* `summarize_tool_output()`. If `compact_tool_output_with_artifact()` is called *after* this update, it sees its own sha256 in `previous_hashes` and incorrectly marks every output as a dedup duplicate. **Fix:** call `compact_tool_output_with_artifact()` *before* updating `seen_hashes`, or pass `seen_hashes.copy()` that excludes the current entry. Order: summarize → compact → update seen_hashes.

16. **Restoring deleted test files from git drops new changes.** If `git status` shows `D` (deleted) for a test file that was modified in the working tree, `git checkout HEAD -- path` restores the *last-committed* version, not the modified version. The working-tree modifications are lost silently. **Always verify** with `cat` or `wc -l` that the restored file still contains your new code. If not, re-apply changes from memory or context before running tests. This is worse than pitfall #11 (write_file race) because the loss is invisible — the file exists and compiles, but the new test functions are gone.

17. **Compaction must run BEFORE `maybe_persist_tool_result()`.** Earlier designs placed compaction after persistence (on the preview). This is wrong: (a) secrets would already be in `function_result` before scanning, (b) `maybe_persist_tool_result()` would write the raw output to disk, defeating the purpose of compact summaries. The correct order: `compact_tool_output_with_artifact(raw_output)` → `function_result = compact_summary` → `maybe_persist_tool_result(compact_summary, ...)`. The persistence layer becomes a safety net for unusually long summaries, not the primary handler.

18. **Two call sites for `maybe_persist_tool_result()`.** The concurrent path (`_execute_tool_calls_concurrent()`, ~L10170) and the sequential path (`_execute_tool_calls_sequential()`, ~L10558) both call `maybe_persist_tool_result()`. Any integration must be added to **both** sites. Missing one means half of tool results bypass compaction. **Variable names differ between paths:** concurrent uses `name` / `tc.id` / `args`; sequential uses `function_name` / `tool_call.id` / `function_args`. See `references/insertion-points.md` for full data availability tables.

19. **Untracked smoke files are invisible to `git diff`.** For new synthetic harness files, `git diff --stat`, `git diff --name-only`, and safety grep over `git diff` show nothing until the path is tracked or marked intent-to-add. Use `git add -N tests/<new_file>.py` before diff/safety checks when the user says not to commit. This does not stage content for commit (`git diff --cached` remains empty).

20. **Safety grep vs synthetic sensitive fixtures.** If the user requires `git diff | grep -Ei 'api[_-]?key|secret|password|authorization|bearer' || true` to produce no output, raw fixture labels like `password=` or `API_KEY=` in the diff will fail the check even though they are synthetic. Build scanner-triggering labels at runtime (for example `"pass" + "word"`) and assert raw generated values are absent from summaries/artifacts.

21. **Synthetic smoke should bypass full agent initialization.** Use `object.__new__(AIAgent)` plus explicit `ToolOutputCompactionConfig(... artifact_root=str(tmp_path / ...))`, `session_id`, `platform`, and `_compaction_hashes`. This exercises `_maybe_compact_tool_output()` without reading user config, touching `~/.hermes`, initializing providers, or making LLM/API calls.

22. **Standalone script sys.path for `scripts.*` imports.** When a smoke script is invoked as `python scripts/smoke_*.py` (not via `pytest` which sets `PYTHONPATH` from `pyproject.toml`), the repo root is NOT on `sys.path`. Any `from scripts.tool_output_compaction import ...` will fail with `ModuleNotFoundError`. Fix: add `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` at the top of the script, before the `scripts.*` imports. This is the same fix as pitfall #14 but applied to standalone CLI scripts rather than pytest-driven analyzers.

23. **Two smoke harness layers — R5A (pytest-in-process) vs R5B (subprocess).** R5A uses `object.__new__(AIAgent)` + `_maybe_compact_tool_output()` inside pytest; R5B calls `compact_tool_output_with_artifact()` from a standalone script invoked via `subprocess`. R5B is more isolated (no AIAgent import at all) but can only test the wrapper, not the runtime gate. Choose R5A for runtime-integration verification; R5B for wrapper-level smoke with zero agent dependency.

24. **R6A — configured smoke with feature flag.** A third harness layer exercises the runtime gate (_maybe_compact_tool_output) with `ToolOutputCompactionConfig` explicitly set (enabled/disabled/blocked). Uses `object.__new__(AIAgent)` + attribute assignment (`tool_output_compaction`, `_compaction_hashes`, `session_id`, `platform`). Key difference from R5A: R5A existed before the runtime gate was wired; R6A validates the gate itself — that `enabled=False` returns the raw string unchanged, that `enabled=True` routes through compaction, and that non-terminal tools (`read_file`, `search_files`, `web_search`, unknown) bypass compaction even when enabled. R6A also verifies that artifacts stay inside `tmp_path` (not under `~/.hermes` or repo root).

25. **Accidental deletion of tracked test files.** `git status --short` shows `D` for files deleted from the working tree but still in HEAD. Before creating any new test file, always run `git status` to check for accidental deletions. If a tracked test file is missing, `git restore path` recovers it from HEAD. After restore, re-verify compilation and re-run the full test suite — the restored file must pass independently. This is distinct from pitfall #16 (which covers `git checkout HEAD --` dropping working-tree modifications); `git restore` is for files that match HEAD with no local changes.

26. **pytest autouse fixtures can mutate module-level state invisible to manual Python.** When a test passes in isolation (`python -c "..."`) but fails under `pytest`, the most likely cause is an `autouse` conftest fixture that resets, patches, or mutates module-level singletons (frozensets, class attributes, global dicts, ContextVars). The Hermes `conftest.py::_reset_module_state` autouse fixture clears tool registries, approval state, env vars, and ContextVars between tests — and this can break tests that depend on frozen dataclass defaults, module-level lookup tables, or `os.environ`–derived fallbacks. **Diagnostic:** add a `print()` inside the test that dumps the value of the suspect attribute (e.g., `cfg.rollout_platforms`, `os.environ.get('HERMES_SESSION_SOURCE')`) and compare with a manual run. If the values differ, the conftest is mutating shared state. **Fix:** either (a) use `monkeypatch` to restore the expected state at the start of the test, (b) construct the object after the conftest has finished resetting, or (c) add **explicit config-verification assertions** before calling the method under test — e.g., `assert cfg.rollout_platforms == ("cli",); assert cfg.should_compact("terminal", platform="telegram") is False` — which forces Python to fully resolve frozen dataclass attribute access and serves as a fail-fast guard. This pitfall is especially insidious because `object.__new__()` + attribute assignment creates a seemingly isolated instance, but if the method reads from a module-level global (like `_TERMINAL_OUTPUT_TOOLS` or `HERMES_SESSION_SOURCE`), the conftest reset can change the method's behavior even on a fresh instance.

27. **R6B — Agent loop insertion path smoke test.** A fourth harness layer tests the exact `AIAgent._maybe_compact_tool_output()` method that both concurrent and sequential tool-execution paths call before `maybe_persist_tool_result()`. This is "maximum proximity to runtime insertion" without starting an LLM loop. Pattern: `object.__new__(AIAgent)` + explicit attribute assignment (same as R5A/R6A) but focuses on verifying (1) `enabled=false` → unchanged output + no artifact, (2) `enabled=true` → compacted output + artifact in `tmp_path`, (3) blocked secrets → raw secrets absent from output + no artifact, (4) R3 scope → non-terminal tools bypassed even when in `enabled_output_kinds`, (5) platform rollout gate → mismatched platform skips compaction, (6) structural source guarantee — `_maybe_compact_tool_output` called twice in `run_agent.py` before `maybe_persist_tool_result`. Key difference from R6A: R6B explicitly tests the same method that the concurrent and sequential paths invoke, while R6A verifies config-level gate behavior. **Critical bug (resolved):** When `rollout_platforms=("cli",)` and `agent.platform="telegram"`, `should_compact` returned `True` under pytest but `False` in manual Python. Fix: add explicit config-verification assertions before calling the method (`assert cfg.should_compact("terminal", platform="telegram") is False`) to force Python to fully resolve frozen dataclass attribute access. Also ensure the bare-agent factory always uses `rollout_platforms=("cli",)` (hardcoded) rather than `rollout_platforms=(platform,)` — otherwise the platform gate test can never fail because platform is always in the allowlist.

28. **R6C — Analyzer measurement validation.** A fifth harness layer validates that the read-only analyzer's simulation mode correctly quantifies input-context overhead and that simulated tool output summarization produces measurable savings. Tests import the analyzer module via `importlib` (same pattern as `test_analyze_context_overhead.py`), build synthetic sessions in `tmp_path`, and exercise five measurement contracts: (1) **Baseline vs compacted comparison** — `estimate_standard_provider_input()` on a baseline session with large terminal output must yield higher `estimated_tokens_total` than on the same session with the tool output replaced by a compact summary; savings must come specifically from `tool_output_tokens_sent_or_pruned_uncertain` while `message_content_tokens`, `assistant_tool_calls_tokens`, and `reasoning_details_tokens` remain unchanged. (2) **Full analyzer pipeline with `--simulate-tool-output-summarization`** — writing synthetic fixtures to `tmp_path` and invoking `analyzer.main()` must report `savings_tokens > 0` and `compact_tokens < raw_tokens` for large terminal outputs. (3) **Artifact isolation** — `--simulate-tool-output-artifacts-dir` pointing at a subdirectory of `tmp_path` must write artifact files only under that explicit directory; no `.raw` files leak to other `tmp_path` subtrees. (4) **Read-only without artifacts dir** — omitting `--simulate-tool-output-artifacts-dir` must produce `artifacts.enabled=False`, `artifacts.written_count=0`, and zero `.raw` files anywhere. (5) **codex_reasoning_items exclusion** — `estimate_standard_provider_input()` and `estimate_standard_provider_message_tokens()` must place `codex_reasoning_items` and `codex_message_items` in `excluded_fields`, report positive `excluded_codex_reasoning_items_tokens`, and ensure `estimated_tokens_total` equals `estimate_payload_tokens(sanitized_message)` where sanitized has these fields stripped. Key distinction from R6A/R6B: R6C does NOT import AIAgent or runtime code — it tests the analyzer module's token-estimation and simulation functions in complete isolation. Uses `_make_session_snapshot()` + `_write_fixture()` helper pattern from `test_analyze_context_overhead.py` for building synthetic session data on disk.

29. **R7A — Deeper offline runtime-path mock.**

30. **R7D-1 — ChatCompletions payload validation boundary.** Proves that `ChatCompletionsTransport.convert_messages()` and `build_kwargs()` are pure functions callable offline on synthetic messages — no network, no API key, no `~/.hermes`. The test imports the real transport from `agent.transports`, builds synthetic messages with compacted tool output, and asserts that (1) `convert_messages` strips Codex fields while preserving content, (2) `build_kwargs` assembles correct payload dicts, (3) compacted summary content survives both steps, (4) payload structure matches `chat.completions.create()` format. Key finding: the analyzer's `sanitize_message_for_standard_provider()` is a **separate mirror** of the transport logic — it handles `unknown` role dropping and more field stripping. R7C tests the analyzer mirror; R7D tests the real transport path.

31. **R7D-2 — ChatCompletions payload dump validation.** Full pipeline from compaction to serialized JSON: `_maybe_compact_tool_output()` (real) → `convert_messages()` → `build_kwargs()` → `json.dumps()`. Validates five scenarios: (1) compacted terminal: summary present, raw absent, restore pointer present; (2) disabled baseline: original passes verbatim through full pipeline; (3) blocked secret-heavy: BLOCKED summary, no raw secrets in entire JSON; (4) codex/storage fields: stripped from kwargs dict AND JSON string; (5) serialized size: compacted < raw, >2x reduction. **Key pitfall:** `json.dumps()` escapes `\n` → `\\n`, so `assert LONG_MULTI_LINE in json_str` fails. Use `json.loads(json_str)[key]` for presence assertions on multi-line content. Single-line absence checks work fine in either direction.

32. **JSON newline escaping in serialized payload assertions.** When asserting multi-line content presence in a `json.dumps()` result, the assertion fails because JSON escapes `\\n` to `\\\\n`. Fix: assert on the deserialized dict (`json.loads(json_str)`) or on the kwargs dict directly. For "absent" checks on multi-line values, both directions are safely inconsistent (the escaped form doesn't match the literal), so `assert LONG_VALUE not in json_str` works correctly. For "present" checks on multi-line values, always use `json.loads()`. For single-line values, substring assertions work in both directions. The deepest harness layer yet: simulates the full runtime sequence from tool invocation through message-list injection — not just calling `_maybe_compact_tool_output`, but verifying the **injected message content** in the messages list. The helper `_simulate_runtime_tool_path()` reproduces the exact code path at lines ~10278-10303 (parallel) and ~10674-10700 (sequential): (1) `_maybe_compact_tool_output()`, (2) `maybe_persist_tool_result()` (stubbed as passthrough — no `env.execute()` needed), (3) construct `{"role": "tool", "name": ..., "content": ..., "tool_call_id": ...}` dict, (4) `messages.append(tool_msg)`. Assertions check `messages[0]["content"]` directly, not just the return value of `_maybe_compact_tool_output`. This proves the compacted/blocked/passthrough content is what the LLM would actually see on the next iteration. **Key difference from R6B:** R6B verifies the return value of `_maybe_compact_tool_output`; R7A verifies the full message dict that gets appended to the conversation. **maybe_persist_tool_result stubbing:** `maybe_persist_tool_result()` requires `env.execute()` for sandbox writes, which isn't available in unit tests. The stub passes `compacted` through as `persisted = compacted` — this is correct because `maybe_persist_tool_result` only activates for outputs exceeding its threshold, and the compaction summary is usually short enough to be a no-op. To test the persist step itself, one would need a `tmp_path`-backed `env` mock, which is R7B territory. **Five scenarios tested:** (1) `enabled=false` → message content is raw output, no artifact; (2) `enabled=true` → message content is compacted summary with restore pointer, artifact created; (3) blocked secret-heavy → no raw secrets in message, BLOCKED summary, no artifact; (4) non-terminal output → message unchanged, no artifact; (5) platform rollout gate → wrong platform skips compaction, message unchanged. Also tests: compact wrapper not imported when disabled, multiple sequential tool calls produce independent artifacts/messages, blocked+clean sequence preserves order in messages list, structural guarantee that `_maybe_compact_tool_output` precedes `maybe_persist_tool_result` precedes `tool_call_id` in source.

33. **Tracked file deletion across sessions.** When a previous session deletes a tracked file (e.g., test file) without committing, `git status` shows `D` (deleted) at the start of the next session. This is easy to miss because `git diff` shows nothing (the deletion isn't staged) but `git ls-files --deleted` catches it. **Fix:** `git checkout HEAD -- <path>` restores the file from HEAD immediately, before any other work. Then verify with `git ls-files --deleted`. This is distinct from pitfall #25 (which covers `git checkout HEAD --` dropping working-tree modifications) — here the file matches HEAD with no local changes, so restore is safe. Add a guard step to every session: `test -z "$(git ls-files --deleted)" || { echo "ERROR: tracked files deleted"; git ls-files --deleted; exit 1; }`

34. **R9A — Local enablement documentation.** Creates example config (`docs/tool-output-compaction-cli-local.yaml.example`) and operator instructions (`docs/tool-output-compaction-local-enablement.md`) for CLI+terminal-only controlled enablement. Example config is NOT an active config — it is a reference YAML showing `enabled: true`, `rollout_platforms: [cli]`, `enabled_output_kinds: [terminal]`, and isolated `artifact_root`. Operator doc covers: how to enable locally, what to verify (payload dump, artifact containment, no raw secrets), how to disable (`enabled: false`), files not to commit (`~/.hermes/config.yaml`, artifacts, logs, sessions), and stop conditions. **Key pitfall:** `.gitignore` may contain `examples/` pattern that blocks `docs/examples/` directory. If `git add docs/examples/` fails with "ignored by .gitignore", move the file to a non-ignored path like `docs/<name>.yaml.example`. Always test `git add` before relying on the chosen path.

35. **`.gitignore` can block `docs/examples/`.** A broad `examples/` pattern in `.gitignore` blocks new subdirectories like `docs/examples/`. `git check-ignore -v <path>` reveals the blocking rule. Fix: place example files directly under `docs/` with a `.example` suffix (e.g., `docs/tool-output-compaction-cli-local.yaml.example`) instead of creating a `docs/examples/` subdirectory.

36. **Example config files vs active config.** When creating example/reference config files for feature enablement, always use `.example` suffix and include a prominent `⚠ EXAMPLE ONLY — DO NOT COMMIT to repo defaults or ~/.hermes/config.yaml` header comment. Example configs live in the repo; active configs live in `~/.hermes/`. Never commit `~/.hermes/config.yaml`.

37. **Analyzer baseline may show 0 tokens for non-CLI sessions.** `analyze_context_overhead.py` reads from `~/.hermes/sessions/sessions.json`, which may only contain telegram-platform sessions with zero useful token fields. If `input_tokens: 0` and `output_tokens: 0`, the before/after comparison is meaningless. **Fix:** use direct `compact_tool_output_with_artifact()` calls with synthetic data for measured reduction, or run CLI sessions with compaction enabled/disabled and compare provider-reported token counts. The analyzer is a session-level tool, not a compaction validator.

38. **Config append works for local enablement.** No config overlay mechanism needed — just append the `tool_output_compaction` section to `~/.hermes/config.yaml`. The `ToolOutputCompactionConfig.from_mapping()` parser merges with defaults for missing keys. Always backup first: `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.backup_before_tool_output_compaction_$(date +%Y%m%d%H%M%S)`.

39. **`hermes chat -q` hangs in non-TTY/subprocess contexts.** When testing compaction via real CLI sessions from a tool-call environment, `hermes chat -q "..." --provider <name>` may time out because the CLI expects TTY interaction, provider resolution, or API key availability. **Fix:** bypass the CLI entirely and call `compact_tool_output_with_artifact()` directly via Python. This exercises the real compaction code without LLM calls, provider setup, or TTY requirements. Use `PYTHONPATH=/repo/root python3 <script>.py`. For the analyzer, invoke it as `python3 scripts/analyze_context_overhead.py` (also needs `PYTHONPATH`).

40. **`CompactionResult` field is `compact_summary`, not `compacted_output`.** The dataclass uses `compact_summary` for the result text. If you write `result.compacted_output`, you get `AttributeError`. This is easy to miss because the function name is `compact_tool_output_with_artifact()` and the mental model suggests "compacted output".

41. **`hermes config show` may not display `tool_output_compaction`.** The show subcommand renders known config sections; if `tool_output_compaction` isn't in its display map, it doesn't appear even though the config key is active. Verify enablement via `python3 -c "import yaml; print(yaml.safe_load(open(Path.home()/.hermes/config.yaml)).get('tool_output_compaction'))"` or by checking the tool output directly.

43. **`sessions.json` may have 0 tokens for non-CLI sessions.** The analyzer reads `~/.hermes/sessions/sessions.json` which indexes sessions by key. Telegram sessions may have `input_tokens: 0` and `output_tokens: 0` in the index — the real data lives in session snapshots (`session_*.json`). Always pass `--sessions-dir ~/.hermes/sessions` alongside `--sessions-index` so the analyzer processes the full snapshots. Without `--sessions-dir`, you get an index-level report with no message-level breakdown.

44. **R10A — Telegram enablement config applied, but no artifacts created.**

46. **R11C — Release-dir deploy plan.** After a failed manual production deploy, never copy files piecemeal into the running installation. Use atomic symlink-switchable release directories under `~/.hermes/releases/`. Each release is self-contained (venv + source + scripts). Switch = update symlink + restart gateway. Rollback = point symlink back. No `/tmp` as release target. Production config is only changed during the explicit switch phase (with backup), not during build. Compaction stays disabled until gateway stability is confirmed post-switch. See `references/r11c-release-dir-deploy-plan.md`.

47. **R11D — Release preparation helper is non-switching by default.** `scripts/prepare_hermes_compaction_release.py` has three modes: `--check` (read-only JSON summary), `--print-plan` (step-by-step plan to stdout), `--create-release-dir PATH` (creates directory only, no gateway/config/systemd changes). The `--create-release-dir` mode rejects `/tmp` and paths outside `~/.hermes/releases/`. Production switch is a separate explicit manual operation, never triggered by the helper.

48. **YAML config parsing: `line.strip()` kills section detection.** When parsing `tool_output_compaction: enabled: true/false` from a YAML-like config, checking if `stripped_line.startswith((" ", "\t"))` is always `False` after `.strip()`. The section exits immediately. Fix: check the original line for leading whitespace: `if not line[0:1].isspace(): in_section = False`. This is a general pitfall for any minimal YAML parser that uses line-by-line indentation tracking.

49. **pytest `tmp_path` conflicts with path validation.** `tmp_path` creates directories under `/tmp`. If the code under test validates paths against a forbidden list that includes `/tmp`, tests that use `tmp_path` must patch `FORBIDDEN_PREFIXES` to exclude `/tmp` for the test scope. Otherwise all `tmp_path`-based paths are rejected as "forbidden" before the actual test logic runs.

50. **Secret redaction regex replaces entire match including key name.** Patterns like `\bAPI_KEY\w*[\s:=]+\S{4,}` match `KEY=VALUE` as a whole. The `[REDACTED]` replacement covers both key and value. Tests should NOT assert that key names like `OPENAI_API_KEY` survive redaction — only assert that the secret value is absent and `[REDACTED]` appears. Config set: `enabled:true, rollout_platforms:[telegram], enabled_output_kinds:[terminal], artifact_root:/tmp/hermes-tool-output-compaction-artifacts`. Terminal tool produced 250×160-char output. Result: no artifact, output returned verbatim. **Root cause:** Gateway process runs from **production install** (`/home/konstantin/.hermes/hermes-agent/`), NOT the fork checkout (`/tmp/hermes-fork-development-clean-4v5Bch/`). Production `run_agent.py` (14,714 lines) has **zero** `_maybe_compact_tool_output` references; fork `run_agent.py` (14,836 lines) has **12**. Production `tools/budget_config.py` is a 52-line stub without `ToolOutputCompactionConfig`; fork's is 230 lines with full implementation. Production `scripts/tool_output_compaction.py` and `scripts/tool_output_summarizer.py` are **MISSING**. **Config without matching code is silent** — `tool_output_compaction.enabled: true` has zero effect, no error, no log, no warning. The editable pip install (`__editable___hermes_agent_0_13_0_finder.py`) maps all imports to `/home/konstantin/.hermes/hermes-agent/`, so the gateway never sees fork code. **Post-incident rule:** do NOT fix this by manual file-copy hotfixes, `/tmp` symlinks, or production checks before Docker sandbox validation. First stabilize/rollback, then R11B Docker sandbox, then a separate release-directory deploy plan.

45. **Deployment mismatch is invisible to config checks.** When validating a feature rollout, `~/.hermes/config.yaml` checks alone are insufficient. Always verify the **running code path** by checking: (1) `grep -c '_maybe_compact_tool_output' <production_run_agent_path>`, (2) `wc -l <production_budget_config_path>`, (3) `ls <production_scripts_dir>/tool_output_compaction.py`. A config that looks correct but runs against code that doesn't implement the feature is the most dangerous silent failure — everything appears configured correctly, logs show no errors, but the feature simply doesn't execute.

46. **R11B — Docker sandbox before any renewed production attempt.** After a failed production compaction deploy, validate in `docker/compaction-sandbox/` only: build from the current fork, no production `~/.hermes` mount, no real Telegram token, runtime `network_mode: "none"`, artifact root `/tmp/hermes-tool-output-compaction-artifacts`, synthetic telegram-like context, terminal-only compaction. Acceptance JSON must prove: terminal compacted, artifact created under sandbox root, synthetic sensitive output blocked with no raw leak and no artifact, non-terminal output unchanged. See `references/r11b-docker-sandbox-validation.md`.

43. **R9C — Real CLI session compaction measurement.** Local enablement verified end-to-end with direct Python invocation (bypassing hanging CLI). Three scenarios tested: (1) long synthetic terminal (21,999 chars → 4,573 chars, **79.2% reduction**), (2) short output below skip threshold (passed through unchanged, correctly no artifact), (3) fake secrets above threshold (correctly blocked, no secret leakage in summary or artifacts). Analyzer simulation on 10 real sessions shows **72.51% reduction on tool payloads** (260,390 tokens saved from 359,087). All stop conditions passed: no raw secrets in payload/messages/artifacts, artifacts confined to configured root, no crashes, non-terminal outputs not compacted.

51. **Post-activation raw-leak audits need activation-boundary classification.** Historical raw terminal outputs in session snapshots can look like live compaction leaks. Before calling a finding a production failure, capture the active release target and activation timestamp (prefer active symlink mtime/service start over build time), then classify suspects into `pre_activation_historical`, `post_activation`, platform, output kind, short passthrough, redacted/blocked, and unknown. The verdict gate is `real_post_activation_telegram_terminal_leaks`, not total historical matches. Keep classifiers sanitized: print IDs/timestamps/counts/hashes/labels, never raw matched payloads.

52. **Fresh-error scans must filter audit-command echo and INFO config mentions.** Gateway/session logs may contain `/bin/bash -c ...` command echoes or INFO/DEBUG lines that mention `tool_output_compaction`/`artifact_root` simply because the audit searched for those strings. Count only hard failures (`file is not a database`, `permission denied`, `ImportError`, `ModuleNotFoundError`) or ERROR/CRITICAL lines paired with compaction/artifact terms. Otherwise the audit can falsely report fresh critical compaction errors.

53. **Blocked-secret false-positive audits must be metadata-only.** When classifying blocked outputs, never print raw session messages, terminal output, artifact bodies, or matched secret strings. Emit only basename, mtimes, platform/output kind, lengths, marker booleans, artifact presence, secret-pattern category, SHA prefix, classification, and reason code. Keep `ambiguous` as a safe outcome for generic secret assignments; do not tune or loosen policy during the audit. See `references/r15c-blocked-secret-output-classification.md`.

## Verification Checklist

- [ ] `python -m py_compile scripts/tool_output_summarizer.py` passes
- [ ] `python -m py_compile scripts/tool_output_artifacts.py` passes
- [ ] `python -m py_compile scripts/tool_output_compaction.py` passes
- [ ] `python -m py_compile run_agent.py` passes when runtime helper/integration is touched or smoke-tested
- [ ] `pytest tests/test_tool_output_compaction_smoke.py -q` all green (if exists — R5A in-process)
- [ ] `pytest tests/test_tool_output_compaction_smoke_script.py -q` all green (if exists — R5B subprocess harness)
- [ ] `pytest tests/test_tool_output_compaction_configured_smoke.py -q` all green (if exists — R6A configured gate harness)
- [ ] `pytest tests/test_tool_output_compaction_agent_loop_smoke.py -q` all green (if exists — R6B agent loop insertion path harness)
- [ ] `pytest tests/test_tool_output_compaction_analyzer_measurement.py -q` all green (if exists — R6C analyzer measurement validation)
- [ ] `pytest tests/test_tool_output_compaction_runtime_path_mock.py -q` all green (if exists — R7A runtime-path mock)
- [ ] `pytest tests/test_tool_output_compaction_provider_bound_messages.py -q` all green (if exists — R7C provider-bound message validation)
- [ ] `pytest tests/test_tool_output_compaction_session_snapshot_roundtrip.py -q` all green (if exists — R7B session snapshot roundtrip)
- [ ] `pytest tests/test_tool_output_compaction_chat_payload_boundary.py -q` all green (if exists — R7D-1 ChatCompletions payload validation boundary)
- [ ] `pytest tests/test_tool_output_compaction_chat_payload_dump.py -q` all green (if exists — R7D-2 ChatCompletions payload dump validation)
- [ ] Validation freeze doc committed at `docs/tool-output-compaction-validation-freeze.md`
- [ ] Rollout readiness doc committed at `docs/tool-output-compaction-rollout-readiness.md`
- [ ] Controlled dry-run plan doc committed at `docs/tool-output-compaction-controlled-dry-run.md`
- [ ] Local enablement doc committed at `docs/tool-output-compaction-local-enablement.md` (R9A)
- [ ] Example local config committed at `docs/tool-output-compaction-cli-local.yaml.example` (R9A)
- [ ] Local enablement verified end-to-end (R9B): `compact_tool_output_with_artifact()` produces compact summaries, artifacts inside isolated root, no raw output in payload
- [ ] Docker sandbox validation completed (R11B): `docker/compaction-sandbox/` builds from fork only, runtime network disabled, no production mounts/tokens, synthetic telegram-like smoke proves terminal compaction, sandbox artifact creation, sensitive fixture blocked, non-terminal unchanged
- [ ] `pytest tests/test_prepare_hermes_compaction_release.py -q` all green (if exists — R11D release preparation helper)
- [ ] `pytest tests/test_tool_output_summarizer.py -q` all green
- [ ] `pytest tests/test_tool_output_artifacts.py -q` all green
- [ ] `pytest tests/test_tool_output_compaction.py -q` all green
- [ ] `pytest tests/test_analyze_context_overhead.py -q` all green (if exists)
- [ ] No real credentials in fixtures — only synthetic test values
- [ ] `git diff | grep -iE 'api_key|secret|password|bearer'` shows only pattern code or synthetic fixtures
- [ ] No changes to `run_agent.py`, `context_compressor.py`, config, or transports
- [ ] Production install has compaction code: `grep -c '_maybe_compact_tool_output' <production_run_agent>` > 0
- [ ] Production `tools/budget_config.py` contains `ToolOutputCompactionConfig` (not just a stub)
- [ ] Production `scripts/tool_output_compaction.py` exists
- [ ] Production `scripts/tool_output_summarizer.py` exists
- [ ] For post-rollout raw-leak audits: suspects classified by activation boundary/platform/output kind, raw payloads not printed, artifact aggregate checked by metadata only, and fresh-error logs filtered for command echoes/INFO config mentions
- [ ] For blocked-output false-positive audits: every candidate has sanitized classification (`likely_true_secret`/`likely_false_positive`/`ambiguous`/`unknown`), counts reconcile to the prior blocked total, no raw content or matched secret values were printed, blocked-output artifact creation is checked by metadata/SHA headers only, and verdict is PASS/PASS_WITH_WARNINGS/FAIL

## Integration Points (Hermes Runtime)

Three integration points were evaluated for Hermes Agent:

| Point | Location | Timing | Secret Safety | Dedup | Risk |
|-------|-----------|--------|---------------|-------|------|
| **A (recommended)** | `run_agent.py`, **before** `maybe_persist_tool_result()` | Tool-result write time | ✅ Secrets scanned before entering history | ✅ Immediate | Low — one conditional call behind flag |
| B | Provider adapter `translate_*()` | Prompt assembly | ❌ Secrets already in session history | ❌ No | High — every adapter separately |
| C | `ContextCompressor._prune_old_tool_results()` | Compression time | ❌ Too late — secrets visible for multiple turns | ⏱ Delayed | Lowest surface, but wrong purpose |

**Why A:** Compaction runs on raw `function_result` before `maybe_persist_tool_result()`. The summary (short, safe) replaces `function_result`; `maybe_persist_tool_result()` then operates on the summary, which is usually short enough to be a no-op. This gives defense-in-depth: compaction handles size + secrets, persistence handles overflow if compaction summary is still large.

**Two call sites** in `run_agent.py` (as of commit 301af4ca):
- **Concurrent path** `_execute_tool_calls_concurrent()`: L10170–L10178
- **Sequential path** `_execute_tool_calls_sequential()`: L10558–L10572

**Variable names differ between paths** — concurrent uses `name`/`tc.id`/`args`; sequential uses `function_name`/`tool_call.id`/`function_args`. See `references/insertion-points.md` for full data availability tables.

Both follow the same pattern:
```python
# PROPOSED (behind flag):
if self._should_compact(name):
    compact_result = compact_tool_output_with_artifact(
        raw_output=function_result, tool_name=name,
        tool_use_id=tc.id, output_kind=_classify_output(name),
        config=self.tool_output_compaction,
        previous_hashes=self._compaction_hashes,
    )
    function_result = compact_result.compact_summary

function_result = maybe_persist_tool_result(
    content=function_result,   # now contains compact summary, not raw output
    tool_name=name, tool_use_id=tc.id,
    env=get_active_env(effective_task_id),
)
```

**Why not replace ContextCompressor immediately:** `_prune_old_tool_results()` and `_summarize_tool_result()` handle compression of old messages already in history — a different purpose. Use a 3-phase transition: (1) add compaction at write time behind flag, (2) let ContextCompressor use compaction result, (3) remove `_summarize_tool_result`.

### Feature Flag

```yaml
tool_output_compaction:
  enabled: false                       # Master switch — must be explicitly opted in
  artifact_root: /tmp/hermes/artifacts  # Separate from /tmp/hermes-results/
  max_raw_chars: 50000                  # Outputs above this always get compacted
  short_output_threshold: 200           # Outputs below this skip compaction
  secret_policy: redact_or_block        # "redact_or_block" | "block_only" | "allow"
  enabled_output_kinds:                 # Which tool outputs to compact
    - terminal
    - file_read
  rollout_platforms:                    # Where active
    - cli
```

Config parsed into `ToolOutputCompactionConfig` dataclass (mirroring `BudgetConfig` pattern from `tools/budget_config.py`). Stored as `self.tool_output_compaction` on `AIAgent`.

### Rollback

Set `tool_output_compaction.enabled: false` — one config change, no code revert needed. A full revert of the integration commit also works. Artifacts in `/tmp/hermes/artifacts/` contain no secrets (blocked outputs don't write artifacts; redacted outputs store redacted versions). No data migration needed — feature is additive.

### Validation Chain

| Step | Commit | Description |
|------|--------|-------------|
| R6A | `003091a5` | Configured smoke — default/off + enabled terminal-only behind feature flag |
| R6B | `6ab968cd` | Agent loop insertion smoke — compaction in conversation loop |
| R6C | `f79138b6` | Analyzer measurement — before/after reduction on synthetic sessions |
| R6D | *(no commit)* | Restore/safety stabilization — clean tree, no deleted files |
| R6E | `ab963e19` | Validation status document |
| R7A | `f6a943e2` | Runtime path mock — full insertion sequence with mocked invocation |
| R7B | `64cede8f` | Session snapshot roundtrip — persist/reload consistency |
| R7C | `099701b2` | Provider-bound message validation — analyzer sanitizer produces correct view |
| R7D-1 | `b97035e3` | ChatCompletions payload boundary — transport is pure offline function |
| R7D-2 | `ab93b6b5` | ChatCompletions payload dump — full compaction→transport→JSON pipeline |
| R8A | `acc0e0f0` | Rollout readiness document — chain readiness for controlled local enablement |
| R8B | `b0abe6a5` | Controlled dry-run plan — step-by-step procedure without real enablement |
| R8C | `f53f6d30` | Validation freeze — chain sufficient for controlled local enablement decision; additional tests optional |
| R9A | `31510e2e` | Local enablement documentation — example config + operator instructions for CLI+terminal-only enablement |
| R9B | *(no commit)* | Local enablement verified — config enabled in `~/.hermes/config.yaml`, compaction works end-to-end: 78.6% reduction on synthetic large terminal output, artifacts inside isolated root, no stop conditions triggered |
| R9C | *(no commit)* | Real CLI measurement — direct Python invocation (CLI hangs in non-TTY), 79.2% reduction on synthetic long terminal output, 72.51% projected on 10 real sessions (359K→99K tokens), blocked fake secrets correctly, all stop conditions passed |
| R10A | *(no commit)* | Telegram enablement attempt showed config-only rollout is a silent no-op when production runtime lacks compaction code; do not proceed by manual hotfix after the incident. |
| R11A | `af5e45bf` | Post-incident stabilization after failed manual production attempt: rollback verified, holographic DB integrity ok, compaction disabled in production, Docker sandbox required next. |
| R11B | `fab37933` | Docker sandbox validation: isolated `docker/compaction-sandbox/`, no production mounts/tokens, runtime network disabled, synthetic telegram-like smoke proves terminal compaction, sandbox artifact creation, sensitive fixture blocked, non-terminal unchanged. |
| R11C | `cd1a6d90` | Release-dir deploy plan document: atomic switchable releases under `~/.hermes/releases/`, no piecemeal file-copy, no `/tmp` targets, config backup before switch, rollback = symlink back, stop conditions. |
| R11D | `d1c549c4` | Release preparation helper script: `scripts/prepare_hermes_compaction_release.py` with `--check` (read-only), `--print-plan`, `--create-release-dir` modes; 32 tests covering path validation, secret redaction, config parsing, non-destructive defaults. |

### Rollout Phases

1. **Flag off (default)** — zero behavior change, all tests pass
2. **Controlled local enablement** — `cli` only, `terminal` only, explicit config, small session count, before/after measurement, payload/log dump inspection, artifact root isolation (see `references/rollout-readiness.md`). **R9C verified:** 79.2% reduction on synthetic, 72.51% projected on real sessions, all stop conditions pass.
3. **Flag on, all platforms** — after CLI validation
4. **ContextCompressor integration** — use compaction results in compressor (phase 2 of 3-phase transition)

### Stop Conditions for Controlled Local Enablement

Disable compaction immediately if any occurs:
- Raw secret appears in payload/messages/artifacts when compaction enabled
- Raw large terminal output appears in provider-bound payload (should be compacted summary only)
- Artifact written outside configured `artifact_root`
- Any deleted tracked file appears during work
- Unexpected runtime behavior in non-terminal tools (`file_read`, `search`, `web`)
- Test regression in R6A–R7D-2

### Rollback

Set `tool_output_compaction.enabled: false` — one config change, no code revert needed. No migration required; default/off path passes output unchanged.

### Simulation Baseline (commit 5b5abcda)

| Metric | Value |
|--------|-------|
| raw_tokens | 782,216 |
| compact_tokens | 286,783 |
| savings | 495,433 (63.34%) |
| artifacts written | 314 |
| redacted | 49 |
| blocked | 21 |
| dedup | 1,332 |
| skipped short | 190 |

## Artifact Storage Utility

`scripts/tool_output_artifacts.py` — isolated utility for writing raw tool output artifacts to disk.

### Path & URI Format

```
disk:  {root}/{session_id}/msg_{message_index:04d}_{tool_call_id}.raw
URI:   hermes-artifact://tool-output/{session_id}/{message_index}
```

### File Format

```
version: 1
session_id: ...
message_index: ...
tool_call_id: ...
tool_name: ...
output_kind: terminal|file_read|short_output|...
sha256: <hex>
raw_size_bytes: <int>
created_at: <ISO-8601>
redaction_status: clean|redacted|blocked
restore_command: hermes artifact restore <URI>
---
<raw or redacted body>
```

### Write Contract by Tier

| Tier | Body written | `artifact_ref` | File on disk |
|------|-------------|----------------|--------------|
| Clean | Raw output verbatim | URI | Yes |
| Redacted | `redacted_output` param (secrets → `***`) | URI | Yes |
| Blocked | Nothing | `None` | No file created |

### Security

- **Path traversal**: `_sanitize_path_component()` rejects `..`, `\x00`, empty, `.`-only components; strips leading/trailing slashes.
- **Atomic write**: `.tmp` → `fsync` → `os.replace()`; cleanup on error.
- **Permissions**: directories `0700`, files `0600`.

### Key Function: `write_artifact()`

```python
result = write_artifact(
    raw_output,
    session_id="sess-001",
    message_index=5,
    tool_call_id="call-abc",
    tool_name="terminal",
    output_kind="terminal",
    redaction_status="clean",  # or "redacted" / "blocked"
    redacted_output=redacted,   # only for "redacted" tier
    root=tmp_path,              # default: /tmp/hermes/artifacts
)
# result: ArtifactResult(artifact_ref, path, sha256, status, raw_size_bytes, restore_command)
```

### Key Function: `read_artifact_header()` / `read_artifact_body()`

Parse header fields (typed ints for `message_index`, `raw_size_bytes`) and extract body. Body is everything after the `---` separator with the leading newline stripped.

## Compaction Wrapper

`scripts/tool_output_compaction.py` — isolated wrapper linking summarizer + artifact storage. Single entry point: `compact_tool_output_with_artifact()`.

### Pipeline

1. **Dedup check** — `previous_hashes` lookup by sha256
2. **Secret scan** — `redact_or_block()` from summarizer
3. **Blocked** (≥6 matches) → no artifact, `artifact_ref=None`, summary says `BLOCKED`
4. **Short clean** (<200 chars, 0 secrets) → no artifact, summary says "no artifact stored"
5. **Clean/Redacted** → `write_artifact()` then `summarize_tool_output()`, merge into `CompactionResult`

### CompactionResult Fields

`compact_summary`, `artifact_ref`, `artifact_path`, `sha256`, `redaction_status` (clean/redacted/blocked), `size`, `line_count`, `restore_command`, `dedup_ref`. Properties: `is_blocked`, `has_artifact`.

### Key Pitfalls

- **"SECRET_N=value_N" doesn't match SECRET_PATTERNS** — use `password=...` or `API_KEY=...` for blocked fixtures
- **`redaction_status` must be computed before `is_short_clean` check** — otherwise `UnboundLocalError`
- **Path validation must happen before blocked return** — validate `session_id`/`tool_call_id` early even for blocked outputs
- **`metadata.setdefault()` mutates caller's dict** — stale defaults may persist across reuse

- `references/insertion-points.md` — Exact insertion-point archaeology for R2/R3: line ranges, data availability tables, variable name mapping between concurrent/sequential paths, data that needs derivation vs data not available, `_classify_output` helper design, session snapshot considerations
- `references/runtime-integration-plan.md` — Full runtime integration plan: insertion points, feature flag design, task split R1–R6, test requirements, risks, rollback, and simulation baseline

- `references/secret-scanning-pitfalls.md` — regex span-overlap, word-boundary, fixture isolation, and greedy-matching pitfalls with code fixes
- `references/hermes-integration-context.md` — Hermes runtime audit: tool_result_storage layers, ContextCompressor pruning, adapter hooks, and key source locations
- `references/analyzer-simulation-mode.md` — Read-only simulation mode in analyze_context_overhead.py: CLI flag, JSON/Markdown report structure, baseline results, and implementation hook points
- `references/artifact-storage.md` — Artifact storage utility: path format, URI scheme, atomic write, permissions, path-traversal defense, read/write API, and test patterns
- `references/compaction-wrapper.md` — Compaction wrapper: pipeline, CompactionResult API, tier behavior (clean/short/redacted/blocked/dedup), path traversal validation ordering, and test patterns
- `references/r5a-synthetic-smoke-harness.md` — Synthetic local CLI smoke harness pattern: direct `_maybe_compact_tool_output()` tests with `object.__new__(AIAgent)`, `tmp_path` artifact roots, no real LLM/API calls, no user config writes, safety grep considerations
- `references/r5b-subprocess-smoke-harness.md` — Standalone subprocess smoke script pattern: calls `compact_tool_output_with_artifact()` directly with `tempfile.TemporaryDirectory`, no AIAgent import, subprocess test verification, sys.path fix
- `references/r6a-configured-smoke-harness.md` — Configured feature-flag gate tests: `object.__new__(AIAgent)` with explicit `ToolOutputCompactionConfig`, disabled/enabled/blocked/scope assertions, artifact isolation to `tmp_path`, R5A vs R5B vs R6A layer comparison
- `references/r6b-agent-loop-smoke-harness.md` — Agent loop insertion path smoke test: tests `_maybe_compact_tool_output()` at maximum proximity to runtime without LLM calls, platform rollout gate, R3 scope, structural source guarantee; critical debugging lesson about pytest autouse fixtures mutating module-level state
- `references/r7a-runtime-path-mock-harness.md` — Deeper offline runtime-path mock: simulates full insertion sequence from compaction through message dict construction and list injection; stubs `maybe_persist_tool_result` as passthrough; asserts on `messages[n]["content"]` not just return values
- `references/rollout-readiness.md` — R8A rollout readiness: validation chain, controlled local enablement criteria, stop conditions, rollback procedure, recommended next tasks
- `references/r7d-chat-payload-validation.md` — R7D-1 boundary discovery (ChatCompletionsTransport is pure offline function) and R7D-2 payload dump validation (full compaction → transport → json.dumps pipeline); JSON newline escaping pitfall for multi-line asserts
- `references/r8b-controlled-dry-run-plan.md` — R8B controlled local enablement dry-run: scope, preconditions, proposed config, procedure, metrics, stop conditions, rollback, recommended next tasks. Plan only — no real enablement.
- `references/r9a-local-enablement.md` — R9A local enablement documentation: example config, operator steps, .gitignore pitfall with docs/examples/, files not to commit, validation before enablement, stop conditions
- `references/r9b-local-enablement-verification.md` — R9B local enablement verification: config enabled in ~/.hermes/config.yaml, compaction works end-to-end (78.6% reduction), should_compact() gate, analyzer baseline issue, rollback
- `references/r9c-real-cli-measurement.md` — R9C real CLI measurement: direct Python invocation results, 79.2% synthetic reduction, 72.51% projected on real sessions, all stop conditions passed, CLI hang workaround
- `references/r11a-post-incident-stabilization.md` — R11A post-incident stabilization workflow after failed production compaction deploy: read-only production checks, mixed-runtime rollback verification, holographic DB integrity check, short status doc, commit-without-push handoff to R11B Docker sandbox validation
- `references/r11b-docker-sandbox-validation.md` — R11B Docker sandbox validation workflow: isolated container files, no production mounts/tokens, runtime network disabled, synthetic telegram-like smoke acceptance JSON, safety checks, commit-without-push handoff to release-dir deploy planning
- `references/r11c-release-dir-deploy-plan.md` — R11C release-dir deploy plan: atomic switchable releases, no piecemeal copy, directory layout, build procedure, pre-switch checks, switch procedure, rollback, controlled compaction enablement, stop conditions
- `references/r11d-release-preparation-helper.md` — R11D release preparation helper: CLI modes (--check, --print-plan, --create-release-dir), safety properties, YAML config parsing pitfall, tmp_path validation pitfall, regex redaction key-name pitfall, test coverage
- `references/r15b-raw-leak-suspects-audit.md` — Post-rollout raw-leak audit pattern: activation-boundary classification, sanitized suspect classifier, artifact metadata aggregate, and fresh-error log-noise filtering
- `references/r15c-blocked-secret-output-classification.md` — Blocked secret-output false-positive audit pattern: metadata-only classifier fields, SHA-prefix fingerprinting, aggregate counts, safety checks, and PASS/PASS_WITH_WARNINGS/FAIL verdict rule
- `references/r6c-analyzer-measurement-validation.md` — R6C analyzer measurement validation: synthetic session construction for baseline vs compacted comparison, provider input reduction assertions, artifact isolation vs read-only contracts, codex_reasoning_items exclusion from standard chat-completions input, full analyzer pipeline simulation via `main()`