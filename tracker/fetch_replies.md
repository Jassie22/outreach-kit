# fetch_replies.md — refreshing tracker/replies.tsv from Gmail

`build_tracker.py` cannot call Gmail itself (no MCP access from a plain
script). Reply detection is therefore a **two-step, semi-manual** process:

1. A Claude session with the Gmail MCP tools searches for replies and writes
   `tracker/replies.tsv`.
2. `build_tracker.py` (or `update-tracker.sh`) reads that file on its next
   run and fills in `Replied?` / `Reply date` / `Reply snippet`.

This file is the prompt for step 1. Paste it to a Claude session that has
Gmail tools available (or ask Claude to "run fetch_replies.md"), whenever
The user wants the tracker's reply status refreshed.

## Prompt

> Read `<repo>/sent.log` — it's a tab-separated
> file, one line per email actually sent, columns: ISO timestamp, recipient
> email address, template name, subject line.
>
> For every unique recipient email address in that file, search Gmail
> (`mcp__claude_ai_Gmail__search_threads` or equivalent) for replies **from**
> that address, sent **after** the timestamp in sent.log for that address.
> A reasonable query per address is `from:<email> after:<sent date>`. Check
> both the inbox and any folder replies might have landed in (e.g. a label
> other than INBOX) — don't restrict to unread.
>
> For each address with at least one qualifying reply, take the **earliest**
> one and record:
>   - the sender's email address (lowercase, exactly as in sent.log)
>   - the ISO date (`YYYY-MM-DD`) of that reply
>   - a short snippet of the reply body — one line, plain text, no tabs or
>     newlines, roughly the first 150 characters, enough for the user to
>     recognise what it says without opening Gmail
>
> Write the results to `<repo>/tracker/replies.tsv`,
> tab-separated, one row per address that replied:
>
> ```
> email<TAB>ISO_date<TAB>snippet
> ```
>
> No header row. Overwrite the whole file (it's a derived cache, not
> something anyone hand-edits) — don't append to a stale copy. If an address
> has no reply, simply omit it; don't write empty rows.
>
> Do not include anything from the message body that looks like a credential,
> token, or other secret in the snippet — redact it as `[REDACTED]` if you
> see one.
>
> When done, tell the user how many replies were found and out of how many
> sent emails, then suggest she run `tracker/update-tracker.sh` to fold the
> results into the spreadsheet.

## Why this is manual, not automatic

- The build script (`build_tracker.py`) is plain Python with no network
  access by design — it's a report generator, not a thing with mailbox
  credentials.
- Gmail access in this setup lives in Claude's MCP tools, not in a
  standalone script you can cron.
- So: refreshing replies is "ask Claude to run this file" (a minute of
  chat), then "run the wrapper" (instant). The systemd timer handles the
  second half automatically, twice a week; it does **not** fetch replies —
  see `tracker/README.md`.

## Format reference — `tracker/replies.tsv`

```
sam@example-scaleup.com	2026-09-10	Thanks for reaching out - can you send over your CV again?
alex@example-agency.com	2026-09-12	Hi there, nothing on my desk right now but I'll keep you in mind.
```

- Tab-separated, 2 or 3 fields per line (`email`, `ISO_date`, optional `snippet`).
- Lines starting with `#` and blank lines are ignored.
- If an address appears more than once, the **earliest** date wins.
- This file is safe to delete — `build_tracker.py` treats it as fully
  optional and just leaves `Replied?` as `No` for everyone if it's missing.
