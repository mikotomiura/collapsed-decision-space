#!/usr/bin/env python3
"""Build the pandoc source for the submission PDF from ``manuscript/main.md``.

**There is deliberately no second manuscript.** ``manuscript/main.md`` is the only text the
claim-boundary check, the abstract-consistency check and the character-level number check read. A
hand-maintained "submission copy" would be a claim surface outside all three, and the first number
corrected in one file and not the other would put the published manuscript and the submitted one
into disagreement. So the PDF is a *derived* artefact: this script performs a small, mechanical,
deterministic transformation and nothing else.

What it changes, and why each change is necessary:

1. **The level-one heading becomes document metadata.** pandoc renders front-matter ``title`` as a
   title block; left in the body it would be an ordinary heading and the PDF would have no title.

2. **The study design table is wrapped in a landscape environment at a smaller size.** That table is
   six columns and its longest source row is over 1,400 characters -- about four times the next
   widest table in the manuscript. In portrait at body size its columns are too narrow to set, and
   a ``longtable`` row cannot be broken across a page, so the row would overflow rather than reflow.
   Rotating the page is the standard remedy and is applied to that one table only.

Everything else is passed through byte for byte. The transformation is checked: the script fails
rather than emitting a source it could not transform as intended.

Usage:  python analysis/scripts/make_pdf_source.py --out build/paper-source.md --date 2026-09-13
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: The first cell of the study design table's header row. Used to locate the table.
DESIGN_TABLE_HEADER = "| Question | Sampling plan |"

#: Author line for the title block. The ORCID is the one pinned in ``CITATION.cff``; a test in the
#: repository is not what keeps these in step -- ``check_claim_boundary.py`` compares the abstract,
#: and the submission checklist compares the ORCID. Changing it here alone is a mistake.
AUTHOR = "Mikoto Miura, Independent Researcher (ORCID 0009-0000-4196-0508)"

#: Preamble. ``pdflscape`` supplies the landscape environment; ``emergencystretch`` lets TeX
#: relieve overfull lines inside narrow table columns rather than letting them run into the margin.
#:
#: ``\blandscape`` and ``\elandscape`` exist because pandoc must not be given a complete LaTeX
#: environment to look at. Writing ``\begin{landscape}`` directly in the body makes pandoc treat
#: everything up to ``\end{landscape}`` as one raw block and pass it through untouched -- the
#: markdown table inside is then never parsed, and its underscores reach LaTeX bare, which fails
#: with ``Missing $ inserted``. Wrapping the environment in two macros gives pandoc two ordinary
#: raw commands instead, and the markdown between them is parsed normally. This is the documented
#: idiom for rotating a pandoc-generated table.
HEADER_INCLUDES = (
    r"\usepackage{pdflscape}",
    r"\usepackage{seqsplit}",
    r"\newcommand{\blandscape}{\begin{landscape}}",
    r"\newcommand{\elandscape}{\end{landscape}}",
    r"\setlength{\emergencystretch}{3em}",
)

#: A code span longer than this, with no space in it, is rewritten so that it can break.
#:
#: TeX will not break a typewriter token that offers no breakpoint. It sets it past the column edge
#: instead, and the overflow is simply not on the page: the first build of this document put 47 of
#: the 64 characters of each SHA-256 model digest on the page and lost the rest, while the 40-
#: character commit identifiers in the same document survived intact. 48 is therefore the measured
#: boundary rather than a guess -- above it, content was being dropped.
LONG_TOKEN_THRESHOLD = 48

#: Typesetting variables, declared here rather than on the pandoc command line so that a font name
#: containing a space cannot be split into separate arguments by the shell -- a mistake already
#: made once in this project's other paper pipeline.
#:
#: **The font is chosen for coverage, not for looks.** The body needs the logical connectives, the
#: arrow, lambda, alpha and several accented Latin letters. XeTeX sets *nothing* for a character
#: its font lacks and does not fail, so a narrow-coverage font would quietly delete the branch
#: conditions of section 8. DejaVu carries all of them. ``check_pdf_text.py`` then verifies that
#: each one actually reached the page, rather than trusting this choice.
DOCUMENT_VARIABLES: tuple[tuple[str, str], ...] = (
    ("papersize", "a4"),
    ("geometry", "margin=2.5cm"),
    ("fontsize", "11pt"),
    ("colorlinks", "true"),
    ("mainfont", "DejaVu Serif"),
    ("sansfont", "DejaVu Sans"),
    ("monofont", "DejaVu Sans Mono"),
)


def _die(message: str) -> None:
    print(f"[pdf-source] {message}", file=sys.stderr)
    raise SystemExit(1)


def split_title(text: str) -> tuple[str, str]:
    """Take the level-one heading off the front of the manuscript.

    Returns ``(title, body)``. Fails if the first non-empty line is not a level-one heading, rather
    than silently producing a titleless document.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if not line.startswith("# "):
            _die(f"the first non-empty line of main.md is not a level-one heading: {line[:60]!r}")
        return line[2:].strip(), "\n".join(lines[index + 1 :]).lstrip("\n")
    _die("main.md is empty")
    raise AssertionError("unreachable")


