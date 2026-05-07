#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${HERMES_BACKUP_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
expected_remote="${HERMES_BACKUP_EXPECTED_REMOTE:-https://github.com/4eburek404/Hermes-Backup.git}"
status_file="${HERMES_BACKUP_STATUS_FILE:-$HOME/.hermes/backup-runner-status.json}"
max_age_days="${HERMES_BACKUP_MAX_ENCRYPTED_AGE_DAYS:-8}"
commit_message="${HERMES_BACKUP_COMMIT_MESSAGE:-backup: $(date -u +%F) nightly}"

json_escape() {
  python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))'
}

write_status() {
  local status="$1"
  local detail="$2"
  mkdir -p "$(dirname "$status_file")"
  local detail_json
  detail_json="$(printf '%s' "$detail" | json_escape)"
  cat >"$status_file.tmp" <<EOF
{"status":"$status","detail":$detail_json,"updated_at_utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","repo":"$repo_dir"}
EOF
  mv "$status_file.tmp" "$status_file"
}

fail() {
  write_status "failed" "$1"
  echo "backup failed: $1" >&2
  exit 1
}

cd "$repo_dir"

remote_url="$(git remote get-url origin)"
[[ "$remote_url" == "$expected_remote" ]] || fail "unexpected origin remote: $remote_url"

git fetch origin main
branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || fail "checkout is on $branch, expected main"

[[ -z "$(git status --porcelain)" ]] || fail "working tree is dirty before backup"

local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/main)"
[[ "$local_head" == "$remote_head" ]] || fail "local HEAD does not match origin/main before backup"

python3 scripts/collect-hermes-backup.py --encrypted-mode auto --max-encrypted-age-days "$max_age_days" --retention latest
python3 scripts/verify-hermes-backup.py --max-encrypted-age-days "$max_age_days" --require-single-active-generation
git diff --check

git add -A
if git diff --cached --quiet; then
  write_status "ok" "no changes"
else
  git commit -m "$commit_message"
  git push origin main
  git fetch origin main
  local_head="$(git rev-parse HEAD)"
  remote_head="$(git rev-parse origin/main)"
  [[ "$local_head" == "$remote_head" ]] || fail "local HEAD does not match origin/main after push"
  write_status "ok" "committed and pushed $local_head"
fi
