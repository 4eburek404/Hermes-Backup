# R11B — Docker sandbox validation for Hermes tool-output compaction

Use this when validating Hermes `tool_output_compaction` after a production incident, before any future production deploy or controlled switch.

## Scope

R11B is **sandbox-only validation**:

- no production runtime/config changes;
- no production `~/.hermes` mount;
- no real Telegram token;
- no Telegram/provider/API smoke;
- no manual file-copy hotfix into production;
- no symlink to `/tmp`;
- no ContextCompressor work;
- no file_read/search/web compaction enablement;
- no push unless explicitly requested.

## Required preflight

```bash
cd /tmp/hermes-fork-development-clean-4v5Bch
test "$(pwd)" = "/tmp/hermes-fork-development-clean-4v5Bch" || exit 1
git status --short --branch --untracked-files=all
git ls-files --deleted
test -z "$(git ls-files --deleted)" || { echo "ERROR: tracked files deleted"; git ls-files --deleted; exit 1; }
docker --version
docker compose version || true
```

## Sandbox file set

Create only these paths:

```text
docker/compaction-sandbox/Dockerfile
docker/compaction-sandbox/docker-compose.yml
docker/compaction-sandbox/config.yaml
docker/compaction-sandbox/smoke_compaction_sandbox.py
docker/compaction-sandbox/README.md
```

`docker-compose.yml` should make the runtime offline:

```yaml
services:
  compaction-sandbox:
    build:
      context: ../..
      dockerfile: docker/compaction-sandbox/Dockerfile
    network_mode: "none"
    environment:
      HERMES_HOME: /tmp/hermes-sandbox-home
      HOME: /tmp/hermes-sandbox-home
      HERMES_REPO_ROOT: /workspace/hermes-agent
    tmpfs:
      - /tmp
    volumes: []
```

Note: image build may pull the base image from Docker Hub if not cached. The smoke itself must run with `network_mode: "none"` and make no network/API calls.

## Sandbox config contract

```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms:
    - telegram
  enabled_output_kinds:
    - terminal
  artifact_root: /tmp/hermes-tool-output-compaction-artifacts
  secret_policy: redact_or_block
```

The smoke script should parse this config from inside the container and assert exact values before testing behavior.

## Smoke script contract

The script should exercise the real isolated compaction wrapper, not production Hermes:

- import `compact_tool_output_with_artifact()` from the copied fork source;
- import `ToolOutputCompactionConfig` / `classify_output_kind` for the same gate semantics;
- create a synthetic telegram-like platform context (`platform="telegram"`, synthetic session id);
- set artifact root to `/tmp/hermes-tool-output-compaction-artifacts` inside the container;
- keep `previous_hashes` local to the smoke process;
- construct sensitive fixtures at runtime from safe fragments (for example `"pass" + "word"`) so diff/safety scans do not contain raw credential-looking assignments.

Required scenarios:

1. **Large terminal output**
   - compaction runs;
   - message differs from raw;
   - `Restore:` pointer appears;
   - raw large output / middle marker does not remain in compacted message;
   - `.raw` artifact exists and is under the container artifact root.
2. **Synthetic sensitive-heavy terminal output**
   - summary contains `BLOCKED`;
   - raw synthetic value does not leak;
   - no artifact is created.
3. **Non-terminal output**
   - `read_file` or equivalent non-terminal tool bypasses compaction;
   - output is unchanged;
   - no artifact is created.

Print exactly one JSON summary suitable for final reporting:

```json
{
  "terminal_compacted": true,
  "artifact_created": true,
  "secret_blocked": true,
  "non_terminal_unchanged": true,
  "artifact_root": "/tmp/hermes-tool-output-compaction-artifacts",
  "raw_leak_detected": false
}
```

Exit non-zero if any required boolean is false or `raw_leak_detected` is true.

## Verification sequence

```bash
python3 -m py_compile docker/compaction-sandbox/smoke_compaction_sandbox.py
python3 -m pytest tests/test_tool_output_compaction_chat_payload_dump.py tests/test_tool_output_compaction_provider_bound_messages.py -q

docker compose -f docker/compaction-sandbox/docker-compose.yml build
docker compose -f docker/compaction-sandbox/docker-compose.yml run --rm compaction-sandbox
```

Then perform safety checks. For new files, run `git add -N` first so `git diff` includes them:

```bash
git add -N docker/compaction-sandbox/Dockerfile \
  docker/compaction-sandbox/docker-compose.yml \
  docker/compaction-sandbox/config.yaml \
  docker/compaction-sandbox/smoke_compaction_sandbox.py \
  docker/compaction-sandbox/README.md

git ls-files --deleted
test -z "$(git ls-files --deleted)" || { echo "ERROR: tracked files deleted"; git ls-files --deleted; exit 1; }
git diff --stat
git diff --name-only
git diff | grep -Ei 'api[_-]?key|secret|password|authorization|bearer|telegram.*token|bot.*token' || true
```

Expected grep matches should be policy/config key text only (for example `secret_policy`, `secret_blocked`), not credential values.

Stage only the sandbox files and commit locally:

```bash
git add docker/compaction-sandbox/Dockerfile \
  docker/compaction-sandbox/docker-compose.yml \
  docker/compaction-sandbox/config.yaml \
  docker/compaction-sandbox/smoke_compaction_sandbox.py \
  docker/compaction-sandbox/README.md

git diff --cached --stat
git diff --cached --name-only
git ls-files --deleted
git commit -m "Add Docker sandbox for Hermes compaction validation"
```

Do not push unless explicitly requested.

## Session outcome example

Verified R11B at local commit `fab37933`:

- Docker `29.4.3`, Compose `v5.1.3` available;
- py_compile passed;
- targeted pytest: `15 passed`;
- docker build succeeded;
- smoke JSON: terminal compacted, artifact created under sandbox root, sensitive fixture blocked, non-terminal unchanged, no raw leak;
- final repo clean;
- deleted tracked files: `0`;
- push not performed.

## Common pitfalls

1. **Build isolation vs runtime isolation.** Docker build may need registry access for the base image; the smoke acceptance criterion is no network/API calls at runtime. Use `network_mode: "none"` for the service.
2. **Compose path context.** From `docker/compaction-sandbox/docker-compose.yml`, `build.context: ../..` points at the fork repo root. Verify with `COPY scripts ./scripts` and `COPY tools ./tools`, not production paths.
3. **Artifact root on tmpfs.** With `tmpfs: /tmp`, artifacts are container-local and disappear after the run; this is desired for sandbox validation.
4. **Untracked sandbox files invisible to diff.** Use `git add -N docker/compaction-sandbox/...` before safety diff/grep.
5. **Synthetic secret fixture diff noise.** Build scanner-triggering labels at runtime (`"pass" + "word"`) and assert generated raw values do not leak. Avoid literal credential-looking assignments in committed files.
