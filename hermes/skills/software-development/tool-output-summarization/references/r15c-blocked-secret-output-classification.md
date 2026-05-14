# R15C Blocked Secret Output Classification

Use this reference when auditing whether blocked secret-heavy tool outputs are true positives, false positives, or ambiguous without exposing raw session content.

## Trigger

Run this pattern after a compaction effectiveness audit reports blocked outputs and a raw-leak audit shows no live leaks, but the user needs to know whether the secret detector is over-cautious.

## Safety boundary

- Do not change production, restart gateway, edit config, change compaction scope, or tune secret policy during the audit.
- Do not print raw session messages, raw terminal output, raw artifacts, or matched secret values.
- Do not use `grep -R ~/.hermes/sessions` with line output.
- If a content fingerprint is needed, print only `sha256(content)[:12]`.
- Scanner output must be metadata/category only.

## Sanitized classifier fields

For each blocked candidate, emit only:

- `session_file` basename and `session_mtime`
- `platform`, if available
- `output_kind`, if available
- `content_length`, `newline_count`
- `blocked_marker`, `redacted_marker`
- `artifact_created`
- `secret_pattern_category`: `token_like`, `private_key_like`, `env_secret_like`, `credential_url_like`, `api_key_like`, or `unknown`
- `sha256_prefix`, never content
- `classification`: `likely_true_secret`, `likely_false_positive`, `ambiguous`, or `unknown`
- reason code

## Classification heuristics

- `likely_true_secret`: private-key markers, credential URLs, API key shapes, env secret assignments with non-placeholder values, or many strong secret-like matches.
- `likely_false_positive`: generic secret words without secret shape, stack traces with no credential pattern, package names, hashes, or other non-credential text.
- `ambiguous`: generic secret assignments or insufficient metadata to prove true/false without reading content.
- `unknown`: parser failure or missing required fields.

## Aggregate summary contract

Report at least:

- total blocked outputs
- sessions with blocked outputs
- by platform
- by output kind
- by secret pattern category
- likely true secret count
- likely false positive count
- ambiguous count
- unknown count
- artifact-created count
- raw-saved count, if determinable

## Safety behavior checks

- Blocked outputs should not create raw artifacts when policy is block/discard for secret-heavy outputs.
- If behavior is redaction instead of blocking, document that explicitly.
- Check session/provider messages only by markers and hashes, not raw content.
- Check recent gateway logs with a time-bounded sanitized filter and exclude audit command echoes.

## Verdict rule

- `PASS`: false positives are zero/negligible and true-secret behavior is correct.
- `PASS_WITH_WARNINGS`: ambiguity remains or false positives are possible, but raw-save/return behavior is safe.
- `FAIL`: likely false positives are high, raw secrets leaked, raw artifacts were created for blocked outputs, or compaction has fresh critical errors.

## R15C case result

In the R15C audit, `84/84` blocked outputs were classified with sanitized metadata only: `43` likely true secret, `1` likely false positive, `40` ambiguous, `0` unknown. No blocked-output raw artifact was found by SHA-header check. Verdict: `PASS_WITH_WARNINGS`; keep blocking ambiguous generic-assignment cases until targeted detector tuning reduces ambiguity.
