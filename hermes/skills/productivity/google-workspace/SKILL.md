---
name: google-workspace
description: "Gmail, Calendar, Drive, Docs, Sheets via OAuth or non-OAuth alternatives (App Password, service accounts, ICS feeds, Apps Script)."
version: 1.0.0
author: Nous Research
license: MIT
metadata:
  hermes:
    tags: [Google, Gmail, Calendar, Drive, Sheets, Docs, Contacts, Email, OAuth]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [himalaya]
---

# Google Workspace

Gmail, Calendar, Drive, Contacts, Sheets, and Docs — through Hermes-managed OAuth, non-OAuth alternatives, and thin CLI/Python wrappers.

## ⚠️ Calendar Execution Gate — READ BEFORE ANY CALENDAR STATE CHANGE

Before **any** Google Calendar operation that changes state (create, update, delete, invite attendees, modify reminders):
1. **Block known-wrong paths, do not merely warn about them.**
2. **For Konstantin's calendar, prefer the established service-account path** (`hermes-calendar@formidable-feat-492812-e9.iam.gserviceaccount.com` shared to calendar `ks.orlov@gmail.com`) rather than starting a user-facing OAuth flow. OAuth setup is for generic/new users or explicit user request.
3. **Do not claim read-only/write capability from API scope alone.** Calendar API scope (`calendar.readonly` vs `calendar`) and Calendar ACL/share role (`reader`/`writer`) are separate. Verify both or state uncertainty.
4. **Timezone is mandatory.** For Konstantin, default to `Asia/Yekaterinburg` / UTC+5 when the user gives a local civil time. Never send a datetime without an explicit offset (`+05:00`) or timezone-aware conversion.
5. **Confirm destructive or externally visible changes.** Creating/deleting events or adding attendees requires a draft/summary and user approval unless the user already gave a specific direct command in the current turn.
6. **Verify after mutation** by reading back the created/changed/deleted event or listing the target time window.

Gmail note: for email operations prefer the `himalaya` skill with Gmail App Password; do not route Konstantin's personal Gmail automation through OAuth unless explicitly requested.

## Current Konstantin Setup — Google Calendar via Service Account

For Konstantin's own calendar tasks, the current working path is **not user-facing OAuth**.

Verified/canonical facts are mirrored in `/home/konstantin/docs/infrastructure.md`:
- Service account: `hermes-calendar@formidable-feat-492812-e9.iam.gserviceaccount.com`
- Calendar ID: `ks.orlov@gmail.com`
- Google Cloud project: `formidable-feat-492812-e9`
- Key file: stored in protected Hermes credentials/config area with chmod 600; do not print secrets and discover the exact path from config/docs only when needed.
- Access method: Python `google-api-python-client` + `google.oauth2.service_account.Credentials`, not `gcalcli --sa`.
- ACL/scope distinction: current ACL check showed writer access, but read jobs may intentionally use `calendar.readonly` scope for safety.

Operational rules:
- **Read-only digest/reporting:** use service-account credentials with `https://www.googleapis.com/auth/calendar.readonly` unless a write is needed.
- **Create/update/delete:** use service-account credentials with `https://www.googleapis.com/auth/calendar`, and verify the Calendar ACL/share role still permits writes before attributing failures.
- **Do not start OAuth setup** for Konstantin's existing Calendar unless explicitly requested; OAuth is a generic fallback/new setup path.
- **CalDAV + App Password is blocked** for Google Calendar; App Password is for Gmail IMAP/SMTP only.
- **colorId is mandatory for Konstantin's family/training events.** Check existing events in the target calendar before creating new ones to match established colorId conventions. Verified convention (2026-05-04): training events (Лед, Зал Сок, Английский язык Паша) use `colorId=5` (teal/blue). Read a few recent events first to confirm the color before batch-creating. Do NOT create events with default color when a convention exists.


## References

