# Flight-search runtime-only maintenance

Use this reference when runtime state `flight-search` exists in `~/.hermes/skills/productivity/flight-search` but the active `~/.hermes/hermes-agent` release/source tree does not contain `skills/productivity/flight-search`.

## Why this matters

A release-dir Hermes install can load `flight-search` from runtime skill state even when the active release lacks the bundled skill path. In that case, normal source-git commands under `~/.hermes/hermes-agent/skills/productivity/flight-search` are not valid provenance, and `audit_skill.py --path ~/.hermes/skills/...` is a runtime state example that may fail because it expects a repo root.

## Safe workflow

1. Verify the layer before editing:

```bash
readlink -f "$HOME/.hermes/hermes-agent"
test -d "$HOME/.hermes/hermes-agent/skills/productivity/flight-search"; echo "release_has_skill=$?"
test -d "$HOME/.hermes/skills/productivity/flight-search"; echo "runtime_has_skill=$?"  # runtime state guard, not source
```

2. If only runtime has the skill, treat the change as runtime-only. Do not claim source commit/push readiness unless a writable source checkout is separately verified.

3. Make a timestamped backup before runtime edits:

```bash
mkdir -p "$HOME/.hermes/backups/skill-audit/flight-search"
RUNTIME_SKILL="$HOME/.hermes/skills/productivity/flight-search"  # runtime state guard, not source
cp -a "$RUNTIME_SKILL" \
  "$HOME/.hermes/backups/skill-audit/flight-search/runtime-before-$(date +%Y%m%d_%H%M%S)"
```

4. For `audit_skill.py` validation, create a temporary repo and copy the runtime skill under `skills/productivity/flight-search`:

```bash
REPO="$(mktemp -d /tmp/flight-search-audit-repo-XXXXXX)"
RUNTIME_FLIGHT_SEARCH="$HOME/.hermes/skills/productivity/flight-search"  # runtime state guard, not source
AUDIT_HELPER="$HOME/.hermes/skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py"  # runtime state guard, not source
VALIDATE_HELPER="$HOME/.hermes/skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py"  # runtime state guard, not source
mkdir -p "$REPO/skills/productivity"
cp -a "$RUNTIME_FLIGHT_SEARCH" "$REPO/skills/productivity/flight-search"
git -C "$REPO" init -q
git -C "$REPO" config user.email audit@example.invalid
git -C "$REPO" config user.name audit
git -C "$REPO" add skills/productivity/flight-search
git -C "$REPO" commit -q -m runtime-flight-search-baseline
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT_HELPER" \
  --repo "$REPO" --skill flight-search --json > /tmp/flight-search-audit.json
PYTHONDONTWRITEBYTECODE=1 python3 "$VALIDATE_HELPER" \
  /tmp/flight-search-audit.json
```

5. After edits, overlay current runtime into a second temporary repo or the same repo, run `git diff --check`, `audit_skill.py --changed --json`, focused tests, full CLI tests if relevant, `doctor`, and generated-artifact cleanup.

## Reporting rule

Final reports must separate:

- release/source absence vs runtime presence;
- runtime file actually changed;
- temp-repo audit evidence vs source provenance;
- commit/push not performed unless a writable source checkout was verified;
- remaining schema-contract warnings that are deliberately left as separate follow-up.
