# Skill Recovery Diagnostics

## When skills appear missing after release-dir migration or sync reset

### Quick verification checklist

1. **Count runtime skills vs bundled manifest:**
   ```bash
   echo "Runtime SKILL.md count:"
   find ~/.hermes/skills -maxdepth 4 -type f -name 'SKILL.md' | wc -l
   echo "Manifest lines:"
   wc -l ~/.hermes/skills/.bundled_manifest
   echo "Bundled (release) SKILL.md count:"
   find ~/.hermes/hermes-agent/skills -maxdepth 4 -type f -name 'SKILL.md' | wc -l
   ```

2. **Identify non-bundled (custom/user) skills not in release:**
   ```bash
   find ~/.hermes/hermes-agent/skills -maxdepth 4 -type f -name 'SKILL.md' -printf '%P\n' | sort > /tmp/bundled.txt
   find ~/.hermes/skills -maxdepth 4 -type f -name 'SKILL.md' -printf '%P\n' | sort > /tmp/runtime.txt
   comm -23 /tmp/runtime.txt /tmp/bundled.txt
   ```

3. **Check state recovery backups:**
   ```bash
   ls -la ~/.hermes/state-recovery-backups/
   find ~/.hermes/state-recovery-backups -maxdepth 5 -type f -name 'SKILL.md' -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' | sort | tail -30
   ```

4. **Verify skill-owned subdirectories (references/, scripts/, cli/, assets/):**
   ```bash
   find ~/.hermes/skills -maxdepth 3 -type d -name 'references' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort
   find ~/.hermes/skills -maxdepth 3 -type d -name 'scripts' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort
   find ~/.hermes/skills -maxdepth 3 -type d -name 'cli' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort
   ```

### Key facts

- **State recovery backups** are created automatically at `~/.hermes/state-recovery-backups/R<version>_<timestamp>/skills.current/`. These are snapshots of `~/.hermes/skills/` taken before a release switch.
- **`.bundled_manifest`** tracks origin hashes for change detection. If it's stale (skills listed but files absent from state dir), recovery is: delete manifest, let `sync_skills()` repopulate.
- **Custom skills** (not in the upstream release) survive sync because `sync_skills()` only copies bundled skills into state dir. User-created and hub-installed skills are never overwritten.
- **Skill-owned directories** (references/, scripts/, cli/, assets/) are NOT synced by `sync_skills()`. They must be checked separately.
- **Recovery sources** for truly lost skills:
  1. `~/.hermes/state-recovery-backups/` (automatic pre-switch snapshots)
  2. `~/.hermes/skills/.curator_backups/` (curator-managed backups)
  3. `~/.hermes/skills/.archive/` (curator-archived stale skills)
  4. Git history in `~/.hermes/hermes-agent/` (for skills tracked in the repo)
  5. GitHub remote branches (for committed and pushed skill changes)

### Custom skill identification

Use the inventory helper:
```bash
python3 ~/.hermes/skills/autonomous-ai-agents/hermes-agent/scripts/inventory-custom-skills.py --repo ~/.hermes/hermes-agent
```

Or manually compare frontmatter `name` fields between bundled and runtime.

### Pitfall: MD5 comparison is not enough

Two skills can have the same relative path and different content (user modified since sync). When verifying recovery:
- Compare by **content hash** (md5sum), not just path existence
- Check mtime: if runtime mtime > bundled mtime, the skill has been locally edited
- The `comm` path-only comparison will miss content divergence

### Pitfall: Untracked git references/

Skills in the repo with `references/` directories that are not committed (showing as `??` in `git status`) will NOT be synced by `sync_skills()` — they need to be manually copied or committed and pushed.