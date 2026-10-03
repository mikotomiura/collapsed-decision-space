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
   ``make_figures.py`` generates from the shipped data. The caption stays in ``main.md`` as prose,
   opening with its label ("**Figure 2.**"); the build takes the label off and sets the rest through
   ``\\caption``, so that LaTeX numbers the figure and sets "Figure 2:" as the official style does
   (``manuscript/tmlr/TEMPLATE-DIFF.md``).
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
8. **Section numbers are taken off the headings and left to LaTeX**, which sets them as the official
   style does ("4.3 Title"). main.md keeps its numbers, because the repository cites them, and the
   build stops if any of them is not the number LaTeX will assign (:func:`number_headings`).

With ``--anonymous``, identifying strings the de-identified bundle has to keep are also withheld
from the page (``.steering`` DA-C-4 and DA-C-5): the name of the upstream project, which the
bundle cannot drop because the provenance checks are byte comparisons against it, commit
identifiers and tags. The bundle is an internal intermediate and is not submitted (DA-DR-16), so
the sentences that point at a location, a supplement or a project-specific file name are rewritten
(:data:`ANONYMOUS_REWRITES`), and §J defines "this repository" once as the compendium made public
after review.

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
#: to occur once. The sentences that named the author's own prior preprint and the venue this work
#: was submitted to before left the manuscript in the 2026-09-30 revision, and
#: ``check_pdf_identity.py`` still fails the anonymous build if either reaches the page.
#:
#: These follow from submitting no supplement (``.steering`` DA-DR-16, F02 = c; DA-TR-1): the
#: anonymous PDF defines "this repository" and "shipped" once, in §J, as the compendium that is
#: made public after review, and rewrites only the sentences that would otherwise point a reviewer
#: at a location, a supplement, or a file name that identifies the upstream project (F01 = b). The
#: build runs on the de-identified bundle, where URLs are already placeholders; this file goes
#: through the same substitutions, so each old sentence is written here as ``main.md`` has it and
#: still matches. ``check_pdf_identity.py`` fails the anonymous build if a withheld word survives,
#: on the page and in the generated source alike.
ANONYMOUS_REWRITES: tuple[tuple[str, str], ...] = (
    # §C.3: the environment variable carries the upstream project's prefix.
    (
        "environment pins `ERRE_ZONE_BIAS_P = 0.2`, but no bias",
        "environment pins the zone-bias probability at 0.2, but no bias",
    ),
    # §G.2: the upstream repository's URL.
    (
        "The records are at\n<https://github.com/mikotomiura/ERRE-Sandbox>. "
        "`analysis/freeze-provenance.json` carries the\n",
        "The records are in the upstream source repository, which will be identified after review.\n"
        "`analysis/freeze-provenance.json` carries the\n",
    ),
    # §I.5: the driver's file name carries a project-specific prefix.
    (
        "which equals that of\n`scripts/paper02_run_arms.py` at upstream commit",
        "which equals that of\nthe driver script at upstream commit",
    ),
    # §J: the definition of "this repository" and "shipped" replaces the repository's URL.
    (
        "**Everything this manuscript refers to is reachable from one place.** The repository is\n"
        "<https://github.com/mikotomiura/collapsed-decision-space>. Work continues on its default "
        "branch, so\n",
        "**Everything this manuscript refers to is in, or referenced from, one research compendium, "
        'which will be made public after review. In this manuscript, "this repository" and '
        '"shipped" refer to that compendium.** Work on it continues, so\n',
    ),
    # §J: the upstream repository's URL, and the statement that no supplementary archive exists.
    (
        "The upstream source repository the apparatus and the provenance records come from is\n"
        "<https://github.com/mikotomiura/ERRE-Sandbox>, and §G.2 gives the commit identifiers "
        "within it.\nApart from the archival deposit of the sealed files described in §J, there is "
        "no separate\nsupplementary archive: the data, the analysis scripts, the apparatus and the "
        "reproduction command\nare all in the repository named here.\n",
        "The apparatus and the provenance records come from an upstream source repository that will "
        "be\nidentified after review; §G.2 describes the commits within it. Apart from the archival "
        "deposit of\nthe sealed files described in §J, the data, the analysis scripts, the apparatus "
        "and the\nreproduction command are all in the compendium named above.\n",
    ),
    # §J: the de-identification tool the anonymous build is made with.
    (
        "The manual `submission-pdf` workflow\nperforms all of it. The anonymous build takes its "
        "manuscript from a copy of this repository\nde-identified by "
        "`analysis/scripts/make_anonymous_bundle.py`, which reports what identifying strings\nit "
        "cannot remove and why; that copy is an intermediate of the build and is not submitted.\n",
        "A manual workflow\nperforms all of it.\n",
    ),
    # §H and §J: the archival deposit's identifiers and its registration time, which a search of
    # the archive would resolve to a record carrying the author's name (TASK-POST review).
    (
        "One\nnow exists, at `10.5281/zenodo.22735436`; §J describes",
        "One\nnow exists, in a public archive that will be identified after review; §J describes",
    ),
    (
        "deposited at `10.5281/zenodo.22735436` (concept) and `10.5281/zenodo.22735437` (this "
        "version) —",
        "deposited in a public archive that will be identified after review —",
    ),
    (
        "those twenty-seven times is **`2026-09-13T23:44:39.000Z`**, and it is the DOI registration "
        "time;",
        "those twenty-seven times, withheld for review, is the DOI registration time;",
    ),
    # §G.2 and §J: what a reader can check needs the public compendium and the upstream repository.
    (
        "upstream repository and are confirmed by following the links above.",
        "upstream repository and can be confirmed against it once it is identified after review.",
    ),
    (
        "A reviewer who wants\nthe outside half performs it; a reviewer who does not still gets steps "
        "1 to 13,",
        "Once the compendium is public, a reader who\nwants the outside half can perform it; one who "
        "does not still gets steps 1 to 13,",
    ),
    # The first-page footnote and §K: the commit counts are public once the compendium is.
    (
        "with commit counts a reader can recompute.",
        "with commit counts a reader can recompute once the compendium is public.",
    ),
    (
        "The extent of that assistance is visible in the public record rather than asserted here,",
        "The extent of that assistance will be visible in the public record after review rather than "
        "asserted here,",
    ),
    # §J: the driver's file name again.
    (
        "That driver is in the\nupstream repository as `scripts/paper02_run_arms.py` at commit\n",
        "That driver is a script in the\nupstream repository, at commit\n",
    ),
    # §K: the continuous integration is public only once the compendium is.
    (
        "re-run by public continuous integration on two operating systems",
        "re-run by continuous integration on two operating systems",
    ),
    # §K, the table: the upstream repository's URL.
    (
        "| Upstream source, <https://github.com/mikotomiura/ERRE-Sandbox>, at commit",
        "| Upstream source repository (identified after review), at commit",
    ),
    # The 2026-10-01 pre-submission review (``.steering`` DA-TR-20, m-1 and M-4). The named build is
    # one author's and says "the author"; the anonymous build must not say how many there are.
    ("reviewed and validated by the author.", "reviewed and validated by the authors."),
    ("does not come from the author.", "does not come from the authors."),
    ("identifies the author.", "identifies the authors."),
    ("seconds on the author's machine.", "seconds on the machine used for this study."),
    ("validated by the human author, who made the", "validated by the human authors, who made the"),
    ("belonging to the\nauthor, and the models", "belonging to the\nauthors, and the models"),
    ("The author declares no competing interests.", "The authors declare no competing interests."),
    # §H and §J: file names that name the archive the deposit is held in.
    ("| `collect_zenodo_witness.py` |", "| the witness collector |"),
    (
        "`analysis/scripts/collect_zenodo_witness.py`, which is sealed, reads that listing and records "
        "it as\n`seal/zenodo-witness.json`, pairing",
        "The sealed witness collector reads that listing and records it as\nthe deposit witness, "
        "pairing",
    ),
    (
        "`seal/zenodo-witness.json` records what that deposit publishes",
        "The deposit witness records what that deposit publishes",
    ),
    # §L: a file name whose suffix names the language of the frozen specification.
    (
        "| `analysis/heldout-stay/SPEC.ja.md` | 21 | 8 | §E |",
        "| the held-out test's specification | 21 | 8 | §E |",
    ),
    (
        "| `analysis/heldout-stay/SPEC.ja.md` | 147 | 12.1 | §8.1 |",
        "| the held-out test's specification | 147 | 12.1 | §8.1 |",
    ),
    (
        "| `analysis/heldout-stay/SPEC.ja.md` | 169 | 6.3 | §C.4 |",
        "| the held-out test's specification | 169 | 6.3 | §C.4 |",
    ),
    # §G.2, the table: upstream commit times to the second, which a search of the upstream history
    # would resolve. The dates are what the argument needs.
    ("| Commit time (UTC) |", "| Commit date (UTC) |"),
    ("| 2026-07-07T17:08:49Z |", "| 2026-07-07 |"),
    ("| 2026-07-10T09:25:18Z |", "| 2026-07-10 |"),
    ("| 2026-07-10T12:25:06Z |", "| 2026-07-10 |"),
    # §1, the first contribution: nothing is supplied for review, so what it rests on can be checked
    # only once the compendium is public.
    (
        "compare most quoted quantities with the data, are in this repository (§J).",
        "compare most quoted quantities with the data, will be made public after review and can be "
        "checked there (§J).",
    ),
)

