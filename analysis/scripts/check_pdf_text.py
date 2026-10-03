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

Usage:  python analysis/scripts/check_pdf_text.py extracted.txt --raw raw.txt --aux paper.aux
        python analysis/scripts/check_pdf_text.py --self-test
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
from make_pdf_source import manuscript_headings  # noqa: E402

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

#: The page budget. A TMLR regular submission has at most 12 pages of "main content, before
#: references" (TMLR FAQ, https://jmlr.org/tmlr/faq.html; the 2025 annual report calls 12 pages
#: "the maximum number of pages for TMLR regular submissions"). The bibliography stands between the
#: main text and the appendices, so the page on which "References" is set bounds the main text. The
#: bound errs on the safe side: a main text of exactly twelve pages that pushes the heading to the
#: top of page 13 fails here. The heading must also come before the first appendix, or the bound
#: would measure nothing.
REFERENCES_LAST_PAGE = 12
#: The first appendix's title. LaTeX numbers the appendices (TEMPLATE-DIFF.md), and pdftotext sets
#: the letter on a line of its own before the title, so the title line is what is matched; a letter
#: on the same line is allowed for an extractor that joins them.
FIRST_APPENDIX_TITLE = "The apparatus and the channel (completed preliminary study)"
#: The two headings the page budget is read from, as line patterns on the extracted page. A line
#: carrying anything besides the heading -- a trailing space included -- does not match, so a
#: heading that pdftotext set differently is reported missing rather than guessed at.
REFERENCES_PATTERN = r"^References$"
FIRST_APPENDIX_PATTERN = r"^(?:A\s+)?" + re.escape(FIRST_APPENDIX_TITLE) + "$"
#: How a figure caption begins on the page: LaTeX's "Figure 2:" (``\caption``, TEMPLATE-DIFF.md).
#: main.md writes the same caption as "**Figure 2.**", which make_pdf_source.py takes off.
CAPTION_ON_PAGE = "Figure {number}:"


def page_of(pages: list[str], pattern: str) -> int | None:
    """1-based number of the first page with a line matching ``pattern``."""
    compiled = re.compile(pattern, re.M)
    for number, page in enumerate(pages, start=1):
        if compiled.search(page):
            return number
    return None


def lines_matching(pages: list[str], pattern: str) -> list[tuple[int, int]]:
    """``(page, line)`` of every line matching ``pattern``, both 1-based, in reading order.

    Positions rather than pages, because two headings can share a page and only the line order
    tells which comes first. Lines are split on ``\\n`` alone: ``str.splitlines`` also splits on
    characters such as U+2028 that pdftotext can emit inside a line.
    """
    compiled = re.compile(pattern)
    return [
        (number, index)
        for number, page in enumerate(pages, start=1)
        for index, line in enumerate(page.split("\n"), start=1)
        if compiled.search(line)
    ]


def page_budget_problems(
    pages: list[str],
    last_page: int,
    first_appendix: str,
    figure_captions: list[str],
) -> list[str]:
    """What is wrong with where the main text ends, read from the extracted pages.

    ``first_appendix`` is the line pattern of the first appendix heading and ``figure_captions``
    the labels the main text's figure captions begin with (``"Figure 1."``). The checks:

    * the References heading and the first appendix heading are each on the page exactly once;
    * the References begin no later than ``last_page``;
    * the first appendix comes after the References, compared by line when they share a page;
    * every figure caption of the main text stands before the References. A figure is a float,
      and LaTeX may carry it past the bibliography, where it would be main-text content the page
      budget does not see.

    ``main`` and ``--self-test`` both call this one function, so the self-test exercises the check
    that runs on the PDF rather than a copy of it.
    """
    problems: list[str] = []
    references = lines_matching(pages, REFERENCES_PATTERN)
    appendix = lines_matching(pages, first_appendix)
    if not references:
        problems.append("the References heading is not in the PDF")
    elif len(references) > 1:
        problems.append(
            f"the References heading occurs {len(references)} times (page, line: {references}), "
            "so the page on which the references begin is ambiguous"
        )
    if not appendix:
        problems.append(f"the first appendix heading ({first_appendix!r}) is not in the PDF")
    elif len(appendix) > 1:
        problems.append(
            f"the first appendix heading occurs {len(appendix)} times (page, line: {appendix})"
        )
    if len(references) != 1:
        return problems
    start = references[0]
    if start[0] > last_page:
        problems.append(
            f"References begin on page {start[0]}; the main text is meant to end by page "
            f"{last_page}"
        )
    if len(appendix) == 1 and appendix[0] < start:
        problems.append(
            f"the first appendix comes before the References (page {appendix[0][0]} line "
            f"{appendix[0][1]}, against page {start[0]} line {start[1]})"
        )
    for label in figure_captions:
        found = lines_matching(pages, r"^\s*" + re.escape(label) + r"(?:\s|$)")
        if not found:
            problems.append(
                f"the caption {label!r} is not in the PDF, so its place relative to the "
                "References cannot be checked"
            )
        elif max(found) > start:
            problems.append(
                f"{label!r} is set on page {max(found)[0]}, after the References on page "
                f"{start[0]}: a float was carried past the bibliography"
            )
    return problems


