# Backup manifest

Created UTC: `2026-05-06T13:13:47.232721+00:00`

Hermes home: `/home/konstantin/.hermes`

Hermes Agent source checkout: `/home/konstantin/.hermes/hermes-agent`

Upstream source backup mode: `manifest + patch`, not full vendored repo.

Skill CLIs source: `/home/konstantin/code/clis`

## Plaintext snapshot

- Holographic memory snapshot: `hermes/holographic-memory/memory_store.sqlite`
- CLI backup: `{'hermes_agent_manifest': 'cli/hermes-agent/manifest.json', 'hermes_agent_patch': 'cli/hermes-agent/tracked-changes.patch', 'hermes_agent_untracked_copied': 2, 'skill_clis': 'cli/skill-clis', 'skill_clis_entries': ['article', 'flights', 'hh-ru', 'knowledge']}`

## Encrypted artifacts

### secret_artifacts
- `secrets-encrypted/hermes-secrets-20260506-131347.tar.zst.age`

### state_artifacts
- `session-history-encrypted/hermes-state-and-sessions-20260506-131347.tar.zst.age.part000`
- `session-history-encrypted/hermes-state-and-sessions-20260506-131347.tar.zst.age.part001`
- `session-history-encrypted/hermes-state-and-sessions-20260506-131347.tar.zst.age.part002`
- `session-history-encrypted/hermes-state-and-sessions-20260506-131347.tar.zst.age.part003`

Raw secret values and transcript contents are intentionally absent from this manifest.
