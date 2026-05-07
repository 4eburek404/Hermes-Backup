---
name: himalaya
description: "Himalaya CLI: IMAP/SMTP email from terminal."
version: 1.0.0
author: community
license: MIT
metadata:
  hermes:
    tags: [Email, IMAP, SMTP, CLI, Communication]
    homepage: https://github.com/pimalaya/himalaya
prerequisites:
  commands: [himalaya]
---

# Himalaya Email CLI

Himalaya is a CLI email client that lets you manage emails from the terminal using IMAP, SMTP, Notmuch, or Sendmail backends.

## ⚠️ Execution Gate — READ BEFORE ANY GMAIL STATE CHANGE

Before **any** Gmail operation that changes state (single or batch delete, move, flag, expunge, archive):
1. **Re-read this gate plus the exact operation section** immediately before executing — do NOT rely on memory from earlier in the session.
2. **Block known-wrong paths instead of treating them as warnings.** For Konstantin's Gmail, do **not** use `himalaya message delete <id>` as the primary delete path: it may call a non-existent `Trash` folder.
3. **Always discover exact folders first** with `himalaya folder list` when using Trash/Spam/custom folders.
4. **Verify after mutation** by listing source and destination folders.

Hard rules for Konstantin's Gmail:
- Soft-delete / "удали" = move to exact localized trash:
  `himalaya message move "[Gmail]/Корзина" <id>`
- Permanent deletion requires explicit user intent like "удали навсегда". Then operate inside `[Gmail]/Корзина`: add `deleted` flag + expunge that exact folder.
- `move` syntax is TARGET first, then IDs: `himalaya message move "Folder" id1 id2`.
- After move/expunge, message IDs become stale in the old folder — re-list before further ID-based operations.

## References

- `references/configuration.md` (config file setup + IMAP/SMTP authentication)
- `references/message-composition.md` (MML syntax for composing emails)

## Prerequisites

1. Himalaya CLI installed (`himalaya --version` to verify)
2. A configuration file at `~/.config/himalaya/config.toml`
3. IMAP/SMTP credentials configured (password stored securely)

### Installation

```bash
# Pre-built binary (Linux/macOS — recommended)
curl -sSL https://raw.githubusercontent.com/pimalaya/himalaya/master/install.sh | PREFIX=~/.local sh

# macOS via Homebrew
brew install himalaya

# Or via cargo (any platform with Rust)
cargo install himalaya --locked
```

## Configuration Setup

Run the interactive wizard to set up an account:

```bash
himalaya account configure
```

Or create `~/.config/himalaya/config.toml` manually:

```toml
[accounts.personal]
email = "you@example.com"
display-name = "Your Name"
default = true

backend.type = "imap"
backend.host = "imap.example.com"
backend.port = 993
backend.encryption.type = "tls"
backend.login = "you@example.com"
backend.auth.type = "password"
backend.auth.cmd = "pass show email/imap"  # or use keyring

message.send.backend.type = "smtp"
message.send.backend.host = "smtp.example.com"
message.send.backend.port = 587
message.send.backend.encryption.type = "start-tls"
message.send.backend.login = "you@example.com"
message.send.backend.auth.type = "password"
message.send.backend.auth.cmd = "pass show email/smtp"
```

## Hermes Integration Notes

- **Reading, listing, searching, moving, deleting** all work directly through the terminal tool
- **Composing/replying/forwarding** — piped input (`cat << EOF | himalaya template send`) is recommended for reliability. Interactive `$EDITOR` mode works with `pty=true` + background + process tool, but requires knowing the editor and its commands
- Use `--output json` for structured output that's easier to parse programmatically
- The `himalaya account configure` wizard requires interactive input — use PTY mode: `terminal(command="himalaya account configure", pty=true)`

## Common Operations

### List Folders

```bash
himalaya folder list
```

### List Emails

List emails in INBOX (default):

```bash
himalaya envelope list
```

List emails in a specific folder:

```bash
himalaya envelope list --folder "Sent"
```

List with pagination:

```bash
himalaya envelope list --page 1 --page-size 20
```

### Search Emails

```bash
himalaya envelope list from john@example.com subject meeting
```

### Read an Email

Read email by ID (shows plain text):

```bash
himalaya message read 42
```

Export raw MIME:

```bash
himalaya message export 42 --full
```

### Reply to an Email

