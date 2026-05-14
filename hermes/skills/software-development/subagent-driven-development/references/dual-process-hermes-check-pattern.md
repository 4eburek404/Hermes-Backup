# Dual-process Hermes check pattern

Session-derived reference for high-stakes verification where the parent needs independent model perspectives and must not lose subagent output.

## Trigger

Use this pattern when the user asks for two independent agents/models, production-impacting checks, update readiness, release/version comparisons, or any task where a single `delegate_task` result is not enough.

## Contract

- Use two separate `hermes chat` processes, not one `delegate_task(tasks=[...])`, when models/providers must differ.
- Give each process the same task boundary but independently worded role labels.
- Make the task read-only unless the user explicitly authorizes mutation.
- Require a final `SUBAGENT_RESULT` block and cap output: max ~20 bullets, no raw logs unless artifact paths are requested.
- Persist each prompt and each process log under a task-specific artifact directory.
- Parent must perform an independent verification pass before reporting final conclusions.

## Non-killing launch/monitor pattern

Start each process as a background process and pipe output to a log artifact:

```bash
cd /home/konstantin/.hermes/hermes-agent
PROMPT=$(python3 -c 'from pathlib import Path; print(Path("/path/to/prompt.txt").read_text())')
hermes chat -Q --source tool --provider <provider> -m <model> -t terminal,file,web -q "$PROMPT" 2>&1 | tee /path/to/process.log
```

Important: do not wrap long subagents in a shell `timeout` that can kill them. Use background process handles, `poll`, and bounded `wait` calls as status checks. If a wait call returns timeout, treat it as “still running” unless the process status says exited/failed.

## Parent verification checklist

For update/release checks, verify directly rather than trusting model agreement:

- current date/time and timezone if freshness matters;
- branch, HEAD, status, local version;
- remotes and live remote refs;
- release metadata from GitHub/API or official source;
- compare result between local/fork base and upstream;
- existence and byte size of subagent logs;
- no remaining background processes;
- dirty files and whether they are related or unrelated.

## Reporting rule

Final report must separate:

- committed/local changes;
- child process status and artifacts;
- parent-verified facts;
- recommendation and risk boundary;
- explicit statement if no update/mutation was applied.

If the worktree is dirty or custom, recommend a clean worktree/backup/stash/commit path before applying upstream updates. Do not say “ready to update” without naming the dirty/custom risk.
