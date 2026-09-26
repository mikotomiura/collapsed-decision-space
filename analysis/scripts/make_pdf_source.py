#!/usr/bin/env python3
"""Build the pandoc source for the TMLR submission PDF from ``manuscript/main.md``.

**There is deliberately no second manuscript.** ``manuscript/main.md`` is the only text the
claim-boundary check, the abstract-consistency check and the character-level number check read. A
hand-maintained "submission copy" would be a claim surface outside all three, and the first number
corrected in one file and not the other would put the published manuscript and the submitted one
into disagreement. So the PDF is a *derived* artefact: this script performs a small, mechanical,
deterministic transformation and nothing else. The typesetting is the official TMLR style
(``manuscript/tmlr/``, vendored byte for byte and pinned by digest in ``VENDORED.json``).

What it changes, and why each change is necessary:

1. **The level-one heading becomes the title**, and the block between the ``TMLR:DROP`` markers
   (the repository's author table, which the TMLR title block replaces) is left out. The anonymous
   build carries no author at all: ``tmlr.sty`` without an option prints "Anonymous authors".
2. **The ``## Abstract`` section becomes the TMLR abstract.** It is taken out with the same
   function ``check_claim_boundary.py`` uses to compare it with ``CITATION.cff``, so the text the
   PDF sets as its abstract is the text that check compared.
3. **The block between the ``TMLR:FOOTNOTE`` markers moves to a footnote on the first page**, at
   the end of the first paragraph of the introduction. It is moved, not copied: the page carries it
   once, as ``main.md`` does.
4. **Figure markers become figure environments** around the ``\\input`` of a figure that
   ``make_figures.py`` generates from the shipped data. The caption stays in ``main.md`` as prose.
5. **Citations become natbib author-year.** ``[n]`` is a permanent identifier from the central
   bibliography; the bibliography of the PDF is generated from the References section of
   ``main.md`` (:func:`parse_references`), so there is no ``.bib`` file to drift from it. Where the
   prose already names the authors (``Hoenig and Heisey [44]``), the marker becomes the year alone;
   everywhere else it becomes a parenthetical citation. Every occurrence is classified against a
   committed fixture, ``manuscript/tmlr/citations.tsv``, so a change in how any citation is set is
   a visible diff rather than a silent one.
6. **The References section is replaced by the bibliography**, at the same place: between the body
   and the appendices, which is what lets the page budget be read off the page on which
   "References" is set.
7. **Over-long typewriter tokens are given permission to break**, and horizontal rules between
   sections are dropped (the TMLR style separates sections itself).

With ``--anonymous``, two identifying strings the de-identified bundle has to keep are also
withheld from the page (``.steering`` DA-C-4 and DA-C-5): the name of the upstream project, which
the supplement cannot drop because the provenance checks are byte comparisons against it, and the
title of the author's own prior preprint, which a search would resolve to the author.

Everything else is passed through byte for byte. The script fails rather than emitting a source it
could not transform as intended.

Usage:
    python analysis/scripts/make_pdf_source.py --out-dir build/pdf
    python analysis/scripts/make_pdf_source.py --out-dir build/pdf --anonymous
    python analysis/scripts/make_pdf_source.py --out-dir build/pdf --write-citations
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_claim_boundary import _extract_main_abstract  # noqa: E402

#: Author block of the named (preprint) build. The ORCID is the one pinned in ``CITATION.cff``;
#: ``check_pdf_text.py`` requires both to survive into the named PDF.
AUTHOR = r"\name Mikoto Miura \\ \addr Independent Researcher \\ \addr ORCID 0009-0000-4196-0508"

#: Markers in ``main.md``. HTML comments, so that the repository rendering shows nothing of them.
DROP_BEGIN = "<!-- TMLR:DROP -->"
DROP_END = "<!-- /TMLR:DROP -->"
FOOTNOTE_BEGIN = "<!-- TMLR:FOOTNOTE -->"
FOOTNOTE_END = "<!-- /TMLR:FOOTNOTE -->"
APPENDIX = "<!-- TMLR:APPENDIX -->"
FIGURE_BEGIN = re.compile(r"^<!-- TMLR:FIGURE ([a-z0-9-]+) -->$")
FIGURE_END = "<!-- /TMLR:FIGURE -->"

#: A code span longer than this, with no space in it, is rewritten so that it can break.
#:
#: TeX will not break a typewriter token that offers no breakpoint. It sets it past the column edge
#: instead, and the overflow is simply not on the page: the first build of this document put 47 of
#: the 64 characters of each SHA-256 model digest on the page and lost the rest, while the 40-
#: character commit identifiers in the same document survived intact. 48 is therefore the measured
#: boundary rather than a guess -- above it, content was being dropped.
LONG_TOKEN_THRESHOLD = 48

#: Table geometry for the column floors of :func:`weight_table_columns`. Tables are set in
#: ``\footnotesize`` (8 pt) by the template; 4.4 pt is the width of one character of 8 pt Latin
#: Modern typewriter, the widest face a cell token is set in, and 14 pt is the column padding either
#: side plus a margin. The TMLR text block is 6.5 in.
TABLE_CHAR_PT = 4.4
TABLE_PADDING_PT = 14.0
LINE_WIDTH_PT = 6.5 * 72.27

#: The upstream project's name, in every spelling the manuscript uses (``ERRE-Sandbox``,
#: ``erre_sandbox``, ``ERRE_SANDBOX``). The same pattern ``make_anonymous_bundle.py`` counts as an
#: accepted exposure; in the anonymous PDF it is withheld instead, and ``check_pdf_identity.py``
#: fails the anonymous build if any occurrence reaches the page.
UPSTREAM_NAME = re.compile(r"erre[_-]?sandbox", re.IGNORECASE)
#: Visibly a placeholder, so that a path such as ``analysis/apparatus/UPSTREAM/...`` is not mistaken
#: for one the supplement contains; the bundle's ANONYMISED.md names the substitution.
UPSTREAM_PLACEHOLDER = "UPSTREAM"

#: A git commit identifier set as code, abbreviated (7 to 39 characters) or full (40), in either
#: case. A public commit can be searched for and leads to its repository, so the anonymous PDF
#: withholds each one (user ruling of 2026-09-26, ``.steering`` DA-C-15); the supplement keeps them,
#: because the frozen and sealed files that bind the claims carry them. It must contain a letter and
#: a digit, which is what keeps a number such as ``20260708`` out of it. ``COMMIT_ON_PAGE`` in
#: ``check_pdf_identity.py`` is the independent check on the page.
COMMIT_SPAN = re.compile(
    r"`((?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*[0-9])[0-9a-fA-F]{7,40})`"
)
COMMIT_PLACEHOLDER = "[commit withheld for review]"

#: The repository's git tags, which a search also resolves to the repository (TASK-POST review).
#: Listed by hand: a shallow CI checkout carries no tags to read them from, so
#: ``check_pdf_identity.py`` holds the same list and fails if any reaches the page.
TAG_NAMES: tuple[str, ...] = ("autopsy-b3-declared", "stage1-submitted")
TAG_PLACEHOLDER = "[tag withheld for review]"

#: Sentences of the manuscript that the anonymous build rewrites, each matched exactly and required
#: to occur once. The first names the author's own prior preprint by its subtitle, which a search
#: resolves as surely as its title (TASK-POST review); the second names the venue this work was
#: submitted to before (user ruling of 2026-09-26, DA-C-16). The named build carries both as written.
ANONYMOUS_REWRITES: tuple[tuple[str, str], ...] = (
    (
        "The determinism and byte-exact cross-platform replay properties of the upstream apparatus\n",
        "The determinism properties of the upstream apparatus\n",
    ),
    (
        "The tag `stage1-submitted` in this repository marks the state submitted to PCI Registered "
        "Reports\nin September 2026.",
        "A tag in this repository marks the state of an earlier submission of this work.",
    ),
)

#: The author's own prior work in the reference list. Named by identifier, not by author, because
#: the de-identified manuscript this script runs on in the anonymous build has already had the
#: name replaced.
SELF_CITATIONS: frozenset[int] = frozenset({40})
WITHHELD_TITLE = "Title withheld for anonymous review"

CITATIONS_FIXTURE = Path("manuscript") / "tmlr" / "citations.tsv"
TMLR_DIR = Path("manuscript") / "tmlr"
TMLR_FILES: tuple[str, ...] = ("tmlr.sty", "tmlr.bst", "fancyhdr.sty", "template.tex")


def _die(message: str) -> None:
    print(f"[pdf-source] {message}", file=sys.stderr)
    raise SystemExit(1)


def verify_vendored(repo_root: Path) -> int:
    """Require the vendored TMLR files to be the bytes ``VENDORED.json`` records.

    The style is official only while it is unmodified, and nothing else in the build would notice a
    local edit to ``tmlr.sty``: it would typeset, and the page would look like the venue's.
    """
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415

    record = json.loads(
        (repo_root / TMLR_DIR / "VENDORED.json").read_text(encoding="utf-8")
    )
    for name, digest in record["sha256"].items():
        actual = hashlib.sha256((repo_root / TMLR_DIR / name).read_bytes()).hexdigest()
        if actual != digest:
            _die(
                f"{TMLR_DIR / name} is not the vendored file VENDORED.json records ({actual[:12]})"
            )
    return len(record["sha256"])


# --------------------------------------------------------------------------------------------------
# References


@dataclass(frozen=True)
class Reference:
    number: int
    authors: tuple[str, ...]  # surnames, in order
    et_al: bool
    author_field: str  # BibTeX author field
    title: str
    venue: str
    year: str
    note: str  # doi / arXiv identifier, as printed
    remark: str  # the parenthetical remark some entries close with, kept verbatim


_REF_START = re.compile(r"^\[(\d+)\] ")
_AUTHOR_PAIR = re.compile(r"^(.+?), ((?:[A-Z][a-z]?\.(?:[- ]?[A-Za-z]{1,2}\.)*))$")


def _split_authors(text: str) -> tuple[tuple[str, ...], bool, str]:
    """Split ``Last, I., Last, I. and Last, I.`` into surnames and a BibTeX author field.

    Initials are kept as initials: the bibliography holds no more of a name than the central
    bibliography does, and expanding one would be invention.
    """
    et_al = text.endswith(" et al.")
    if et_al:
        text = text[: -len(" et al.")]
    text = text.replace(" and ", ", ")
    parts = [part.strip() for part in text.split(", ")]
    if len(parts) % 2:
        _die(f"cannot pair surnames with initials in the author list {text!r}")
    surnames: list[str] = []
    fields: list[str] = []
    for surname, initials in zip(parts[0::2], parts[1::2], strict=True):
        if not _AUTHOR_PAIR.match(f"{surname}, {initials}"):
            _die(f"unexpected author form {surname!r}, {initials!r}")
        surnames.append(surname)
        fields.append(f"{{{surname}}}, {initials}")
    if et_al:
        fields.append("others")
    return tuple(surnames), et_al, " and ".join(fields)


def parse_references(text: str, *, anonymous: bool = False) -> tuple[Reference, ...]:
    """Read the References section of ``main.md`` into structured entries.

    Fails on any entry it cannot read completely, rather than emitting a bibliography that has
    quietly lost a field.
    """
    match = re.search(
        r"^## References\n(.*?)(?=^## |^<!-- TMLR:APPENDIX -->|\Z)", text, re.M | re.S
    )
    if not match:
        _die("main.md has no '## References' section")
    entries: list[list[str]] = []
    for line in match.group(1).splitlines():
        if _REF_START.match(line):
            entries.append([line])
        elif entries and line.strip():
            entries[-1].append(line)
        elif entries:
            entries.append([])
    references: list[Reference] = []
    for lines in (e for e in entries if e):
        entry = " ".join(part.strip() for part in lines)
        if not _REF_START.match(entry):
            continue
        # The period after the author list is optional: the de-identified manuscript the anonymous
        # build runs on writes the author's own entry as "Author, Anonymous" with none.
        m = re.match(r"^\[(\d+)\] (.+?)\.? \*(.+?)\*\s*(.*)$", entry)
        if not m:
            _die(f"cannot parse reference entry: {entry[:80]!r}")
        number, author_text, title, rest = (
            int(m.group(1)),
            m.group(2),
            m.group(3),
            m.group(4),
        )
        if anonymous and number in SELF_CITATIONS:
            # Replaced wholesale by render_bib; its author list is the redaction placeholder and
            # is not a list of surnames with initials.
            surnames, et_al, author_field = ("Anonymous",), False, "Anonymous"
        else:
            if not author_text.endswith("."):
                author_text += "."
            surnames, et_al, author_field = _split_authors(author_text)
        note = ""
        note_match = re.search(
            r"\b(doi:\S+?|arXiv:\d{4}\.\d{4,5})(?=[,.]?\s|[,.]?$)", rest
        )
        if note_match:
            note = note_match.group(1)
        venue = rest
        if note.startswith("doi:"):
            venue = venue.replace(note, "")
        remark = ""
        remark_match = re.search(r"\s*\((.*)\)\s*$", venue)
        if remark_match:
            remark = remark_match.group(1).strip()
            venue = venue[: remark_match.start()].strip()
        years = re.findall(r"\b(?:19|20)\d{2}\b", venue)
        if not years:
            _die(f"reference [{number}] carries no year")
        year = years[-1]
        venue = re.sub(r",?\s*" + year + r"\.?\s*$", "", venue).strip().rstrip(",.")
        if note.startswith("arXiv:") and venue == note:
            note = ""  # the venue already is the identifier
        references.append(
            Reference(
                number,
                surnames,
                et_al,
                author_field,
                title.rstrip("."),
                venue,
                year,
                note,
                remark,
            )
        )
    numbers = [r.number for r in references]
    if len(numbers) != len(set(numbers)):
        _die(f"duplicate reference identifiers: {sorted(numbers)}")
    if not references:
        _die("the References section holds no entries")
    return tuple(references)


def _bib_escape(text: str) -> str:
    return text.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")


def render_bib(references: tuple[Reference, ...], *, anonymous: bool) -> str:
    out: list[str] = []
    for ref in references:
        author, title, venue, note = ref.author_field, ref.title, ref.venue, ref.note
        remark = ref.remark
        if anonymous and ref.number in SELF_CITATIONS:
            author, title, venue, note, remark = (
                "Anonymous",
                WITHHELD_TITLE,
                "Preprint",
                "",
                "",
            )
        fields = [
            f"  author = {{{author}}}",
            f"  title = {{{{{_bib_escape(title)}}}}}",
            f"  howpublished = {{{_bib_escape(venue)}}}",
            f"  year = {{{ref.year}}}",
        ]
        parts = [f"\\url{{{note}}}"] if note else []
        if remark:
            parts.append(f"({_bib_escape(remark)})")
        if parts:
            fields.append(f"  note = {{{' '.join(parts)}}}")
        out.append(f"@misc{{cds{ref.number},\n" + ",\n".join(fields) + "\n}\n")
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------
# Citations


def _textual_forms(ref: Reference) -> tuple[str, ...]:
    """The ways the prose names a reference's authors before its marker."""
    names = ref.authors
    forms = [f"{names[0]} and colleagues", f"{names[0]} et al."]
    if len(names) == 1 and not ref.et_al:
        forms.append(names[0])
    elif not ref.et_al:
        forms.append(", ".join(names[:-1]) + " and " + names[-1])
    return tuple(forms)


