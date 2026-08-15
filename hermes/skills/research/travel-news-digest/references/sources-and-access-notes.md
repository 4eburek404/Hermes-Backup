# Source Access Notes

- Runtime catalog: `scripts/sources.yaml`.
- Direct RSS/Atom is preferred.
- Google News RSS covers publishers without a stable public feed.
- Preserve each query's `hl`, `gl`, and `ceid` edition settings.
- A failed source is reported and does not fail the whole digest.
- For requested article details, hand the selected link to `../web-content-acquisition/SKILL.md`; do not add extraction to this CLI.
- Reintroduce HTML fetching only after a named required publisher cannot be covered by RSS or Google News.
