# R11A — Post-incident stabilization after failed production compaction deploy

Use this after a failed Hermes `tool_output_compaction` production attempt, especially when the incident involved mixed runtime, provider errors, or holographic memory DB corruption.

## Scope

R11A is **stabilization and planning only**:

- no production deploy;
- no copying fork files into production;
- no runtime/config changes;
- no gateway restart unless independently required;
- no real Telegram token or external smoke;
- create a short engineering status document and commit it, but do not push.

## Read-only evidence checklist

### 1. Fork repo safety

```bash
cd /tmp/hermes-fork-development-clean-4v5Bch
test "$(pwd)" = "/tmp/hermes-fork-development-clean-4v5Bch" || exit 1
git status --short --branch --untracked-files=all
git ls-files --deleted
git diff --stat
```

Expected before writing the R11A doc: clean tree and zero deleted tracked files.

### 2. Gateway stability

```bash
systemctl --user is-active hermes-gateway
systemctl --user show hermes-gateway -p ActiveState -p SubState -p ExecMainPID -p NRestarts --no-pager
journalctl --user -u hermes-gateway -n 500 --no-pager
```

Also scan `~/.hermes/logs/{gateway.log,agent.log,errors.log}` for target incident patterns. Do not report stale tail matches as fresh incidents; filter by a post-recovery cutoff when possible.

Target patterns:

- `ImportError`
- `ToolOutputCompactionConfig`
- `file is not a database`
- `HTTP 503` / `503 Service Unavailable`

Record non-target warnings (for example Telegram `httpx.ReadError` reconnect/resume), but do not fix them inside R11A.

### 3. Production runtime is not mixed

Production install path in Konstantin's setup:

```bash
PROD=/home/konstantin/.hermes/hermes-agent
```

Check that rollback really removed fork compaction runtime:

```bash
grep -q '_maybe_compact_tool_output' "$PROD/run_agent.py" && echo present || echo absent
grep -q 'ToolOutputCompactionConfig' "$PROD/tools/budget_config.py" && echo present || echo absent
ls "$PROD/scripts/tool_output_compaction.py" "$PROD/scripts/tool_output_summarizer.py" "$PROD/scripts/tool_output_artifacts.py"
```

Expected after rollback: helper absent, config dataclass absent, compaction scripts absent.

### 4. Config without secrets

Read `~/.hermes/config.yaml` via Python/YAML and print only sanitized fields:

- whether `tool_output_compaction` section is present;
- `enabled` boolean;
- rollout platforms and output kinds;
- sanitized provider/model route: provider name, model name, base URL host only.

Never print API keys, tokens, Authorization headers, `.env`, or full URLs with query secrets.

Expected after rollback: `tool_output_compaction.enabled=false` or section absent; no Telegram compaction rollout.

### 5. Holographic memory DB

Safe read-only check:

```bash
file ~/.hermes/memory_store.db
sqlite3 ~/.hermes/memory_store.db 'PRAGMA integrity_check;'
```

Python read-only URI is safer for richer details:

```python
sqlite3.connect('file:/home/konstantin/.hermes/memory_store.db?mode=ro', uri=True)
```

Record path, size, mtime, file type, integrity result, and optional facts/entities counts. Do not delete, recreate, move, or vacuum the DB.

## R11A document shape

Create `docs/hermes-tool-output-compaction-post-incident-status.md` with short engineering sections:

1. Incident summary
2. Current production status
3. What was restored
4. What is explicitly disabled
5. What must not be done again
6. Required next phase: R11B — Docker sandbox validation
7. R11B acceptance criteria
8. Production deploy rule

The deploy rule: Docker sandbox green first, then separate release-directory deploy plan, then controlled switch.

## Verification and commit

Run:

```bash
python3 -m py_compile scripts/analyze_context_overhead.py
python3 -m pytest tests/test_tool_output_compaction_chat_payload_dump.py tests/test_tool_output_compaction_provider_bound_messages.py -q
```

For a new doc, use intent-to-add before diff checks so `git diff` sees it:

```bash
git add -N docs/hermes-tool-output-compaction-post-incident-status.md
git ls-files --deleted
git diff --stat
git diff --name-only
git diff | grep -Ei 'api[_-]?key|secret|password|authorization|bearer|telegram.*token|bot.*token' || true
```

Safety grep may match policy words in the document (for example “no real Telegram token” or “fake secret blocked”). Treat these as expected policy text only if no actual secret value is present.

Then stage only the R11A document and commit:

```bash
git add docs/hermes-tool-output-compaction-post-incident-status.md
git commit -m "Document Hermes compaction post-incident status"
```

Do not push.

## Final report fields

Report compactly:

- production stable: yes/no
- mixed runtime: yes/no
- compaction enabled in production: yes/no
- holographic DB healthy: yes/no/unknown
- fresh ImportError/503/file-is-not-database: yes/no
- committed file
- commit hash
- tests result
- final repo status
- deleted tracked files
- push status
- recommended next task: R11B Docker sandbox validation
