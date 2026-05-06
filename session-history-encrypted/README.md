# Encrypted state and session history bundle

This directory contains encrypted archives for privacy-heavy runtime history:

- consistent SQLite backup of `~/.hermes/state.db`;
- `~/.hermes/sessions/` transcript files;
- practical old `state.db.bak-*` files when included by the collector.

Rules:

- Raw DBs and raw session transcripts must never be committed in plaintext.
- Large encrypted archives are split into `*.tar.zst.age.partNNN` files to stay below GitHub's regular-file limit.
- The normal policy keeps one active generated state/session manifest and only its referenced parts in HEAD. Old encrypted blobs may still exist in Git history, but not in the current tree.
- Restore by concatenating parts in lexical order, decrypting with `age`, then extracting with `tar --zstd`.
- Test-decrypt should verify names/counts/SQLite integrity without printing transcript contents.
