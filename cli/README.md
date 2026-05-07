# CLI backup layer

This directory stores reproducible CLI/source state needed beyond the Hermes overlay.

## `hermes-agent/`

The upstream Hermes Agent checkout is **not** vendored wholesale. Restore by installing/cloning upstream, checking out the recorded commit, then applying `tracked-changes.patch` and copying safe files from `untracked/` if still needed.

## `skill-clis/`

Source snapshots from `/home/konstantin/.hermes/hermes-agent/local/skill-clis` used by local skills. `/home/konstantin/code/clis` is kept as a compatibility symlink. Generated caches, `.git`, virtualenvs, build outputs, and pycache files are excluded.
