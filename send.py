#!/usr/bin/env python3
"""
outreach-sender — personal recruiter outreach with a CV attached.

Design constraint that drives everything here: the attachment is read from
disk, as bytes, by this script, at send time. It never passes through an LLM
context, a clipboard, or a chat window. An LLM may help write the template
prose; it never touches the CV file.

Standard library only. No pip install, no dependencies to audit.
"""

import argparse
import csv
import os
import random
import re
import smtplib
from email.utils import formataddr

FROM_NAME = ""
import sys
import time
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECIPIENTS = HERE / "recipients.csv"
TEMPLATE_DIR = HERE / "templates"
ATTACH_DIR = HERE / "attachments"
SENT_LOG = HERE / "sent.log"
ENV_FILE = HERE / ".env"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Deliberately loose but not permissive: catches the realistic typos in a
# hand-maintained CSV (missing @, trailing comma, stray space) without
# pretending to implement RFC 5322.
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

REQUIRED_COLUMNS = {"email", "greeting", "company", "opener", "lane", "status"}


# --------------------------------------------------------------------------
# env
# --------------------------------------------------------------------------

def load_env(path: Path) -> dict:
    """
    Tiny hand-rolled .env parser. Not python-dotenv, on purpose: one less
    dependency in a script that handles an app password.

    Supports: KEY=value, KEY="value", KEY='value', # comments, blank lines,
    and a leading `export `. Does not support multi-line values or variable
    interpolation, because a Gmail app password needs neither.
    """
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def resolve_credentials() -> tuple:
    """Real environment wins over .env, so a one-off override is possible."""
    file_env = load_env(ENV_FILE)
    address = os.environ.get("GMAIL_ADDRESS") or file_env.get("GMAIL_ADDRESS", "")
    # Display name shown in the recipient's inbox. Without it, mail clients fall
    # back to the raw address, which reads as automated.
    global FROM_NAME
    FROM_NAME = os.environ.get("FROM_NAME") or file_env.get("FROM_NAME", "")
    password = os.environ.get("GMAIL_APP_PASSWORD") or file_env.get("GMAIL_APP_PASSWORD", "")
    return address.strip(), password.strip()


# --------------------------------------------------------------------------
# template
# --------------------------------------------------------------------------

def load_template(name: str) -> tuple:
    """
    Returns (subject, body). The subject is the first line of the template
    file, prefixed `SUBJECT:`, and is stripped from the body.
    """
    path = TEMPLATE_DIR / f"{name}.txt"
    if not path.exists():
        available = sorted(p.stem for p in TEMPLATE_DIR.glob("*.txt"))
        die(
            f"template not found: {path}\n"
            f"available templates: {', '.join(available) if available else '(none)'}"
        )
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("SUBJECT:"):
        die(
            f"template {path} must begin with a line starting 'SUBJECT:'\n"
            f"first line was: {lines[0] if lines else '(empty file)'}"
        )
    subject = lines[0][len("SUBJECT:"):].strip()
    if not subject:
        die(f"template {path} has an empty SUBJECT: line")
    body = "\n".join(lines[1:]).lstrip("\n")
    if not body.strip():
        die(f"template {path} has a SUBJECT: but no body")
    return subject, body


def render(template_text: str, row: dict, rownum: int) -> str:
    """
    Fill placeholders, loudly.

    A half-filled template landing in a real recruiter's inbox is the worst
    outcome this tool can produce — worse than sending nothing. So: any
    placeholder the CSV does not supply, or supplies as whitespace, is a hard
    error naming the row, not a silent blank or a literal '{opener}'.
    """
    needed = set(PLACEHOLDER_RE.findall(template_text))
    problems = []
    for key in sorted(needed):
        if key not in row:
            problems.append(f"column '{key}' is missing from recipients.csv")
        elif not (row.get(key) or "").strip():
            problems.append(f"column '{key}' is empty")
    if problems:
        raise ValueError(
            f"row {rownum} ({row.get('email', '?')}): "
            + "; ".join(problems)
        )
    out = template_text
    for key in needed:
        out = out.replace("{" + key + "}", row[key].strip())
    leftover = PLACEHOLDER_RE.findall(out)
    if leftover:
        raise ValueError(
            f"row {rownum} ({row.get('email', '?')}): unrendered placeholders "
            f"remain after substitution: {', '.join(sorted(set(leftover)))}"
        )
    return out


# --------------------------------------------------------------------------
# recipients / dedupe
# --------------------------------------------------------------------------