#: The author's own prior work in the reference list. Named by identifier, not by author, because
#: the de-identified manuscript this script runs on in the anonymous build has already had the
#: name replaced. Empty since the 2026-09-30 revision, which cites none (``.steering`` DA-DR-16);
#: the withholding stays in place for an entry added later, and ``check_pdf_identity.py`` keeps
#: failing the anonymous build on the title of the one that was cited before.
SELF_CITATIONS: frozenset[int] = frozenset()
WITHHELD_TITLE = "Title withheld for anonymous review"

#: Authors that are organisations rather than people, named by hand for the same reason as the
#: self-citations: a parser that accepted any author list without initials would also accept a
#: person's name that had lost them, and the bibliography would carry it without a word. The one
#: entry is the web page cited for what a Registered Report asks of a protocol.
CORPORATE_AUTHORS: frozenset[str] = frozenset({"Center for Open Science"})

CITATIONS_FIXTURE = Path("manuscript") / "tmlr" / "citations.tsv"
TMLR_DIR = Path("manuscript") / "tmlr"
TMLR_FILES: tuple[str, ...] = (
    "tmlr.sty",
    "tmlr.bst",
    "fancyhdr.sty",
    "template.tex",
    "caption.lua",
)


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
        elif author_text in CORPORATE_AUTHORS:
            # Braced, so that BibTeX keeps the name whole instead of reading a surname out of it.
            surnames, et_al, author_field = (author_text,), False, "{" + author_text + "}"
        else:
            if not author_text.endswith("."):
                author_text += "."
            surnames, et_al, author_field = _split_authors(author_text)
        note = ""
        note_match = re.search(
            r"\b(doi:\S+?|arXiv:\d{4}\.\d{4,5}|https?://\S+?)(?=[,.]?\s|[,.]?$)", rest
        )
        if note_match:
            note = note_match.group(1)
        venue = rest
        if note.startswith(("doi:", "http")):
            venue = venue.replace(note, "")
        remark = ""
        remark_match = re.search(r"\s*\((.*)\)\s*$", venue)
        if remark_match:
            remark = remark_match.group(1).strip()
            venue = venue[: remark_match.start()].strip()
        undated = re.search(r",?\s*n\.d\.\s*$", venue)
        if undated:
            # A web page that shows no date is cited "n.d.", not under the year it was read in.
            year = "n.d."
            venue = venue[: undated.start()].strip().rstrip(",.")
        else:
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