def _pages(*placed: tuple[str, int, int]) -> list[str]:
    """Synthetic extracted pages: 20 pages of filler, with each ``(text, page, line)`` placed."""
    pages = [["body text"] * 6 for _ in range(20)]
    for text, page, line in placed:
        pages[page - 1][line - 1] = text
    return ["\n".join(lines) for lines in pages]


def page_budget_self_test() -> tuple[int, list[str]]:
    """Run :func:`page_budget_problems` on synthetic pages whose answer is known.

    Returns the number of cases run and what went wrong. Each case names the diagnostic it must
    produce, and a case is counted as caught only if exactly that one problem is returned: a case
    that fails for another reason, or for that reason and others besides, has not shown that the
    check sees what it is meant to see. The page numbers are placed relative to
    ``REFERENCES_LAST_PAGE``, so the cases test the budget this file enforces.
    """
    last = REFERENCES_LAST_PAGE
    one, two = CAPTION_ON_PAGE.format(number=1), CAPTION_ON_PAGE.format(number=2)
    captions = [one, two]
    app = FIRST_APPENDIX_TITLE
    figures = ((f"{one} A caption", 3, 2), (f"{two} Another caption", 5, 4))
    cases: tuple[tuple[str, list[str], str | None], ...] = (
        ("S1 References on the last page allowed, the first appendix after it",
         _pages(("References", last, 3), ("A", last + 2, 1), (app, last + 2, 3), *figures), None),
        ("S1b the appendix letter on the same line as its title",
         _pages(("References", last, 3), (f"A {app}", last + 2, 1), *figures), None),
        ("S2 References one page too late",
         _pages(("References", last + 1, 3), (app, last + 3, 1), *figures),
         f"References begin on page {last + 1}"),
        ("S3 the first appendix on an earlier page than the References",
         _pages(("References", last, 3), (app, last - 1, 1), *figures),
         "the first appendix comes before the References"),
        ("S4 no References heading",
         _pages((app, last + 2, 1), *figures), "the References heading is not in the PDF"),
        ("S5 the References line carries a trailing space",
         _pages(("References ", last, 3), (app, last + 2, 1), *figures),
         "the References heading is not in the PDF"),
        ("S6 the same page, the first appendix on an earlier line",
         _pages(("References", last, 5), (app, last, 2), *figures),
         "the first appendix comes before the References"),
        ("S7 no first appendix heading",
         _pages(("References", last, 3), *figures), "the first appendix heading"),
        ("S8 the References heading twice",
         _pages(("References", last - 3, 3), ("References", last, 3), (app, last + 2, 1), *figures),
         "the References heading occurs 2 times"),
        ("S9 a figure caption after the References",
         _pages(("References", last - 1, 3), (app, last + 2, 1), figures[0], (f"{two} Another caption", last, 1)),
         f"{two!r} is set on page"),
        ("S10 a figure caption missing",
         _pages(("References", last, 3), (app, last + 2, 1), figures[0]),
         f"the caption {two!r} is not in the PDF"),
        ("S11 a caption in main.md's form, not LaTeX's",
         _pages(("References", last, 3), (app, last + 2, 1), figures[0], ("Figure 2. Another caption", 5, 4)),
         f"the caption {two!r} is not in the PDF"),
    )  # fmt: skip
    problems: list[str] = []
    for name, pages, expected in cases:
        found = page_budget_problems(pages, last, FIRST_APPENDIX_PATTERN, captions)
        if expected is None:
            if found:
                problems.append(f"{name}: the control returned {found}")
        elif not found:
            problems.append(f"{name}: not caught (no problem returned)")
        elif len(found) != 1 or expected not in found[0]:
            problems.append(f"{name}: caught for another reason: expected {expected!r}, got {found}")
    return len(cases), problems