def already_sent() -> set:
    """
    Every address that appears in sent.log, lowercased.

    Dedupe is a hard requirement: emailing the same recruiter the same cold
    pitch twice is the fastest way to be remembered for the wrong reason.
    The log is the source of truth, not the CSV, because the log is appended
    at the moment of the send and survives a CSV rewrite.
    """
    seen = set()
    if not SENT_LOG.exists():
        return seen
    for line in SENT_LOG.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("\t")]
        for part in parts:
            if EMAIL_RE.match(part):
                seen.add(part.lower())
                break
    return seen


def read_recipients() -> list:
    if not RECIPIENTS.exists():
        die(f"recipients file not found: {RECIPIENTS}")
    with RECIPIENTS.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            die(f"{RECIPIENTS} is empty — it needs a header row")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            die(
                f"{RECIPIENTS} is missing required column(s): "
                f"{', '.join(sorted(missing))}\n"
                f"expected header: email,greeting,company,role,opener,lane,status"
            )
        rows = []
        # rownum is the line in the file, header included, so the number
        # printed matches what a text editor shows.
        for i, row in enumerate(reader, start=2):
            row = {k: (v or "") for k, v in row.items()}
            # templates were written against {agency}; company is the column now
            row.setdefault("agency", row.get("company", ""))
            rows.append((i, row))
        return rows


# --------------------------------------------------------------------------
# attachments
# --------------------------------------------------------------------------

def wants_attachment(row: dict) -> bool:
    """
    Does this recipient get the CV attached? Yes, in every lane.

    Cold-email convention says link rather than attach outside the agency
    lane, on the grounds that an unsolicited attachment reads as "review me".
    Her call, 2026-09-16, overrides that for all lanes: send the CV. A founder
    who has to click through to GitHub to find out whether you are worth
    replying to mostly just does not click.

    An explicit `attach` column can still switch it off for a single row.
    """
    return (row.get("attach") or "").strip().lower() not in {"no", "n", "false", "0"}


