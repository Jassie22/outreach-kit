#!/usr/bin/env python3
"""
The LinkedIn worklist: people worth connecting with by hand.

Email is the preferred route because it can be automated. LinkedIn is the
fallback, and it is a manual job, so this is a worklist rather than a queue.
It carries the note to open a connection request on, and nothing that would
need re-looking-up.

Included: anyone with a verified profile URL. Ranked by how useful they are
to reach, since the connection limit is the scarce resource, not the contacts.

Excluded: people sourcing flagged as having left the company on the row (a
connection note about the wrong employer is worse than no note), channels,
and warm contacts who should be messaged directly rather than connected with.

    ./build_linkedin_list.py
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

# Where the master contact list lives. Override with OUTREACH_DATA_DIR
# if you keep contacts outside the repo (a private notes folder, say).
VAULT = Path(os.environ.get("OUTREACH_DATA_DIR",
                            Path(__file__).resolve().parent / "data"))
MASTER = VAULT / "recruiter-outreach-list.csv"
OUT = VAULT / "linkedin-outreach.csv"

PROFILE = re.compile(r"(https?://)?([\w.]*\.)?linkedin\.com/in/[\w\-%À-ÿ]+", re.I)
STALE = re.compile(r"\b(has left|have left|no longer at|headline now reads|"
                   r"appears to have left|is stale|confirm (he|she|they) (is|are) still)\b", re.I)

# Reach the people who can actually say yes first.
PRIORITY = {
    "Founder / CEO": 0, "Co-founder (technical)": 0, "CTO": 0,
    "Head of Engineering": 1, "VP Engineering": 1, "Engineering Lead": 1,
    "Head of Talent": 2, "Talent Partner": 2, "Technical Recruiter": 2,
    "Agency Founder": 3, "Agency Director": 3, "Solo Recruiter": 3,
    "Principal Consultant": 4, "Senior Consultant": 4, "Agency Consultant": 4,
}


def clean(url: str) -> str:
    m = PROFILE.search(url or "")
    if not m:
        return ""
    u = m.group(0)
    return u if u.startswith("http") else f"https://{u}"


def main() -> int:
    with MASTER.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    out, skipped = [], {"no profile": 0, "stale": 0, "channel or warm": 0}
    for r in rows:
        rtype = (r.get("type") or "").strip().upper()
        if rtype == "CHANNEL" or rtype.startswith("WARM"):
            skipped["channel or warm"] += 1
            continue
        url = clean(r.get("linkedin", ""))
        if not url:
            skipped["no profile"] += 1
            continue
        if STALE.search(r.get("verified", "")):
            skipped["stale"] += 1
            continue
        has_email = "@" in (r.get("email") or "") and "no email" not in (r.get("email") or "").lower()
        out.append({
            "priority": PRIORITY.get((r.get("role") or "").strip(), 5),
            "name": r.get("name", ""),
            "role": r.get("role", ""),
            "company": r.get("company", ""),
            "linkedin": url,
            "also_emailing": "yes" if has_email else "no",
            "what_they_do": (r.get("specialism") or "").strip(),
            "hook": (r.get("notes") or "").strip(),
            "connected": "",
            "note_sent": "",
            "replied": "",
        })

    out.sort(key=lambda r: (r["also_emailing"] == "yes", r["priority"], r["company"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    only_li = sum(1 for r in out if r["also_emailing"] == "no")
    print(f"{len(out)} profiles written to {OUT}")
    print(f"  {only_li} are LinkedIn-only, i.e. the only route to that company")
    print(f"  {len(out) - only_li} also have an email queued")
    for why, n in skipped.items():
        print(f"  skipped, {why}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
