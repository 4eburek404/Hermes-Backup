# CLI backup layer

This directory stores reproducible CLI/source state needed beyond the Hermes overlay.

## `hermes-agent/`

The upstream Hermes Agent checkout is **not** vendored wholesale. Restore by installing/cloning upstream, checking out the recorded commit, then applying `tracked-changes.patch` and copying safe files from `untracked/` if still needed.

## `skill-clis/`

Source snapshots from `/home/konstantin/code/clis` used by local skills. Generated caches, `.git`, virtualenvs, build outputs, and pycache files are excluded.

## `skills/`

Codex skill companions that describe how to use the local CLI snapshots. For example, `skills/flight-search` is the workflow guide for `skill-clis/flights`.
