---
name: spec-driven-development
description: Legacy compatibility alias for behavior-driven-development; use only when an existing workflow explicitly requests the old name.
version: 2.0.0
author: Konstantin Orlov + Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: software-development
    tags: [legacy, compatibility, bdd, development]
---

# Legacy compatibility alias

`behavior-driven-development` is the development owner for features, bug fixes,
behavior/contract changes, and behavior-sensitive refactors.

This skill remains temporarily so workflows that still reference the historical
name do not break during migration. It owns no separate methodology or acceptance
contract.

When invoked:

1. load and follow `behavior-driven-development` when it is available;
2. preserve any already-established observed/required behavior and evidence;
3. do not treat this legacy skill name as an acceptance criterion;
4. do not introduce an SDD-specific workflow in parallel with BDD.

The alias can be removed after dependent GitHub workflows have migrated to the
BDD owner.
