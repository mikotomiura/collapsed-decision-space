#!/usr/bin/env python3
"""Render the References section of ``manuscript/main.md`` from ``manuscript/refs.json``.

The reference list used to be prose in ``main.md``, and every other form of it -- the BibTeX file
of the PDF build, a reference manager's import -- had to be parsed back out of that prose. A parser
of prose fails open: an entry it half-reads still comes out looking like a reference. So the list
is now held as data. ``manuscript/refs.json`` is a CSL-JSON array, the format reference managers
and citation processors read, and the References section of ``main.md`` is **generated** from it:
this script renders the entries between two markers, and ``--check`` fails if the text between the
markers is not what the data renders to. The same arrangement already holds the decision rules of
§E (``render_decision_rules.py``); the markers here have a different name, so that neither check
can mistake the other's block for its own.

**What each entry holds.** The fields CSL-JSON defines carry the meaning: the type, every author
(family name and initials, in order), the title in sentence case, the container, volume, issue, page
or article number, publisher, edition, DOI, URL and year. Initials are kept as initials, as in the central bibliography
the numbers come from; a fuller form would be invention. A field the prose does not print (the URL
of an arXiv record, the authors an "et al." stands for) is still held, so that a processor that
needs it does not have to guess.

The ``x-cds`` object of each entry holds what is not meaning but the way this manuscript prints it,
so that the rendered list reads as the hand-written one did:

* ``n`` -- the permanent identifier ``[n]`` from the author's central bibliography;
* ``et-al-after`` -- print this many authors, then "et al." (absent: print all of them);
* ``page-prefix`` -- the text printed before a page range ("pp. " for a conference paper);
* ``number-prefix`` -- the text printed before an article number ("article ");
* ``remark`` -- a parenthetical remark closing the entry, printed verbatim (none at present).

An author is either a person (``family`` and ``given``, the initials) or an organisation
(``literal``). A web page (``webpage``) carries the date it was read (``accessed``) and, when it
shows none, no ``issued`` date: it is printed "n.d." rather than given the year it was read.

**What the rendering does not do.** It does not set the list in any publication style. The PDF
build reads the rendered prose back into BibTeX (``make_pdf_source.parse_references``), so the
prose keeps the form that parser reads: ``[n] Authors. *Title.* venue, year. doi:...``.

Usage:
    python analysis/scripts/render_references.py            # print the block
    python analysis/scripts/render_references.py --write    # rewrite the block in main.md
    python analysis/scripts/render_references.py --check    # exit 1 if the block has drifted
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REFS_PATH = Path("manuscript") / "refs.json"
MANUSCRIPT_PATH = Path("manuscript") / "main.md"

BEGIN_MARKER = "<!-- BEGIN RENDERED FROM manuscript/refs.json -- DO NOT EDIT BY HAND -->"
END_MARKER = "<!-- END RENDERED FROM manuscript/refs.json -->"

#: The width the entries are wrapped to. Only the line breaks depend on it; ``--check`` compares
#: the rendered block byte for byte, so it is part of the rendering, not a preference.
WIDTH = 100

#: The fields each type must carry, beyond ``id``, ``type``, ``author``, ``title`` and ``x-cds.n``
#: (and ``issued``, for every type but a web page). An entry missing one fails rather than rendering
#: a shorter reference.
REQUIRED_BY_TYPE: dict[str, tuple[str, ...]] = {
    "article": ("number",),  # a preprint: the repository's identifier
    "article-journal": ("container-title", "volume", "DOI"),
    "paper-conference": ("container-title", "page", "DOI"),
    "book": ("publisher", "DOI"),
    "webpage": ("URL", "accessed"),
}

KNOWN_FIELDS = frozenset(
    {
        "id",
        "type",
        "author",
        "title",
        "container-title",
        "volume",
        "issue",
        "page",
        "number",
        "publisher",
        "DOI",
        "URL",
        "issued",
        "edition",
        "accessed",
        "x-cds",
    }
)
KNOWN_X_CDS = frozenset({"n", "et-al-after", "page-prefix", "number-prefix", "remark"})

#: A wrapped line must not begin with something markdown reads as structure. A continuation line
#: opening with "[27] " would also be read by ``parse_references`` as a new entry.
_UNSAFE_LINE_START = re.compile(r"^(?:\[\d+\] |\d+[.)] |[-+*>#|] |<)")


def load(root: Path) -> list[dict[str, Any]]:
    data = json.loads((root / REFS_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"[references] FAIL: {REFS_PATH} is not a JSON array")
    return data


def validate(items: list[dict[str, Any]]) -> list[str]:
    """What is wrong with the data itself, before anything is rendered from it."""
    problems: list[str] = []
    previous = 0
    for index, item in enumerate(items):
        x_cds = item.get("x-cds", {})
        n = x_cds.get("n")
        label = f"[{n}]" if n is not None else f"entry {index}"
        if not isinstance(n, int) or n <= previous:
            problems.append(f"{label}: x-cds.n must be an integer above {previous} (ascending)")
        else:
            previous = n
        if item.get("id") != f"cds{n}":
            problems.append(f"{label}: id is {item.get('id')!r}, expected 'cds{n}'")
        for field in sorted(set(item) - KNOWN_FIELDS):
            problems.append(f"{label}: unknown field {field!r}")
        for field in sorted(set(x_cds) - KNOWN_X_CDS):
            problems.append(f"{label}: unknown x-cds field {field!r}")
        kind = item.get("type")
        if kind not in REQUIRED_BY_TYPE:
            problems.append(f"{label}: type {kind!r} is not one this renderer knows")
            continue
        dated = ("issued",) if kind != "webpage" else ()
        for field in ("author", "title", *dated, *REQUIRED_BY_TYPE[kind]):
            if not item.get(field):
                problems.append(f"{label}: {kind} entry has no {field!r}")
        for author in item.get("author", []):
            person = bool(author.get("family") and author.get("given"))
            if person == bool(author.get("literal")) or len(author) != (2 if person else 1):
                problems.append(
                    f"{label}: an author must be a person (family, given) or an organisation "
                    f"(literal), not {author}"
                )
        cut = x_cds.get("et-al-after")
        if cut is not None and not (isinstance(cut, int) and 0 < cut < len(item.get("author", []))):
            problems.append(f"{label}: et-al-after = {cut!r} does not shorten the author list")
        if "page" in item and "number" in item and kind != "article":
            problems.append(f"{label}: both a page range and an article number")
        if "edition" in item and not str(item["edition"]).isdigit():
            problems.append(f"{label}: edition {item['edition']!r} is not a number")
    return problems


def _ordinal(edition: str) -> str:
    number = int(edition)
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _year(item: dict[str, Any]) -> str:
    if "issued" not in item:
        return "n.d."
    return str(item["issued"]["date-parts"][0][0])


def _date(value: dict[str, Any]) -> str:
    year, month, day = value["date-parts"][0]
    return f"{year:04d}-{month:02d}-{day:02d}"


def _authors(item: dict[str, Any]) -> str:
    names = [a.get("literal") or f"{a['family']}, {a['given']}" for a in item["author"]]
    cut = item["x-cds"].get("et-al-after")
    if cut:
        return ", ".join(names[:cut]) + " et al."
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _venue(item: dict[str, Any]) -> list[str]:
    """The comma-separated parts printed after the title, the year last."""
    x_cds = item["x-cds"]
    kind = item["type"]
    if kind == "article":
        return [item["number"], _year(item)]
    if kind == "webpage":
        return ["Web page", _year(item)]
    if kind == "book":
        edition = [f"{_ordinal(item['edition'])} edition"] if item.get("edition") else []
        return [item["publisher"], *edition, _year(item)]
    parts = [item["container-title"]]
    if kind == "article-journal":
        volume = item["volume"] + (f"({item['issue']})" if item.get("issue") else "")
        parts.append(volume)
    if item.get("page"):
        parts.append(x_cds.get("page-prefix", "") + item["page"])
    elif item.get("number"):
        parts.append(x_cds.get("number-prefix", "") + item["number"])
    parts.append(_year(item))
    return parts


def render_entry(item: dict[str, Any]) -> str:
    """One entry as a single line of prose."""
    authors = _authors(item)
    if not authors.endswith("."):
        authors += "."
    title = item["title"]
    if not title.endswith((".", "?", "!")):
        title += "."
    venue = ", ".join(_venue(item))
    text = f"[{item['x-cds']['n']}] {authors} *{title}* {venue}" + ("" if venue.endswith(".") else ".")
    if item.get("DOI"):
        text += f" doi:{item['DOI']}"
    if item["type"] == "webpage":
        text += f" {item['URL']} (retrieved {_date(item['accessed'])})"
    if item["x-cds"].get("remark"):
        text += f" ({item['x-cds']['remark']})"
    return text


def wrap(entry: str) -> str:
    # A token that would read as markup at the start of a line ("2013." as a list item) is bound to
    # the token before it, so that the wrap cannot put it there.
    tokens: list[str] = []
    for token in entry.split(" "):
        if tokens and _UNSAFE_LINE_START.match(token + " "):
            tokens[-1] += "\0" + token
        else:
            tokens.append(token)
    lines = textwrap.wrap(
        " ".join(tokens), width=WIDTH, break_long_words=False, break_on_hyphens=False
    )
    lines = [line.replace("\0", " ") for line in lines]
    for line in lines[1:]:
        if _UNSAFE_LINE_START.match(line):
            raise SystemExit(
                f"[references] FAIL: a wrapped line would begin with markup: {line[:40]!r}"
            )
    return "\n".join(lines)


def render(items: list[dict[str, Any]]) -> str:
    """The whole block, markers included."""
    body = "\n\n".join(wrap(render_entry(item)) for item in items)
    return f"{BEGIN_MARKER}\n\n{body}\n\n{END_MARKER}"


def extract_block(text: str) -> str | None:
    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        return None
    start = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    return text[start:end] if start < end else None


def _entries(block: str) -> dict[str, str]:
    """``[n]`` -> the entry's text with its whitespace collapsed."""
    inner = block.removeprefix(BEGIN_MARKER).removesuffix(END_MARKER)
    out: dict[str, str] = {}
    for paragraph in inner.split("\n\n"):
        text = " ".join(paragraph.split())
        match = re.match(r"^(\[\d+\]) ", text)
        if match:
            out[match.group(1)] = text
        elif text:
            out[f"(unnumbered: {text[:30]!r})"] = text
    return out


