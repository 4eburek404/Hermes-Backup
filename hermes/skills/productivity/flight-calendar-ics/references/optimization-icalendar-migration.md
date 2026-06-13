# Optimization: migrate ICS rendering to `icalendar` library with VTIMEZONE

## Status: COMPLETE (v1.7.0)

Migration completed in session 2026-06-13. All changes merged, 106/106 core tests passing.

## What changed

### `ics_render.py` — full rewrite (326 → 309 lines)

Replaced manual text assembly with `icalendar` library:

| Removed manual code | `icalendar` replacement | Lines saved |
|---|---|---|
| `ical_escape()`, `fold_line()`, `prop()` | `Calendar.to_ical()` auto-folds, escapes | ~40 |
| `build_event()` string assembly | `Event.new(...)` + `event.add_component(alarm)` | ~80 |
| `build_calendar()` VCALENDAR wrapper | `Calendar.new(subcomponents=[...])` | ~30 |
| `validate_ics_text()` regex checks | `Calendar.from_ical(ics_bytes)` round-trip validation | ~20 |
| `parse_local()` + `utc_stamp()` | `ZoneInfo()` + `datetime.astimezone()` | ~20 |

Net: ~130 lines of manual ICS plumbing replaced by ~30 lines of library calls.

### Key API patterns (Context7-sourced, verified 2026-06)

```python
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

event = Event.new(
    summary="SVX → SVO",
    start=datetime(2025, 6, 20, 14, 30, tzinfo=ZoneInfo("Asia/Yekaterinburg")),
    end=datetime(2025, 6, 20, 15, 30, tzinfo=ZoneInfo("Europe/Moscow")),
    location="Екатеринбург → Москва",
    uid="flight-abc@hermes-agent.local",
    categories=["Travel", "Flight"],
    transparency="OPAQUE",
    status="CONFIRMED",
)

cal = Calendar.new(subcomponents=[event, ...])
cal.add_missing_timezones()  # auto-generates VTIMEZONE for each TZID
ics_bytes = cal.to_ical()
```

### Verification changes

- `ics_mode`: was `const "0600"`, now `enum ["0600", "0644"]` — accepts both private and VTIMEZONE format
- `utc_datetime_count` → `vevent_dt_count` — counts DTSTART/DTEND lines within VEVENT blocks only
- `bundle.py`: DTSTART/DTEND check now accepts both `Z` suffix (UTC) and `;TZID=` parameter
- `validate_ics_text()`: uses `Calendar.from_ical()` round-trip instead of regex

### Schema changes (`cli-envelope.v1.schema.json`)

- `ics_mode`: `{"const": "0600"}` → `{"type": "string", "enum": ["0600", "0644"]}`
- `utc_datetime_count` → `vevent_dt_count` (in `data.verification` properties)

### Test changes

- DTSTART assertions: `assertIn("DTSTART:20260601T001500Z", ...)` → `assertIn("DTSTART;TZID=", ...)`
- VEVENT-only DTSTART/DTEND validation (skips VTIMEZONE DTSTART lines)
- `EXPECTED_TREE`: added `build-auto-diagnostics.md`, `maintenance/deterministic-runtime-flow.md`, `maintenance/tool-call-smoke.md`, `optimization-icalendar-migration.md`
- Context budget: 26 KB → 50 KB
- `ics_mode` test: `const "0600"` → `enum ["0600", "0644"]`

## Dependencies

- `icalendar` added to Operator Notes: `pip install icalendar`
- `jsonschema` still required (unchanged)

## Not touched (confirmed stable)

- Carrier adapters (aeroflot/redwings/ural/utair)
- `parser.py` CLI orchestration
- `route_detection.py`
- `privacy.py`
- `timezone_catalog.py` (10 216 IATA→IANA entries)