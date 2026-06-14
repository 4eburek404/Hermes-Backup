# Telegram MEDIA Delivery Pitfalls

Diagnosed 2026-06-14 after repeated failures to deliver `.ics` files to Telegram DM topics.

## Root Cause: Streaming Suppresses Final-Send MEDIA Processing

When the gateway streams responses (`streamed=True`), it sets `content_delivered=True` early. The final-send path then logs:

```
Suppressing normal final send for session ...: final delivery already confirmed
(streamed=True previewed=False content_delivered=True).
```

Inline `MEDIA:/path` in chat text is delivered as **literal text** — the user sees the path string, not the file.

## Root Cause: Bare `target="telegram"` Goes to Home Channel

`send_message` with `target="telegram"` (bare platform name) resolves to the **home channel** (`chat_id: 254089514`), NOT the current DM topic. The tool returns `success: true` and `mirrored: true` — the file IS delivered, but to the wrong place. The user in a DM topic never sees it.

## Correct Delivery Pattern

1. After CLI build succeeds (`ok == true`), `chmod 644` the `.ics` file.
2. Use `send_message(action='list')` to find the current topic's `chat_id:thread_id`.
3. Send with numeric target: `send_message(action='send', message='MEDIA:<path>', target='telegram:<chat_id>:<thread_id>')`.
4. Example: `target='telegram:254089514:259454'`.

## Evidence from Gateway Logs

```
2026-06-14 19:58:54,677 INFO gateway.run: Suppressing normal final send ...
    streamed=True previewed=False content_delivered=True
2026-06-14 20:02:18,992 INFO gateway.run: Suppressing normal final send ...
    streamed=True previewed=False content_delivered=True
```

Both inline MEDIA attempts were suppressed. The `send_message` tool calls (message_id 20194, 20201) succeeded but went to home channel (bare `target="telegram"`). Only message_id 20208 with explicit topic target reached the user — but as literal text because it was inline MEDIA in a streaming response. Message_id 20213 with `send_message` + numeric target `telegram:254089514:259454` finally delivered the file correctly.

## Key Code Paths

- `gateway/platforms/base.py` line ~3274: `_send_media` dispatches `.ics` → `send_document` (not image/video/audio).
- `gateway/platforms/telegram.py` line 3268: `send_document` uses `bot.send_document` with `InputFile`.
- `tools/send_message_tool.py` line 22: `_TELEGRAM_TOPIC_TARGET_RE = re.compile(r"^\s*(-?\d+)(?::(\d+))?\s*$")` — numeric `chat_id:thread_id` is the unambiguous format.
- `gateway/platforms/base.py` line 834: `.ics` → `"text/calendar"` in `SUPPORTED_DOCUMENT_TYPES`.