To reply non-interactively from Hermes, read the original message, compose a reply, and pipe it:

```bash
# Get the reply template, edit it, and send
himalaya template reply 42 | sed 's/^$/\nYour reply text here\n/' | himalaya template send
```

Or build the reply manually:

```bash
cat << 'EOF' | himalaya template send
From: you@example.com
To: sender@example.com
Subject: Re: Original Subject
In-Reply-To: <original-message-id>

Your reply here.
EOF
```

Reply-all (interactive — needs $EDITOR, use template approach above instead):

```bash
himalaya message reply 42 --all
```

### Forward an Email

```bash
# Get forward template and pipe with modifications
himalaya template forward 42 | sed 's/^To:.*/To: newrecipient@example.com/' | himalaya template send
```

### Write a New Email

**Non-interactive (use this from Hermes)** — pipe the message via stdin:

```bash
cat << 'EOF' | himalaya template send
From: you@example.com
To: recipient@example.com
Subject: Test Message

Hello from Himalaya!
EOF
```

Or with headers flag:

```bash
himalaya message write -H "To:recipient@example.com" -H "Subject:Test" "Message body here"
```

Note: `himalaya message write` without piped input opens `$EDITOR`. This works with `pty=true` + background mode, but piping is simpler and more reliable.

### Move/Copy Emails

Move to folder (note: TARGET folder comes FIRST, then IDs):

```bash
himalaya message move "Archive" 42
```

Batch move multiple IDs:

```bash
himalaya message move "Archive" 42 43 44
```

Copy to folder:

```bash
himalaya message copy "Important" 42
```

### Delete an Email

For Konstantin's Gmail, **do not use `himalaya message delete <id>` as the normal path**. It can fail because Himalaya tries a folder named `Trash`, while the actual Gmail trash folder is localized.

Soft-delete (normal meaning of "удали") — move to localized trash:

```bash
himalaya folder list  # verify exact folder name first if unsure
himalaya message move "[Gmail]/Корзина" 42
```

Permanent deletion — only when the user explicitly asks to delete forever:

```bash
# 1) Work in the exact Trash folder, not INBOX
himalaya envelope list --folder "[Gmail]/Корзина" --page-size 50 --output json

# 2) Use IDs from the Trash folder listing
himalaya flag add --folder "[Gmail]/Корзина" 42 deleted
himalaya folder expunge "[Gmail]/Корзина"
```

Generic/non-localized accounts may support `himalaya message delete 42`, but do not use it as the default for Konstantin's Gmail.

**Gmail pitfall:** Russian-localized accounts use `[Gmail]/Корзина` and `[Gmail]/Спам`. Always use the exact folder name from `himalaya folder list`.

### Manage Flags

Add flag:

```bash
himalaya flag add 42 --flag seen
```

Remove flag:

```bash
himalaya flag remove 42 --flag seen
```

## Multiple Accounts

List accounts:

```bash
himalaya account list
```

Use a specific account:

```bash
himalaya --account work envelope list
```

## Attachments

Save attachments from a message:

```bash
himalaya attachment download 42
```

Save to specific directory:

```bash
himalaya attachment download 42 --dir ~/Downloads
```

## Output Formats

Most commands support `--output` for structured output:

```bash
himalaya envelope list --output json
himalaya envelope list --output plain
```

## Debugging

Enable debug logging:

```bash
RUST_LOG=debug himalaya envelope list
```

Full trace with backtrace:

```bash
RUST_LOG=trace RUST_BACKTRACE=1 himalaya envelope list
```

## Tips

- Use `himalaya --help` or `himalaya <command> --help` for detailed usage.
- Message IDs are relative to the current folder; re-list after folder changes.
- For composing rich emails with attachments, use MML syntax (see `references/message-composition.md`).
- Store passwords securely using `pass`, system keyring, or a command that outputs the password.

## Gmail Daily Digest Cronjob

When building a cron-based morning digest from Gmail via himalaya, follow these formatting rules. These were established after glm-5.1:cloud produced unusable output — model choice matters.

### Model preference for digest tasks
- **gemma4:cloud** — produces clean, structured digests following format instructions
- **glm-5.1:cloud** — tends to dump structured data as dual-bullets («Показатель / Значение»), ignores formatting constraints; **avoid for digest tasks**

### Required digest format

