#!/usr/bin/env python3
"""
build_tracker.py — build outreach-tracker.xlsx from the recruiter/outreach
data scattered across this repo and your contact list.

Inputs:
  - recruiter-outreach-list.csv  (master contact list, kept outside git)
  - sent.log                     (what send.py actually sent, this repo)
  - recipients.csv               (placeholder source for send.py, this repo)
  - templates/*.txt              (template bodies, to reconstruct what was sent)
  - tracker/replies.tsv          (optional, hand-refreshed — see fetch_replies.md)

Output:
  - tracker/outreach-tracker.xlsx, one sheet "Outreach" + one sheet "Summary"

Design notes (read before editing):

  Contacts are not all reachable by email. ~1/3 of the master list (startups,
  in-house talent, VC/portfolio channels) has no published email address at
  all — LinkedIn, a careers page, or a named contact is the only route. Every
  one of the 168 master rows must still appear as a row in the sheet, so the
  identity key for a row is NOT always the email address:

      stable_id = "email:<lower email>"                 when an email exists
                = "na:<lower name>::<lower agency>"      otherwise

  This id is what "preserve across rebuilds" keys off, for both `Notes` and
  the other hand-maintained columns (`Contacted via LinkedIn?`, and — for any
  row not sent by this repo's mailer — `Channel used` / `Date sent` too).

  Only two things are ever authoritative from automation and always overwrite
  whatever a human typed: `Emailed?` / `Date sent` / `Channel used=Email` /
  `Subject` / `Body sent`, all sourced from sent.log, and `Replied?` / `Reply
  date` / `Reply snippet`, sourced from replies.tsv (itself hand-refreshed via
  fetch_replies.md — see that file for why this can't be automatic).
  Everything else a person can type into the sheet — `Notes`, `Contacted via
  LinkedIn?`, and `Channel used` / `Date sent` for a row never sent by
  send.py — is preserved verbatim across rebuilds. Read it back from the
  existing xlsx before writing a new one; never invent a value for it.
"""

import argparse
import csv
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    print(
        "openpyxl is required. Install with:\n"
        "  pip install --user openpyxl\n"
        "or, on a PEP 668 / externally-managed system:\n"
        "  pip install --user --break-system-packages openpyxl",
        file=sys.stderr,
    )
    sys.exit(1)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
MASTER_CSV = Path(os.environ.get("OUTREACH_DATA_DIR",
                                 Path(__file__).resolve().parent.parent / "data")
                  ) / "recruiter-outreach-list.csv"
SENT_LOG = REPO_ROOT / "sent.log"
RECIPIENTS_CSV = REPO_ROOT / "recipients.csv"
TEMPLATE_DIR = REPO_ROOT / "templates"
REPLIES_TSV = HERE / "replies.tsv"
OUTPUT_XLSX = HERE / "outreach-tracker.xlsx"

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

HEADERS = [
    "Name", "Email", "Company", "Role", "Type",
    "LinkedIn", "Phone", "Contact form / website URL",
    "Channel used", "Contacted via LinkedIn?",
    "Emailed?", "Date sent", "Subject", "Body sent",
    "Replied?", "Reply date", "Reply snippet",
    "Days since sent", "Next action", "Notes",
]

COL_WIDTHS = {
    "Name": 20, "Email": 30, "Company": 22, "Role": 20, "Type": 20,
    "LinkedIn": 34, "Phone": 14, "Contact form / website URL": 30,
    "Channel used": 13, "Contacted via LinkedIn?": 15,
    "Emailed?": 10, "Date sent": 12, "Subject": 32, "Body sent": 60,
    "Replied?": 10, "Reply date": 12, "Reply snippet": 45,
    "Days since sent": 10, "Next action": 22, "Notes": 40,
}
WRAP_COLS = {"Body sent", "Reply snippet", "Notes"}

NEXT_ACTION_PRIORITY = {
    "Replied - action needed": 0,
    "Chase": 1,
    "Waiting": 2,
    "": 3,
    "Done": 4,
}

FILL_CHASE = PatternFill(start_color="FFE8B3", end_color="FFE8B3", fill_type="solid")
FILL_REPLIED = PatternFill(start_color="C6E7C6", end_color="C6E7C6", fill_type="solid")


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def norm_email(raw: str) -> str:
    raw = (raw or "").strip().lower()
    return raw if "@" in raw else ""


def stable_id(email: str, name: str, agency: str) -> str:
    e = norm_email(email)
    if e:
        return f"email:{e}"
    return f"na:{(name or '').strip().lower()}::{(agency or '').strip().lower()}"


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------