def page_mutation(
    pages: list[str], last_page: int, first_appendix: str, figure_captions: list[str]
) -> tuple[list[str], list[str]]:
    """Push the real References heading past the budget with blank pages, and require the S2 fail.

    The self-test shows that :func:`page_budget_problems` reads synthetic pages correctly; this shows
    that it reads the pages of the PDF actually built. ``k`` empty pages are inserted before the
    page that carries the References heading, ``k`` chosen so that the heading lands on the first
    page past the budget. The unmutated pages are the control (``k`` = 0) and must pass; the mutant
    must return exactly the diagnostic of case S2 and nothing else. Returns what it did, as lines to
    print, and what went wrong.
    """
    report: list[str] = []
    failures: list[str] = []
    control = page_budget_problems(pages, last_page, first_appendix, figure_captions)
    references = lines_matching(pages, REFERENCES_PATTERN)
    report.append(
        f"k = 0 (control): References on page {references[0][0] if references else None}, "
        f"{len(control)} problem(s)"
    )
    if control:
        failures.append(f"the control (k = 0) returned {control}")
    if len(references) != 1:
        failures.append(f"the References heading occurs {len(references)} times, so no mutant is built")
        return report, failures
    start = references[0][0]
    k = last_page + 1 - start
    if k <= 0:
        failures.append(f"References already begin on page {start}, past the budget; k would be {k}")
        return report, failures
    mutant = pages[: start - 1] + [""] * k + pages[start - 1 :]
    moved = lines_matching(mutant, REFERENCES_PATTERN)
    found = page_budget_problems(mutant, last_page, first_appendix, figure_captions)
    report.append(
        f"k = {k}: References moved from page {start} to page {moved[0][0] if moved else None}, "
        f"{len(found)} problem(s): {found}"
    )
    expected = f"References begin on page {last_page + 1}"
    if not found:
        failures.append(f"k = {k}: not caught (no problem returned)")
    elif len(found) != 1 or expected not in found[0]:
        failures.append(f"k = {k}: caught for another reason: expected {expected!r}, got {found}")
    return report, failures


def figure_numbers(repo_root: Path) -> dict[str, str]:
    """Figure name -> the label its caption carries on the page ("Figure 2:").

    Read from the markers in main.md, where the same caption opens "**Figure 2.**".
    """
    text = (repo_root / "manuscript" / "main.md").read_text(encoding="utf-8")
    return {
        name: CAPTION_ON_PAGE.format(number=int(number))
        for name, number in re.findall(
            r"<!-- TMLR:FIGURE ([a-z0-9-]+) -->\n\*\*Figure (\d+)\.\*\*", text
        )
    }


_LEVELS = {"section": 1, "subsection": 2, "subsubsection": 3}
_TOC_ENTRY = re.compile(
    r"^\\@writefile\{toc\}\{\\contentsline \{(section|subsection|subsubsection)\}"
    r"\{\\numberline \{([^{}]*)\}(.*)\}\{(\d+)\}\{[^{}]*\}\\protected@file@percent \}$"
)
_LOF_ENTRY = re.compile(
    r"^\\@writefile\{lof\}\{\\contentsline \{figure\}\{\\numberline \{([^{}]*)\}"
)
_LOT_ENTRY = re.compile(
    r"^\\@writefile\{lot\}\{\\contentsline \{table\}\{\\numberline \{([^{}]*)\}"
)
#: A table title in main.md: pandoc's caption line, written with the "Table:" prefix so that the
#: repository rendering reads it as a title. LaTeX numbers the titled tables in order.
TABLE_CAPTION = re.compile(r"^Table: \S", re.M)


