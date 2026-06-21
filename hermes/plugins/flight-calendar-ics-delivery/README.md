# flight-calendar-ics-delivery

Hermes delivery guard for the `flight-calendar-ics` skill.

The skill CLI produces a verified `agent_handoff` with `MEDIA:<path>` and a
safe summary. This plugin handles the Hermes-specific delivery step:

1. `post_tool_call` observes successful `agent_handoff.ready=true` results and
   sends the `.ics` via `send_message`.
2. `transform_tool_result` replaces the raw tool result with a short delivered
   confirmation for the model.
3. `pre_tool_call` blocks later attempts to read, edit, redact, refold, or
   reserialize the already delivered `.ics`.

Optional config:

```yaml
plugins:
  flight_calendar_ics_delivery:
    target: telegram
```

The default target is `telegram`.
