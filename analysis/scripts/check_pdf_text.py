#!/usr/bin/env python3
"""Check the text read back out of the submission PDF.

**A PDF that builds is not a PDF that carries the manuscript.** Two failure modes make that gap
real rather than theoretical, and both are silent:

* XeTeX does not stop on a character its font lacks. It emits a warning and sets *nothing*, so a
  symbol such as the logical `and` joining the branch conditions of section E can vanish from the
  page while the build reports success.
* A ``longtable`` row cannot be broken across a page. If a table's columns are set too narrow the
  row overflows instead of reflowing, and content can be pushed off the page. The six-column study
  design table used to be the acute case and was rotated onto a landscape page; it has been removed
  from the manuscript, and the widest table left is three columns. The column-header check below is
  retained and retargeted at that table rather than deleted, because the failure mode is a property
  of ``longtable``, not of the table that first exposed it.

So the PDF is read back with ``pdftotext`` and checked against what it is supposed to contain. The
numeric half of that is **not hardcoded here**: it imports the same ``REQUIRED`` table that
``check_manuscript_numbers.py`` uses, so the quantities the PDF must show are read from the frozen
inputs by key. One SSOT, checked in two places.

Whitespace is normalised before matching, because TeX decides its own line breaks and a quantity
broken across two lines is still present.

**What this check deliberately does not do, and why nobody should add it.** It does not look for
contiguous sentences from inside table cells. ``pdftotext`` emits a multi-column table one *line* at
a time across all columns, so the prose of two adjacent cells arrives interleaved: a sentence that
reads continuously on the page is split by fragments of its neighbour in the extracted text.
Searching for a phrase from a cell therefore reports it missing even when the page carries it
perfectly, and three such false alarms were raised against this document before the cause was
understood. Column *headers* are short enough to survive on one line, which is why they are checked
and cell bodies are not. To verify cell contents, compare the set of words on the page, not their
order.

``pdftotext`` also joins a word that TeX hyphenated at a line break, dropping the hyphen: this
document renders ``sample-complexity`` as ``samplecomplexity`` in the extracted text while its other
sixty-three hyphenated words are unaffected. That is an artefact of reading the PDF back, not of the
PDF.

Usage:  python analysis/scripts/check_pdf_text.py extracted.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402
from check_manuscript_numbers import REQUIRED, literal_of  # noqa: E402
from make_figures import expected_rows  # noqa: E402

#: Headings and title-block fields that must survive into the PDF. Each is load-bearing for the
#: submission rather than decorative: the title and the author block come from a transformation
#: this repository performs (``make_pdf_source.py``) and would be absent if it silently failed, the
#: disclosure and ethics sections are what a venue checks for, and the two sections named after
#: them are where the pre-registration itself lives.
#:
#: These are compared against the extracted text, so they must be the headings the manuscript
#: actually carries. An earlier version of this tuple still named the previous title and two
#: sections that had been removed, which would have failed the build for the right reason but the
#: wrong cause; keeping it in step with ``main.md`` is part of editing ``main.md``.
REQUIRED_PHRASES: tuple[str, ...] = (
    "Three gates, three proxies",
    "Decision rules",
    "Eligibility: what is known at seal time, and what is not",
    "What the seal covers, and what breaks it",
    "AI usage disclosure",
    "Ethics, funding and competing interests",
    "Data, code and reproducibility",
)

#: The title block differs between the two builds, and each must carry its own. The named build
#: (``tmlr.sty`` with ``preprint``) sets the author block of ``make_pdf_source.py``; the anonymous
#: build (no option) must set what the official style sets instead, and ``check_pdf_identity.py``
#: then checks that nothing else identifies the author.
NAMED_PHRASES: tuple[str, ...] = ("Mikoto Miura", "0009-0000-4196-0508")
ANONYMOUS_PHRASES: tuple[str, ...] = ("Anonymous authors", "Paper under double-blind review")

#: The first page must carry the AI-use disclosure as a footnote (the TMLR checklist item); its
#: opening words are what ``make_pdf_source.py`` moves there from the manuscript.
FIRST_PAGE_PHRASES: tuple[str, ...] = ("Use of AI assistance.",)

#: The page budget. The main text is meant to run to about twelve pages, and the bibliography
#: stands between it and the appendices, so the page on which "References" is set bounds the main
#: text. It must also come before the first appendix, or the bound would measure nothing.
REFERENCES_LAST_PAGE = 13
FIRST_APPENDIX_HEADING = "A. The apparatus and the channel"


def page_of(pages: list[str], pattern: str) -> int | None:
    """1-based number of the first page with a line matching ``pattern``."""
    compiled = re.compile(pattern, re.M)
    for number, page in enumerate(pages, start=1):
        if compiled.search(page):
            return number
    return None


def figure_numbers(repo_root: Path) -> dict[str, str]:
    """Figure name -> its caption label ("Figure 2."), read from the markers in main.md."""
    text = (repo_root / "manuscript" / "main.md").read_text(encoding="utf-8")
    return dict(re.findall(r"<!-- TMLR:FIGURE ([a-z0-9-]+) -->\n\*\*(Figure \d+\.)\*\*", text))


def row_on_page(page: str, label: str, values: list[str]) -> bool:
    """Whether the page's text, in content-stream order, carries ``label`` then ``values``.

    ``make_figures.py`` emits each row's text nodes consecutively, so extraction in stream order
    (``pdftotext -raw``) reads a row as one run. Layout-based extraction does not: it lays out a
    column of labels and a column of numbers as separate blocks, and xpdf and poppler do so
    differently, so a row check on layout text measured the extractor rather than the page.
    """
    pattern = re.escape(label) + "".join(r"\s+" + re.escape(v) for v in values) + r"(?!\S)"
    return re.search(pattern, " ".join(page.split())) is not None


def check_figures(repo_root: Path, pages: list[str]) -> list[str]:
    """Each figure's numbers must stand, row by row, on the page that carries its caption."""
    problems: list[str] = []
    numbers = figure_numbers(repo_root)
    expected = expected_rows(repo_root)
    if sorted(numbers) != sorted(expected):
        return [f"figures placed in main.md {sorted(numbers)} are not those drawn {sorted(expected)}"]
    order = sorted(numbers.values(), key=lambda label: int(label.split()[1][:-1]))
    if order != [f"Figure {i}." for i in range(1, len(order) + 1)]:
        problems.append(f"the figure captions are not numbered 1, 2, 3...: {order}")
    for name, rows in expected.items():
        page_number = page_of(pages, r"^\s*" + re.escape(numbers[name]) + " ")
        if page_number is None:
            problems.append(f"the caption {numbers[name]!r} ({name}) is not in the PDF")
            continue
        page = pages[page_number - 1]
        missing = [label for label, values in rows if not row_on_page(page, label, values)]
        if missing:
            problems.append(
                f"{numbers[name]} ({name}): {len(missing)} of {len(rows)} rows are not on page "
                f"{page_number} as drawn, e.g. {missing[:3]}"
            )
    return problems