- `references/gmail-search-syntax.md` — Gmail search operators (is:unread, from:, newer_than:, etc.)
- `references/calendar-event-python-template.md` — Reliable Python/service-account event creation template (avoids heredoc quoting issues, includes timezone and reminder pitfalls)

## Scripts

- `scripts/setup.py` — OAuth2 setup (run once to authorize generic/new OAuth users)
- `scripts/google_api.py` — OAuth-token compatibility wrapper CLI. It prefers `gws` when available, while preserving Hermes' existing JSON output contract. For Konstantin's existing Calendar, do not assume this OAuth wrapper is the active path; prefer the service-account path above.

## First-Time Setup — Generic OAuth Path Only

This section is for generic/new OAuth setup. **For Konstantin's existing Calendar, do not start here**; use the Current Konstantin Setup/service-account path unless he explicitly asks to configure OAuth.

The OAuth setup is fully non-interactive — you drive it step by step so it works
on CLI, Telegram, Discord, or any platform.

Define a shorthand first:

```bash
GSETUP="python ${HERMES_HOME:-$HOME/.hermes}/skills/productivity/google-workspace/scripts/setup.py"
```

### Step 0: Check if already set up

```bash
$GSETUP --check
```

If it prints `AUTHENTICATED`, skip to Usage — setup is already done.

### Step 1: Triage — ask the user what they need

Before starting OAuth setup, ask the user TWO questions:

**Question 1: "What Google services do you need? Just email, or also
Calendar/Drive/Sheets/Docs?"**

- **Email only** → They don't need this skill at all. Use the `himalaya` skill
  instead — it works with a Gmail App Password (Settings → Security → App
  Passwords) and takes 2 minutes to set up. No Google Cloud project needed.
  Load the himalaya skill and follow its setup instructions.

- **Email + Calendar** → Continue with this skill, but use
  `--services email,calendar` during auth so the consent screen only asks for
  the scopes they actually need.

- **Calendar/Drive/Sheets/Docs only** → Continue with this skill and use a
  narrower `--services` set like `calendar,drive,sheets,docs`.

- **Full Workspace access** → Continue with this skill and use the default
  `all` service set.

**Question 2: "Does your Google account use Advanced Protection (hardware
security keys required to sign in)? If you're not sure, you probably don't
— it's something you would have explicitly enrolled in."**

- **No / Not sure** → Normal setup. Continue below.
- **Yes** → Their Workspace admin must add the OAuth client ID to the org's
  allowed apps list before Step 4 will work. Let them know upfront.

### Step 2: Create OAuth credentials (one-time, ~5 minutes)

Tell the user:

> You need a Google Cloud OAuth client. This is a one-time setup:
>
> 1. Create or select a project:
>    https://console.cloud.google.com/projectselector2/home/dashboard
> 2. Enable the required APIs from the API Library:
>    https://console.cloud.google.com/apis/library
>    Enable: Gmail API, Google Calendar API, Google Drive API,
>    Google Sheets API, Google Docs API, People API
> 3. Create the OAuth client here:
>    https://console.cloud.google.com/apis/credentials
>    Credentials → Create Credentials → OAuth 2.0 Client ID
> 4. Application type: "Desktop app" → Create
> 5. If the app is still in Testing, add the user's Google account as a test user here:
>    https://console.cloud.google.com/auth/audience
>    Audience → Test users → Add users
> 6. Download the JSON file and tell me the file path
>
> Important Hermes CLI note: if the file path starts with `/`, do NOT send only the bare path as its own message in the CLI, because it can be mistaken for a slash command. Send it in a sentence instead, like:
> `The JSON file path is: /home/user/Downloads/client_secret_....json`

Once they provide the path:

```bash
$GSETUP --client-secret /path/to/client_secret.json
```

If they paste the raw client ID / client secret values instead of a file path,
write a valid Desktop OAuth JSON file for them yourself, save it somewhere
explicit (for example `~/Downloads/hermes-google-client-secret.json`), then run
`--client-secret` against that file.

### Step 3: Get authorization URL

Use the service set chosen in Step 1. Examples:

