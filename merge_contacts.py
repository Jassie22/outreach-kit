#!/usr/bin/env python3
"""
Merge sourcing batches into the master outreach list, deduped.

Several agents source contacts in parallel and they WILL overlap: the same
agency found from a job ad and from a directory, the same startup listed by
two accelerators, the same person spelled two ways. This script is the single
place that decides who survives.

Three dedupe keys, checked in order of how much we trust them:

  1. email          exact, lowercased. Same address is the same person, full stop.
  2. company        one contact per company is the standing rule, so a second
                    person at a company we already have is parked, not merged.
  3. person+company same human, spelled differently.

Company identity is resolved by DOMAIN first (email domain, else website
domain), because "Acme Talent" / "acmetalent" / "Acme Talent Ltd" are one
company and one domain. Name matching is the fallback for rows with no domain.

Free email providers are never treated as a company domain: a solo recruiter on
gmail is their own company, keyed on their name, per the rule that a solo
recruiter trading under their own name has that name as the company.

Nothing is deleted. Losers go to the parked file with a reason.

    ./merge_contacts.py --dry-run       show what would happen
    ./merge_contacts.py                 write it
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# Where the master contact list lives. Override with OUTREACH_DATA_DIR
# if you keep contacts outside the repo (a private notes folder, say).
VAULT = Path(os.environ.get("OUTREACH_DATA_DIR",
                            Path(__file__).resolve().parent / "data"))
MASTER = VAULT / "recruiter-outreach-list.csv"
PARKED = VAULT / "recruiter-outreach-parked.csv"
REPORT = VAULT / "recruiter-outreach-dedupe-report.md"
BLOCKLIST = VAULT / "do-not-contact.txt"

BATCH_GLOB = "batch-*.csv"

FIELDS = ["type", "role", "name", "company", "email", "linkedin", "specialism",
          "location", "website", "profile", "verified", "notes"]

FREE_MAIL = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "hotmail.co.uk",
    "live.com", "live.co.uk", "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com",
    "aol.com", "protonmail.com", "proton.me", "btinternet.com", "sky.com",
}

# Words that carry no identity. "Acme" and "Acme Recruitment Ltd" are one
# company; "Bond Search" and "Bond Search Limited" likewise.
NOISE = {
    "ltd", "limited", "llp", "plc", "inc", "incorporated", "llc", "group",
    "holdings", "uk", "gb", "london", "the", "and", "co", "company",
    "recruitment", "recruiting", "recruiters", "recruiter", "resourcing",
    "talent", "search", "staffing", "consulting", "consultancy", "consultants",
    "partners", "partnership", "associates", "solutions", "services",
    "technology", "technologies", "tech", "digital", "people", "hire", "hiring",
}

PLACEHOLDER = re.compile(
    r"^(n/?a|none|no email published|not published|unknown|tbc|-+)$", re.I)


def is_blank(value: str) -> bool:
    v = (value or "").strip()
    return not v or bool(PLACEHOLDER.match(v))


def norm_email(value: str) -> str:
    v = (value or "").strip().lower()
    if is_blank(v) or "@" not in v:
        return ""
    # a pattern-guessed address is a hypothesis, not an identity
    if "[" in v or "guess" in v:
        return ""
    return v


def domain_of(value: str) -> str:
    """Registrable-ish domain from an email or a URL. Empty if free or absent."""
    v = (value or "").strip().lower()
    if is_blank(v):
        return ""
    if "@" in v:
        v = v.rsplit("@", 1)[-1]
    v = re.sub(r"^\w+://", "", v)
    v = v.split("/")[0].split("?")[0]
    v = re.sub(r"^www\.", "", v)
    v = v.strip().strip(".")
    if not v or "." not in v or v in FREE_MAIL:
        return ""
    return v


def norm_company(value: str) -> str:
    """Identity-bearing tokens only, sorted so word order can't split a match."""
    v = (value or "").lower()
    v = re.sub(r"[^a-z0-9 ]+", " ", v)
    tokens = [t for t in v.split() if t and t not in NOISE]
    if not tokens:                      # name was entirely noise: keep it whole
        tokens = [t for t in v.split() if t]
    return " ".join(sorted(tokens))


def norm_person(value: str) -> str:
    v = re.sub(r"[^a-z ]+", " ", (value or "").lower())
    return " ".join(sorted(t for t in v.split() if len(t) > 1))


# Not company names. Two solo recruiters both filed under "Independent" are two
# businesses, not one, so these fall through to keying on the person.
NOT_A_COMPANY = {"independent", "freelance", "self employed", "sole trader",
                 "n a", "none", "unknown", ""}


def company_keys(row: dict) -> list[str]:
    """
    Every identity a company might already be filed under.

    Checking only the best key is not enough. The same company arrives once
    with an email (keyed on its domain) and once without (keyed on its name),
    and those two keys never meet, so it survives as two rows. Return all of
    them and match on any.
    """
    keys = []
    for source in (row.get("email", ""), row.get("website", "")):
        dom = domain_of(source)
        if dom and f"dom:{dom}" not in keys:
            keys.append(f"dom:{dom}")
    name = norm_company(row.get("company", ""))
    if name and name not in NOT_A_COMPANY:
        keys.append(f"co:{name}")
    if not keys:
        # solo recruiter under their own name: no site, free-mail address
        person = norm_person(row.get("name", ""))
        if person:
            keys.append(f"person:{person}")
    return keys