#: Every column header of the widest table in the manuscript -- the eligibility audit of section F.
#: Losing the right-hand columns of a wide table is the specific way ``longtable`` goes wrong, and
#: it would not be visible from a page count. This table is the one to watch because its two
#: right-hand columns are the ones that carry the audit: the third says what was unknown at seal
#: time and the fourth says what is reported after the run, and a page that dropped them would
#: still look like a complete table.
WIDEST_TABLE_COLUMNS: tuple[str, ...] = (
    "Planned analysis",
    "Role",
    "Realised outcome known at seal time?",
    "Reported after the run",
)

#: The column headers of the analysis map of section 1.3, the widest table the revision added. Its
#: right-hand columns say when each layer was fixed and what it licenses, which is the part a page
#: that dropped them would lose without looking incomplete.
ANALYSIS_MAP_COLUMNS: tuple[str, ...] = (
    "Layer",
    "Computes, on which data",
    "Fixed when",
    "Licenses",
)

#: Characters the body depends on that a text font may not carry. Each is load-bearing: the
#: logical connectives join the branch conditions of section E, the arrow gives the evaluation
#: order, lambda names the channel, and the accented letters are authors' names in the references.
#: Dropping any of them silently changes what the page says.
REQUIRED_GLYPHS: tuple[tuple[str, str], ...] = (
    ("§", "section sign"),
    ("→", "rightwards arrow"),
    ("λ", "greek small letter lamda"),
    ("α", "greek small letter alpha"),
    ("∧", "logical and"),
    ("∨", "logical or"),
    ("≥", "greater-than or equal to"),
    ("≤", "less-than or equal to"),
    ("≈", "almost equal to"),
    ("ć", "latin small letter c with acute"),
    ("š", "latin small letter s with caron"),
    ("ö", "latin small letter o with diaeresis"),
)


def normalise(text: str) -> str:
    """Collapse whitespace so that a quantity broken across lines still matches."""
    return " ".join(text.split())


