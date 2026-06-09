# Structural Cleanup Review

Use this note when the user asks to bring `flight-calendar-ics` into a clean structured state before feature work. It records durable audit findings from a read-only cleanup review; verify live state again before editing.

## Read-only review sequence

1. Prove active runtime path and source checkout separately.
   - Runtime skill path: `~/.hermes/skills/productivity/flight-calendar-ics`.
   - Source checkout may be under a backup/source repo; do not assume runtime is source.
2. Check duplicate active skills by searching for `SKILL.md` files with `name: flight-calendar-ics` under active skill roots.
3. Compare full runtime/source manifests, excluding generated artifacts and caches; do not rely on a single file diff.
4. Run functional validation without creating persistent bytecode/cache artifacts:
   - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_flight_calendar_ics_cli.py`
   - `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_flight_calendar_ics_cli -v`
   - `python scripts/flight_calendar_ics.py --json doctor`
   - safe sample `build make` from a non-private template in a temp output directory.
   - `python scripts/travelpayouts_airport_catalog.py inspect`
5. Run skill audit from a temporary top-level repo that contains `skills/` if the real source layout is nested; classify that result as validation evidence, not source provenance.

## Cleanup priorities

1. **Active loader ambiguity:** backup directories inside `~/.hermes/skills/...` with the same frontmatter `name` are hygiene blockers. Move them outside the active loader tree or change backup frontmatter; do not silently delete.
2. **Source/runtime drift:** a runtime-only diff is not automatically garbage. Inspect whether it encodes durable behavior or a recent correction, then promote it to source before source→runtime sync.
3. **Audit scanner calibration:** secret-like blockers in code/tests may be false positives from variable forwarding, placeholders, or redaction fixtures. Classify with redacted context and AST/structure before calling them leaks.
4. **Envelope contract alignment:** if generic skill audit expects an `issues` field but this CLI validates against its own `schemas/cli-envelope.v1.schema.json`, resolve the contract mismatch deliberately instead of treating a passing `doctor` as enough.
5. **Registry legacy names:** retired filenames listed as absorbed legacy names can look like broken references to scanners. Reformat them as non-link labels or teach the scanner that the block is intentionally historical.
6. **Schema openness:** document intentional `extensions` surfaces separately from closed core itinerary fields, or tighten the schema if those extension points are no longer required.

## Report shape

For read-only cleanup reviews, report:

- active path/source path/branch/HEAD/status;
- exact functional test results;
- runtime/source parity counts and differing files;
- audit blockers as confirmed vs unconfirmed/calibration items;
- structural cleanup order;
- explicit statement that no files were changed if scope was read-only.

Do not print PNRs, booking URLs, passenger names, document/contact/payment data, generated deep links, bearer tokens, or full private artifact contents in the report.
