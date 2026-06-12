# Privacy Hardening

This reference owns durable safety rules. Deterministic redaction and bundle checks belong in `privacy.py`, `bundle.py`, schema contracts, and tests.

## Sensitive classes

Never print, commit, fixture, summarize, or store in docs:

- full private carrier booking URLs or deep links;
- booking keys, locators, access keys, and equivalent credentials;
- passenger names and identity fields;
- ticket numbers, document, contact, and payment data;
- generated request headers or authentication material;
- generated `.ics` body text from a real booking.

Use placeholders in examples. Keep private values only in local private input files and generated private bundles.

## CLI expectations

- JSON envelopes may expose safe paths, counts, route names, error codes, and redacted evidence.
- Route detection evidence must be host/fingerprint based and safe.
- Private bundle files should be mode-restricted.
- Diagnostic commands must be read-only unless a separate explicit mutating mode is approved.

## Test pattern

Lock safety invariants with positive behavior tests:

- redaction replaces private-looking values;
- bundle verification reports private modes and no placeholders;
- envelopes validate against schema;
- chat-summary omission classes are listed in `doctor.data.agent_contract.privacy`;
- fixtures are synthetic and do not contain real booking data.

Do not add long-lived tests that merely assert removed helper names or deleted files are absent. Use one-off scans as audit evidence and protect active behavior with contract tests.

## Reporting

Final reports should list changed files, commands, pass/fail status, and safe counts. Do not include private matches, source document text, generated `.ics` contents, or raw carrier responses.