```bash
$GSETUP --auth-url --services email,calendar --format json
$GSETUP --auth-url --services calendar,drive,sheets,docs --format json
$GSETUP --auth-url --services all --format json
```

This returns JSON with an `auth_url` field and also saves the exact URL to
`~/.hermes/google_oauth_last_url.txt`.

Agent rules for this step:
- Extract the `auth_url` field and send that exact URL to the user as a single line.
- Tell the user that the browser will likely fail on `http://localhost:1` after approval, and that this is expected.
- Tell them to copy the ENTIRE redirected URL from the browser address bar.
- If the user gets `Error 403: access_denied`, send them directly to `https://console.cloud.google.com/auth/audience` to add themselves as a test user.

### Step 4: Exchange the code

The user will paste back either a URL like `http://localhost:1/?code=4/0A...&scope=...`
or just the code string. Either works. The `--auth-url` step stores a temporary
pending OAuth session locally so `--auth-code` can complete the PKCE exchange
later, even on headless systems:

```bash
$GSETUP --auth-code "THE_URL_OR_CODE_THE_USER_PASTED" --format json
```

If `--auth-code` fails because the code expired, was already used, or came from
an older browser tab, it now returns a fresh `fresh_auth_url`. In that case,
immediately send the new URL to the user and have them retry with the newest
browser redirect only.

### Step 5: Verify

```bash
$GSETUP --check
```

Should print `AUTHENTICATED`. Setup is complete — token refreshes automatically from now on.

### Notes

- Token is stored at `~/.hermes/google_token.json` and auto-refreshes.
- Pending OAuth session state/verifier are stored temporarily at `~/.hermes/google_oauth_pending.json` until exchange completes.
- If `gws` is installed, `google_api.py` points it at the same `~/.hermes/google_token.json` credentials file. Users do not need to run a separate `gws auth login` flow.
- To revoke: `$GSETUP --revoke`

## Usage

Generic OAuth-wrapper commands go through the API script. For Konstantin's existing Calendar, this is **not** the preferred backend; use the service-account path above.

Set `GAPI` as a shorthand for generic OAuth-wrapper operations:

```bash
GAPI="python ${HERMES_HOME:-$HOME/.hermes}/skills/productivity/google-workspace/scripts/google_api.py"
```

### Gmail

```bash
# Search (returns JSON array with id, from, subject, date, snippet)
$GAPI gmail search "is:unread" --max 10
$GAPI gmail search "from:boss@company.com newer_than:1d"
$GAPI gmail search "has:attachment filename:pdf newer_than:7d"

# Read full message (returns JSON with body text)
$GAPI gmail get MESSAGE_ID

# Send
$GAPI gmail send --to user@example.com --subject "Hello" --body "Message text"
$GAPI gmail send --to user@example.com --subject "Report" --body "<h1>Q4</h1><p>Details...</p>" --html
$GAPI gmail send --to user@example.com --subject "Hello" --from '"Research Agent" <user@example.com>' --body "Message text"

# Reply (automatically threads and sets In-Reply-To)
$GAPI gmail reply MESSAGE_ID --body "Thanks, that works for me."
$GAPI gmail reply MESSAGE_ID --from '"Support Bot" <user@example.com>' --body "Thanks"

# Labels
$GAPI gmail labels
$GAPI gmail modify MESSAGE_ID --add-labels LABEL_ID
$GAPI gmail modify MESSAGE_ID --remove-labels UNREAD
```

### Calendar

For Konstantin's existing calendar, prefer the service-account path described at the top of this skill. The `GAPI` commands below are the generic OAuth-token wrapper path; use them only when OAuth is the intended backend.

