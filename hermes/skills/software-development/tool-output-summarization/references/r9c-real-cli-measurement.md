# R9C — Real CLI Session Compaction Measurement

## Date
2026-05-11

## Approach
Direct Python invocation of `compact_tool_output_with_artifact()` — the CLI
hangs in non-TTY/subprocess contexts (`hermes chat -q` times out), so real
agent sessions were not feasible. Instead, called the compaction wrapper
directly, then ran `analyze_context_overhead.py` on existing session snapshots.

## Scenarios Tested

### Scenario 1: Long synthetic terminal output (no secrets)
- Input: 100 lines × 200 chars = 21,999 chars
- Output: 4,573 chars → **79.2% reduction**
- Artifact: `/tmp/hermes-tool-output-compaction-artifacts/r9c-session-1-synthetic-long/msg_0000_call-r9c-s1.raw`
- Redaction status: `clean`, has_artifact: True, is_blocked: False

### Scenario 2: Short output (below skip threshold)
- Input: 52 chars (under `SHORT_OUTPUT_SKIP_ARTIFACT_CHARS=200`)
- Output: 164 chars (unchanged, metadata overhead makes it larger)
- No artifact written (correct)
- Redaction status: `clean`, has_artifact: False

### Scenario 3: Blocked (fake secrets above threshold)
- Input: 8 lines with `api_key=FAKE_SECRET_R9C_*` (above block threshold)
- Output: 113 chars → BLOCKED
- Redaction status: `blocked`, has_artifact: False
- No `FAKE_SECRET_R9C` in compact summary (verified by string search)

### Secret Scan Results
- No fake secrets leaked in any compact summary or artifact file

## Analyzer Results (10 Real Sessions)

### Without Simulation (Actual)
- Snapshot sizing total: 705,944 tokens
- Estimated provider input total: 723,317 tokens
- Messages (provider): 601,482 tokens
- Tool output (uncertain): 356,572 tokens

### With Simulation (Compacted)
- Tool messages processed: 691
- Raw estimated tokens: 359,087
- Compact estimated tokens: 98,697
- **Estimated savings: 260,390 tokens (72.51%)**
- Secret scan: clean=671, redacted=14, blocked=6
- Dedup candidates: 480 (69% of tool outputs)
- Output kinds: terminal=419, file_read=160, short_output=112

### Artifact Simulation
- Written: 141 artifacts
- Redacted: 14
- Blocked: 6
- Dedup: 480
- Skipped (short): 64
- Total artifact bytes: 363,620

## Stop Conditions — All Passed
- ✅ Raw large terminal output not in provider-bound payload (replaced by compact summary)
- ✅ Raw secrets not in messages/payload/artifacts
- ✅ Artifacts only inside `/tmp/hermes-tool-output-compaction-artifacts`
- ✅ Hermes not crashing (direct invocation verified)
- ✅ Non-terminal outputs not compacted (`enabled_output_kinds=[terminal]`)

## Key Technical Findings
- `hermes chat -q` hangs in non-TTY — use direct Python invocation instead
- `CompactionResult` uses `compact_summary`, not `compacted_output`
- `hermes config show` doesn't display `tool_output_compaction` section — verify via Python
- `sessions.json` may have 0 tokens for non-CLI sessions — always pass `--sessions-dir`
- Analyzer `--simulate-tool-output-summarization` with `--simulate-tool-output-artifacts-dir` writes artifacts to the specified dir