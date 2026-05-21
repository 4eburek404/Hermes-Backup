# CLI backup layer

This directory stores reproducible Hermes CLI/source state needed beyond the plaintext overlay.

## `hermes-agent/`

The upstream Hermes Agent checkout is **not** vendored wholesale. Restore by installing/cloning upstream, checking out the recorded commit, then applying `tracked-changes.patch` and copying safe files from `untracked/` if still needed.

Legacy standalone skill CLI snapshots are intentionally not collected. Active skill-owned CLIs live inside their owning skill directories under `hermes/skills/<category>/<skill>/cli/`.