#: The label a figure's caption opens with in main.md, where it is prose ("**Figure 2.**").
CAPTION_LABEL = re.compile(r"^\*\*Figure (\d+)\.\*\*\s+")


def replace_figures(body: str) -> tuple[str, list[str]]:
    """Turn each figure block into a figure environment whose caption LaTeX sets and numbers.

    In main.md the caption is a paragraph that opens with its label, "**Figure 2.**", so that the
    repository rendering shows it. The official style sets "Figure 2:" through ``\\caption``, and
    this build does the same (``manuscript/tmlr/TEMPLATE-DIFF.md``): the label is taken off, and the
    rest of the paragraph goes into a ``tmlr-caption`` div that ``caption.lua`` hands to
    ``\\caption`` after pandoc has converted its markdown. LaTeX then numbers the figures itself, so
    main.md's numbers must be the ones it will assign -- 1, 2, 3 in order of appearance -- and the
    build stops if they are not. ``check_pdf_text.py --aux`` compares them with the numbers LaTeX
    actually recorded.
    """
    out: list[str] = []
    names: list[str] = []
    inside: str | None = None
    caption: list[str] = []
    for line in body.splitlines():
        match = FIGURE_BEGIN.match(line.strip())
        if match:
            if inside:
                _die(f"figure {match.group(1)} opens inside figure {inside}")
            inside = match.group(1)
            names.append(inside)
            caption = []
        elif line.strip() == FIGURE_END:
            if not inside:
                _die("a figure closes that was never opened")
            text = "\n".join(caption).strip()
            label = CAPTION_LABEL.match(text)
            if not label:
                _die(f"figure {inside}: the caption does not open with '**Figure N.**'")
            if int(label.group(1)) != len(names):
                _die(
                    f"figure {inside} is labelled Figure {label.group(1)} in main.md, but it is "
                    f"figure {len(names)} in order of appearance, which is the number LaTeX gives it"
                )
            if "\n\n" in text:
                _die(f"figure {inside}: the caption must be one paragraph")
            out.extend(
                (
                    f"\\TMLRFigureBegin{{fig-{inside}}}",
                    "",
                    f'::: {{.tmlr-caption label="fig-{inside}"}}',
                    text[label.end() :],
                    ":::",
                    "",
                    "\\TMLRFigureEnd",
                )
            )
            inside = None
        elif inside:
            caption.append(line)
        else:
            out.append(line)
    if inside:
        _die(f"figure {inside} is never closed")
    if len(names) != len(set(names)):
        _die(f"a figure is placed twice: {names}")
    return "\n".join(out), names