def _title_key(title: str) -> str:
    """A heading title reduced to lower-case letters and digits, LaTeX commands removed, so that
    main.md's "Notes to §1" and the .aux's "Notes to \\S 1" compare equal."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\\[A-Za-z@]+", "", title).lower())


def aux_heading_problems(
    aux: str, headings: list[tuple[int, str, str]], figure_count: int, table_count: int = 0
) -> list[str]:
    """Compare the section and figure numbers LaTeX recorded in the ``.aux`` with main.md's.

    ``headings`` is ``(level, number, title)`` for every heading of the body, as main.md numbers
    it (``make_pdf_source.manuscript_headings``). The build predicts LaTeX's numbers and stops if
    main.md disagrees; this reads what LaTeX actually assigned, so a prediction that was itself
    wrong -- a counter the build did not model, a heading LaTeX did not number -- is caught here.
    """
    recorded = [
        (_LEVELS[m.group(1)], m.group(2), m.group(3), m.group(4))
        for m in map(_TOC_ENTRY.match, aux.split("\n"))
        if m
    ]
    if not recorded:
        return ["the .aux records no numbered heading, so the section numbers were not compared"]
    problems: list[str] = []
    divergence = ""
    for (level, number, title), (aux_level, aux_number, aux_title, page) in zip(
        headings, recorded, strict=False
    ):
        if (level, number) != (aux_level, aux_number):
            divergence = (
                f"main.md numbers {title!r} {number} at level {level}; LaTeX numbered the heading "
                f"in that place {aux_number} at level {aux_level} (page {page})"
            )
            break
        if _title_key(title) != _title_key(aux_title):
            divergence = f"heading {number}: LaTeX set {aux_title!r} where main.md has {title!r}"
            break
    if len(recorded) != len(headings):
        problems.append(
            f"the .aux records {len(recorded)} numbered headings, main.md has {len(headings)}"
            + (f"; the first to differ: {divergence}" if divergence else "")
        )
    elif divergence:
        problems.append(divergence)
    figures = [m.group(1) for m in map(_LOF_ENTRY.match, aux.split("\n")) if m]
    if figures != [str(n) for n in range(1, figure_count + 1)]:
        problems.append(
            f"LaTeX numbered the figures {figures}; main.md places {figure_count}, numbered 1 to "
            f"{figure_count}"
        )
    tables = [m.group(1) for m in map(_LOT_ENTRY.match, aux.split("\n")) if m]
    if tables != [str(n) for n in range(1, table_count + 1)]:
        problems.append(
            f"LaTeX numbered the tables {tables}; main.md titles {table_count} with 'Table:', "
            f"numbered 1 to {table_count}"
        )
    return problems


def aux_self_test() -> tuple[int, list[str]]:
    """Run :func:`aux_heading_problems` on synthetic ``.aux`` text whose answer is known."""

    def toc(level: str, number: str, title: str, page: int, anchor: str) -> str:
        return (
            f"\\@writefile{{toc}}{{\\contentsline {{{level}}}{{\\numberline {{{number}}}{title}}}"
            f"{{{page}}}{{{anchor}}}\\protected@file@percent }}"
        )

    headings = [(1, "1", "Introduction"), (2, "1.1", "Notes to §1"), (1, "A", "An appendix")]
    lines = [
        "\\relax ",
        toc("section", "1", "Introduction", 1, "section.1"),
        toc("subsection", "1.1", "Notes to \\S 1", 1, "subsection.1.1"),
        "\\@writefile{lof}{\\contentsline {figure}{\\numberline {1}{\\ignorespaces A caption}}{2}{figure.1}\\protected@file@percent }",
        toc("section", "A", "An appendix", 3, "appendix.A"),
    ]  # fmt: skip
    good = "\n".join(lines)
    cases: tuple[tuple[str, str, str | None], ...] = (
        ("A1 the recorded numbers and titles agree", good, None),
        ("A2 LaTeX numbered a subsection differently", good.replace("{1.1}", "{1.2}"), "LaTeX numbered the heading in that place 1.2"),
        ("A3 a heading LaTeX did not number", "\n".join(lines[:2] + lines[3:]), "the .aux records 2 numbered headings, main.md has 3"),
        ("A4 a figure LaTeX did not number", "\n".join(lines[:3] + lines[4:]), "LaTeX numbered the figures []"),
        ("A5 an .aux without numbered headings", "\\relax ", "the .aux records no numbered heading"),
        ("A6 a title that differs", good.replace("An appendix", "Another appendix"), "heading A: LaTeX set"),
        ("A7 a titled table main.md does not declare", good + "\n\\@writefile{lot}{\\contentsline {table}{\\numberline {1}{A title}}{2}{table.1}\\protected@file@percent }", "LaTeX numbered the tables ['1']; main.md titles 0"),
    )  # fmt: skip
    problems: list[str] = []
    for name, aux, expected in cases:
        found = aux_heading_problems(aux, headings, 1, 0)
        if expected is None:
            if found:
                problems.append(f"{name}: the control returned {found}")
        elif not found:
            problems.append(f"{name}: not caught (no problem returned)")
        elif len(found) != 1 or expected not in found[0]:
            problems.append(f"{name}: caught for another reason: expected {expected!r}, got {found}")
    return len(cases), problems


def row_on_page(page: str, label: str, values: list[str]) -> bool:
    """Whether the page's text, in content-stream order, carries ``label`` then ``values``.

    ``make_figures.py`` emits each row's text nodes consecutively, so extraction in stream order
    (``pdftotext -raw``) reads a row as one run. Layout-based extraction does not: it lays out a
    column of labels and a column of numbers as separate blocks, and xpdf and poppler do so
    differently, so a row check on layout text measured the extractor rather than the page.
    """
    # Bounded on both sides, so that a label "C" cannot match the tail of "...ABC".
    pattern = r"(?<!\S)" + re.escape(label) + "".join(r"\s+" + re.escape(v) for v in values) + r"(?!\S)"
    return re.search(pattern, " ".join(page.split())) is not None


def check_figures(repo_root: Path, pages: list[str]) -> list[str]:
    """Each figure's numbers must stand, row by row, on the page that carries its caption."""
    problems: list[str] = []
    numbers = figure_numbers(repo_root)
    expected = expected_rows(repo_root)
    if sorted(numbers) != sorted(expected):
        return [f"figures placed in main.md {sorted(numbers)} are not those drawn {sorted(expected)}"]
    order = sorted(numbers.values(), key=lambda label: int(label.split()[1][:-1]))
    if order != [CAPTION_ON_PAGE.format(number=i) for i in range(1, len(order) + 1)]:
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
    "Realized outcome known at seal time?",
    "Reported after the run",
)

