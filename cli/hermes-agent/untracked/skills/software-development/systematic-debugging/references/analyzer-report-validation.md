# Analyzer / report validation workflow

Use this pattern when changing read-only analyzers or baseline report generators that must remain grounded in live files.

## Verification sequence

1. Run the focused unit test file first.
   - Example: `pytest tests/test_analyze_context_overhead.py -q`
2. Run the analyzer against a minimal fixture set.
   - Example:
     ```bash
     python scripts/analyze_context_overhead.py \
       --sessions-index tests/fixtures/context_overhead/sessions_index_minimal.json \
       --sessions-dir tests/fixtures/context_overhead \
       --limit 20 \
       --out-md /tmp/report.md \
       --out-json /tmp/report.json
     ```
3. Run the analyzer against the live baseline.
   - Example:
     ```bash
     python scripts/analyze_context_overhead.py \
       --sessions-index ~/.hermes/sessions/sessions.json \
       --sessions-dir ~/.hermes/sessions \
       --limit 20 \
       --out-md /tmp/baseline.md \
       --out-json /tmp/baseline.json
     ```
4. Inspect the JSON output, not just stdout, for the new report sections and counts.

## What to check in the JSON

- `messages.total_estimated_tokens`
- `message_roles`
- `assistant_tool_calls`
- `assistant_reasoning`
- `tool_outputs`
- `top_oversized_messages`
- `top_sessions_by_message_tokens`

## Common pitfalls

- Do not trust stdout alone; it usually reports only a subset of totals.
- If a fixture row is missing `total_tokens`, derived totals may be used and warnings are expected.
- If a file was previously read with offset/limit pagination, re-read the whole file before overwriting it. Partial views can hide syntax or structural errors.
- For baseline comparisons, keep report generation read-only: no config changes, no runtime edits, no writing into `~/.hermes`.

## Useful symptom from this session

A syntax error was introduced by editing a test file after a partial read. The fix was to re-open the file, correct the typo, and rerun the focused test before the CLI checks.