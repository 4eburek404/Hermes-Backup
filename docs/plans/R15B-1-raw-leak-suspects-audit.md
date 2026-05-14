# R15B-1 raw-leak suspects audit plan

Scope: classify R15A raw-leak suspects with sanitized aggregate scanning only.

1. Read-only baseline: active target, gateway active state, compaction config section, artifact root directory/symlink checks.
2. Locate R15A reports/analyzer outputs without printing raw session/tool content; sync repo branch and check dirty state.
3. Write `/tmp/hermes_r15b_classify_raw_leaks.py` to structurally parse sessions/analyzer JSON and emit sanitized metadata/aggregate counts only.
4. Run classifier; verify suspect categories and artifact aggregate safety without reading artifact bodies.
5. Check time-bounded gateway/agent logs for critical compaction/artifact errors only.
6. Write ops report and repo doc; commit/push repo doc only if unrelated dirty state is absent.
7. Final report: counts, verdict, paths, commit hash, and explicit no production/gateway mutation status.

Safety constraints: no production mutation, no gateway restart, no config/scope/skills/memory changes, no raw session messages, no raw terminal output, no raw artifact bodies.