def despace(text: str) -> str:
    """Remove whitespace entirely.

    A token too long to fit its column is given permission to break between characters, so a
    64-character digest can arrive from ``pdftotext`` with a newline in the middle of it. Collapsing
    runs of whitespace to a single space is not enough to reassemble that; the space has to go. This
    is used only as a fallback for quantities, where the alternative is a false failure on a value
    that is present and correct on the page.
    """
    return "".join(text.split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted", type=Path, help="text extracted from the PDF by pdftotext")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        required=True,
        help="text extracted by pdftotext -raw, in content-stream order (the figure rows)",
    )
    parser.add_argument(
        "--anonymous", action="store_true", help="the PDF is the anonymous submission build"
    )
    args = parser.parse_args(argv)

    if not args.extracted.is_file():
        print(f"[pdf-text] FAIL: no extracted text at {args.extracted}", file=sys.stderr)
        return 1

    raw = args.extracted.read_text(encoding="utf-8", errors="replace")
    flat = normalise(raw)
    tight = despace(raw)

    if len(flat) < 20_000:
        print(
            f"[pdf-text] FAIL: the extracted text is {len(flat)} characters, which is far short of "
            "a manuscript of this length. The PDF is probably truncated or largely unset.",
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []

    title_phrases = ANONYMOUS_PHRASES if args.anonymous else NAMED_PHRASES
    for phrase in (*REQUIRED_PHRASES, *title_phrases):
        if normalise(phrase) not in flat:
            problems.append(f"a required phrase is absent: {phrase!r}")

    pages = raw.split("\f")
    for phrase in FIRST_PAGE_PHRASES:
        if normalise(phrase) not in normalise(pages[0]):
            problems.append(f"the first page does not carry {phrase!r} (the AI-use footnote)")
    references = page_of(pages, r"^References$")
    appendix = page_of(pages, r"^" + re.escape(FIRST_APPENDIX_HEADING))
    if references is None or appendix is None:
        problems.append("the References heading or the first appendix is not in the PDF")
    else:
        if references > REFERENCES_LAST_PAGE:
            problems.append(
                f"References begin on page {references}; the main text is meant to end by page "
                f"{REFERENCES_LAST_PAGE}"
            )
        if appendix < references:
            problems.append("the first appendix comes before the References")

    if not args.raw.is_file():
        problems.append(f"no stream-order text at {args.raw}")
    else:
        raw_pages = args.raw.read_text(encoding="utf-8", errors="replace").split("\f")
        problems += check_figures(args.repo_root, raw_pages)

    for column in WIDEST_TABLE_COLUMNS:
        if normalise(column) not in flat:
            problems.append(
                f"a column header of the section F table is absent: {column!r} "
                "(the table may have been set too wide and lost its right-hand columns)"
            )

    for column in ANALYSIS_MAP_COLUMNS:
        if normalise(column) not in flat:
            problems.append(
                f"a column header of the section 1.3 analysis map is absent: {column!r} "
                "(the table may have been set too wide and lost its right-hand columns)"
            )

    for glyph, name in REQUIRED_GLYPHS:
        if glyph not in raw:
            problems.append(
                f"the character {glyph!r} ({name}) does not appear in the PDF. "
                "XeTeX sets nothing for a character the font lacks and does not fail, "
                "so this is a missing glyph rather than an absent sentence."
            )

    # The quantities come from the frozen inputs by key, exactly as check_manuscript_numbers.py
    # reads them. A number that reaches the manuscript but not the page fails here.
    sources: dict[str, dict[str, Any]] = {}
    for label, filename, key_path, how in REQUIRED:
        if filename not in sources:
            sources[filename] = load_json(args.repo_root / "data" / "raw" / filename)
        value: Any = sources[filename]
        for key in key_path:
            value = value[key]
        literal = literal_of(value, how)
        # A long token may have been broken across lines to keep it on the page, so a quantity
        # missing from the whitespace-collapsed text is looked for again with whitespace removed.
        if literal not in flat and despace(literal) not in tight:
            problems.append(f"the quantity {label} = {literal} does not appear in the PDF")

    if problems:
        print("[pdf-text] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[pdf-text] OK: References begin on page {references} (at most {REFERENCES_LAST_PAGE}), "
        "the AI-use footnote is on the first page, every figure's numbers stand row by row on its "
        f"page, {len(REQUIRED_PHRASES) + len(title_phrases)} required phrases, "
        f"all {len(WIDEST_TABLE_COLUMNS)} column headers of the section F table and "
        f"{len(ANALYSIS_MAP_COLUMNS)} of the section 1.3 analysis map, "
        f"{len(REQUIRED_GLYPHS)} glyphs at risk of silent loss, and "
        f"{len(REQUIRED)} quantities read from the frozen inputs are present in the PDF "
        f"({len(flat)} characters of text)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