#: The column headers of the analysis map of section 2.4, the widest table the revision added. Its
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
    parser.add_argument(
        "extracted", type=Path, nargs="?", help="text extracted from the PDF by pdftotext"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        help="text extracted by pdftotext -raw, in content-stream order (the figure rows)",
    )
    parser.add_argument(
        "--anonymous", action="store_true", help="the PDF is the anonymous submission build"
    )
    parser.add_argument(
        "--aux",
        type=Path,
        help="the .aux of the build, which records the section and figure numbers LaTeX assigned",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the page-budget and .aux checks on synthetic input whose answer is known, and "
        "nothing else",
    )
    parser.add_argument(
        "--page-mutation",
        action="store_true",
        help="insert blank pages before the References of the extracted text until they fall one "
        "page past the budget, require the page-budget check to fail with exactly that "
        "diagnostic, and require the unmutated text to pass; nothing else",
    )
    args = parser.parse_args(argv)

    if args.page_mutation:
        if args.extracted is None or not args.extracted.is_file():
            parser.error("--page-mutation needs the extracted text")
        pages = args.extracted.read_text(encoding="utf-8", errors="replace").split("\f")
        captions = sorted(
            figure_numbers(args.repo_root).values(),
            key=lambda label: int(label.split()[1][:-1]),
        )
        report, failures = page_mutation(
            pages, REFERENCES_LAST_PAGE, FIRST_APPENDIX_PATTERN, captions
        )
        for line in report:
            print(f"[pdf-text] page mutation: {line}")
        if failures:
            print("[pdf-text] FAIL: page mutation", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(
            "[pdf-text] OK page mutation: the real pages pass, and with the References pushed one "
            f"page past REFERENCES_LAST_PAGE = {REFERENCES_LAST_PAGE} they fail with exactly the "
            "S2 diagnostic"
        )
        return 0

    if args.self_test:
        ran_pages, failures = page_budget_self_test()
        ran_aux, aux_failures = aux_self_test()
        failures += aux_failures
        ran = ran_pages + ran_aux
        if ran_pages == 0 or ran_aux == 0:
            print(
                f"[pdf-text] FAIL: the self-test ran {ran_pages} page-budget and {ran_aux} .aux "
                "cases; neither may be zero",
                file=sys.stderr,
            )
            return 1
        if failures:
            print(f"[pdf-text] FAIL: self-test, {len(failures)} of {ran} cases", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(
            f"[pdf-text] OK self-test: {ran_pages} page-budget and {ran_aux} .aux cases run, each "
            "returned exactly the expected diagnostic (or none, for the controls), at "
            f"REFERENCES_LAST_PAGE = {REFERENCES_LAST_PAGE}"
        )
        return 0
    if args.extracted is None or args.raw is None or args.aux is None:
        parser.error("the extracted text, --raw and --aux are required unless --self-test is given")

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
    captions = sorted(
        figure_numbers(args.repo_root).values(), key=lambda label: int(label.split()[1][:-1])
    )
    problems += page_budget_problems(pages, REFERENCES_LAST_PAGE, FIRST_APPENDIX_PATTERN, captions)
    references = page_of(pages, REFERENCES_PATTERN)

    if not args.raw.is_file():
        problems.append(f"no stream-order text at {args.raw}")
    else:
        raw_pages = args.raw.read_text(encoding="utf-8", errors="replace").split("\f")
        problems += check_figures(args.repo_root, raw_pages)

    if not args.aux.is_file():
        problems.append(f"no .aux at {args.aux}, so the section numbers were not compared")
    else:
        manuscript = (args.repo_root / "manuscript" / "main.md").read_text(encoding="utf-8")
        headings = manuscript_headings(manuscript)
        problems += aux_heading_problems(
            args.aux.read_text(encoding="utf-8", errors="replace"),
            [(h.level, h.number, h.title) for h in headings],
            len(captions),
            len(TABLE_CAPTION.findall(manuscript)),
        )

    for column in WIDEST_TABLE_COLUMNS:
        if normalise(column) not in flat:
            problems.append(
                f"a column header of the section F table is absent: {column!r} "
                "(the table may have been set too wide and lost its right-hand columns)"
            )

    for column in ANALYSIS_MAP_COLUMNS:
        if normalise(column) not in flat:
            problems.append(
                f"a column header of the section 2.4 analysis map is absent: {column!r} "
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
        f"every heading and figure carries the number main.md gives it in the .aux, "
        "the AI-use footnote is on the first page, every figure's numbers stand row by row on its "
        f"page, {len(REQUIRED_PHRASES) + len(title_phrases)} required phrases, "
        f"all {len(WIDEST_TABLE_COLUMNS)} column headers of the section F table and "
        f"{len(ANALYSIS_MAP_COLUMNS)} of the section 2.4 analysis map, "
        f"{len(REQUIRED_GLYPHS)} glyphs at risk of silent loss, and "
        f"{len(REQUIRED)} quantities read from the frozen inputs are present in the PDF "
        f"({len(flat)} characters of text)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