_CITE = re.compile(r"\[(\d+(?:, \d+)*)\]")


def convert_citations(
    body: str, references: tuple[Reference, ...]
) -> tuple[str, list[tuple[str, str, str]]]:
    """Rewrite ``[n]`` markers as natbib citations, outside code spans and fenced blocks.

    Returns the body and one ``(context, identifiers, mode)`` row per occurrence, which is compared
    against the committed fixture.
    """
    by_number = {r.number: r for r in references}
    shielded = _shielded_spans(body)
    rows: list[tuple[str, str, str]] = []

    def replace(match: re.Match[str]) -> str:
        if any(start <= match.start() < end for start, end in shielded):
            return match.group(0)
        numbers = [int(n) for n in match.group(1).split(", ")]
        unknown = [n for n in numbers if n not in by_number]
        if unknown:
            _die(
                f"citation [{match.group(1)}] names no entry of the References section: {unknown}"
            )
        keys = ",".join(f"cds{n}" for n in numbers)
        # The prose that names the authors may run across a line break, so the text before the
        # marker is compared with its whitespace collapsed.
        before = (
            " ".join(body[max(0, match.start() - 120) : match.start()].split()) + " "
        )
        mode = "citep"
        if len(numbers) == 1:
            for form in _textual_forms(by_number[numbers[0]]):
                if before.endswith(" " + form + " ") or before.endswith(
                    "*" + form + " "
                ):
                    mode = "citeyearpar"
                    break
        context = " ".join(before.split()[-4:])
        rows.append((context, match.group(1), mode))
        return f"\\{mode}{{{keys}}}"

    return _CITE.sub(replace, body), rows


