# Holographic / fact_store diagnosis — 2026-05-11

Scope: read-only diagnosis of `fact_store` error observed in Telegram session.

Symptom:
- `fact_store.search(query="holographic memory fact_store")` returned: `'NoneType' object has no attribute 'search'`.

Plan:
1. Reproduce tool error with a low-risk read operation.
2. Locate `fact_store` implementation and initialization path in Hermes source.
3. Inspect sanitized config/runtime/log evidence without exposing secrets.
4. Report checked facts, root-cause hypothesis/confirmation, and safe next step.

Out of scope unless explicitly approved:
- Editing Hermes source/config.
- Restarting gateway/session.
- Mutating memory/fact_store contents.
