# Hermes fork release-sync conflict playbook

Session source: 2026-05-10 preparation for syncing Konstantin's Hermes fork from `origin/main` to upstream release tag `v2026.5.7` / Hermes Agent `0.13.0`.

Use this reference when updating a forked/source-installed Hermes checkout, especially when Konstantin's source/runtime skill layout is involved.

## Safe update shape

1. Verify primary checkout before any update action:

```bash
cd ~/.hermes/hermes-agent
git branch --show-current
git rev-parse --short=12 HEAD
git status --short
git remote -v
```

2. Fetch refs, but do not merge in the active checkout if it is dirty:

```bash
git fetch origin main --prune
git fetch upstream main --tags --prune
```

3. Export dirty state before touching anything else:

```bash
mkdir -p /home/konstantin/docs/plans/artifacts
git status --short > /home/konstantin/docs/plans/artifacts/<date>-hermes-pre-update-dirty.status
git diff --binary > /home/konstantin/docs/plans/artifacts/<date>-hermes-pre-update-dirty.patch
```

4. Create an isolated analysis worktree/branch from `origin/main`, then merge the release tag there only:

```bash
git worktree add -b sync/hermes-<release>-analysis /tmp/hermes-<release>-sync-analysis origin/main
cd /tmp/hermes-<release>-sync-analysis
git merge --no-commit --no-ff <release-tag>
```

Do not run `hermes update`, push, restart gateway, reset/stash-pop, or commit in the active checkout until the isolated branch is resolved and verified.

## Stage-aware conflict analysis

For each conflicted file, compare all stages, not just conflict markers:

```bash
git show :1:<path>   # merge base
git show :2:<path>   # ours / fork origin/main
git show :3:<path>   # theirs / upstream release tag
git diff --cc -- <path>
git log --oneline --left-right --cherry-pick origin/main...<release-tag> -- <path>
```

Document for every file:

- what the fork changed and why;
- what upstream changed;
- whether upstream fixed the same problem, a neighboring problem, or an unrelated one;
- the proposed resolution and verification gate.

## Known `v2026.5.7` conflict lessons

### `agent/curator.py`

Fork purpose: preserve Konstantin's source/runtime split. Authored skill source is the repo checkout `~/.hermes/hermes-agent/skills`; `~/.hermes/skills` is runtime state/archive.

Upstream changes: dry-run mode, first-run deferral, richer reports, activity metrics, `absorbed_into` handling, runtime review model binding, and defensive `~/.hermes/logs/curator` creation.

Resolution pattern: keep upstream curator functionality, but keep fork source-layout truth. Do not commit hardcoded `/home/konstantin/...` paths in prompts; use checkout/profile-safe wording or tool-based paths.

### `scripts/release.py`

Fork purpose: add a fork-specific contributor mapping for `4eburek404`.

Upstream changes: large `AUTHOR_MAP` expansion/corrections.

Resolution pattern: union maps. Do not choose one side and drop either upstream mappings or the fork-specific mapping. Avoid copying private email details into reports.

### `tools/skill_usage.py`

Fork purpose: keep `get_skills_dir()` for source and `get_skills_state_dir()` for runtime state. `.usage.json`, `.archive`, `.bundled_manifest`, and hub lock state must not be treated as authored source.

Upstream changes: file locking, curator-managed provenance, `latest_activity_at()` / `activity_count()`, recursive archive restore, hub off-limits detection using `install_path` and frontmatter names.

Resolution pattern: base on upstream's provenance/concurrency/restore logic, but preserve fork path invariants:

- `_skills_dir()` -> checkout source (`get_skills_dir()`);
- `_state_dir()` -> runtime state (`get_skills_state_dir()`);
- `_usage_file()` and `_archive_dir()` -> runtime state;
- `_read_bundled_manifest_names()` -> runtime manifest;
- hub lock reading should accumulate keys and frontmatter names from available locks, resolving relative `install_path` against `_skills_dir()`.

## Policy-drift checks after conflict resolution

Upstream release changes may add tests/help text inconsistent with the fork policy even when files do not conflict. In the 0.13 sync, check at least:

- external-dir tests such as `tests/agent/test_external_skills.py` and `tests/tools/test_skill_manager_tool.py::TestExternalSkillMutations` when this fork intentionally ignores `skills.external_dirs`;
- slash-command/help text such as `/reload-skills` and `hermes_cli/tips.py` for stale `~/.hermes/skills` or `skills.external_dirs` claims;
- curator prompt text for source-safe, profile-safe path wording.

## Verification gate before active deployment

After resolving conflicts in the isolated worktree, first stage only the resolved conflict files and any deliberately adapted focused tests. This clears the merge index without committing and avoids accidentally adding the whole upstream release diff:

```bash
git add agent/curator.py scripts/release.py tools/skill_usage.py \
  tests/agent/test_curator.py tests/tools/test_skill_usage.py
git ls-files -u | wc -l
git diff --name-only --diff-filter=U -- \
  agent/curator.py scripts/release.py tools/skill_usage.py \
  tests/agent/test_curator.py tests/tools/test_skill_usage.py
```