def _shielded_spans(body: str) -> list[tuple[int, int]]:
    """Character ranges inside code spans or fenced blocks, where ``[n]`` is not a citation."""
    spans: list[tuple[int, int]] = []
    offset = 0
    fence_start: int | None = None
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if fence_start is None:
                fence_start = offset
            else:
                spans.append((fence_start, offset + len(line)))
                fence_start = None
        elif fence_start is None:
            for match in re.finditer(r"`[^`\n]*`", line):
                spans.append((offset + match.start(), offset + match.end()))
        offset += len(line)
    if fence_start is not None:
        _die("a fenced code block is never closed")
    return spans


def check_citation_fixture(
    repo_root: Path, rows: list[tuple[str, str, str]], write: bool
) -> None:
    path = repo_root / CITATIONS_FIXTURE
    header = "# context (last four words before the marker)\tidentifiers\tmode\n"
    rendered = header + "".join(
        f"{context}\t{ids}\t{mode}\n" for context, ids, mode in rows
    )
    if write:
        path.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"[pdf-source] wrote {CITATIONS_FIXTURE} ({len(rows)} citations)")
        return
    if not path.is_file():
        _die(
            f"{CITATIONS_FIXTURE} is missing; run with --write-citations and review it"
        )
    if path.read_text(encoding="utf-8") != rendered:
        _die(
            f"the citations of main.md no longer classify as {CITATIONS_FIXTURE} records. "
            "Rerun with --write-citations and review the diff: every change in how a citation "
            "is set must be seen"
        )


