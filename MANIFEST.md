# Backup manifest

Created UTC: `2026-05-07T13:35:39.383536+00:00`

Hermes home: `/home/konstantin/.hermes`

Hermes Agent source checkout: `/home/konstantin/.hermes/hermes-agent`

Upstream source backup mode: `manifest + patch`, not full vendored repo.

Skill CLIs source: `/home/konstantin/code/clis`

## Plaintext snapshot

- Holographic memory snapshot: `hermes/holographic-memory/memory_store.sqlite`
- CLI backup: `{'hermes_agent_manifest': 'cli/hermes-agent/manifest.json', 'hermes_agent_patch': 'cli/hermes-agent/tracked-changes.patch', 'hermes_agent_untracked_copied': 2, 'skill_clis': 'cli/skill-clis', 'skill_clis_entries': ['article', 'flights', 'hh-ru', 'knowledge']}`

## Encrypted artifacts

- Policy: `{'mode': 'always', 'weekly_encrypted_dow': 6, 'local_weekday': 3, 'local_time': '2026-05-07T15:35:39.383536+02:00', 'max_encrypted_age_days': 8.0, 'retention': 'latest', 'latest_secret_timestamp': '20260506-151544', 'latest_state_timestamp': '20260506-151544', 'secret_age_days': 0.9305, 'state_age_days': 0.9305, 'existing_encrypted_ok': True, 'encrypted_stale': False, 'secret_metadata_changed': True, 'secret_source_count': 13, 'secret_change_detection_excluded_sources': ['/home/konstantin/.hermes/channel_directory.json'], 'refresh_reason': 'forced_always', 'retention_removed_count': 7, 'retention_removed': ['secrets-encrypted/hermes-secrets-20260506-151544.tar.zst.age', 'secrets-encrypted/manifest-20260506-151544.json', 'session-history-encrypted/hermes-state-and-sessions-20260506-151544.tar.zst.age.part000', 'session-history-encrypted/hermes-state-and-sessions-20260506-151544.tar.zst.age.part001', 'session-history-encrypted/hermes-state-and-sessions-20260506-151544.tar.zst.age.part002', 'session-history-encrypted/hermes-state-and-sessions-20260506-151544.tar.zst.age.part003', 'session-history-encrypted/manifest-20260506-151544.json']}`
- Refreshed this run: `True`
- Secrets manifest: `secrets-encrypted/manifest-20260507-133539.json`
- State/sessions manifest: `session-history-encrypted/manifest-20260507-133539.json`

### secret_artifacts
- `secrets-encrypted/hermes-secrets-20260507-133539.tar.zst.age`

### state_artifacts
- `session-history-encrypted/hermes-state-and-sessions-20260507-133539.tar.zst.age.part000`
- `session-history-encrypted/hermes-state-and-sessions-20260507-133539.tar.zst.age.part001`
- `session-history-encrypted/hermes-state-and-sessions-20260507-133539.tar.zst.age.part002`
- `session-history-encrypted/hermes-state-and-sessions-20260507-133539.tar.zst.age.part003`
- `session-history-encrypted/hermes-state-and-sessions-20260507-133539.tar.zst.age.part004`

Raw secret values and transcript contents are intentionally absent from this manifest.
