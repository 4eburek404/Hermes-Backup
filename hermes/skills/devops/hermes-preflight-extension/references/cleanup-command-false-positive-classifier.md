# R14D-5e: Cleanup Command False Positive Classifier in Passive Logs

## Problem

Journald and agent.log can contain lines that match RELEASE_CRITICAL_PATTERNS
but are NOT runtime errors — they are shell command echoes (sudo rm, grep, etc.)
that happen to contain critical patterns as text arguments. These false positives
block releases with `passive_logs_status: FAIL`.

Example: `sudo rm -rf /tmp/hermes-tool-output-compaction-artifacts` in journald
matches the `/tmp/hermes-tool-output` critical pattern, but it's a manual cleanup
command, not a Hermes runtime error.

## Solution: `_is_cleanup_command_line()` classifier

Add a regex-based classifier that identifies log lines which are shell command
echoes, not runtime errors. Filter these lines BEFORE pattern matching.

### Implementation pattern

```python
import re

_CLEANUP_COMMAND_INDICATORS = re.compile(
    r'(?:'
    r'sudo\s+(?:rm|find|grep|cat|ls|journalctl|rmflags)\s'
    r'|/bin/(?:ba)?sh\s+-c'
    r'|\brm\s+-[rR]f\b'
    r'|\bgrep\s+-[EfriR]'
    r'|\bjournalctl\b.*\bgrep\b'
    r'|\(command\s+continued\)'
    r')',
    re.IGNORECASE,
)

def _is_cleanup_command_line(line: str) -> bool:
    """Return True if the line is a cleanup/diagnostic command echo."""
    return bool(_CLEANUP_COMMAND_INDICATORS.search(line))
```

### Integration pattern

In both journald and agent.log scanning sections, filter lines before
`_scan_lines_for_patterns()`:

```python
# Filter cleanup command lines before pattern matching
filtered_lines = [line for line in raw_lines if not _is_cleanup_command_line(line)]
ignored_count = len(raw_lines) - len(filtered_lines)
if ignored_count > 0:
    results["passive_logs_ignored_false_positive_count"] += ignored_count
    samples = [_sanitize_line(line) for line in raw_lines
                if _is_cleanup_command_line(line)][:3]
    results["passive_logs_ignored_false_positive_samples"].extend(samples)
    results["passive_logs_notes"].append(
        f"journald: {ignored_count} cleanup/diagnostic command line(s) ignored"
    )
```

### Critical: `import re` at module level

The `_CLEANUP_COMMAND_INDICATORS = re.compile(...)` constant is evaluated at
module import time. If `import re` is missing from the top-level imports,
you get `NameError: name 're' is not defined` at import time, which crashes
the ENTIRE preflight script (every test that runs it via subprocess fails).
**Always verify that `re` is imported at module level** after adding regex
constants outside functions.

### Metadata fields

- `passive_logs_ignored_false_positive_count` — total lines ignored as cleanup commands
- `passive_logs_ignored_false_positive_samples` — up to 3 sanitized samples per log source

### What is NOT ignored (still triggers FAIL)

- ImportError, ModuleNotFoundError
- python-telegram-bot not installed
- No adapter available / failed to connect
- file is not a database
- ToolOutputCompactionConfig errors
- PermissionError in runtime context
- artifact_root=/tmp/hermes-tool-output in runtime/config errors

### Test patterns

Structural tests (source-level):
1. `_is_cleanup_command_line` function exists
2. Cleanup classifier is called inside `check_passive_logs`
3. Regex patterns match sudo rm, /bin/bash -c, grep -Efi, journalctl, rm -rf
4. `/tmp/hermes-tool-output` still in RELEASE_CRITICAL_PATTERNS
5. ImportError still in RELEASE_CRITICAL_PATTERNS
6. Metadata fields `passive_logs_ignored_false_positive_count` and `passive_logs_ignored_false_positive_samples` present
7. No systemctl start/stop/restart in classifier
8. No symlink switch in classifier
9. No config/memory/artifact modification in classifier

Live test:
- Full preflight with cleanup commands in journald should return
  `passive_logs_ignored_false_positive_count >= 1` and `passive_logs_status: PASS`.