Use scoped verification for the files you resolved, because a release-tag merge can contain unrelated upstream whitespace or documentation issues that make all-repo `git diff --cached --check` noisy. Run both a scoped whitespace check and a precise conflict-marker scan on the changed files:

```bash
git diff --cached --check -- \
  agent/curator.py scripts/release.py tools/skill_usage.py \
  tests/agent/test_curator.py tests/tools/test_skill_usage.py
python3 - <<'PY'
from pathlib import Path
files = [
    Path('agent/curator.py'),
    Path('scripts/release.py'),
    Path('tools/skill_usage.py'),
    Path('tests/agent/test_curator.py'),
    Path('tests/tools/test_skill_usage.py'),
]
hits=[]
for p in files:
    for i,l in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(),1):
        if l.startswith('<<<<<<< ') or l == '=======' or l.startswith('>>>>>>> '):
            hits.append((str(p), i, l))
print('marker_hits=', len(hits))
for f,i,l in hits:
    print(f'{f}:{i}:{l}')
PY
```

Then run syntax and focused tests:

```bash
python3 -m py_compile agent/curator.py scripts/release.py tools/skill_usage.py \
  tests/agent/test_curator.py tests/tools/test_skill_usage.py
python3 -m pytest \
  tests/agent/test_curator.py \
  tests/agent/test_curator_activity.py \
  tests/agent/test_curator_reports.py \
  tests/tools/test_skill_usage.py \
  -q -o 'addopts='
```

When adapting tests for Konstantin's source/runtime split, use separate fixture paths: source skills under the checkout `skills/` tree or a monkeypatched `_skills_dir()`, and runtime state under `get_skills_state_dir()` / `$HERMES_HOME/skills`. Reload modules after monkeypatching `HERMES_HOME` when helpers resolve paths at import time. Keep dummy credentials explicit non-secret values such as `slot-key`, `ignored-key`, or `legacy-key`; avoid placeholder strings that redaction layers may rewrite in transcripts and confuse expected assertions.

Then add/adapt focused tests for source/runtime policy and release attribution.

## Additional post-resolution gates learned from the 0.13 sync

After the conflict-file gate passes, run at least one selected broader gate before commit decision. The 0.13 sync used this set because it exercises the surfaces most likely to regress after source/runtime and external-dir policy adaptations:

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest \
  tests/agent/test_skill_commands.py \
  tests/agent/test_skill_commands_reload.py \
  tests/cli/test_cli_reload_skills.py \
  tests/gateway/test_reload_skills_command.py \
  tests/gateway/test_reload_skills_discord_resync.py \
  tests/gateway/test_gateway_command_help.py \
  tests/gateway/test_discord_slash_commands.py \
  tests/gateway/test_update_command.py \
  tests/gateway/test_update_streaming.py \
  tests/hermes_cli/test_cmd_update.py \
  tests/hermes_cli/test_update_autostash.py \
  tests/hermes_cli/test_update_gateway_restart.py \
  tests/hermes_cli/test_update_stale_dashboard.py \
  tests/hermes_cli/test_update_yes_flag.py \
  -q -o 'addopts='
```

If this gate exposes a stale test expectation, verify the runtime source before patching the test. Example from 0.13: `hermes_cli/main.py::_install_python_dependencies_with_optional_fallback()` intentionally removed `--quiet` from `pip install` commands so slow dependency builds show progress; `tests/hermes_cli/test_update_autostash.py` still mocked exact commands with `--quiet`, so the fallback path was not exercised. Correct fix: update the mock/expected install commands to match the current code (`uv pip install -e .[all]`, `-e .`, `-e .[extra]`), then rerun the focused regression and the selected broader gate.

Before commit decision, remember that a successful merge can have the entire upstream release diff staged, not only the locally resolved files. Check staging shape explicitly:

```bash
git status --porcelain=v1 -z | python3 - <<'PY'
import sys, collections
entries=[e.decode() for e in sys.stdin.buffer.read().split(b'\0') if e]
counts=collections.Counter(e[:2] for e in entries)
staged=[e[3:] for e in entries if e[:2] != '??' and e[0] in 'MADRC']
unstaged=[e[3:] for e in entries if e[:2] != '??' and e[1] in 'MADRC']
untracked=[e[3:] for e in entries if e[:2] == '??']
print('status_entries=', len(entries))
print('code_counts=', dict(sorted(counts.items())))
print('staged_count=', len(staged))
print('unstaged_count=', len(unstaged))
print('untracked_count=', len(untracked))
PY
git ls-files -u | wc -l
```

A clean selected gate plus `unmerged=0` means “closer to commit-ready,” not “deploy-ready.” Commit/push/update/restart still require staged-diff policy review and separate reconciliation of the dirty primary checkout.

Only after the sync branch is verified should it be committed/pushed and considered for active checkout update + gateway restart.
