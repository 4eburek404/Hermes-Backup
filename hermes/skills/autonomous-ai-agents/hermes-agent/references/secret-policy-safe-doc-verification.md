# Secret-policy-safe doc verification

Context: During R15D-1, a validation `grep` over `docs/hermes-compaction-raw-artifact-restore-policy.md` was blocked by active secret policy. The doc intentionally contained terms about secrets, blocked outputs, tokens, API keys, private keys, and credential-like controls. The block did **not** prove that the file contained a real secret.

## Rule

When verifying Hermes policy/runbook docs that intentionally discuss secret-related controls:

- Do not treat blocked `grep` output as proof of a real secret.
- Do not weaken `secret_policy` to make validation output visible.
- Do not rerun broad `grep`/search commands that print matching lines.
- Use yes/no checks that emit only controlled status labels, not matched content.

## Safe patterns

Shell:

```bash
grep -q "TERM" file && echo "TERM: yes" || echo "TERM: no"
```

Python:

```python
from pathlib import Path

p = Path("docs/hermes-compaction-raw-artifact-restore-policy.md")
text = p.read_text(encoding="utf-8")
terms = [
    "artifact_root",
    "symlink",
    "secret re-scan",
    "max bytes",
    "max lines",
    "blocked secret",
    "no scope expansion",
    "Telegram",
    "terminal",
    "R15A",
    "R15B",
    "R15C",
]
for term in terms:
    print(f"{term}: {'yes' if term in text else 'no'}")
```

## Reporting

Say: "The original grep/check output was blocked by secret policy; this may be a documentation-term false positive. I verified required terms with a safe yes/no checker instead."

Do not print raw matched lines from secret-related docs in the final report.
