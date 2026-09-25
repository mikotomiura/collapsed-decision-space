#!/usr/bin/env python3
"""Check that every section reference resolves, including the ones files that cannot change make.

On 2026-09-26 the manuscript was reordered into TMLR order -- body, References, appendices -- and
its sections renumbered (appendices are lettered). Two kinds of reference can go wrong under that,
and neither is visible from reading the page:

* **A reference in an editable file that was not renumbered**, or was renumbered to a section that
  does not exist. ``§12.8`` no longer names anything; a leftover one reads as a citation and points
  nowhere. Every ``§`` reference in the manuscript and in the repository's own documents must
  therefore name a heading that exists.
* **A reference in a file that must not change** -- sealed (``repro.sh``), frozen (the held-out
  specification) or declared (the post hoc simulation's grid and outputs). These still cite the
  earlier numbers, and editing them is not an option: their bytes are what the seal, the freeze or
  the declaration binds. ``manuscript/tmlr/section-map.json`` lists each one with the section it now
  means, and appendix L of the manuscript carries the same table for a reader. This script requires
  every listed literal to still stand at its line, every row of the table to be in the manuscript
  exactly once, and **no other** citation of that kind to exist in those files -- so a frozen
  reference nobody listed fails the run instead of silently pointing at the wrong section.

What it does not establish: that a reference that resolves points at the *right* section. The
renumbering was applied from one old-to-new map, which is what makes that likely; a check that the
text around each reference is about the section it names would need a reader.

Usage:  python analysis/scripts/check_crossrefs.py [--self-test]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: A heading number: ``1``, ``4.3``, ``A``, ``I.5``.
HEADING = re.compile(r"^#{2,4} ([0-9]+(?:\.[0-9]+)*|[A-Z](?:\.[0-9]+)*)\.? ", re.M)
TOKEN = re.compile(r"§([0-9]+(?:\.[0-9]+)*|[A-Z](?:\.[0-9]+)*)(?![0-9A-Za-z])")

#: A ``§`` preceded by one of these names a section of another document, not of the manuscript.
FOREIGN = re.compile(
    r"(`(?!manuscript/main\.md`)[^`]+`\s*|protocol(?:\.md)?`?\s*|SPEC(?:\.ja\.md)?`?\s*"
    r"|CLAIM-BOUNDARY(?:\.md)?`?\s*)$"
)

#: The repository's own documents whose ``§`` references are checked, besides the manuscript. A
#: document may also cite its own sections; those resolve against its own headings.
DOCUMENTS: tuple[str, ...] = (
    "README.md",
    "README.ja.md",
    "manuscript/CLAIM-BOUNDARY.md",
    "manuscript/REPORTED-BRANCH.md",
    "manuscript/refs.md",
    "data/data.md",
    "env.md",
)

#: Files that must not change, and the shapes in which they cite a section of the manuscript.
FROZEN_SCOPE: tuple[str, ...] = (
    "repro.sh",
    "analysis/freeze-provenance.json",
    "analysis/heldout-stay/",
    "analysis/autopsy/",
    "data/posthoc/",
    "data/prospective/README.md",
    "seal/",
)
FROZEN_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"manuscript/main\.md,? section [0-9]+(?:\.[0-9]+)*"),
    re.compile(r"本文 ?§[0-9]+(?:\.[0-9]+)*"),
    re.compile(r"§[0-9]+(?:\.[0-9]+)* of the manuscript"),
    re.compile(r"(?<=base of )section [0-9]+(?:\.[0-9]+)*"),
)

SECTION_MAP = Path("manuscript/tmlr/section-map.json")
GENERATED = re.compile(r"<!-- BEGIN GENERATED.*?<!-- END GENERATED[^\n]*-->", re.S)


def headings(text: str) -> set[str]:
    return set(HEADING.findall(text))


def unresolved(text: str, known: set[str], where: str) -> list[str]:
    """``§`` references in ``text`` that name no heading in ``known``."""
    problems = []
    for match in TOKEN.finditer(text):
        before = text[max(0, match.start() - 40) : match.start()]
        if FOREIGN.search(before):
            continue
        if match.group(1) not in known:
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"{where}:{line}: {match.group(0)} names no section")
    return problems


def frozen_citations(root: Path, files: list[str]) -> set[tuple[str, int, str]]:
    found: set[tuple[str, int, str]] = set()
    for rel in files:
        for number, line in enumerate(
            (root / rel).read_text(encoding="utf-8").splitlines(), start=1
        ):
            for shape in FROZEN_SHAPES:
                for match in shape.finditer(line):
                    found.add((rel, number, match.group(0)))
    return found


def map_row(entry: dict[str, object]) -> str:
    return f"| `{entry['file']}` | {entry['line']} | {entry['old']} | §{entry['new']} |"


def check(root: Path, tracked: list[str]) -> list[str]:
    main = (root / "manuscript" / "main.md").read_text(encoding="utf-8")
    known = headings(main)
    problems = unresolved(GENERATED.sub("", main), known, "manuscript/main.md")
    for rel in DOCUMENTS:
        text = (root / rel).read_text(encoding="utf-8")
        problems += unresolved(text, known | headings(text), rel)

    entries = json.loads((root / SECTION_MAP).read_text(encoding="utf-8"))[
        "frozen_citations"
    ]
    listed = set()
    flat = " ".join(main.split())
    for entry in entries:
        rel, line, literal = entry["file"], entry["line"], entry["literal"]
        listed.add((rel, line, literal))
        lines = (root / rel).read_text(encoding="utf-8").splitlines()
        if line > len(lines) or literal not in lines[line - 1]:
            problems.append(
                f"{SECTION_MAP}: {rel}:{line} no longer carries {literal!r}"
            )
        if entry["new"] not in known:
            problems.append(
                f"{SECTION_MAP}: §{entry['new']} (for {rel}:{line}) names no section"
            )
        count = flat.count(" ".join(map_row(entry).split()))
        if count != 1:
            problems.append(
                f"main.md carries the appendix L row for {rel}:{line} {count} times, not once"
            )
    scope = sorted(
        rel
        for rel in tracked
        if any(rel == s or rel.startswith(s) for s in FROZEN_SCOPE)
    )
    found = frozen_citations(root, [rel for rel in scope if (root / rel).is_file()])
    for rel, line, literal in sorted(found - listed):
        problems.append(
            f"{rel}:{line}: {literal!r} cites a manuscript section but is not in {SECTION_MAP}"
        )
    return problems


def _tracked(root: Path) -> list[str]:
    import subprocess  # noqa: PLC0415

    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def self_test(root: Path) -> list[str]:
    """Each class of failure must be reported, and the unmodified inputs must pass."""
    main = (root / "manuscript" / "main.md").read_text(encoding="utf-8")
    known = headings(main)
    problems = []
    if unresolved("see §12.8 and §Z.1", known, "t") != [
        "t:1: §12.8 names no section",
        "t:1: §Z.1 names no section",
    ]:
        problems.append(
            "self-test: a reference to a section that does not exist was not reported"
        )
    if unresolved("in `seal/protocol.md` §12.8", known, "t"):
        problems.append(
            "self-test: a reference to another document was reported as unresolved"
        )
    if not unresolved("`manuscript/main.md` §12.8", known, "t"):
        problems.append(
            "self-test: a qualified reference to the manuscript was treated as foreign"
        )
    if not frozen_citations_text("# manuscript/main.md section 9.9; more"):
        problems.append("self-test: an unlisted frozen citation was not found")
    return problems


def frozen_citations_text(text: str) -> list[str]:
    return [m.group(0) for shape in FROZEN_SHAPES for m in shape.finditer(text)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="also check that failures fire"
    )
    args = parser.parse_args(argv)
    problems = check(args.repo_root, _tracked(args.repo_root))
    if args.self_test:
        problems += self_test(args.repo_root)
    if problems:
        print("[crossrefs] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    entries = json.loads((args.repo_root / SECTION_MAP).read_text(encoding="utf-8"))
    print(
        f"[crossrefs] OK: every section reference in the manuscript and {len(DOCUMENTS)} documents "
        f"names a heading; {len(entries['frozen_citations'])} citations in files that cannot "
        "change are listed with the section they now mean, and no other exists"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