def collect_attachments() -> list:
    """
    Every regular file in attachments/, read as bytes off the disk.

    This is the load-bearing function of the whole tool. The CV's contents go
    straight from the filesystem into the MIME part. Nothing summarises it,
    nothing re-types it, nothing uploads it anywhere first.
    """
    if not ATTACH_DIR.exists():
        return []
    files = sorted(
        p for p in ATTACH_DIR.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    return files


def build_message(sender: str, row: dict, subject: str, body: str,
                  attachments: list) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = formataddr((FROM_NAME, sender)) if FROM_NAME else sender
    msg["To"] = row["email"].strip()
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.attach(MIMEText(body, "plain", "utf-8"))
    for path in attachments:
        data = path.read_bytes()          # <- from disk, at send time
        part = MIMEApplication(data, Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        # MIMEApplication base64-encodes by default; being explicit about it
        # because binary-safe transport is the point of the attachment.
        msg.attach(part)
    return msg


# --------------------------------------------------------------------------
# logging
# --------------------------------------------------------------------------

def log_sent(email: str, template: str, subject: str) -> None:
    """
    Append and flush immediately. A crash halfway through a batch must never
    leave a message sent but unrecorded — that turns into a duplicate on the
    next run, which is the one failure mode this tool must not have.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{stamp}\t{email}\t{template}\t{subject}\n"
    with SENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def die(msg: str, code: int = 2) -> None:
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    sys.exit(code)


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f} KB"
    return f"{n/(1024*1024):.1f} MB"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="send.py",
        description="Send personalised recruiter outreach from your own Gmail, "
                    "with the CV attached straight from disk.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Dry run is the default. Nothing leaves the machine without --send.\n"
            "  python3 send.py --dry-run\n"
            "  python3 send.py --send --limit 10\n"
            "  python3 send.py --send --only first.last@example-agency.com\n"
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="render everything, print it, send nothing (DEFAULT)")
    mode.add_argument("--send", action="store_true",
                      help="actually send. Must be explicit.")
    p.add_argument("--limit", type=int, default=25,
                   help="cap this batch (default 25)")
    p.add_argument("--throttle", nargs=2, type=float, metavar=("MIN", "MAX"),
                   default=[240.0, 900.0],
                   help="random delay in seconds between sends (default 240 900, so a\n                         tranche spreads over hours rather than arriving as one burst)")
    p.add_argument("--template", default="a1",
                   help="template name in templates/ without .txt (default a1)")
    p.add_argument("--only", metavar="EMAIL",
                   help="send to just this one recipient, for testing")
    p.add_argument("--no-attach", action="store_true",
                   help="proceed with no attachment (required if attachments/ is empty)")
    p.add_argument("--i-know-what-im-doing", dest="override", action="store_true",
                   help="required alongside --send for batches over 50")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    sending = bool(args.send)          # --dry-run is the default; --send opts in
    tmin, tmax = args.throttle
    if tmin < 0 or tmax < tmin:
        die(f"--throttle needs 0 <= MIN <= MAX, got {tmin} {tmax}")

    subject, body_template = load_template(args.template)

    # --- attachments -----------------------------------------------------
    attachments = collect_attachments()
    if not attachments and not args.no_attach:
        die(
            f"attachments/ is empty ({ATTACH_DIR}).\n"
            "The entire point of this tool is to attach your CV, so it will not\n"
            "send a bare email by accident. Either drop the CV in that folder, or\n"
            "pass --no-attach if you genuinely want to send with no attachment."
        )
    if not attachments:
        print("WARNING: sending with NO attachment (--no-attach was passed).\n")

    # --- credentials -----------------------------------------------------
    sender, password = ("", "")
    if sending:
        if not ENV_FILE.exists():
            die(
                f".env not found at {ENV_FILE}\n"
                "Copy .env.example to .env and fill in GMAIL_ADDRESS and\n"
                "GMAIL_APP_PASSWORD. See the 'Setup' section of README.md for how\n"
                "to generate a Gmail app password (you need 2FA on the account)."
            )
        sender, password = resolve_credentials()
        if not sender or not password:
            blank = [n for n, v in (("GMAIL_ADDRESS", sender),
                                    ("GMAIL_APP_PASSWORD", password)) if not v]
            die(
                f"blank in .env: {', '.join(blank)}\n"
                "Both must be set. See the 'Setup' section of README.md — the app\n"
                "password is a 16-character string from Google, not your normal\n"
                "Gmail password."
            )
    else:
        sender = resolve_credentials()[0] or "(GMAIL_ADDRESS not set — dry run)"

    # --- recipients ------------------------------------------------------
    rows = read_recipients()
    sent_already = already_sent()

    queue = []
    skipped = []   # (email, reason)
    for rownum, row in rows:
        email = (row.get("email") or "").strip()
        label = email or f"row {rownum}"

        if args.only and email.lower() != args.only.strip().lower():
            continue
        if not email:
            skipped.append((label, "no email address in row"))
            continue
        if not EMAIL_RE.match(email):
            skipped.append((label, "malformed email address"))
            continue
        if email.lower() in sent_already:
            skipped.append((label, "already in sent.log"))
            continue
        # --only is an explicit, deliberate test send: it overrides the status
        # gate (that's the point of naming one address), but never the
        # sent.log dedupe above.
        if (row.get("status") or "").strip() and not args.only:
            skipped.append((label, f"status={row['status'].strip()}"))
            continue
        queue.append((rownum, row))

    if args.only and not queue and not skipped:
        die(f"--only {args.only}: no such address in {RECIPIENTS.name}")

    # --- render (fail before any send, not halfway through) --------------
    prepared = []
    render_errors = []
    # Each row may name its own template (identical bodies across a batch are a
    # spam signal), so validate against the template that row will ACTUALLY use,
    # not the CLI default. Otherwise a row fails on a placeholder its own
    # template never references.
    tpl_cache = {}
    for rownum, row in queue:
        name = (row.get("template") or "").strip() or args.template
        try:
            if name not in tpl_cache:
                tpl_cache[name] = load_template(name)
            row_subj, row_body = tpl_cache[name]
            prepared.append((rownum, row, render(row_body, row, rownum)))
        except ValueError as exc:
            render_errors.append(str(exc))
    # An incomplete row is "not ready yet", not a fatal error. Skip it, keep the
    # rest of the batch, and report it clearly so it can be finished and picked
    # up on the next run. It is never sent half-filled.
    for msg in render_errors:
        skipped.append((msg, "not ready, will retry next run"))
    if render_errors and not prepared:
        die(
            "every queued row is incomplete — nothing to send:\n  "
            + "\n  ".join(render_errors)
            + "\n\nFill in the missing columns in recipients.csv and re-run."
        )

    over_limit = len(prepared) - args.limit
    if over_limit > 0:
        prepared = prepared[:args.limit]
        skipped.append((f"{over_limit} recipient(s)", f"over --limit {args.limit}"))

    # --- safety gate -----------------------------------------------------
    if sending and len(prepared) > 500 and not args.override:
        die(
            f"{len(prepared)} recipients in one batch. Refusing without "
            "--i-know-what-im-doing.\n"
            "Why: this sends from your personal Gmail, the same address recruiters\n"
            "reply to. A burst that size looks like bulk mail to Gmail's outbound\n"
            "filters and to the receiving spam filters. Reputation damage lands on\n"
            "the address your entire job search runs through, and it is slow and\n"
            "painful to undo. 20-30 a day is the safe rate — use --limit."
        )

    mode_label = "SEND" if sending else "DRY RUN (nothing will be sent)"
    print("=" * 72)
    print(f"outreach-sender — {mode_label}")
    print(f"  from      : {sender}")
    print(f"  template  : {args.template}  |  subject: {subject}")
    if attachments:
        for a in attachments:
            print(f"  attachment: {a.name} ({fmt_size(a.stat().st_size)})")
    else:
        print("  attachment: (none)")
    print(f"  queued    : {len(prepared)}   skipped: {len(skipped)}")
    if sending:
        print(f"  throttle  : {tmin:.0f}-{tmax:.0f}s between sends")
    print("=" * 72)

    # --- do the work -----------------------------------------------------
    sent_count = 0
    failures = []
    server = None

    try:
        if sending and prepared:
            try:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender, password)
            except smtplib.SMTPAuthenticationError as exc:
                die(
                    f"Gmail rejected the login: {exc}\n"
                    "Usually this means GMAIL_APP_PASSWORD is a normal account\n"
                    "password rather than a 16-character app password, or 2FA is\n"
                    "not enabled on the account. See README.md 'Setup'."
                )
            except OSError as exc:
                die(f"could not connect to {SMTP_HOST}:{SMTP_PORT}: {exc}")

        for idx, (rownum, row, body) in enumerate(prepared):
            email = row["email"].strip()
            row_attach = attachments if wants_attachment(row) else []
            # Per-recipient subject AND body. Identical bodies across a batch are
            # the strongest spam signal there is, so each row may name its own
            # template file; the CLI --template is only the fallback.
            row_tpl = (row.get('template') or '').strip() or args.template
            row_subject_tpl = tpl_cache.get(row_tpl, (subject, body_template))[0]
            # The subject carries placeholders too ({agency}), and an unrendered
            # one ships "Engineering roles at {agency}?" to a real person. Put
            # it through the same renderer as the body.
            row_subject = (row.get('subject') or '').strip() or row_subject_tpl
            row_subject = render(row_subject, row, rownum)
            msg = build_message(sender, row, row_subject, body, row_attach)

            if not sending:
                print(f"\n--- [{idx+1}/{len(prepared)}] row {rownum} "
                      + "-" * 30)
                print(f"To     : {email}")
                print(f"Subject: {row_subject}")
                if row_attach:
                    print("Attach : " + ", ".join(
                        f"{a.name} ({fmt_size(a.stat().st_size)})" for a in row_attach))
                else:
                    print("Attach : (none — this lane links instead)")
                print()
                print(body)
                continue

            try:
                server.sendmail(sender, [email], msg.as_string())
            except smtplib.SMTPServerDisconnected as exc:
                # Gmail drops long-idle connections; one reconnect attempt is
                # worth it rather than failing the rest of the batch.
                failures.append((email, f"disconnected: {exc}; reconnecting"))
                try:
                    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60)
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(sender, password)
                    server.sendmail(sender, [email], msg.as_string())
                except Exception as exc2:  # noqa: BLE001 - one bad address must not abort
                    failures[-1] = (email, f"failed after reconnect: {exc2}")
                    continue
                failures.pop()
            except Exception as exc:  # noqa: BLE001 - never abort the batch
                failures.append((email, str(exc)))
                print(f"  FAILED  {email}: {exc}")
                continue

            # row_tpl, not args.template: the CLI value is only the fallback,
            # so logging it records the wrong template for every row that
            # names its own, and the tracker reads this file.
            log_sent(email, row_tpl, row_subject)
            sent_count += 1
            print(f"  sent    {email}  ({sent_count}/{len(prepared)})")

            if idx < len(prepared) - 1:
                # Random, human-ish spacing. A tight burst of identical
                # messages is exactly the signature outbound spam filters look
                # for, and the cost of tripping one is the personal address
                # the whole job search depends on.
                delay = random.uniform(tmin, tmax)
                print(f"  waiting {delay:.0f}s")
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\ninterrupted — sent.log is up to date for everything sent so far.")
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass

    # --- summary ---------------------------------------------------------
    print("\n" + "=" * 72)
    print("SUMMARY")
    if sending:
        print(f"  sent    : {sent_count}")
    else:
        print(f"  rendered: {len(prepared)} (dry run — nothing sent)")
    print(f"  skipped : {len(skipped)}")
    for label, reason in skipped:
        print(f"      - {label}: {reason}")
    print(f"  failed  : {len(failures)}")
    for email, err in failures:
        print(f"      - {email}: {err}")
    print("=" * 72)
    if not sending and prepared:
        print("\nThis was a dry run. Add --send to actually send.")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