def score(row: dict) -> tuple:
    """Higher is better. Decides which row survives a collision."""
    has_email = bool(norm_email(row.get("email", "")))
    verified = "verified" in (row.get("verified") or "").lower()
    has_hook = len((row.get("notes") or "").strip()) > 40
    has_person = bool((row.get("name") or "").strip())
    has_role = bool((row.get("role") or "").strip())
    completeness = sum(1 for f in FIELDS if not is_blank(row.get(f, "")))
    return (has_email, verified, has_person, has_hook, has_role, completeness)


def load_blocklist(path: Path) -> tuple[set, set]:
    """Company names (normalised) and domains that must never be contacted."""
    names, domains = set(), set()
    if not path.exists():
        return names, domains
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "." in line and " " not in line:
            domains.add(line.lower())
        else:
            names.add(norm_company(line))
    return names, domains


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return []
        out = []
        for raw in reader:
            row = {f: (raw.get(f) or "").strip() for f in FIELDS}
            # batches may name the column either way
            if not row["company"]:
                row["company"] = (raw.get("agency") or "").strip()
            row["_source"] = path.name
            if any(row[f] for f in FIELDS):
                out.append(row)
        return out


def write(path: Path, rows: list[dict], extra: list[str] = ()) -> None:
    fields = FIELDS + list(extra)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report only, write nothing")
    ap.add_argument("--batch-dir", type=Path, default=VAULT,
                    help=f"where the {BATCH_GLOB} files live (default {VAULT})")
    args = ap.parse_args()

    master = load(MASTER)
    batches = sorted(args.batch_dir.glob(BATCH_GLOB))
    incoming = [r for p in batches for r in load(p)]

    if not batches:
        print(f"no {BATCH_GLOB} files in {args.batch_dir} — nothing to merge")
    print(f"master   : {len(master)} rows")
    for p in batches:
        print(f"batch    : {p.name} ({len(load(p))} rows)")
    print(f"incoming : {len(incoming)} rows\n")

    block_names, block_domains = load_blocklist(BLOCKLIST)
    if block_names or block_domains:
        print(f"blocklist: {len(block_names)} name(s), {len(block_domains)} domain(s)\n")

    kept: list[dict] = []
    parked: list[dict] = []
    by_email: dict[str, dict] = {}
    by_company: dict[str, dict] = {}
    by_person: dict[str, dict] = {}
    collisions = defaultdict(list)

    # CHANNEL rows are boards and communities, not companies — one per name,
    # and they must never collide with a real company on a shared domain.
    def consider(row: dict) -> None:
        dom = domain_of(row["email"]) or domain_of(row["website"])
        if norm_company(row["company"]) in block_names or dom in block_domains:
            parked.append({**row, "_why": "on the do-not-contact list"})
            return
        if row["type"].strip().upper() == "CHANNEL":
            key = f"chan:{norm_company(row['company'] or row['name'])}"
            if key in by_company:
                parked.append({**row, "_why": "duplicate channel"})
                return
            by_company[key] = row
            kept.append(row)
            return

        email = norm_email(row["email"])
        ckeys = company_keys(row)
        pkeys = [f"{norm_person(row['name'])}|{k}" for k in ckeys] if row["name"] else []

        checks = [(email, by_email, "same email")]
        checks += [(k, by_person, "same person") for k in pkeys]
        checks += [(k, by_company, "company already covered") for k in ckeys]

        def remember(target: dict) -> None:
            if email:
                by_email[email] = target
            for k in pkeys:
                by_person[k] = target
            for k in ckeys:
                by_company[k] = target

        for key, index, why in checks:
            if not key or key not in index:
                continue
            held = index[key]
            if score(row) > score(held):
                # incoming wins: swap, park the incumbent
                kept[kept.index(held)] = row
                parked.append({**held, "_why": f"{why} as {row['name'] or row['company']}"})
                remember(row)
            else:
                parked.append({**row, "_why": f"{why} as {held['name'] or held['company']}"})
                # the loser's keys still point at the winner, so a third copy
                # arriving under either spelling is caught too
                for k in ckeys:
                    by_company.setdefault(k, held)
                if email:
                    by_email.setdefault(email, held)
            collisions[held["company"] or held["name"]].append(
                f"{row['name'] or '(no name)'} [{row['_source']}] — {why}")
            return

        kept.append(row)
        remember(row)

    for row in master + incoming:
        consider(row)

    print(f"kept     : {len(kept)}")
    print(f"parked   : {len(parked)}")
    print(f"companies with a collision: {len(collisions)}\n")

    with_email = sum(1 for r in kept if norm_email(r["email"]))
    print(f"of the kept rows, {with_email} have a usable email address")

    if args.dry_run:
        for company, hits in list(collisions.items())[:15]:
            print(f"  {company}: {'; '.join(hits[:3])}")
        print("\ndry run — nothing written")
        return 0

    if MASTER.exists():
        shutil.copy2(MASTER, MASTER.with_suffix(".csv.bak"))
    write(MASTER, kept)
    write(PARKED, parked, extra=["_why", "_source"])

    lines = ["# Outreach list dedupe report", "",
             f"- master in: {len(master)}", f"- batches in: {len(incoming)}",
             f"- kept: {len(kept)}", f"- parked: {len(parked)}",
             f"- kept rows with an email: {with_email}", "",
             "## Collisions", ""]
    for company, hits in sorted(collisions.items()):
        lines.append(f"**{company}**")
        lines += [f"- {h}" for h in hits]
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nwrote {MASTER}")
    print(f"wrote {PARKED}")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
