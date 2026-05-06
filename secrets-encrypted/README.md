# Encrypted secrets bundle

This directory contains encrypted archives of raw Hermes/Codex credential material required for full restore.

Rules:

- Only `*.tar.zst.age` files and non-secret manifests belong here.
- Raw `.env`, `auth.json`, service-account JSON, app passwords, tokens, private keys, or OAuth refresh tokens must never be committed in plaintext.
- Manifests list source paths and file metadata only; they must not contain values.
- Encryption uses `age` to the SSH public key recorded in each manifest.