def load_master(path: Path) -> list:
    if not path.exists():
        die(f"master contact list not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        name = (r.get("name") or "").strip()
        agency = (r.get("company") or r.get("agency") or "").strip()
        email = norm_email(r.get("email"))
        out.append({
            "stable_id": stable_id(email, name, agency),
            "name": name,
            "email": email,
            "agency": agency,
            "role": (r.get("role") or "").strip(),
            "type": (r.get("type") or "").strip(),
            "linkedin": (r.get("linkedin") or "").strip(),
            "phone": "",  # no phone column exists in the source CSV today
            "website": (r.get("website") or "").strip(),
            "master_notes": (r.get("notes") or "").strip(),
        })
    return out


def load_sent_log(path: Path) -> dict:
    """email(lower) -> latest {date, template, subject}."""
    out = {}
    if not path.exists():
        return out
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            print(f"warning: sent.log line {lineno} has {len(parts)} fields, skipping", file=sys.stderr)
            continue
        ts, email, template, subject = parts
        email = norm_email(email)
        if not email:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            print(f"warning: sent.log line {lineno} has unparseable timestamp {ts!r}, skipping", file=sys.stderr)
            continue
        prev = out.get(email)
        if prev is None or dt > prev["dt"]:
            out[email] = {"dt": dt, "date": dt.date(), "template": template, "subject": subject}
    return out


def load_recipients(path: Path) -> dict:
    """email(lower) -> raw csv row, used to render template placeholders."""
    out = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            email = norm_email(row.get("email"))
            if email:
                out[email] = row
    return out


def load_replies(path: Path) -> dict:
    """email(lower) -> earliest {date, snippet}. Optional file; see fetch_replies.md."""
    out = {}
    if not path.exists():
        return out
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            print(f"warning: replies.tsv line {lineno} malformed, skipping", file=sys.stderr)
            continue
        email = norm_email(parts[0])
        date_str = parts[1].strip()
        snippet = parts[2].strip() if len(parts) > 2 else ""
        if not email or not date_str:
            continue
        try:
            d = datetime.fromisoformat(date_str).date()
        except ValueError:
            print(f"warning: replies.tsv line {lineno} has unparseable date {date_str!r}, skipping", file=sys.stderr)
            continue
        prev = out.get(email)
        if prev is None or d < prev["date"]:
            out[email] = {"date": d, "snippet": snippet}
    return out


def load_templates(dirpath: Path) -> dict:
    """template name -> (subject, body_with_placeholders)."""
    out = {}
    if not dirpath.exists():
        return out
    for p in sorted(dirpath.glob("*.txt")):
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("SUBJECT:"):
            continue
        subject = lines[0][len("SUBJECT:"):].strip()
        body = "\n".join(lines[1:]).lstrip("\n")
        out[p.stem] = (subject, body)
    return out


PRESERVED_COLS = ["Notes", "Contacted via LinkedIn?", "Channel used", "Date sent"]


def load_preserved(path: Path) -> dict:
    """stable_id -> {col_name: value} for every hand-maintained column, read
    back from a pre-existing workbook so a rebuild never clobbers manual edits."""
    out = {}
    if not path.exists():
        return out
    wb = load_workbook(path, data_only=True)
    if "Outreach" not in wb.sheetnames:
        return out
    ws = wb["Outreach"]
    header_row = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        idx_email = header_row.index("Email")
        idx_name = header_row.index("Name")
        idx_agency = header_row.index("Company")
    except ValueError:
        return out
    col_idx = {c: header_row.index(c) for c in PRESERVED_COLS if c in header_row}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[idx_email] is None and row[idx_name] is None:
            continue
        sid = stable_id(row[idx_email] or "", row[idx_name] or "", row[idx_agency] or "")
        entry = {}
        for col, idx in col_idx.items():
            val = row[idx]
            if val not in (None, ""):
                entry[col] = val
        if entry:
            out[sid] = entry
    return out


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def render_body(body_template: str, recipient_row: dict) -> tuple:
    """Returns (rendered_or_raw_text, flagged: bool)."""
    if recipient_row is None:
        return body_template, True
    needed = set(PLACEHOLDER_RE.findall(body_template))
    unresolved = []
    out = body_template
    for key in needed:
        val = (recipient_row.get(key) or "").strip()
        if not val:
            unresolved.append(key)
            continue
        out = out.replace("{" + key + "}", val)
    if unresolved:
        flag = f"[UNRESOLVED PLACEHOLDER(S): {', '.join(sorted(unresolved))}]\n\n"
        return flag + out, True
    return out, False


# --------------------------------------------------------------------------
# date math
# --------------------------------------------------------------------------

def business_days_elapsed(start: date, end: date) -> int:
    """Weekday count strictly between start and end (exclusive of start,
    inclusive of end), i.e. how many working days have passed since `start`.
    Does not account for public holidays."""
    if end <= start:
        return 0
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            n += 1
        d += timedelta(days=1)
    return n


# --------------------------------------------------------------------------
# row building
# --------------------------------------------------------------------------

def die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def build_rows(today: date) -> list:
    master = load_master(MASTER_CSV)
    sent = load_sent_log(SENT_LOG)
    recipients = load_recipients(RECIPIENTS_CSV)
    replies = load_replies(REPLIES_TSV)
    templates = load_templates(TEMPLATE_DIR)
    preserved = load_preserved(OUTPUT_XLSX)

    seen_ids = {m["stable_id"] for m in master}
    # sent.log / recipients.csv may reference an address the master list
    # doesn't have (e.g. a test send to your own inbox) — still needs a row.
    for email, entry in sent.items():
        sid = stable_id(email, "", "")
        if sid in seen_ids:
            continue
        rec_row = recipients.get(email, {})
        master.append({
            "stable_id": sid,
            "name": rec_row.get("first_name", "") or "",
            "email": email,
            "agency": rec_row.get("company") or rec_row.get("agency") or "",
            "role": (rec_row.get("role") or "").strip(),
            "type": (rec_row.get("lane") or "").strip(),
            "linkedin": "",
            "phone": "",
            "website": "",
            "master_notes": "",
        })
        seen_ids.add(sid)

    render_flags = []
    out_rows = []
    for m in master:
        sid = m["stable_id"]
        email = m["email"]
        pres = preserved.get(sid, {})

        log_entry = sent.get(email) if email else None
        emailed = log_entry is not None

        # Notes: preserved value wins always; otherwise seed once from the
        # master CSV's own notes column.
        notes = pres.get("Notes")
        if notes is None:
            notes = m["master_notes"]

        linkedin_contacted = pres.get("Contacted via LinkedIn?", "") or ""

        if emailed:
            channel_used = "Email"
            date_sent = log_entry["date"]
        else:
            channel_used = pres.get("Channel used", "") or ""
            if not channel_used and linkedin_contacted.strip().lower() == "yes":
                channel_used = "LinkedIn"
            ds_raw = pres.get("Date sent")
            if isinstance(ds_raw, datetime):
                date_sent = ds_raw.date()
            elif isinstance(ds_raw, date):
                date_sent = ds_raw
            elif isinstance(ds_raw, str) and ds_raw.strip():
                try:
                    date_sent = datetime.fromisoformat(ds_raw.strip()).date()
                except ValueError:
                    date_sent = None
            else:
                date_sent = None

        subject = ""
        body_sent = ""
        if emailed:
            subject = log_entry["subject"]
            template_pair = templates.get(log_entry["template"])
            if template_pair is None:
                body_sent = "(template file not found on disk — cannot reconstruct body)"
                render_flags.append((email, log_entry["template"], "template missing"))
            else:
                _, body_template = template_pair
                recipient_row = recipients.get(email)
                body_sent, flagged = render_body(body_template, recipient_row)
                if flagged:
                    render_flags.append((email, log_entry["template"], "unresolved placeholder(s) or no matching recipients.csv row"))

        reply = replies.get(email) if email else None
        contacted_at_all = bool(channel_used)
        if not contacted_at_all:
            replied = "—"
        elif reply is not None:
            replied = "Yes"
        else:
            replied = "No"

        days_since_sent = ""
        biz_days = None
        if date_sent is not None:
            days_since_sent = (today - date_sent).days
            biz_days = business_days_elapsed(date_sent, today)

        notes_say_closed = "closed" in (str(notes) or "").lower()

        if notes_say_closed:
            # A human said "closed" in Notes — that's final regardless of
            # whether our own channel tracking ever saw this contact.
            next_action = "Done"
        elif not contacted_at_all:
            next_action = ""
        elif replied == "Yes":
            next_action = "Replied - action needed"
        elif biz_days is not None and biz_days >= 5:
            next_action = "Chase"
        elif biz_days is not None:
            next_action = "Waiting"
        else:
            # contacted (e.g. LinkedIn) but no date on record — flag for
            # manual follow-up rather than silently doing nothing.
            next_action = "Chase"

        out_rows.append({
            "Name": m["name"],
            "Email": email,
            "Company": m["agency"],
            "Role": m["role"],
            "Type": m["type"],
            "LinkedIn": m["linkedin"],
            "Phone": m["phone"],
            "Contact form / website URL": m["website"],
            "Channel used": channel_used,
            "Contacted via LinkedIn?": linkedin_contacted,
            "Emailed?": "Yes" if emailed else "No",
            "Date sent": date_sent,
            "Subject": subject,
            "Body sent": body_sent,
            "Replied?": replied,
            "Reply date": reply["date"] if reply else None,
            "Reply snippet": reply["snippet"] if reply else "",
            "Days since sent": days_since_sent,
            "Next action": next_action,
            "Notes": notes,
        })

    out_rows.sort(key=lambda r: (
        NEXT_ACTION_PRIORITY.get(r["Next action"], 3),
        r["Type"],
        r["Name"],
    ))
    return out_rows, render_flags


# --------------------------------------------------------------------------
# xlsx writing
# --------------------------------------------------------------------------

def write_xlsx(rows: list, path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Outreach"

    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    for r in rows:
        ws.append([r[h] for h in HEADERS])

    last_row = ws.max_row
    last_col_letter = get_column_letter(len(HEADERS))
    ws.auto_filter.ref = f"A1:{last_col_letter}{last_row}"

    for i, h in enumerate(HEADERS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = COL_WIDTHS.get(h, 16)

    wrap_align = Alignment(wrap_text=True, vertical="top")
    top_align = Alignment(vertical="top")
    wrap_idx = {HEADERS.index(c) + 1 for c in WRAP_COLS}
    for row in ws.iter_rows(min_row=2, max_row=last_row):
        for cell in row:
            cell.alignment = wrap_align if cell.column in wrap_idx else top_align

    next_action_col = HEADERS.index("Next action") + 1
    replied_col = HEADERS.index("Replied?") + 1
    for row in ws.iter_rows(min_row=2, max_row=last_row):
        na = row[next_action_col - 1].value
        replied = row[replied_col - 1].value
        fill = None
        if na == "Chase":
            fill = FILL_CHASE
        elif replied == "Yes":
            fill = FILL_REPLIED
        if fill:
            for cell in row:
                cell.fill = fill

    for row in ws.iter_rows(min_row=2, max_row=last_row):
        for h in ("Date sent", "Reply date"):
            cell = row[HEADERS.index(h)]
            if isinstance(cell.value, date):
                cell.number_format = "yyyy-mm-dd"

    build_summary_sheet(wb, rows)
    wb.save(path)


def build_summary_sheet(wb, rows: list):
    ws = wb.create_sheet("Summary")
    ws.append(["Type", "Contacts", "Emailed", "Replied", "Needs chase", "Done"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    by_type = {}
    for r in rows:
        t = r["Type"] or "(untyped)"
        agg = by_type.setdefault(t, {"total": 0, "emailed": 0, "replied": 0, "chase": 0, "done": 0})
        agg["total"] += 1
        if r["Emailed?"] == "Yes" or r["Channel used"]:
            agg["emailed"] += 1 if r["Emailed?"] == "Yes" else 0
        if r["Replied?"] == "Yes":
            agg["replied"] += 1
        if r["Next action"] == "Chase":
            agg["chase"] += 1
        if r["Next action"] == "Done":
            agg["done"] += 1

    for t in sorted(by_type):
        a = by_type[t]
        ws.append([t, a["total"], a["emailed"], a["replied"], a["chase"], a["done"]])

    total_row = ["TOTAL", len(rows),
                 sum(1 for r in rows if r["Emailed?"] == "Yes"),
                 sum(1 for r in rows if r["Replied?"] == "Yes"),
                 sum(1 for r in rows if r["Next action"] == "Chase"),
                 sum(1 for r in rows if r["Next action"] == "Done")]
    ws.append([])
    ws.append(total_row)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)

    widths = [26, 10, 10, 10, 12, 8]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Build outreach-tracker.xlsx")
    ap.add_argument("--dry-run", action="store_true", help="report what would be written, change nothing")
    args = ap.parse_args(argv)

    today = date.today()
    rows, render_flags = build_rows(today)

    total = len(rows)
    emailed = sum(1 for r in rows if r["Emailed?"] == "Yes")
    contacted = sum(1 for r in rows if r["Channel used"])
    replied = sum(1 for r in rows if r["Replied?"] == "Yes")
    chase = sum(1 for r in rows if r["Next action"] == "Chase")

    print(f"contacts total       : {total}")
    print(f"emailed              : {emailed}")
    print(f"contacted (any chan.): {contacted}")
    print(f"replied              : {replied}")
    print(f"needing chase        : {chase}")
    if render_flags:
        print(f"\n{len(render_flags)} body-render flag(s):")
        for email, template, reason in render_flags:
            print(f"  - {email} ({template}): {reason}")

    if args.dry_run:
        print(f"\n[dry-run] would write {OUTPUT_XLSX} — nothing written.")
        return 0

    write_xlsx(rows, OUTPUT_XLSX)
    print(f"\nwrote {OUTPUT_XLSX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