```
📬 **Gmail-дайджест** — {дата}

**📊 Входящие:** {всего} | **Непрочитано:** {непрочитано} | **Новых за сутки:** {новых}

**🔔 Важное** *(письма, требующие внимания — ответы, задачи, проблемы)*
— {отправитель}: {тема} — {1-2 предложения сути}
...

**📄 Информационное** *(рассылки, чеки, уведомления без действия)*
— {отправитель}: {тема}
...

**👥 Топ отправителей:** {имя1} ({n}), {имя2} ({n}), ...
```

### Formatting pitfalls (from real failures)

| ❌ Don't | ✅ Do |
|---------|------|
| «Показатель: Всего во Входящих» + «Значение: 36» (two bullets) | **Входящие:** 36 (inline key:value) |
| Include user's own emails in top senders | Filter out user's own address from top senders |
| Dump everything in one flat list | Split into Важное / Информационное; hide Важное section when empty |
| Truncate subjects on quotes/special chars | Render full subject, escape if needed |
| Long prompt with no format guardrails | Specify exact output template + explicit «no dual-bullet, inline only» rule |

### Reference
- `references/digest-prompt.md` — full prompt template for the gmail-daily-digest cronjob

## Bulk Inbox Cleanup Workflow

Use when the user asks to "clean up email" or "sort inbox" — categorizing many emails and batch-processing them by category.

### Step 1: Dump inbox as JSON

```bash
himalaya envelope list --page-size 500 --output json 2>/dev/null > /tmp/inbox.json
```

### Step 2: Categorize with Python

Parse JSON, classify by sender/subject patterns:

```python
import json
from collections import Counter

with open("/tmp/inbox.json") as f:
    data = json.load(f)

def get_from(e):
    f = e.get("from", {})
    if isinstance(f, dict):
        return f.get("name") or f.get("addr", "?")
    return str(f).strip()

# Example: categorize into buckets
cheki, bbt, kommunalka = [], [], []
for e in data:
    eid, subj, frm = e["id"], (e.get("subject") or ""), get_from(e)
    if "Чек" in subj or "ОФД" in frm:
        cheki.append(eid)
    elif "BBT" in subj:
        bbt.append(eid)
    elif "Квитанция" in subj:
        kommunalka.append(eid)

# Show stats to user, get approval, then save ID lists
for name, ids in [("cheki", cheki), ("bbt", bbt), ("kommunalka", kommunalka)]:
    with open(f"/tmp/{name}_ids.txt", "w") as f:
        for i in ids:
            f.write(i + "\n")
```

### Step 3: Batch-process by category

Present the breakdown to the user and process with their approval. Use batches of 20-25 IDs to avoid IMAP timeout.

```bash
# Move to folder (TARGET first, then IDs)
while IFS= read -r id; do echo "$id"; done < /tmp/cheki_ids.txt | xargs -n 20 | while read batch; do
    himalaya message move "Чеки и квитанции" $batch
done
```

For Konstantin's Gmail, treat "delete" as soft-delete unless the user explicitly says permanent deletion:

```bash
# Soft-delete: move to localized Gmail Trash. Do NOT use `himalaya message delete`.
while IFS= read -r id; do echo "$id"; done < /tmp/delete_ids.txt | xargs -n 20 | while read batch; do
    himalaya message move "[Gmail]/Корзина" $batch
done
```

Permanent batch deletion is destructive and requires explicit confirmation plus a fresh re-list of `[Gmail]/Корзина`, because IDs change after moving.

### Pitfalls

- Known-wrong path for Konstantin's Gmail: do **not** use `himalaya message delete <id>` as the default delete action; use `himalaya message move "[Gmail]/Корзина" <id>` for soft-delete.
- `delete` is not permanent even when it works; permanent deletion requires explicit user intent and `flag add --folder "[Gmail]/Корзина" ... deleted` + `folder expunge "[Gmail]/Корзина"` using IDs from the Trash folder.
- `move` takes TARGET first, then IDs: `himalaya message move "Folder" id1 id2...`
- After moving or expunging, IDs may become stale — re-dump before further operations that reference old IDs.
- Gmail folder names depend on account locale: `[Gmail]/Корзина` (Russian), `[Gmail]/Trash` (English). Always verify with `himalaya folder list`.
- Batch size >25 may hit IMAP timeout; stick to 20-25 IDs per command.