```bash
# Generic OAuth wrapper: list events (defaults to next 7 days)
$GAPI calendar list --calendar primary
$GAPI calendar list --calendar primary --start 2026-03-01T00:00:00+05:00 --end 2026-03-07T23:59:59+05:00

# Generic OAuth wrapper: create event (ISO 8601 with explicit timezone required)
$GAPI calendar create --calendar primary --summary "Team Standup" --start 2026-03-01T10:00:00+05:00 --end 2026-03-01T10:30:00+05:00
$GAPI calendar create --calendar primary --summary "Lunch" --start 2026-03-01T12:00:00+05:00 --end 2026-03-01T13:00:00+05:00 --location "Cafe"
$GAPI calendar create --calendar primary --summary "Review" --start 2026-03-01T14:00:00+05:00 --end 2026-03-01T15:00:00+05:00 --attendees "alice@co.com,bob@co.com"

# Generic OAuth wrapper: delete event (requires explicit confirmation unless already directly requested)
$GAPI calendar delete --calendar primary EVENT_ID
```

Blocked wrong path: do not pass local civil times like `2026-05-25T12:00:00` without `+05:00`; the wrapper must reject missing timezones rather than silently treating them as UTC.

- **colorId is mandatory for Konstantin's recurring events.** Before batch-creating events that follow a weekly pattern (training, classes, etc.), list existing events in the target time range and note their `colorId`. Apply the same `colorId` to new events. For Konstantin's Паша training events (Лед, Зал Сок, Английский язык), the convention is `colorId=5`. Omitting colorId defaults to the calendar default color, which breaks visual consistency and requires a follow-up update pass.

### Drive

```bash
$GAPI drive search "quarterly report" --max 10
$GAPI drive search "mimeType='application/pdf'" --raw-query --max 5
```

### Contacts

```bash
$GAPI contacts list --max 20
```

### Sheets

```bash
# Read
$GAPI sheets get SHEET_ID "Sheet1!A1:D10"

# Write
$GAPI sheets update SHEET_ID "Sheet1!A1:B2" --values '[["Name","Score"],["Alice","95"]]'

# Append rows
$GAPI sheets append SHEET_ID "Sheet1!A:C" --values '[["new","row","data"]]'
```

### Docs

```bash
$GAPI docs get DOC_ID
```

## Output Format

All commands return JSON. Parse with `jq` or read directly. Key fields:

- **Gmail search**: `[{id, threadId, from, to, subject, date, snippet, labels}]`
- **Gmail get**: `{id, threadId, from, to, subject, date, labels, body}`
- **Gmail send/reply**: `{status: "sent", id, threadId}`
- **Calendar list**: `[{id, summary, start, end, location, description, htmlLink}]`
- **Calendar create**: `{status: "created", id, summary, htmlLink}`
- **Drive search**: `[{id, name, mimeType, modifiedTime, webViewLink}]`
- **Contacts list**: `[{name, emails: [...], phones: [...]}]`
- **Sheets get**: `[[cell, cell, ...], ...]`

## Calendar Event Style Conventions — Konstantin

When creating recurring/scheduled events for Konstantin's family calendar, always check **existing events first** to match their style (colorId, location, summary format).

Known conventions (verified from calendar history):
- **Training events (Лед, Зал Сок, Английский язык Паша)** → `colorId=5` (blue/turquoise), no reminders
- **Лед (ice rink)** → `location: "Верхняя Салда"`
- **Зал Сок** → no location field
- Before batch-creating, always `list` events for the relevant week first to confirm the current style and detect conflicts.

## Rules

1. **Never send email or create/delete events without confirming with the user first**, unless the user already gave a specific direct command in the current turn. Show the draft content/action summary and ask for approval when intent is ambiguous or the action is destructive/externally visible.
2. **For Konstantin's Calendar, do not treat OAuth auth as the prerequisite.** Use the established service-account path; check OAuth setup only for generic OAuth-wrapper tasks.
3. **Use the Gmail search syntax reference** for complex Gmail queries — load it with `skill_view("google-workspace", file_path="references/gmail-search-syntax.md")`.
4. **Calendar times must include timezone.** For Konstantin, local times default to Asia/Yekaterinburg / `+05:00`; convert explicitly and never send naive datetimes.
5. **ACL and scope are separate.** A `calendar.readonly` script scope is not proof that the service account has only reader ACL; write operations need both `calendar` scope and writer ACL.
6. **Verify after Calendar writes/deletes** by reading the event or listing the target time window.
7. **Respect rate limits** — avoid rapid-fire sequential API calls. Batch reads when possible.