def compare(items: list[dict[str, Any]], manuscript: str) -> list[str]:
    """What differs between the data and the block in the manuscript, entry by entry."""
    problems = validate(items)
    if problems:
        return problems
    found = extract_block(manuscript)
    if found is None:
        return [f"{MANUSCRIPT_PATH} must carry exactly one block between the RENDERED markers"]
    expected = render(items)
    if found == expected:
        return []
    want, have = _entries(expected), _entries(found)
    for key in want:
        if key not in have:
            problems.append(f"{key} is in {REFS_PATH} but not in the block of {MANUSCRIPT_PATH}")
        elif want[key] != have[key]:
            problems.append(f"{key} differs: refs.json renders {want[key]!r}, main.md has {have[key]!r}")
    for key in have:
        if key not in want:
            problems.append(f"{key} is in the block of {MANUSCRIPT_PATH} but not in {REFS_PATH}")
    if not problems:
        problems.append("the block differs from the rendering only in its line breaks or spacing")
    return problems


def self_check(items: list[dict[str, Any]], manuscript: str) -> list[str]:
    """Break copies of the two inputs and require ``compare`` to name what was broken.

    A comparison whose only observed outcome is "equal" has not been shown to see anything. Each
    case is a copy of the real data or the real manuscript with one change, and it must be reported
    with the entry it touched; the unchanged pair is the control and must not be.
    """
    failures: list[str] = []
    first, last = items[0]["x-cds"]["n"], items[-1]["x-cds"]["n"]

    year_moved = copy.deepcopy(items)
    year_moved[0]["issued"]["date-parts"][0][0] += 1
    author_dropped = copy.deepcopy(items)
    author_dropped[-1]["author"] = author_dropped[-1]["author"][:-1] or [
        {"family": "X", "given": "X."}
    ]
    block = extract_block(manuscript) or ""
    last_entry = wrap(render_entry(items[-1]))
    entry_removed = manuscript.replace(block, block.replace("\n\n" + last_entry, "", 1))
    cases: tuple[tuple[str, list[dict[str, Any]], str, str | None], ...] = (
        ("control (no change)", items, manuscript, None),
        ("the year of the first entry moved", year_moved, manuscript, f"[{first}] differs"),
        ("an author of the last entry dropped", author_dropped, manuscript, f"[{last}] differs"),
        ("the last entry removed from main.md", items, entry_removed, f"[{last}] is in"),
    )
    for name, data, text, expected in cases:
        found = compare(data, text)
        if expected is None:
            if found:
                failures.append(f"self-check, {name}: the control returned {found}")
        elif len(found) != 1 or expected not in found[0]:
            failures.append(f"self-check, {name}: expected one problem containing {expected!r}, got {found}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="rewrite the block in main.md")
    mode.add_argument("--check", action="store_true", help="exit 1 if the block has drifted")
    args = parser.parse_args(argv)

    items = load(args.repo_root)
    problems = validate(items)
    if problems:
        print(f"[references] FAIL: {REFS_PATH} is not valid", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    path = args.repo_root / MANUSCRIPT_PATH
    manuscript = path.read_text(encoding="utf-8")

    if args.write:
        block = extract_block(manuscript)
        if block is None:
            print(f"[references] FAIL: {MANUSCRIPT_PATH} has no single RENDERED block", file=sys.stderr)
            return 1
        path.write_text(manuscript.replace(block, render(items)), encoding="utf-8", newline="\n")
        print(f"[references] wrote {len(items)} entries into {MANUSCRIPT_PATH}")
        return 0

    if args.check:
        problems = compare(items, manuscript) + self_check(items, manuscript)
        if problems:
            print("[references] FAIL", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(
            f"[references] OK: the References block of {MANUSCRIPT_PATH} is what the "
            f"{len(items)} entries of {REFS_PATH} render to, and a moved year, a dropped author "
            "and a removed entry are each reported against the entry they touch"
        )
        return 0

    print(render(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
