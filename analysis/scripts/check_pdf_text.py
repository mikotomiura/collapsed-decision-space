#!/usr/bin/env python3
"""Check the text read back out of the submission PDF.

**A PDF that builds is not a PDF that carries the manuscript.** Two failure modes make that gap
real rather than theoretical, and both are silent:

* XeTeX does not stop on a character its font lacks. It emits a warning and sets *nothing*, so a
  symbol such as the logical `and` joining the branch conditions of section 8 can vanish from the
  page while the build reports success.
* A ``longtable`` row cannot be broken across a page. The study design table is far wider than any
  other table here; if its columns are set too narrow the row overflows instead of reflowing, and
  content can be pushed off the page.

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
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402
from check_manuscript_numbers import REQUIRED, literal_of  # noqa: E402

#: Headings that must survive into the PDF. Section 8.1, 14 and 15 are the ones added for PCI RR
#: compliance; if the landscape wrapping or the title-block transformation drops one, the
#: submission would be non-compliant in exactly the way those sections exist to prevent.
REQUIRED_PHRASES: tuple[str, ...] = (
    "A powered null on a verified channel",
    "Mikoto Miura",
    "0009-0000-4196-0508",
    "Study design table",
    "Level declaration and eligibility self-audit",
    "AI usage disclosure",
    "Ethics, funding and competing interests",
    "Data, code and reproducibility",
)

#: Every column header of the study design table. The table is rotated onto its own page and set
#: small; losing the right-hand columns is the specific way that goes wrong, and it would not be
#: visible from a page count.
DESIGN_TABLE_COLUMNS: tuple[str, ...] = (
    "Question",
    "Sampling plan",
    "Analysis plan",
    "Rationale for the sensitivity of the design",
    "Interpretation given different outcomes",
    "What the outcome bears on",
)

#: Characters the body depends on that a text font may not carry. Each is load-bearing: the
#: logical connectives join the branch conditions of section 8, the arrow gives the evaluation
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

    for phrase in REQUIRED_PHRASES:
        if normalise(phrase) not in flat:
            problems.append(f"a required phrase is absent: {phrase!r}")

    for column in DESIGN_TABLE_COLUMNS:
        if normalise(column) not in flat:
            problems.append(
                f"a study design table column header is absent: {column!r} "
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
        f"[pdf-text] OK: {len(REQUIRED_PHRASES)} required phrases, "
        f"all {len(DESIGN_TABLE_COLUMNS)} study design table columns, "
        f"{len(REQUIRED_GLYPHS)} glyphs at risk of silent loss, and "
        f"{len(REQUIRED)} quantities read from the frozen inputs are present in the PDF "
        f"({len(flat)} characters of text)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
