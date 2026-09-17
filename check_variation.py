#!/usr/bin/env python3
"""
How similar are the templates to each other?

Bulk filters cluster near-identical bodies, so the thing worth measuring is not
"are these files different" (trivially yes) but "how much text do any two of
them share". Two measures, because they catch different problems:

  shingle   overlap of 4-word sequences. Catches whole reused sentences.
  sequence  difflib ratio on the token stream. Catches the same paragraph
            lightly reworded.

Shared boilerplate (the sign-off, the GitHub link, the stock evidence line) is
fine and expected within a lane. What must not happen is two templates in the
same lane reading as one email with a word swapped.

    ./check_variation.py                all templates
    ./check_variation.py --lane f       just the founder lane
"""
from __future__ import annotations

import argparse
import re
import sys
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"

# Above this, two bodies in the same lane are too close for comfort.
WARN_SHINGLE = 0.45
WARN_SEQUENCE = 0.70

PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def body_tokens(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    # drop the SUBJECT line: subjects are compared separately
    text = "\n".join(l for l in text.splitlines() if not l.startswith("SUBJECT:"))
    text = PLACEHOLDER.sub(" ", text)          # placeholders vary per recipient
    text = re.sub(r"[^a-zA-Z0-9' ]+", " ", text.lower())
    return [t for t in text.split() if t]


def subject_of(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SUBJECT:"):
            return line[len("SUBJECT:"):].strip()
    return ""


def shingles(tokens: list[str], n: int = 4) -> set[tuple]:
    return {tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lane", help="only templates whose name starts with this")
    ap.add_argument("--all-pairs", action="store_true",
                    help="print every pair, not just the worst")
    args = ap.parse_args()

    paths = sorted(p for p in TEMPLATES.glob("*.txt")
                   if not args.lane or p.stem.startswith(args.lane))
    if len(paths) < 2:
        print("need at least two templates to compare")
        return 1

    tokens = {p: body_tokens(p) for p in paths}
    shings = {p: shingles(t) for p, t in tokens.items()}

    rows, warnings = [], []
    for a, b in combinations(paths, 2):
        sa, sb = shings[a], shings[b]
        overlap = len(sa & sb) / max(1, min(len(sa), len(sb)))
        ratio = SequenceMatcher(None, tokens[a], tokens[b]).ratio()
        same_lane = a.stem[0] == b.stem[0]
        rows.append((overlap, ratio, a.stem, b.stem, same_lane))
        if same_lane and (overlap > WARN_SHINGLE or ratio > WARN_SEQUENCE):
            warnings.append((overlap, ratio, a.stem, b.stem))

    rows.sort(reverse=True)
    print(f"{len(paths)} templates, {len(rows)} pairs\n")
    print(f"{'shingle':>8} {'seq':>6}  pair")
    for overlap, ratio, a, b, same_lane in (rows if args.all_pairs else rows[:12]):
        flag = "  <-- same lane, too close" if same_lane and (
            overlap > WARN_SHINGLE or ratio > WARN_SEQUENCE) else ""
        print(f"{overlap:8.2f} {ratio:6.2f}  {a} / {b}{flag}")

    subjects = {p.stem: subject_of(p) for p in paths}
    dupes = {}
    for stem, subj in subjects.items():
        dupes.setdefault(subj, []).append(stem)
    repeated = {s: v for s, v in dupes.items() if len(v) > 1}

    print(f"\nsubjects: {len(set(subjects.values()))} distinct across {len(subjects)} templates")
    for subj, stems in repeated.items():
        print(f"  reused by {', '.join(stems)}: {subj}")

    if warnings:
        print(f"\n{len(warnings)} same-lane pair(s) above threshold "
              f"(shingle {WARN_SHINGLE}, sequence {WARN_SEQUENCE}):")
        for overlap, ratio, a, b in warnings:
            print(f"  {a} / {b}: shingle {overlap:.2f}, sequence {ratio:.2f}")
        return 1

    print("\nno same-lane pair is above threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
