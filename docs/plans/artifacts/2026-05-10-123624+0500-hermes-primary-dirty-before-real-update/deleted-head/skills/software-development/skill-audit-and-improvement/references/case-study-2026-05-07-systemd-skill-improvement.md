# Case Study: 2026-05-07 Systemd Skill Improvement

This reference records the reusable lessons behind the `skill-audit-and-improvement` workflow. It is not a full session log; it is a compact pattern library for future skill audits.

## What happened

A session consolidated and improved multiple Hermes skills and source/runtime conventions. The most substantial change was upgrading `systemd-web-service-deployment` from a runbook-only skill into a runbook plus read-only owning CLI.

The final branch was `skills-improvements`; the relevant commit was `f5fbba25086771fb14435e1e2409c4335c1fb8c3`.

## What worked

1. **Provenance before editing**
   - Branch, HEAD, status, and target diffs were checked before modifying skill files.
   - This prevented stale assumptions about `/home/konstantin/code/clis`, `local/skill-clis`, and runtime `~/.hermes/skills`.

2. **Owning-skill CLI placement**
   - The CLI was placed under the skill that owns it:
     `skills/devops/systemd-web-service-deployment/cli/`.
   - This matched the new source model and avoided resurrecting stale shared CLI directories.

3. **Read-only default**
   - The CLI became an auditor/verifier, not a deployer.
   - It did not restart services, reload systemd, enable Tailscale Funnel, chown files, deploy artifacts, or write production files.

4. **Structured JSON output**
   - Commands returned top-level `ok`, `command`, `data`, and `issues` fields.
   - This made future agent reasoning deterministic.

5. **Independent review**
   - A fresh reviewer found a Basic Auth redirect risk that self-review missed.
   - Fix: do not follow redirects when an Authorization header is present.

6. **Security and stale-path scans**
   - Secret scans forced redaction of examples.
   - Stale-path scans prevented old CLI/source layout from creeping back in.

7. **Commit/push discipline**
   - Dirty source changes became reproducible only after commit and push.
   - Backup intentionally stores repo refs, not dirty development files.

## What should be repeated

For future skill audits:

```bash
cd /home/konstantin/.hermes/hermes-agent
git status --short --branch --untracked-files=all
git diff -- skills/<category>/<skill>/
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json
```

For new or changed Python scripts/CLIs, use an AST syntax check that does not create repo-local bytecode:

```bash
python3 - <<'PY'
from pathlib import Path
import ast
path = Path('<script.py>')
ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('syntax_ok')
PY
```

For owning CLIs with tests:

```bash
cd skills/<category>/<skill>/cli
python3 -m unittest discover -s tests -v
python3 -m <module> --json doctor
```

## Failure modes to guard against

- Treating a runtime directory as source.
- Leaving important skill edits dirty and then reporting them as backed up.
- Creating a one-off skill instead of patching a class-level workflow.
- Embedding real secrets or credential-shaped values in examples.
- Adding a CLI that mutates production state by default.
- Skipping a fresh independent review for security-sensitive code.
- Ignoring prompt-cache/fresh-session boundaries after adding new skills.

## Audit conclusion pattern

A complete skill-audit report should answer:

- What was changed?
- Why was this the correct layer: skill body, reference, template, script, CLI, memory, docs, or fact store?
- What evidence proves it works?
- What remains unrelated or baseline?
- How can it be rolled back?
