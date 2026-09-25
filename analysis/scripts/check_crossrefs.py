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

#: A ``§`` preceded by one of these names a section of another document, not of the manuscript:
#: a named file (backticked, with a document suffix, and not the manuscript itself), the sealed
#: protocol, the held-out specification, or the claim boundary. An arbitrary code span is not
#: enough: a stale reference right after an unrelated code span would otherwise be hidden
#: (TASK-POST review).
FOREIGN = re.compile(
    r"(`(?!manuscript/main\.md`)[^`\s]+\.(?:md|json|toml|yml|sh|py)`\s*|protocol(?:\.md)?`?\s*"
    r"|SPEC(?:\.ja\.md)?`?\s*|CLAIM-BOUNDARY(?:\.md)?`?\s*)$"
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

#: Files that must not change. Walked on the filesystem, not listed through git: step 9 of the
#: sealed repro.sh runs this check, and repro.sh has never needed git -- it runs from an archive,
#: from the de-identified bundle and from a downloaded zip. The first version called
#: ``git ls-files``, failed outside a checkout, and found nothing inside an ignored directory
#: (TASK-POST review).
FROZEN_SCOPE: tuple[str, ...] = (
    "repro.sh",
    "analysis/freeze-provenance.json",
    "analysis/heldout-stay",
    "analysis/autopsy",
    "data/posthoc",
    "data/prospective/README.md",
    "seal",
)
FROZEN_SUFFIXES: frozenset[str] = frozenset(
    {".md", ".json", ".sh", ".py", ".txt", ".tsv", ""}
)

#: The shapes in which a frozen file cites a section of the manuscript. ``DOTTED`` is general: a
#: dotted ``§N.M`` that is not one of the file's own headings cites the manuscript's numbering (the
#: held-out specification cites "§12.1 の confound", and numbers its own sections by integers only),
#: and must be listed like the explicit shapes.
FROZEN_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"manuscript/main\.md,? section [0-9]+(?:\.[0-9]+)*"),
    re.compile(r"本文 ?§[0-9]+(?:\.[0-9]+)*"),
    re.compile(r"§[0-9]+(?:\.[0-9]+)* of the manuscript"),
    re.compile(r"(?<=base of )section [0-9]+(?:\.[0-9]+)*"),
)
DOTTED = re.compile(r"§([0-9]+\.[0-9]+(?:\.[0-9]+)*)")

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


def frozen_citations_text(text: str) -> list[tuple[int, str]]:
    """(line, literal) of every citation of the manuscript's numbering in one frozen file."""
    own = headings(text)
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        spans: list[tuple[int, int]] = []
        for shape in FROZEN_SHAPES:
            for match in shape.finditer(line):
                spans.append((match.start(), match.end()))
                found.append((number, match.group(0)))
        for match in DOTTED.finditer(line):
            inside = any(s <= match.start() < e for s, e in spans)
            if not inside and match.group(1) not in own:
                found.append((number, match.group(0)))
    return found


def frozen_files(root: Path) -> list[str]:
    files: list[str] = []
    for entry in FROZEN_SCOPE:
        path = root / entry
        if path.is_file():
            files.append(entry)
        elif path.is_dir():
            files += sorted(
                p.relative_to(root).as_posix()
                for p in path.rglob("*")
                if p.is_file()
                and p.suffix in FROZEN_SUFFIXES
                and "__pycache__" not in p.parts
            )
    return files


def map_row(entry: dict[str, object]) -> str:
    return f"| `{entry['file']}` | {entry['line']} | {entry['old']} | §{entry['new']} |"


def check(root: Path) -> list[str]:
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
    files = frozen_files(root)
    # A scope with a missing entry is a failure, not a pass: a check that found nothing to read has
    # read nothing.
    missing = [e for e in FROZEN_SCOPE if not (root / e).exists()]
    if missing:
        problems.append(f"frozen files to check are missing: {missing}")
    for rel in files:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for line, literal in frozen_citations_text(text):
            if (rel, line, literal) not in listed:
                problems.append(
                    f"{rel}:{line}: {literal!r} cites a manuscript section but is not in "
                    f"{SECTION_MAP}"
                )
    return problems


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
    if not unresolved("`unrelated` §12.8", known, "t"):
        problems.append(
            "self-test: a stale reference after a code span was treated as foreign"
        )
    if not frozen_citations_text("# manuscript/main.md section 9.9; more"):
        problems.append("self-test: an unlisted frozen citation was not found")
    if frozen_citations_text(
        "## 3. Own\n\nsee §3 of this file"
    ) or not frozen_citations_text("## 12. Own\n\nthe confound of §12.1"):
        problems.append(
            "self-test: a dotted citation was not told apart from an own section"
        )
    if not frozen_files(root):
        problems.append("self-test: the frozen scope is empty")
    return problems


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
    problems = check(args.repo_root)
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