@dataclass(frozen=True)
class Heading:
    level: int  # 1 section, 2 subsection, 3 subsubsection
    number: str  # as main.md writes it and LaTeX will set it: "4", "4.1", "B", "B.3"
    title: str


_HEADING = re.compile(r"^(#{2,}) (.+?)\s*$")
_HEADING_NUMBER = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+(\S.*)$")


def number_headings(body: str) -> tuple[str, list[Heading]]:
    """Take the numbers off main.md's headings and leave the numbering to LaTeX.

    The section numbers are identifiers the rest of the repository cites ("§4.3"), so they stay in
    main.md. The official style numbers sections itself and sets them as "4.3 Title", not
    "4.3. Title"; the build now does the same (``manuscript/tmlr/TEMPLATE-DIFF.md``). That is only
    safe if main.md's numbers are the ones LaTeX will assign, so each is predicted -- sections
    1, 2, ... before the appendices and A, B, ... after ``\\appendix``, subsections from 1 within
    their section -- and the build stops on the first that differs. The prediction is checked
    against what LaTeX actually recorded by ``check_pdf_text.py --aux``.
    """
    lines = body.split("\n")
    headings: list[Heading] = []
    counters = [0, 0, 0]
    appendix = False
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.strip() == "\\TMLRAppendix":
            appendix = True
            counters = [0, 0, 0]
            continue
        match = _HEADING.match(line)
        if not match:
            continue
        level = len(match.group(1)) - 1
        if level > 3:
            _die(f"a heading deeper than the third level has no LaTeX number: {line!r}")
        numbered = _HEADING_NUMBER.match(match.group(2))
        if not numbered:
            _die(f"a heading carries no section number: {line!r}")
        counters[level - 1] += 1
        counters[level:] = [0] * (3 - level)
        head = chr(ord("A") + counters[0] - 1) if appendix else str(counters[0])
        expected = ".".join([head, *(str(c) for c in counters[1:level])])
        number, title = numbered.group(1), numbered.group(2)
        if number != expected:
            _die(
                f"the heading {line!r} is numbered {number} in main.md, but LaTeX will number it "
                f"{expected}; renumber main.md (and what cites it) rather than the build"
            )
        headings.append(Heading(level, number, title))
        lines[index] = f"{match.group(1)} {title}"
    if fenced:
        _die("a fenced code block is never closed")
    return "\n".join(lines), headings


def manuscript_headings(text: str) -> list[Heading]:
    """The headings of the body the PDF sets, with the numbers LaTeX is expected to give them."""
    _, body = split_title(text)
    body = replace_references(take_abstract(drop_block(body)))
    return number_headings(body)[1]


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
    body, headings = number_headings(body)
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
        f"{len(figures)} figure(s), {len(headings)} headings left to LaTeX to number, "
        f"{table_count} table(s) weighted, "
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
