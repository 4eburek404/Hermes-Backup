# Backup manifest

Created UTC: `2026-05-14T00:02:41.757926+00:00`

Hermes home: `/home/konstantin/.hermes`

Hermes Agent source checkout: `/home/konstantin/.hermes/hermes-agent`

Upstream source backup mode: `manifest + patch`, not full vendored repo.

Skill CLIs source: `/home/konstantin/code/clis.separate-repo-20260507-1349`

## Plaintext snapshot

- Holographic memory snapshot: `hermes/holographic-memory/memory_store.sqlite`
- CLI backup: `{'hermes_agent_manifest': 'cli/hermes-agent/manifest.json', 'hermes_agent_patch': None, 'hermes_agent_untracked_copied': 0, 'skill_clis': 'cli/skill-clis', 'skill_clis_entries': ['article', 'flights', 'hh-ru', 'knowledge']}`

## Encrypted artifacts

- Policy: `{'mode': 'auto', 'weekly_encrypted_dow': 6, 'local_weekday': 3, 'local_time': '2026-05-14T02:02:41.757926+02:00', 'max_encrypted_age_days': 8.0, 'retention': 'latest', 'latest_secret_timestamp': '20260512-000538', 'latest_state_timestamp': '20260512-000538', 'secret_age_days': 1.998, 'state_age_days': 1.998, 'existing_encrypted_ok': True, 'encrypted_stale': False, 'secret_metadata_changed': True, 'secret_source_count': 13, 'secret_change_detection_excluded_sources': ['/home/konstantin/.hermes/channel_directory.json'], 'refresh_reason': 'secret_metadata_changed', 'retention_removed_count': 11, 'retention_removed': ['secrets-encrypted/hermes-secrets-20260512-000538.tar.zst.age', 'secrets-encrypted/manifest-20260512-000538.json', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part000', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part001', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part002', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part003', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part004', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part005', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part006', 'session-history-encrypted/hermes-state-and-sessions-20260512-000538.tar.zst.age.part007', 'session-history-encrypted/manifest-20260512-000538.json']}`
- Refreshed this run: `True`
- Secrets manifest: `secrets-encrypted/manifest-20260514-000241.json`
- State/sessions manifest: `session-history-encrypted/manifest-20260514-000241.json`

### secret_artifacts
- `secrets-encrypted/hermes-secrets-20260514-000241.tar.zst.age`

### state_artifacts
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part000`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part001`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part002`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part003`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part004`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part005`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part006`
- `session-history-encrypted/hermes-state-and-sessions-20260514-000241.tar.zst.age.part007`

Raw secret values and transcript contents are intentionally absent from this manifest.
