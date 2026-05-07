# Calendar Event Creation — Python Service-Account Template

Reliable pattern for creating Google Calendar events via the service-account path.
Uses `write_file` → `python3` instead of inline heredoc to avoid quoting issues.

## Template Script

```python
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

SA_KEY = Path('~/.hermes/credentials/gcal_service_account.json').expanduser()
CAL_ID = 'ks.orlov@gmail.com'

creds = service_account.Credentials.from_service_account_file(
    str(SA_KEY), scopes=['https://www.googleapis.com/auth/calendar'])

svc = build('calendar', 'v3', credentials=creds)

# ── Build description with parenthesized string concatenation ──
description_text = (
    "Line 1 of description\n"
    "Line 2 of description\n"
    "Line 3 with special chars: «quotes» etc.\n"
)

event_body = {
    'summary': 'Event Title Here',
    'description': description_text,
    'start': {
        'dateTime': '2026-05-06T18:00:00+05:00',  # ALWAYS include offset
        'timeZone': 'Asia/Yekaterinburg',           # double-check spelling!
    },
    'end': {
        'dateTime': '2026-05-06T19:30:00+05:00',
        'timeZone': 'Asia/Yekaterinburg',
    },
    'reminders': {
        'useDefault': False,
        'overrides': [
            {'method': 'popup', 'minutes': 60},
            {'method': 'email', 'minutes': 60},
        ]
    },
    # Optional: 'location': 'Somewhere',
    # Optional: 'colorId': '5',  # blue/teal for training events
}

event = svc.events().insert(calendarId=CAL_ID, body=event_body).execute()
print(json.dumps({
    'status': 'created',
    'id': event['id'],
    'summary': event['summary'],
    'start': event['start']['dateTime'],
    'end': event['end']['dateTime'],
    'htmlLink': event.get('htmlLink', ''),
}, ensure_ascii=False, indent=2))
```

## invocation Pattern

1. `write_file` the script to `/tmp/create_event.py`
2. `python3 /tmp/create_event.py`
3. Verify by listing events for the target time window

## Key Rules

- **Always include timezone offset** (`+05:00`) in `dateTime` — never send naive datetimes.
- **Verify timezone ID spelling**: `Asia/Yekaterinburg` (not Yekaterinberg).
- **Use parenthesized string concatenation** for multiline descriptions — avoids quoting/escaping issues.
- **Set `useDefault: False`** when specifying custom reminders.
- **After creation, verify** by reading back the event or listing the time window.