## Non-OAuth Alternatives (when OAuth is blocked, unwanted, or not the established path)

For generic users, OAuth via Desktop client is one possible primary path. For Konstantin's existing Google Calendar, the service-account path above is already established and should be preferred. Below are proven alternatives, ranked by feasibility.

### Quick Reference: Which method for which need?

| Need | Best method | Auth required from user |
|---|---|---|
| Read-only, zero setup | ICS secret feed | None (copy URL once) |
| Read-only, structured API | Public calendar + API key | None (but calendar becomes public) |
| Full access (read + write) | Service account | GC project creation + 1 manual share |
| Flexible, no external keys | Apps Script Web App | 1-time deploy in script.google.com |

### CalDAV + App Password — DOES NOT WORK

Google blocks CalDAV access via App Password. A `PROPFIND` to `https://apidata.googleusercontent.com/caldav/v2/` with basic auth returns `loginRequired`. Do NOT waste time on this path — it's a known dead end. App Password works for IMAP/SMTP only.

### Method A: ICS Secret Feed (read-only, 2 minutes)

1. Google Calendar web → Settings → «Integrate calendar» → copy «Secret address in iCal format»
2. Use directly: `curl -s "https://calendar.google.com/calendar/ical/...SECRET.../basic.ics"`
3. Or sync locally with vdirsyncer (`type = http` storage pointing to the ICS URL)

Pitfall: only main calendar, no shared calendars. Read-only.

### Method B: Service Account (read + write, ~10 minutes)

Full Calendar API access via JSON key — no browser, no consent screen, no redirects.

1. **Install/verify Python dependencies:** use an environment with `google-api-python-client` and `google-auth` available. If missing, install them in the appropriate venv; do not rely on `gcalcli --sa`.
2. **Create service account in GC Console:**
   - https://console.cloud.google.com → project → APIs & Services → enable **Calendar API**
   - Credentials → Create Credentials → **Service Account** (name: e.g. `hermes-calendar`)
   - After creation → Keys → Add Key → JSON → download
3. **Share calendar:** In Google Calendar settings → «Access» → add SA's `client_email` (from JSON, `...@...iam.gserviceaccount.com`) with desired permissions
4. **Save key:** `mkdir -p ~/.hermes/credentials && cp key.json ~/.hermes/credentials/gcal_service_account.json && chmod 600`
5. **Verify (Python-first path — gcalcli `--sa` flag does NOT work in v4.5.1+):**
   ```python
   from pathlib import Path
   from google.oauth2 import service_account
   from googleapiclient.discovery import build

   SA_KEY = Path('~/.hermes/credentials/gcal_service_account.json').expanduser()
   CAL_ID = 'user@gmail.com'
   creds = service_account.Credentials.from_service_account_file(
       str(SA_KEY), scopes=['https://www.googleapis.com/auth/calendar.readonly'])
   svc = build('calendar', 'v3', credentials=creds)
   events = svc.events().list(calendarId=CAL_ID, maxResults=5,
       singleEvents=True, orderBy='startTime').execute()
   for ev in events.get('items', []):
       print(ev['start'].get('dateTime',''), '|', ev.get('summary',''))
   ```
   For write access, use `calendar` scope instead of `calendar.readonly`.

   **Important:** API/OAuth scope and Calendar sharing permission are separate. `calendar.readonly` means this script is intentionally using a read-only scope; it does **not** prove the service account has only Viewer/reader ACL rights. Conversely, write access needs both a write-capable scope (`calendar`) and a Calendar ACL/share role that permits changes (`writer` / UI “Make changes”). Verify ACL separately before saying an account is read-only.