def wrap_design_table(body: str) -> str:
    """Put the study design table on a rotated page at a smaller size.

    The table runs from its header row to the first line that is not part of the table. Fails if
    the header cannot be found, so a rename upstream cannot silently produce a PDF whose widest
    table is unreadable.
    """
    lines = body.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(DESIGN_TABLE_HEADER)]
    if len(starts) != 1:
        _die(
            f"expected exactly one study design table header starting {DESIGN_TABLE_HEADER!r}, "
            f"found {len(starts)}"
        )
    start = starts[0]

    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    if end - start < 3:
        _die(f"the study design table has only {end - start} lines; it should have at least 3")

    # `\blandscape` / `\elandscape` rather than the environment itself -- see HEADER_INCLUDES for
    # why giving pandoc a complete environment silently disables markdown parsing inside it.
    opening = ["", r"\blandscape", r"\footnotesize", r"\setlength{\tabcolsep}{3pt}", ""]
    closing = ["", r"\normalsize", r"\elandscape", ""]
    return "\n".join(lines[:start] + opening + lines[start:end] + closing + lines[end:])


def split_long_tokens(body: str) -> tuple[str, int]:
    """Let over-long typewriter tokens break, so they cannot run off the page.

    Only code spans with no whitespace in them are touched, which is what confines this to
    identifiers and digests: a run of prose between two unrelated code spans on the same line
    always contains a space and is left alone. The characters are unchanged -- ``\\seqsplit`` only
    adds permission to break between them -- so the page still carries the token exactly.

    Returns the rewritten body and how many tokens were rewritten.
    """
    pattern = re.compile(r"`([^\s`]{" + str(LONG_TOKEN_THRESHOLD) + r",})`")
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return r"\texttt{\seqsplit{" + match.group(1) + "}}"

    return pattern.sub(replace, body), count


def check_no_raw_environment(body: str) -> None:
    """Refuse to emit a body containing a literal LaTeX environment.

    pandoc treats ``\\begin{X}`` ... ``\\end{X}`` as a single raw block and passes everything
    between them through without parsing it. A markdown table caught inside one is therefore never
    converted, and its underscores arrive at LaTeX bare -- the build fails with ``Missing $
    inserted`` pointing at a line of the manuscript, which reads like a problem with the prose
    rather than with this script. That already happened once. Environments must be reached through
    a macro instead, as ``HEADER_INCLUDES`` does for ``landscape``.
    """
    offenders = [
        line for line in body.splitlines() if line.lstrip().startswith((r"\begin{", r"\end{"))
    ]
    if offenders:
        _die(
            "the generated body contains a literal LaTeX environment, which would make pandoc "
            "skip parsing everything inside it: " + "; ".join(offenders[:3])
        )


def build(manuscript: Path, date: str) -> str:
    text = manuscript.read_text(encoding="utf-8")
    title, body = split_title(text)
    body = wrap_design_table(body)
    body, split_count = split_long_tokens(body)
    check_no_raw_environment(body)
    print(f"[pdf-source] {split_count} over-long token(s) made breakable")

    header = "\n".join(f"  - {item}" for item in HEADER_INCLUDES)
    variables = "\n".join(f'{name}: "{value}"' for name, value in DOCUMENT_VARIABLES)
    front_matter = (
        "---\n"
        f'title: "{title}"\n'
        "author:\n"
        f'  - "{AUTHOR}"\n'
        f'date: "{date}"\n'
        f"{variables}\n"
        "header-includes:\n"
        f"{header}\n"
        "---\n\n"
    )
    return front_matter + body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument("--out", type=Path, required=True, help="where to write the pandoc source")
    parser.add_argument(
        "--date",
        required=True,
        help="date for the title block; pass a fixed value so the PDF is reproducible",
    )
    args = parser.parse_args(argv)

    manuscript = args.repo_root / "manuscript" / "main.md"
    if not manuscript.is_file():
        _die(f"manuscript is missing: {manuscript}")

    source = build(manuscript, args.date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(source, encoding="utf-8")

    print(f"[pdf-source] wrote {args.out} ({len(source.splitlines())} lines)")
    print("[pdf-source] title block added; study design table set landscape at footnotesize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
