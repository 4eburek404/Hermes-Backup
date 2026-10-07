# Offline reassessment bundle

Run `reassess.py` from any working directory in a clean checkout. It loads the pinned `source/manifest.json`, immutable original `runs/r1`–`runs/r3` raw traces/evidence/scores, and the checked-in development-workflow evaluator. `input-checksums.json` pins the input artifacts against baseline `96ee449e5f956c37c467dde0aa31c80fb98e0731` and the script aborts on mismatch.

The script creates an isolated fixture in a temporary child directory of this bundle, replays only recorded file-patch content in memory, re-extracts test evidence, and overwrites only `reassessment-96ee449/runs/rN/{evidence.json,score.json,event-refs.json}`. It executes no historical command and calls no Hermes binary, provider, model, or network service. Temporary fixture directories are deleted on exit. It uses no pre-existing `/tmp`, `$TMPDIR`, or Hermes cache data.

Each event reference records the raw trace call and result line numbers plus their original sanitized event objects. Evidence records test-source hashes per pytest event and SHA-256 hashes of all original inputs, the manifest, evaluator, and checksum manifest. The report states the verified scores and evidence limits.

Clean-worktree execution is recorded in `clean-copy-verification.json`: all nine generated evidence/score/reference files were byte-identical to the published outputs. The detached worktree was removed after verification.