6. **Create event (Python):**
   ```python
   svc.events().insert(calendarId=CAL_ID, body={
       'summary': 'Meeting', 'start': {'dateTime': '2026-04-29T10:00:00+05:00'},
       'end': {'dateTime': '2026-04-29T10:30:00+05:00'}}).execute()
   ```

Pitfalls:
- **gcalcli `--sa` flag does NOT work** in v4.5.1+ — the option is not recognized, falls through as "invalid choice". Use Python/google-api-python-client directly instead.
- Calendar must be explicitly shared with the SA email — without this, API returns empty list
- Google Workspace orgs may block sharing with external SAs; works reliably for `@gmail.com` accounts
- The JSON key provides access to ALL shared calendars — treat it like a password (chmod 600)

### Method C: Apps Script Web App (read + write, no GC project)

1. https://script.google.com → New project
2. Paste script (e.g. `doGet()` returns JSON events via `CalendarApp`)
3. Deploy → New deployment → Web App → execute as «Me», access «Anyone»
4. Use: `curl "https://script.google.com/macros/s/.../exec"`

Pitfalls: URL is public (can be mitigated with IP filtering). Requires JavaScript knowledge.

### Method D: Public Calendar + API Key (read-only)

1. Calendar settings → «Make publicly accessible»
2. Create API key in GC Console (APIs & Services → Credentials → API Key)
3. `curl "https://www.googleapis.com/calendar/v3/calendars/primary/events?key=YOUR_KEY"`

Pitfall: anyone with the calendar link can see events. Read-only.

## Pitfalls — Calendar Event Creation via Python

1. **Typo trap: `Asia/Yekaterinberg` (wrong) vs `Asia/Yekaterinburg` (correct).** The Google Calendar API returns `400 Invalid time zone definition` with no hint about which part is wrong. Always double-check timezone strings character-by-character. Common misspellings: Yekaterinberg → Yekaterinburg, Asia/Yaktutsk → Asia/Yakutsk.

2. **Inline heredoc Python scripts with multiline strings break on quote escaping.** When creating calendar events via the service-account Python path, do NOT pass a multiline Python script as an inline heredoc to terminal — single-quoted strings with newlines and special characters frequently cause `SyntaxError: unterminated string literal`. Instead, write the Python script to a temp file (`/tmp/create_event.py`) with `write_file`, then `python3 /tmp/create_event.py`. This avoids all quoting/escaping issues.

3. **MSK → UTC+5 conversion.** When the user says "16:00 МСК", the Asia/Yekaterinburg datetime is `18:00+05:00` (MSK = UTC+3, Yekaterinburg = UTC+5). Always convert explicitly and show the converted time before making the API call.

4. **Reminders require `useDefault: False` + explicit overrides.** To set a custom reminder (e.g., 1 hour before), the event body must include `'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 60}]}`. Setting only `minutes` without `useDefault: False` silently keeps default reminders instead.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `HttpError 400: Invalid time zone definition` | Typo in timezone ID. Most common: `Asia/Yekaterinberg` → `Asia/Yekaterinburg`. Check character-by-character. See Pitfalls section. |
| `NOT_AUTHENTICATED` from OAuth wrapper | For generic OAuth tasks, run setup Steps 2-5 above. For Konstantin's existing Calendar, this usually means you used the wrong backend; switch to the service-account path instead of starting OAuth. |
| `REFRESH_FAILED` | OAuth token revoked or expired — redo Steps 3-5 only if OAuth is intended |
| `HttpError 403: Insufficient Permission` | Distinguish scope vs ACL: OAuth/service-account token may lack scope, or Calendar share may lack writer role. Verify both before attributing cause. |
| `HttpError 403: Access Not Configured` | Calendar API not enabled in the active Google Cloud project |
| `ModuleNotFoundError` | Install missing Python deps (`google-api-python-client`, `google-auth`) in the active environment |
| Advanced Protection blocks auth | Workspace admin must allowlist the OAuth client ID; irrelevant to service-account Calendar access once the calendar is shared |

## Revoking Access

```bash
$GSETUP --revoke
```
