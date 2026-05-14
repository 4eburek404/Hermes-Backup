# Time-Bounded Log Parsing for Preflight

## Problem
agent.log accumulates historical errors (ImportError, ModuleNotFoundError, etc.)
that are stale and don't affect the current RC. Scanning the full tail causes
false FAIL when historical critical patterns are found.

## Solution
Parse timestamps on each log line and classify as:
- **fresh** (within `--logs-since-minutes` window, default 30min) — can cause FAIL
- **historical** (before window) — counted in `agent_log_historical_critical_ignored_count`, non-blocking
- **unparsed** (no recognizable timestamp) — counted in `agent_log_unparsed_lines_ignored_count`, non-blocking

## Timestamp Formats Supported
```python
_AGENT_LOG_TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S,%f",      # 2026-05-12 14:30:45,123
    "%Y-%m-%d %H:%M:%S",          # 2026-05-12 14:30:45
    "%Y-%m-%dT%H:%M:%S.%f",      # 2026-05-12T14:30:45.123456
    "%Y-%m-%dT%H:%M:%S",         # 2026-05-12T14:30:45
    "%b %d %H:%M:%S",             # May 12 14:30:45 (no year — uses current year)
]
```

## Key Implementation Details
- `_parse_log_timestamp(line, now_dt)`: tries each format on the start of the line
- Lines with `%b %d %H:%M:%S` format get `now_dt.year` injected (syslog-style, no year)
- Timezone-naive timestamps are assumed UTC
- Journald is inherently time-filtered via `journalctl --since="N minutes ago"`
- agent.log tail limit: 5000 lines (not the full file)
- `preflight_started_at_utc` is recorded at the start of `check()` for window calculation
- `window_start = preflight_started_at_utc - timedelta(minutes=since_minutes)`

## CLI Threading
```
parse_args() → main() → check(..., logs_since_minutes=30)
                        → check_passive_logs(hermes_home, results, errors, since_minutes)
```
Don't use `getattr(args, ...)` hacks — add the parameter to `check()` explicitly.

## Metadata Fields Added (R14D-3a)
- `passive_logs_since_minutes` — the window size (default 30)
- `passive_logs_window_start` — ISO timestamp of window start
- `agent_log_historical_critical_ignored_count` — count of release-critical patterns in historical lines
- `agent_log_unparsed_lines_ignored_count` — count of lines with no parseable timestamp
- `passive_logs_status` — PASS / WARN / FAIL (only fresh critical patterns can cause FAIL)

## Test Approach
- Forbidden-pattern tests (systemctl, truncate, write_text) must strip docstrings first:
  ```python
  import re
  func_no_doc = re.sub(r'""".*?"""', '', func, flags=re.DOTALL)
  ```
- When testing "no mutating systemctl commands", use `"systemctl start"` not `" start "`
  to avoid matching "at the start of the line" in comments.
- Tests referencing docs must use `SCRIPT.parent.parent / "docs" / "hermes-release-preflight.md"`,
  not a `DOCS` constant (doesn't exist in the test file).
- When appending new test functions: write to a temp file via `write_file`, then
  `terminal("cat /tmp/file.py >> target")`. Avoid `cat >> target << 'EOF'` heredocs
  with Python code containing triple quotes — the heredoc delimiter collides with
  Python string syntax and causes SyntaxError in the sandbox.