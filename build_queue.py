#!/usr/bin/env python3
"""
Turn the master contact list into a send queue.

Sourcing and sending want different shapes. The master list is a research
record with eleven columns of provenance; the sender wants one row per person
with a template, an opener and nothing else. This is the bridge.

What it does NOT do is write the openers. Those are per-recipient prose and
they are the whole point, so the queue lands with `opener` blank and the
sender refuses to send a row until it is filled. That refusal is deliberate:
an empty opener means the row is skipped and retried next run, never sent
half-finished.

Templates are rotated within each lane so no two consecutive sends share a
body. Anyone already in sent.log is left out.

    ./build_queue.py --dry-run
    ./build_queue.py --lane founder --limit 20
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Where the master contact list lives. Override with OUTREACH_DATA_DIR
# if you keep contacts outside the repo (a private notes folder, say).
DATA_DIR = Path(os.environ.get("OUTREACH_DATA_DIR",
                            Path(__file__).resolve().parent / "data"))
MASTER = DATA_DIR / "recruiter-outreach-list.csv"
SENT_LOG = HERE / "sent.log"
QUEUE = HERE / "recipients.csv"
TEMPLATES = HERE / "templates"

QUEUE_FIELDS = ["email", "first_name", "greeting", "company", "role", "template",
                "subject", "opener", "question", "lane", "status"]

# Which lane a contact belongs to, from their row type and role.
AGENCY_ROLES = {"agency consultant", "senior consultant", "principal consultant",
                "team lead", "agency director", "agency founder", "solo recruiter"}
FOUNDER_ROLES = {"founder / ceo", "co-founder (technical)", "cto",
                 "head of engineering", "vp engineering", "engineering lead"}
INHOUSE_ROLES = {"head of talent", "talent partner", "technical recruiter",
                 "hiring manager", "talent acquisition partner"}

# Sourcing records staleness in `verified` rather than deleting the row, so
# the research is kept. The queue must honour it.
STALE = re.compile(r"\b(has left|have left|no longer at|headline now reads|"
                   r"appears to have left|is stale|confirm he is still|"
                   r"confirm she is still|confirm they are still)\b", re.I)

PLACEHOLDER = re.compile(r"^(n/?a|none|no email published|not published|unknown|tbc|-+)$", re.I)


def usable_email(value: str) -> str:
    v = (value or "").strip()
    if not v or "@" not in v or PLACEHOLDER.match(v):
        return ""
    if "[" in v or "guess" in v.lower():
        return ""           # a pattern guess is a hypothesis, not an address
    return v.lower()


def lane_of(row: dict) -> str:
    role = (row.get("role") or "").strip().lower()
    rtype = (row.get("type") or "").strip().lower()
    if role in AGENCY_ROLES or "agency" in rtype:
        return "agency"
    if role in INHOUSE_ROLES:
        return "in-house"
    if role in FOUNDER_ROLES or "startup" in rtype or "scaleup" in rtype:
        return "founder"
    return ""


LANE_PREFIX = {"agency": "a", "founder": "f", "in-house": "h"}


def templates_for(lane: str) -> list[str]:
    prefix = LANE_PREFIX.get(lane, "")
    if not prefix:
        return []
    names = sorted(p.stem for p in TEMPLATES.glob(f"{prefix}[0-9]*.txt"))
    return names


# Sourcing sometimes files a placeholder where a person should be:
# "(general enquiries)", "(no named consultant published)". Those are not
# names, and "Hi (general," is the worst possible first line.
NOT_A_NAME = re.compile(r"[()\[\]/@0-9]|^(no|none|general|unknown|n/?a|team|info)$", re.I)


# Honorifics are not first names. "Hi Dr," is worse than "Hello,".
HONORIFIC = {"dr", "dr.", "prof", "prof.", "professor", "mr", "mrs", "ms",
             "miss", "mx", "sir", "dame", "rev"}


def first_name(full: str) -> str:
    parts = [p for p in re.split(r"[\s,]+", (full or "").strip()) if p]
    while parts and parts[0].lower() in HONORIFIC:
        parts = parts[1:]
    if not parts or NOT_A_NAME.search(parts[0]):
        return ""
    return parts[0]


def greeting_for(first: str) -> str:
    """A named person gets their name. An agency inbox gets a plain hello."""
    return f"Hi {first}" if first else "Hello"


def load_sent() -> set:
    if not SENT_LOG.exists():
        return set()
    out = set()
    for line in SENT_LOG.read_text(encoding="utf-8").splitlines():
        m = re.search(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+", line)
        if m:
            out.add(m.group(0).lower())
    return out


def load_existing_queue() -> dict:
    """Keep openers already written rather than blanking them on a rebuild."""
    if not QUEUE.exists():
        return {}
    with QUEUE.open(newline="", encoding="utf-8") as fh:
        return {(r.get("email") or "").strip().lower(): r
                for r in csv.DictReader(fh)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lane", choices=["agency", "founder", "in-house"],
                    help="only queue this lane")
    ap.add_argument("--limit", type=int, help="at most this many rows")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if not MASTER.exists():
        print(f"no master list at {MASTER}")
        return 1

    with MASTER.open(newline="", encoding="utf-8") as fh:
        master = list(csv.DictReader(fh))

    already_sent = load_sent()
    existing = load_existing_queue()

    rows, reasons = [], defaultdict(int)
    for r in master:
        email = usable_email(r.get("email", ""))
        if not email:
            reasons["no usable email"] += 1
            continue
        if email in already_sent:
            reasons["already emailed"] += 1
            continue
        if STALE.search(r.get("verified", "")):
            # sourcing flagged that this person has moved on. An email about a
            # company they left is worse than no email at all.
            reasons["contact has left that company"] += 1
            continue
        if (r.get("type") or "").strip().upper().startswith("WARM"):
            # an existing relationship; a cold template would be insulting
            reasons["warm contact, handle individually"] += 1
            continue
        lane = lane_of(r)
        if not lane:
            reasons["lane not determinable"] += 1
            continue
        if args.lane and lane != args.lane:
            continue
        rows.append((lane, r, email))

    # rotate templates within each lane so consecutive sends differ
    counters = defaultdict(int)
    out = []
    for lane, r, email in rows:
        pool = templates_for(lane)
        if not pool:
            reasons[f"no templates for {lane}"] += 1
            continue
        tpl = pool[counters[lane] % len(pool)]
        counters[lane] += 1
        prior = existing.get(email, {})
        first = first_name(r.get("name", ""))
        out.append({
            "email": email,
            "first_name": first,
            "greeting": prior.get("greeting") or greeting_for(first),
            "company": (r.get("company") or "").strip(),
            "role": (r.get("role") or "").strip(),
            "template": prior.get("template") or tpl,
            "subject": prior.get("subject", ""),
            "opener": prior.get("opener", ""),
            # founder templates close on a real question about their work,
            # written per recipient; other lanes close in the template
            "question": prior.get("question", ""),
            "lane": lane,
            "status": prior.get("status", ""),
        })

    if args.limit:
        out = out[:args.limit]

    ready = sum(1 for r in out if r["opener"].strip())
    print(f"master rows      : {len(master)}")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  skipped, {why}: {n}")
    print(f"queued           : {len(out)}")
    print(f"  openers written: {ready}")
    print(f"  openers needed : {len(out) - ready}")
    by_lane = defaultdict(int)
    for r in out:
        by_lane[r["lane"]] += 1
    print(f"  by lane        : {dict(by_lane)}")

    if args.dry_run:
        print("\ndry run, nothing written")
        return 0

    with QUEUE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"\nwrote {QUEUE}")
    if len(out) - ready:
        print(f"{len(out) - ready} row(s) need an opener before they can send")
    return 0


if __name__ == "__main__":
    sys.exit(main())
