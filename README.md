# outreach-kit

A CLI for personalised job-search outreach, built to run alongside Claude Code.

The model writes one bespoke line per recipient; this sends the result. The
split matters: **the CV is read from disk at send time and never passes through
the model's context.** A base64-encoded PDF is roughly 15k tokens, so attaching
it through an LLM once per recipient would cost more than the rest of the run
put together, and buy nothing.

Stdlib only. No dependencies beyond Python 3.9+, except `openpyxl` if you want
the spreadsheet tracker.

## What this is not

Not a mass mailer. Every message has a hand-written first line, one contact per
company, and a daily cap. If you point it at a bought list it will work and it
will also get your domain blocked, which is the outcome you deserve.

## Setup

### 1. Gmail app password

Ordinary account passwords do not work for SMTP. You need a 16-character app
password, which requires 2-Step Verification on the account first.

1. Turn on 2-Step Verification: <https://myaccount.google.com/signinoptions/two-step-verification>
2. Create an app password: <https://myaccount.google.com/apppasswords>
3. Name it anything ("outreach"). Google shows a 16-character string once.
4. Copy it into `.env`. Spaces are fine, they are stripped.

If the password field is missing, 2SV is not on yet. If SMTP rejects the login,
it is almost always the account password rather than the app password.

```
cp .env.example .env
chmod 600 .env
```

Other providers work if they speak SMTP + STARTTLS: set `SMTP_HOST` and
`SMTP_PORT`. Outlook and Zoho both do.

### 2. Your CV

Drop it in `attachments/`. Any file there is attached to every message:

```
cp ~/path/to/your-cv.pdf attachments/
```

The folder is gitignored, so your CV never ends up in a commit. The sender
refuses to run if it is empty rather than quietly sending a CV-less email; pass
`--no-attach` if that is genuinely what you want.

The file is read from disk at send time, which is the whole reason the attach
step lives here and not in the model.

### 2b. Edit the templates before you send anything

`templates/` ships examples, not a voice. Every one contains `REPLACE THIS
PARAGRAPH` where your evidence block goes, and signs off `Your name`.

`send.py --send` refuses the batch if any of that survives into a rendered
message, so a first run cannot email a recruiter a paragraph of instructions.
Fix the templates and set `FROM_NAME` in `.env`, then it will let you through.
`--dry-run` always works and is how you check.

### 3. Your contact list

`data/recruiter-outreach-list.example.csv` shows the columns. The important ones:

| Column | Why it matters |
|---|---|
| `company` | Dedupe key. One contact per company, enforced by `merge_contacts.py` |
| `role` | Decides the lane: founder, in-house talent, or agency consultant |
| `email` | `no email published` is a valid, useful answer |
| `notes` | **The hook.** One verifiable fact plus a URL. This is what the opener gets built from, and a row without it is close to useless |
| `verified` | Where you saw it. Write `has left` here if they have moved on and the queue will skip them |

Real contact data is gitignored. Only the `.example.csv` files are tracked, and
you should keep it that way: publishing a few hundred people's addresses next to
the personalised line you wrote about each of them is a GDPR problem as well as
an embarrassing one.

Set `OUTREACH_DATA_DIR` if you keep contacts outside the repo.

## The loop

```
./merge_contacts.py --dry-run     # fold new sourcing batches in, deduped
./merge_contacts.py

./build_queue.py                  # master list -> send queue, openers left blank
                                  # (then write the openers — see below)

./check_variation.py              # fail if two same-lane templates drifted close

./send.py --dry-run --limit 5     # read what would actually go out
./send.py --send --limit 30       # send, throttled
```

`build_queue.py` deliberately leaves `opener` empty. The sender refuses to send
a row with an unfilled placeholder, so an unfinished row is skipped and retried
next run rather than going out half-written. That refusal is the point.

### Writing the openers with Claude Code

1. Put `skills/cold-outreach/` and `skills/humaniser/` in `~/.claude/skills/`.
2. Fill in every `FILL IN` in `cold-outreach/SKILL.md`. It ships with the
   structural rules and none of the tone, because a skill carrying someone
   else's voice writes someone else's emails.
3. Install `hooks/outreach-skill-reminder.sh` (instructions in the file). It
   injects a reminder when a prompt looks like outreach. A hook cannot force a
   skill to load, but the failure mode it prevents is real: drafting from memory
   of a skill read earlier in the session, silently dropping your newest rules.
4. Ask Claude to fill the `opener` column for a batch, then read them.

Two things worth knowing, both learned the hard way:

- **Re-invoke the skill after editing it.** The copy loaded at the start of a
  session is a snapshot. Edit the file and the running session does not see it.
- **Check the openers against the templates.** An opener that repeats a phrase
  the template already contains reads as careless, and it is invisible unless
  you diff them. `check_variation.py` catches template-to-template drift; the
  opener-to-body check is worth adding to your review.

### Sourcing contacts with subagents

Contact discovery parallelises well and is tedious by hand. Give each agent one
segment, a strict output schema, and an exclusion list of everyone you already
have. Segments that work: agencies by region, agencies by specialism, startups
by stage, scale-ups, companies currently advertising your exact role.

Insist on: one contact per company; a verifiable source URL per row; `no email
published` as an acceptable answer; and never inventing a person or an address.
Agents will pad a file to hit a target unless you tell them not to.

On technique, ranked by what actually yields:

1. **Sitemaps.** Agency team pages are usually JS-rendered, so fetching `/team`
   gets an empty shell. `/sitemap.xml` (also `/sitemap_index.xml`,
   `/wp-sitemap.xml`, and any `Sitemap:` line in `/robots.txt`) exposes one
   profile URL per consultant, and those pages carry `mailto:` links.
2. **Privacy policies and terms pages.** The most overlooked source by a
   distance. Companies are legally obliged to publish a monitored contact
   address, and it is frequently a real inbox.
3. **Live job ads.** Agency postings often carry the posting consultant's own
   address, and the ad tells you their desk and salary band at the same time.
4. **Company inboxes, ranked.** `careers@` beats `hello@` beats `info@`. Collect
   `privacy@` and `support@` last and do not send a job enquiry there.

One trap: only keep an address whose local part contains the person's own name.
A page-wide grep for emails picks up the office switchboard address and
attributes it to whoever happens to be on that page.

## Guards

Everything here exists because the failure it prevents is worse than no email.

- **`sent.log`** is append-only and fsynced per message. Nobody gets two.
- **Unfilled placeholder** — row skipped, batch continues, reported.
- **Missing CV** — refuses to run rather than sending without it.
- **Batch over 500** — requires `--override`.
- **`--dry-run`** prints the exact bytes, attachment included.
- **Throttle** — 4 to 15 minutes randomised, so 30 emails spread across an
  afternoon rather than arriving as one recognisable burst.
- **Contact has moved on** — write `has left` in `verified` and the queue drops
  them. An email about a company someone left is worse than no email.
- **`do-not-contact.txt`** — matched on normalised company name and on email
  domain, so your current employer cannot slip in via a sourcing batch.

## Scheduling

`systemd --user` timer, weekday mornings:

```ini
# ~/.config/systemd/user/outreach-send.timer
[Timer]
OnCalendar=Tue,Wed,Thu,Fri *-*-* 09:15:00
Persistent=true
RandomizedDelaySec=600
```

Mid-morning beats 08:00, because recipients are through the overnight pile by
then and the batch still lands inside the working day. Weekends are skipped: a
cold CV arriving on a Sunday reads as automated, because it is.

## Licence

MIT. The templates are examples, not a voice. Replace them.