# --------------------------------------------------------------------------------------------------
# Body transformations


def split_title(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if not line.startswith("# "):
            _die(
                f"the first non-empty line of main.md is not a level-one heading: {line[:60]!r}"
            )
        return line[2:].strip(), "\n".join(lines[index + 1 :])
    _die("main.md is empty")
    raise AssertionError("unreachable")


def _one_block(body: str, begin: str, end: str, what: str) -> tuple[str, str, str]:
    if body.count(begin) != 1 or body.count(end) != 1:
        _die(f"main.md must carry exactly one {what} block ({begin} ... {end})")
    head, rest = body.split(begin)
    inner, tail = rest.split(end)
    return head, inner, tail


def drop_block(body: str) -> str:
    head, _, tail = _one_block(body, DROP_BEGIN, DROP_END, "TMLR:DROP")
    if head.strip():
        _die("the TMLR:DROP block must be the first thing after the title")
    return tail


def take_abstract(body: str) -> str:
    """Remove the ``## Abstract`` section (up to its closing rule) from the body."""
    match = re.search(r"^## Abstract\n.*?^---$\n", body, re.M | re.S)
    if not match:
        _die("main.md has no '## Abstract' section closed by a horizontal rule")
    return body[: match.start()] + body[match.end() :]


def move_footnote(body: str) -> str:
    """Move the footnote block to the end of the first paragraph of the first section."""
    head, inner, tail = _one_block(body, FOOTNOTE_BEGIN, FOOTNOTE_END, "TMLR:FOOTNOTE")
    note = " ".join(inner.split())
    if not note:
        _die("the TMLR:FOOTNOTE block is empty")
    body = head + tail
    first = re.search(r"^## .*\n\n((?:.+\n)+)", body, re.M)
    if not first:
        _die("no paragraph follows the first section heading to carry the footnote")
    end = first.end(1) - 1
    return body[:end] + f"^[{note}]" + body[end:]


def replace_figures(body: str) -> tuple[str, list[str]]:
    out: list[str] = []
    names: list[str] = []
    inside: str | None = None
    for line in body.splitlines():
        match = FIGURE_BEGIN.match(line.strip())
        if match:
            if inside:
                _die(f"figure {match.group(1)} opens inside figure {inside}")
            inside = match.group(1)
            names.append(inside)
            out.extend((f"\\TMLRFigureBegin{{fig-{inside}}}", ""))
        elif line.strip() == FIGURE_END:
            if not inside:
                _die("a figure closes that was never opened")
            out.extend(("", "\\TMLRFigureEnd"))
            inside = None
        else:
            out.append(line)
    if inside:
        _die(f"figure {inside} is never closed")
    if len(names) != len(set(names)):
        _die(f"a figure is placed twice: {names}")
    return "\n".join(out), names


def replace_references(body: str) -> str:
    """Set the bibliography where the References section stands, and mark the appendices."""
    if body.count(APPENDIX) > 1:
        _die("main.md carries more than one TMLR:APPENDIX marker")
    match = re.search(
        r"^## References\n.*?(?=^<!-- TMLR:APPENDIX -->|\Z)", body, re.M | re.S
    )
    if not match:
        _die("main.md has no '## References' section")
    head, tail = body[: match.start()], body[match.end() :]
    if APPENDIX in head:
        _die("the TMLR:APPENDIX marker stands before the References section")
    if tail.strip() and not tail.startswith(APPENDIX):
        _die("the TMLR:APPENDIX marker must follow the References section directly")
    tail = tail.replace(APPENDIX, "\\TMLRAppendix\n", 1)
    return head + "\\TMLRBibliography\n\n" + tail


def weight_table_columns(body: str) -> tuple[str, int]:
    """Give each pipe table's columns widths in proportion to what they hold.

    pandoc sizes the columns of a wide pipe table by the dash counts of its separator row, and every
    table in ``main.md`` writes that row as ``|---|---|``, so each column would get the same width
    and a column of one-word labels would take as much of the page as a column of sentences. The
    separator row is rewritten with dash counts proportional to the longest cell of each column
    (capped, so that one long cell does not starve the rest). Only the separator row changes; no cell
    does.
    """
    lines = body.splitlines()
    count = 0
    for index, line in enumerate(lines):
        if not re.fullmatch(r"\|(?:\s*:?-{3,}:?\s*\|)+", line.strip()) or index == 0:
            continue
        start = index - 1
        end = index + 1
        while end < len(lines) and lines[end].lstrip().startswith("|"):
            end += 1
        rows = [lines[start], *lines[index + 1 : end]]
        cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
        columns = len(cells[0])
        if any(len(row) != columns for row in cells):
            continue  # a pipe inside a cell; leave the table as pandoc would see it
        longest = [max(min(len(row[k]), 90) for row in cells) for k in range(columns)]
        # A token with no space in it cannot wrap, so a column must be wide enough for its longest
        # one: the first TMLR build set a 19-character value in a column narrower than it, and the
        # value ran on into the next column's text. The floor is absolute, not relative: a column's
        # share of the line must hold its longest token at the table's size (TABLE_CHAR_PT per
        # character, plus the padding either side), and the other columns give way.
        unbreakable = [
            max(
                len(token.strip("`*"))
                for row in cells
                for token in (row[k].split() or [""])
            )
            for k in range(columns)
        ]
        floors = [
            (u * TABLE_CHAR_PT + TABLE_PADDING_PT) / LINE_WIDTH_PT for u in unbreakable
        ]
        if sum(floors) > 1:
            continue  # cannot be satisfied; leave pandoc's own widths and let the read-back judge
        share = [max(6, n) for n in longest]
        fractions = [s / sum(share) for s in share]
        for _ in range(columns):  # raise the columns below their floor, shrink the rest
            short = [k for k in range(columns) if fractions[k] < floors[k]]
            if not short:
                break
            fixed = {k: floors[k] for k in short}
            rest = [k for k in range(columns) if k not in fixed]
            room = 1 - sum(fixed.values())
            total = sum(fractions[k] for k in rest)
            fractions = [
                fixed[k] if k in fixed else fractions[k] * room / total
                for k in range(columns)
            ]
        weights = [max(3, round(f * 300)) for f in fractions]
        lines[index] = "|" + "|".join("-" * w for w in weights) + "|"
        count += 1
    return "\n".join(lines), count


def drop_rules(body: str) -> str:
    return "\n".join(line for line in body.splitlines() if line.strip() != "---")


def split_long_tokens(body: str) -> tuple[str, int]:
    """Let over-long typewriter tokens break, so they cannot run off the page.

    Only code spans with no whitespace in them are touched. The characters are unchanged --
    ``\\seqsplit`` only adds permission to break between them.
    """
    pattern = re.compile(r"`([^\s`]{" + str(LONG_TOKEN_THRESHOLD) + r",})`")
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        token = match.group(1).replace("_", r"\_")
        return r"\texttt{\seqsplit{" + token + "}}"

    return pattern.sub(replace, body), count


def check_no_raw_environment(body: str) -> None:
    """Refuse to emit a body containing a literal LaTeX environment.

    pandoc treats ``\\begin{X}`` ... ``\\end{X}`` as a single raw block and passes everything
    between them through without parsing it, so a markdown table caught inside one arrives at LaTeX
    unconverted. Any environment must be reached through a macro declared in the template instead
    (``\\TMLRFigureBegin`` is one).
    """
    offenders = [
        line
        for line in body.splitlines()
        if line.lstrip().startswith((r"\begin{", r"\end{"))
    ]
    if offenders:
        _die(
            "the generated body contains a literal LaTeX environment, which would make pandoc "
            "skip parsing everything inside it: " + "; ".join(offenders[:3])
        )


def _yaml_block(text: str) -> str:
    return "\n".join("  " + line if line else "" for line in text.splitlines())


def build(
    repo_root: Path, *, anonymous: bool, write_citations: bool
) -> tuple[str, str, list[str]]:
    manuscript = repo_root / "manuscript" / "main.md"
    text = manuscript.read_text(encoding="utf-8")
    abstract = _extract_main_abstract(manuscript)
    if not abstract:
        _die("the abstract could not be extracted from main.md")
    references = parse_references(text, anonymous=anonymous)

    title, body = split_title(text)
    body = drop_block(body)
    body = take_abstract(body)
    body = move_footnote(body)
    body, figures = replace_figures(body)
    body = replace_references(body)
    body = drop_rules(body)
    body, table_count = weight_table_columns(body)
    body, rows = convert_citations(body, references)
    abstract, abstract_rows = convert_citations(abstract, references)
    rows = abstract_rows + rows
    check_citation_fixture(repo_root, rows, write_citations)
    cited = {int(n) for _, ids, _ in rows for n in ids.split(", ")}
    uncited = sorted({r.number for r in references} - cited)
    if uncited:
        _die(f"the References section lists entries nothing cites: {uncited}")
    # Before the long tokens are made breakable, not after: that step escapes the underscore of a
    # path such as `analysis/apparatus/erre_sandbox/...`, and the escaped form no longer matches the
    # name. The first anonymous build put it on the page exactly that way.
    if anonymous:
        for old, new in ANONYMOUS_REWRITES:
            if body.count(old) != 1:
                _die(
                    f"an anonymous rewrite no longer matches main.md exactly once: {old[:60]!r}"
                )
            body = body.replace(old, new)
        title = UPSTREAM_NAME.sub(UPSTREAM_PLACEHOLDER, title)
        abstract = UPSTREAM_NAME.sub(UPSTREAM_PLACEHOLDER, abstract)
        body = UPSTREAM_NAME.sub(UPSTREAM_PLACEHOLDER, body)
        body = COMMIT_SPAN.sub(COMMIT_PLACEHOLDER, body)
        for tag in TAG_NAMES:
            body = body.replace(f"`{tag}`", TAG_PLACEHOLDER)
    # A citation marker the conversion did not recognise -- a range, a list without the space the
    # pattern expects -- would reach the page as a bare "[41–43]". Anything of that shape left
    # outside code is a failure, not a style variant.
    residue = [
        m.group(0)
        for m in re.finditer(r"\[\d+(?:\s*[,–-]\s*\d+)*\]", body)
        if not any(s <= m.start() < e for s, e in _shielded_spans(body))
    ]
    if residue:
        _die(f"citation-shaped markers survived conversion: {residue[:5]}")
    body, split_count = split_long_tokens(body)
    check_no_raw_environment(body)

    front = ["---", f'title: "{title}"', "abstract: |", _yaml_block(abstract), "---"]
    source = "\n".join(front) + "\n\n" + body.lstrip("\n") + "\n"
    print(
        f"[pdf-source] {len(references)} references, {len(rows)} citations, "
        f"{len(figures)} figure(s), {table_count} table(s) weighted, "
        f"{split_count} over-long token(s) made breakable"
    )
    return source, render_bib(references, anonymous=anonymous), figures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--out-dir", type=Path, required=True, help="directory to build in"
    )
    parser.add_argument(
        "--anonymous", action="store_true", help="build the anonymous submission"
    )
    parser.add_argument(
        "--write-citations",
        action="store_true",
        help=f"rewrite {CITATIONS_FIXTURE} from the manuscript instead of comparing against it",
    )
    args = parser.parse_args(argv)

    vendored = verify_vendored(args.repo_root)
    print(f"[pdf-source] the {vendored} vendored TMLR files match VENDORED.json")
    source, bib, figures = build(
        args.repo_root, anonymous=args.anonymous, write_citations=args.write_citations
    )
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "paper-source.md").write_text(source, encoding="utf-8", newline="\n")
    (out / "refs.bib").write_text(bib, encoding="utf-8", newline="\n")
    # The style option and the author block are template *variables*, not metadata: pandoc parses
    # metadata as markdown and would escape the backslashes of the TMLR author macros, or drop a raw
    # block, leaving the title block empty (which is what the first build did). Variables pass
    # through as they are. The anonymous build sets neither, and tmlr.sty prints its own line.
    variables = ["variables:"]
    if not args.anonymous:
        variables += ["  tmlr-option: preprint", f"  tmlr-author: '{AUTHOR}'"]
    else:
        variables += ["  tmlr-option: ''"]
    (out / "pandoc-vars.yaml").write_text(
        "\n".join(variables) + "\n", encoding="utf-8", newline="\n"
    )
    for name in TMLR_FILES:
        shutil.copyfile(args.repo_root / TMLR_DIR / name, out / name)
    (out / "figures.txt").write_text(
        "".join(f"fig-{name}\n" for name in figures), encoding="utf-8", newline="\n"
    )
    kind = "anonymous" if args.anonymous else "named"
    print(f"[pdf-source] wrote {out}/paper-source.md and refs.bib ({kind})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
