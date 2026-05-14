# R15C Blocked Secret Outputs Audit Plan

**Goal:** Safely classify blocked secret-heavy tool outputs without exposing raw content or changing production.

**Constraints:** read-only production baseline; no gateway restart; no config/policy/scope changes; no raw session/message/terminal/artifact output; scanner emits only metadata, categories, hashes, and aggregate counts.

## Steps
1. Verify active symlink, gateway status, and `tool_output_compaction` config read-only.
2. Verify R15A/R15B report files and repo branch/status.
3. Create `/tmp/hermes_r15c_classify_blocked_outputs.py` as a structural JSON/JSONL session scanner that never prints raw content or matched secret values.
4. Run the scanner and save sanitized JSON summary under `/tmp`.
5. Check time-bounded sanitized gateway logs for critical compaction errors.
6. Write ops report and repo doc using aggregate-only results.
7. Stage, commit, and push only `docs/hermes-compaction-blocked-secret-outputs-audit.md`; verify local and remote SHA match.
