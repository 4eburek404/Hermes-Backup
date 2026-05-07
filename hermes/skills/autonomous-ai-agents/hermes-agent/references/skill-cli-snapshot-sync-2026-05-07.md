# Skill + companion CLI snapshot sync

Use when a user asks to install or refresh a skill and its companion CLI from an external repo snapshot, especially a repo layout like:

```text
cli/
├── skills/<skill-name>/SKILL.md
└── skill-clis/<cli-name>/pyproject.toml
```

## Proven workflow

1. Load the relevant Hermes/skill-authoring skill first, then inspect the current installed skill and CLI:
   ```bash
   command -v <cli>
   <cli> --version || true
   python3 -m pip show <package-name> || true
   ```
2. Resolve the exact upstream commit before copying:
   ```bash
   git ls-remote https://github.com/<owner>/<repo>.git HEAD refs/heads/main
   ```
3. Sparse-clone only the needed tree into `/tmp`:
   ```bash
   rm -rf /tmp/<repo>-cli
   GIT_TERMINAL_PROMPT=0 git clone --filter=blob:none --sparse --branch main https://github.com/<owner>/<repo>.git /tmp/<repo>-cli
   cd /tmp/<repo>-cli
   git sparse-checkout set cli
   git rev-parse HEAD
   ```
4. Identify the source layout, then sync:
   - skills: `cli/skills/<name>/` → `~/.hermes/skills/<category>/<name>/`
   - if `cli/skills/<name>` is a symlink, resolve its target and include that target in the sparse checkout before reading/copying (for example `cli/skills/flight-search -> ../../hermes/skills/productivity/flight-search`; run `git sparse-checkout set cli hermes/skills/productivity/flight-search`)
   - companion CLI: `cli/skill-clis/<name>/` → local source checkout such as `/home/konstantin/code/clis/<name>/`
5. Prefer non-destructive `rsync -a` for CLI snapshots when local extras exist. Exclude bytecode/caches; do not delete local research directories unless explicitly approved.
6. Refresh both executable shim and package metadata. A CLI can report the new version from source while `pip show` still says the old editable version:
   ```bash
   python3 -m pip install -e /home/konstantin/code/clis/<name>
   make -C /home/konstantin/code/clis/<name> install-local
   ```
7. Verify source parity and runtime behavior:
   ```bash
   <cli> --version
   python3 - <<'PY'
   from importlib import metadata
   import <module>
   print(metadata.version('<package-name>'))
   print(<module>.__file__)
   PY
   <cli> --json doctor
   python3 -m pytest -q /home/konstantin/code/clis/<name>/tests
   ```
8. Decide and verify duplicate/legacy cleanup explicitly:
   - Default migration behavior: if the refreshed skill has a new name, install it alongside the old skill first and report overlap.
   - If the user explicitly asks for “no legacy”, “no duplicates”, or removal of the old name, delete the legacy skill with `skill_manage(action='delete', name='<old-skill>')` and verify it is gone.
   - Do not rely only on filename globbing for duplicate checks; scan `~/.hermes/skills/**/SKILL.md` frontmatter and descriptions, assert exactly one current skill name, and assert the legacy name is absent. Then check `skills_list(category='<category>')` and a negative `skill_view('<old-skill>')`.
9. Use `skill_view('<skill-name>')` and `skills_list(category='<category>')` to verify the skill library sees the new skill. If the current session started before the skill existed, explain that a fresh session/reset is needed for it to appear in the prompt's always-on available-skill list.
10. Record only compact durable facts in `fact_store` if paths/versions are likely to matter later; update stale facts instead of adding duplicates.
11. Clean up temporary sparse checkouts after parity/tests pass. Before deletion, make sure no tool/process cwd is inside that checkout (use `cd /` or run cleanup with an explicit safe workdir); deleting the current cwd can make later terminal/file tools fail with `getcwd: No such file or directory`. Verify the temp path is actually removed before documenting it as removed; do not patch a plan/report saying cleanup succeeded in parallel with the cleanup command.

## Pitfalls

- **Package metadata drift:** an editable source checkout may be current while `pip show` is stale. Reinstall editable package after syncing `pyproject.toml`.
- **Skill name migration:** if the refreshed skill has a new name, install it alongside the old skill first. Do not delete the older skill without explicit cleanup approval; instead report overlap and suggest consolidation. If the user explicitly says no legacy/no duplicates, delete the old skill and prove absence with a frontmatter scan plus negative `skill_view`.
- **Duplicate checks by filename are weak:** `search_files` globs can miss installed skills because the name is in frontmatter, not the path. Scan every `SKILL.md` under the skill root and parse `name:` / `description:` when proving there is only one active skill for a domain.
- **Do not document cleanup before it is verified:** cleanup commands can timeout even for simple `/tmp` removals. Remove temp checkouts, then verify no matching paths remain, then update the plan/report.
- **Prompt cache:** newly installed skills can be loaded by `skill_view`, but the current Telegram/gateway session's available-skills prompt snapshot may remain stale until `/reset` or a fresh session.
- **Plan closeout:** for Konstantin, multi-step durable Hermes state changes need a plan in `/home/konstantin/docs/plans/`, updated with verification and archived after completion.
- **Verification is more than `--version`:** also check module path, package metadata, a no-network smoke command, and tests when available.
