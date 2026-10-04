#!/usr/bin/env python3
"""Check the APA 7 ``.docx`` against ``manuscript/main.md``: every change by contract, the rest word for word.

**A ``.docx`` that opens is not a ``.docx`` that carries the manuscript.** It is derived by
``make_docx_source.py`` and pandoc, and either can lose a paragraph, set a citation against the
wrong entry or put one figure's picture under another's label, while the file still opens and
looks like a paper. So the ``.docx`` is read back, from its XML, and checked against the inputs it
was derived from -- ``main.md``, ``manuscript/refs.json`` and ``CITATION.cff`` -- which this script
reads on its own: it does not take the text of either side from the other.

**What the conversion changes is a contract, not an exclusion.** Every change is an item with its
place in ``main.md``, its input and its output, and each item is checked by itself
(design-final §4.1):

* **citations** -- per citation, the identifiers and the kind (parenthetical, narrative, inside a
  parenthesis) agree with ``manuscript/tmlr/citations.tsv``; the names a narrative citation takes
  out are the ones the prose wrote before the marker; the text citeproc set is the row of
  ``manuscript/docx/citations-apa.tsv``, and that row names each entry's first author and year as
  ``refs.json`` has them;
* **the reference list** -- one entry per item of ``refs.json``, read as its fields in order (every
  author, the year, the title, the container, volume and issue, pages or article number, edition,
  publisher, DOI or URL) with nothing but punctuation between them; the entries in APA order, and
  every item cited;
* **the Author Note** -- the author table's rows, verbatim, and the AI disclosure moved there from
  §K: once in the ``.docx``, and nowhere else;
* **the title page and the abstract** -- the title, author and affiliation as ``main.md`` and
  ``CITATION.cff`` both give them, the abstract they both hold, and the keywords;
* **figures** -- per figure, its label, its title, and the picture under them: the PNG recorded for
  that figure, by SHA-256;
* **tables** -- per table, its label, its title, and every cell;
* **what is left out** -- the lead paragraph of the author table, the note after the references and
  the markers, which must not reach the ``.docx``.

**Everything else is compared word for word**, in order, with the same normalisation on both sides
(Unicode NFC, straight quotes, collapsed whitespace). The items above stand in the comparison as
placeholders, so that a citation or a table that moved, or a paragraph lost beside one, still shows.
The reference list stands there too, as one placeholder under its heading, and the page breaks
before it and before each appendix are required where they belong and nowhere else. A paragraph
whose style marks it for an item (a picture, a page break) must hold nothing else.

Then the text is read for what must not be in it: a British spelling outside the places where one
is kept (the generated rule text of §E, code, the reference list), a character the manuscript
depends on that is missing, the residue of a citation that did not resolve, and the brackets of the
comparison's own placeholders. Content the reader cannot account for -- in a text box, in a header,
in a comment, hidden, or in any element outside the few pandoc writes (a content control, alternate
content, an equation, a symbol, a field, a tracked change) -- is reported rather than read through
or skipped; so is any property outside the few pandoc sets (a merged cell, a row height, a cropped
or transparent picture, a section break), and a picture must have the form pandoc writes, attribute
by attribute. Styles are resolved through their inheritance and must neither hide text nor break
pages where the check does not expect it; each style has one identity; the styles the body uses
carry only the few properties and values a readable page needs; the header holds the page number
field and nothing else; the labels numbering draws (a bullet, a number) are part of the compared
text; and every link must show and lead where main.md and refs.json say.

**What the body does not carry is the reference document's.** pandoc copies the theme, the fonts,
the header, the page and the styles from ``reference.docx``, which ``make_docx_source.py`` builds
and the workflow builds twice and compares. So ``--reference`` is required, and the ``.docx`` must
have its parts and no others but the pictures, its copied parts byte for byte, its styles (but the
highlighting styles pandoc adds, which nothing may use), settings, section, content types and
relationships. The document properties (``docProps/core.xml`` and ``custom.xml``) are not compared:
the page does not show them, and no field that could show them is allowed.

**And the check is checked.** ``--self-test`` builds a small ``.docx`` from a synthetic manuscript,
which must pass, and then breaks a copy of it one way at a time -- a paragraph dropped or doubled, a
number or a sign changed, a figure's picture dropped or swapped, a reference dropped or its year
changed, a citation pointed at another entry, a table cell's boundary moved, a British spelling, the
AI disclosure changed or left behind, and more -- each of which must be reported with exactly the
diagnostics it should produce, by check and by place. ``--mutation-test`` does the same to the real
``.docx``.

Usage:
    python analysis/scripts/check_docx_text.py build/docx/paper.docx \\
        --contract build/docx/contract.json --figures build/docx/figs/figures.json \\
        --reference build/docx/reference.docx \\
        [--write-text build/docx/paper-docx.txt] [--mutation-test] [--write-citations-apa]
    python analysis/scripts/check_docx_text.py --figure-text build/docx/figs
    python analysis/scripts/check_docx_text.py --self-test
"""

from __future__ import annotations

import argparse
import collections
import copy
import difflib
import hashlib
import io
import json
import re
import sys
import tempfile
import unicodedata
import warnings
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_pdf_text import REQUIRED_GLYPHS, row_on_page  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


MAIN = Path("manuscript") / "main.md"
REFS = Path("manuscript") / "refs.json"
CFF = Path("CITATION.cff")
TMLR_CITATIONS = Path("manuscript") / "tmlr" / "citations.tsv"
APA_CITATIONS = Path("manuscript") / "docx" / "citations-apa.tsv"
APA_HEADER = "# context (last four words before the marker)\tidentifiers\tkind\tAPA citation as citeproc set it\n"

DROP_BEGIN = "<!-- TMLR:DROP -->"
DROP_END = "<!-- /TMLR:DROP -->"
FOOTNOTE_BEGIN = "<!-- TMLR:FOOTNOTE -->"
FOOTNOTE_END = "<!-- /TMLR:FOOTNOTE -->"
APPENDIX = "<!-- TMLR:APPENDIX -->"
FIGURE_BEGIN = re.compile(r"^<!-- TMLR:FIGURE ([a-z0-9-]+) -->$")
FIGURE_END = "<!-- /TMLR:FIGURE -->"
REFS_BEGIN = "<!-- BEGIN RENDERED FROM manuscript/refs.json -- DO NOT EDIT BY HAND -->"
REFS_END = "<!-- END RENDERED FROM manuscript/refs.json -->"
GENERATED_BEGIN = re.compile(r"^<!-- BEGIN GENERATED FROM \S+ -- DO NOT EDIT BY HAND -->$")
GENERATED_END = re.compile(r"^<!-- END GENERATED FROM \S+ -->$")

#: The rows of the author table, in the order the Author Note sets them, and the two the byline
#: takes. The AI disclosure goes between the License row and the Correspondence row.
NOTE_BEFORE = ("ORCID", "Protocol status", "Code and data", "License")
NOTE_AFTER = ("Correspondence",)
BYLINE = ("Author", "Affiliation")

#: Paragraph styles of the ``.docx`` that mark a part of the contract. Every paragraph in one of
#: these is checked by its own item; none is left out of the comparison.
HEAD_STYLES = (
    "Title",
    "Author",
    "Affiliation",
    "Author Note Heading",
    "Author Note",
    "Abstract Title",
    "Abstract",
    "Keywords",
    "Title Repeat",
)
CITATION_STYLE = "Citation"
#: The character style a list's label is read in (it is drawn by numbering, not set in a run).
LABEL_STYLE = "List Label"
#: The style of the space a cell's paragraphs are joined with when the cell is read as one text.
JOIN_STYLE = "Paragraph Join"
CODE_STYLE = "Verbatim Char"

#: British spellings, as a closed list of word forms rather than suffix patterns, which would catch
#: "otherwise" and "precise". The stems are those the manuscript was converted from (``.steering``
#: spelling inventory of 2026-10-04) and the usual ones of technical prose. A form is never allowed
#: as a word: the places a British spelling is kept are excluded by position.
_ISE_STEMS = (
    "normal|renormal|random|character|discret|real|summar|rational|canonical|organ|optim|minim|"
    "maxim|standard|general|recogn|util|categor|priorit|parameter|initial|serial|visual|formal|"
    "special|final|operational|stabil|synchron|token|custom|emphas|central|penal|legal|neutral|"
    "capital|quantis|apologis|critic|harmon|hospital|memor|mobil|polar|regular|stigmat|subsid"
)
BRITISH = re.compile(
    r"\b(?:(?:" + _ISE_STEMS + r")is(?:e|es|ed|ing|ation|ations|er|ers)"
    # "analyses" is left out: it is also the plural of the noun, in either spelling.
    r"|analys(?:e|ed|ing)|re-analys(?:ed|ing)"
    r"|(?:behavio|colo|favo|neighbo|hono|labo|harbo|humo|flavo|vapo|rigo|endeavo)ur\w*"
    r"|(?:cent|met|fib|lit|theat|calib|spect)re[sd]?"
    r"|(?:label|model|travel|cancel|signal|level|fuel|total|counsel|marshal)l(?:ed|ing)"
    r"|licence[sd]?|artefacts?|judgements?|defence|offence|programmes?|catalogues?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class Problem:
    check: str
    where: str
    message: str = field(compare=False)

    def key(self) -> tuple[str, str]:
        return self.check, self.where

    def __str__(self) -> str:
        return f"[{self.check}] {self.where}: {self.message}"


# --------------------------------------------------------------------------------------------------
# Normalisation, applied to both sides alike

_TRANSLATE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
        "\u2009": " ",
        "\u202f": " ",
        "\u2011": "-",
    }
)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_TRANSLATE).replace("\u2026", "...")
    return " ".join(text.split())


# --------------------------------------------------------------------------------------------------
# main.md, read on its own

PLACEHOLDER_CITE = "\u27e6CITE\u27e7"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)
#: The brackets of every placeholder of the comparison; neither may occur in the text of the .docx.
RESERVED = chr(0x27E6) + chr(0x27E7)


def _blank_code(text: str) -> str:
    """Code spans replaced by as many x's, so that offsets still match and no marker is seen."""
    return re.sub(r"`[^`\n]*`", lambda m: "x" * len(m.group(0)), text)


def inline(md: str, *, cell: bool = False) -> str:
    """The text a markdown fragment of this manuscript reads as: code kept, markup taken off."""
    if cell:
        md = md.replace("\\|", "|")
    out: list[str] = []
    position = 0
    # A code span may run across a line break inside a paragraph, as pandoc reads it.
    for match in re.finditer(r"`([^`]*)`", md):
        out.append(_plain(md[position : match.start()]))
        out.append(match.group(1))
        position = match.end()
    out.append(_plain(md[position:]))
    return "".join(out)


def _plain(text: str) -> str:
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\((?:[^)\s]+)\)", r"\1", text)
    text = text.replace("*", "")
    # pandoc's smart punctuation, outside code: "---" is an em dash and "--" an en dash, as in the PDF.
    text = text.replace("---", EM_DASH).replace("--", EN_DASH)
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", text)


@dataclass
class MBlock:
    kind: str  # heading, para, item, code, table, figure, footnote, references, note, marker, rule
    line: int  # 1-based
    last: int  # 1-based
    raw: str
    level: int = 0
    name: str = ""
    number: int = 0  # a figure's label number, a table's number in order of appearance
    caption: str = ""
    caption_line: int = 0
    rows: list[list[str]] = field(default_factory=list)
    generated: bool = False
    appendix: bool = False


@dataclass
class MCite:
    k: int
    line: int
    ids: tuple[int, ...]
    kind: str
    removed: str
    prefix: str
    suffix: str
    context: str
    mode: str
    start: int
    end: int
    block: int  # index of the block it is in


@dataclass
class Manuscript:
    text: str
    title: str
    rows: dict[str, tuple[int, str]]
    lead: tuple[int, int, str]
    dropped_lines: list[int]
    abstract: str
    abstract_lines: tuple[int, int]
    blocks: list[MBlock]
    ai: MBlock
    note: MBlock
    cites: list[MCite]
    generated: tuple[int, int]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def read_manuscript(text: str, refs: list[dict[str, Any]]) -> Manuscript:
    lines = text.split("\n")
    if not lines[0].startswith("# "):
        raise ValueError("main.md does not open with its title")
    title = lines[0][2:].strip()
    begin, end = lines.index(DROP_BEGIN), lines.index(DROP_END)
    rows: dict[str, tuple[int, str]] = {}
    lead_lines: list[int] = []
    dropped: list[int] = []
    for index in range(begin + 1, end):
        line = lines[index]
        if not line.strip():
            continue
        if line.startswith("|"):
            cells = _cells(line)
            if len(cells) == 2 and cells[0] and not re.fullmatch(r"-+", cells[0]):
                rows[cells[0]] = (index + 1, cells[1])
                continue
        elif line.strip() != "---":
            lead_lines.append(index + 1)
        dropped.append(index + 1)
    lead_text = " ".join(lines[n - 1] for n in lead_lines)
    head = lines.index("## Abstract", end)
    close = lines.index("---", head)
    abstract = " ".join(" ".join(lines[head + 1 : close]).split())

    blocks: list[MBlock] = []
    i, n = close + 1, len(lines)
    appendix = False
    generated: list[int] = []
    inside_generated = False
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            figure = FIGURE_BEGIN.match(stripped)
            if stripped == FOOTNOTE_BEGIN:
                j = lines.index(FOOTNOTE_END, i)
                blocks.append(MBlock("footnote", i + 2, j, "\n".join(lines[i + 1 : j])))
                i = j + 1
                continue
            if figure:
                j = lines.index(FIGURE_END, i)
                raw = "\n".join(lines[i + 1 : j]).strip()
                label = re.match(r"^\*\*Figure (\d+)\.\*\*\s+", raw)
                if not label:
                    raise ValueError(f"line {i + 2}: a figure caption does not open with its label")
                blocks.append(
                    MBlock(
                        "figure",
                        i + 2,
                        j,
                        raw,
                        name=figure.group(1),
                        caption=raw[label.end() :],
                        number=int(label.group(1)),
                    )
                )
                i = j + 1
                continue
            if stripped == REFS_BEGIN:
                j = lines.index(REFS_END, i)
                blocks.append(MBlock("references", i + 1, j + 1, "\n".join(lines[i : j + 1])))
                i = j + 1
                while i < n and not lines[i].strip():
                    i += 1
                k = i
                while k < n and lines[k].strip():
                    k += 1
                blocks.append(MBlock("note", i + 1, k, "\n".join(lines[i:k])))
                i = k
                continue
            if stripped == APPENDIX:
                appendix = True
            if GENERATED_BEGIN.match(stripped):
                inside_generated = True
                generated.append(i + 1)
            if GENERATED_END.match(stripped):
                inside_generated = False
                generated.append(i + 1)
            blocks.append(MBlock("marker", i + 1, i + 1, stripped))
            i += 1
            continue
        if stripped == "---":
            blocks.append(MBlock("rule", i + 1, i + 1, line))
            i += 1
            continue
        if stripped.startswith("```"):
            j = i + 1
            while j < n and not lines[j].strip().startswith("```"):
                j += 1
            blocks.append(
                MBlock(
                    "code",
                    i + 1,
                    j + 1,
                    "\n".join(lines[i + 1 : j]),
                    generated=inside_generated,
                    appendix=appendix,
                )
            )
            i = j + 1
            continue
        heading = re.match(r"^(#{2,}) (.+?)\s*$", line)
        if heading:
            blocks.append(
                MBlock(
                    "heading",
                    i + 1,
                    i + 1,
                    heading.group(2),
                    level=len(heading.group(1)) - 1,
                    generated=inside_generated,
                    appendix=appendix,
                )
            )
            i += 1
            continue
        if stripped.startswith("|"):
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            table_rows = [_cells(row) for row in lines[i:j]]
            if len(table_rows) < 2 or not all(re.fullmatch(r":?-{3,}:?", c) for c in table_rows[1]):
                raise ValueError(f"line {i + 1}: a table without a separator row")
            k = j
            while k < n and not lines[k].strip():
                k += 1
            if k >= n or not lines[k].startswith("Table: "):
                raise ValueError(f"line {i + 1}: a table without a 'Table:' caption")
            m = k
            while m < n and lines[m].strip():
                m += 1
            caption = " ".join(lines[k:m])[len("Table: ") :]
            blocks.append(
                MBlock(
                    "table",
                    i + 1,
                    j,
                    "\n".join(lines[i:j]),
                    number=sum(1 for b in blocks if b.kind == "table") + 1,
                    caption=caption,
                    caption_line=k + 1,
                    rows=[table_rows[0], *table_rows[2:]],
                    generated=inside_generated,
                    appendix=appendix,
                )
            )
            i = m
            continue
        item = re.match(r"^(?:[-+*]|\d+\.) ", line)
        if item:
            j = i + 1
            while j < n and lines[j].startswith("  ") and lines[j].strip():
                j += 1
            raw = "\n".join([line[item.end() :], *(row.strip() for row in lines[i + 1 : j])])
            blocks.append(
                MBlock("item", i + 1, j, raw, generated=inside_generated, appendix=appendix)
            )
            i = j
            continue
        j = i + 1
        while (
            j < n
            and lines[j].strip()
            and not re.match(r"^(?:#|\||```|<!--|(?:[-+*]|\d+\.) )", lines[j].strip())
            and lines[j].strip() != "---"
        ):
            j += 1
        blocks.append(
            MBlock(
                "para",
                i + 1,
                j,
                "\n".join(lines[i:j]),
                generated=inside_generated,
                appendix=appendix,
            )
        )
        i = j
    ai = [b for b in blocks if b.kind == "footnote"]
    note = [b for b in blocks if b.kind == "note"]
    if len(ai) != 1 or len(note) != 1:
        raise ValueError(
            "main.md must carry one AI-disclosure block and one note after the references"
        )
    if len(generated) % 2:
        raise ValueError("a generated block is never closed")
    manuscript = Manuscript(
        text,
        title,
        rows,
        (lead_lines[0] if lead_lines else 0, lead_lines[-1] if lead_lines else 0, lead_text),
        dropped,
        abstract,
        (head + 2, close),
        blocks,
        ai[0],
        note[0],
        [],
        (generated[0], generated[-1]) if generated else (0, 0),
    )
    manuscript.cites = find_cites(manuscript, refs)
    return manuscript


def _forms(item: dict[str, Any]) -> list[str]:
    """How the prose may name an entry's authors before its marker, from the entry itself."""
    names = [a.get("family") or a.get("literal") for a in item["author"]]
    cut = item.get("x-cds", {}).get("et-al-after")
    shown, et_al = (names[:cut], True) if cut else (names, False)
    forms = [f"{shown[0]} and colleagues", f"{shown[0]} et al."]
    if len(shown) == 1 and not et_al:
        forms.append(shown[0])
    elif not et_al:
        forms.append(", ".join(shown[:-1]) + " and " + shown[-1])
    return forms


def find_cites(manuscript: Manuscript, refs: list[dict[str, Any]]) -> list[MCite]:
    text = manuscript.text
    by_id = {item["x-cds"]["n"]: item for item in refs}
    offsets = [0]
    for line in text.split("\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    blanked = _blank_code(text)
    out: list[MCite] = []
    for index, block in enumerate(manuscript.blocks):
        if block.kind not in ("para", "item", "heading", "figure", "table"):
            continue
        a, b = offsets[block.line - 1], offsets[block.last]
        for match in re.finditer(r"\[(\d+(?:, \d+)*)\]", blanked[a:b]):
            start, finish = a + match.start(), a + match.end()
            if block.kind in ("table", "figure"):
                raise ValueError(
                    f"line {block.line}: a citation in a table or a figure caption is not handled"
                )
            ids = tuple(int(x) for x in match.group(1).split(", "))
            before = " ".join(text[max(0, start - 120) : start].split()) + " "
            mode, form = "citep", ""
            if len(ids) == 1 and ids[0] in by_id:
                for candidate in _forms(by_id[ids[0]]):
                    if before.endswith(" " + candidate + " ") or before.endswith(
                        "*" + candidate + " "
                    ):
                        mode, form = "citeyearpar", candidate
                        break
            paragraph = blanked[a:start]
            kind, removed, prefix, suffix = "parenthetical", "", "", ""
            cut_from, cut_to = start, finish
            if form:
                words = r"\s+".join(re.escape(x) for x in form.split())
                found = re.search(r"(?<=[\s*])" + words + r"\s+$", text[a:start])
                if not found:
                    raise ValueError(f"line {block.line}: cannot locate {form!r} before the marker")
                kind, removed, cut_from = "narrative", form, a + found.start()
            if paragraph.count("(") > paragraph.count(")"):
                opening = a + paragraph.rfind("(")
                depth, close = 1, finish
                while close < b and depth:
                    depth += {"(": 1, ")": -1}.get(blanked[close], 0)
                    close += 1
                kind = "in-parentheses"
                prefix = " ".join(text[opening + 1 : start].split())
                suffix = " ".join(text[finish : close - 1].split())
                cut_from, cut_to = opening, close
            out.append(
                MCite(
                    len(out) + 1,
                    text.count("\n", 0, start) + 1,
                    ids,
                    kind,
                    removed,
                    prefix,
                    suffix,
                    " ".join(before.split()[-4:]),
                    mode,
                    cut_from,
                    cut_to,
                    index,
                )
            )
    return out


# --------------------------------------------------------------------------------------------------
# The .docx, read from its XML


@dataclass
class DPara:
    index: int
    style: str
    runs: list[tuple[str, str]]  # (text, character style)
    images: list[str]  # relationship identifiers of embedded pictures
    bookmarks: list[str]
    links: list[tuple[str, str]] = field(default_factory=list)  # (relationship id, displayed text)

    @property
    def text(self) -> str:
        return "".join(t for t, _ in self.runs)


@dataclass
class DTable:
    index: int
    rows: list[list[DPara]]
    bookmarks: list[str]


@dataclass
class Docx:
    blocks: list[DPara | DTable]
    media: dict[str, str]  # relationship id -> sha256 of the part it targets
    links: dict[str, str]  # relationship id -> target of an external hyperlink
    footnotes: list[str]
    parts: dict[str, bytes]
    bookmarks: list[str]  # every bookmark name of the body, in order, wherever it stands
    problems: list[Problem] = field(default_factory=list)  # what the reader could not account for
    break_count: int = 0  # paragraphs in the style Page Break, wherever they stand


def _style_names(parts: dict[str, bytes]) -> dict[str, str]:
    names: dict[str, str] = {}
    if "word/styles.xml" in parts:
        for style in ET.fromstring(parts["word/styles.xml"]).iter(w("style")):
            name = style.find(w("name"))
            names[style.get(w("styleId"), "")] = name.get(w("val"), "") if name is not None else ""
    return names


#: The only elements the body of the ``.docx`` may hold, by parent: what pandoc writes for this
#: manuscript, and nothing else. An element outside this list is reported, not read through and not
#: skipped -- a content control, alternate content, an equation, a symbol, a field, a tracked change
#: or an imported document each carried text past an earlier version of this check (Codex reviews
#: of 2026-10-04).
ALLOWED: dict[str, frozenset[str]] = {
    "body": frozenset({"p", "tbl", "bookmarkStart", "bookmarkEnd", "sectPr"}),
    "p": frozenset({"pPr", "r", "hyperlink", "bookmarkStart", "bookmarkEnd"}),
    "hyperlink": frozenset({"r"}),
    "r": frozenset({"rPr", "t", "drawing", "br"}),
    "tbl": frozenset({"tblPr", "tblGrid", "tr"}),
    "tr": frozenset({"trPr", "tc"}),
    "tc": frozenset({"tcPr", "p"}),
}
_CONTAINERS = frozenset({"p", "hyperlink", "r", "tbl", "tr", "tc"})
#: What each property element may hold, by the same rule: what pandoc writes, so that no merged
#: cell, row height, colour, section break or other property can change what a reader sees while
#: the text stays the same (Codex review of 2026-10-04: a header cell spanning two columns and a row
#: one twip high both passed). A property listed here holds only the listed children; any other
#: property is a leaf.
PROPERTIES: dict[str, frozenset[str]] = {
    "pPr": frozenset({"pStyle", "numPr"}),
    "numPr": frozenset({"ilvl", "numId"}),
    "rPr": frozenset({"rStyle", "b", "bCs", "i", "iCs"}),
    "tblPr": frozenset({"tblStyle", "tblW", "tblLayout", "tblLook"}),
    "trPr": frozenset({"tblHeader"}),
    "tcPr": frozenset(),
    "tblGrid": frozenset({"gridCol"}),
    "sectPr": frozenset({"headerReference", "footerReference", "pgSz", "pgMar"}),
}
_HIDING = ("vanish", "specVanish", "webHidden")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
#: The attributes the body's elements may carry, as pandoc writes them, by element; an element not
#: listed carries none. The table's properties and the picture are matched as wholes, and the section
#: with the reference document's. A text node's spaces are kept only by ``xml:space="preserve"``,
#: and no other value is allowed (Codex review of 2026-10-04: "default" passed, letting a reader drop
#: the spaces between words).
BODY_ATTRIBUTES: dict[str, frozenset[str]] = {
    "bookmarkStart": frozenset({w("id"), w("name")}),
    "bookmarkEnd": frozenset({w("id")}),
    "gridCol": frozenset({w("w")}),
    "hyperlink": frozenset({f"{{{R}}}id"}),
    "ilvl": frozenset({w("val")}),
    "numId": frozenset({w("val")}),
    "pStyle": frozenset({w("val")}),
    "rStyle": frozenset({w("val")}),
    "tblHeader": frozenset({w("val")}),
    "t": frozenset({XML_SPACE}),
    "br": frozenset({w("type")}),
}
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
#: A picture as pandoc writes one, element by element and attribute by attribute: a rectangle,
#: stretched over its frame, with no cropping, turning, mirroring or effect, and no text. ``*`` takes
#: any value (an identifier, a name, alternative text the page does not show); ``=cx`` and ``=cy``
#: take the picture's size, which the frame and the picture inside it must share (Codex reviews of
#: 2026-10-04: a picture cropped to its last tenth, made transparent, mirrored, turned, or squeezed
#: into a tenth of its frame each passed, since the embedded PNG was unchanged).
PICTURE = ET.fromstring(
    f'<w:drawing xmlns:w="{W}" xmlns:wp="{WP}" xmlns:a="{A}" xmlns:pic="{PIC}" xmlns:r="{R}">'
    '<wp:inline><wp:extent cx="=cx" cy="=cy"/><wp:effectExtent b="0" l="0" r="0" t="0"/>'
    '<wp:docPr descr="*" title="*" id="*" name="*"/>'
    f'<a:graphic><a:graphicData uri="{PIC}"><pic:pic><pic:nvPicPr><pic:cNvPr descr="*" id="*" name="*"/>'
    '<pic:cNvPicPr><a:picLocks noChangeArrowheads="1" noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>'
    '<pic:blipFill><a:blip r:embed="*"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
    '<pic:spPr bwMode="auto"><a:xfrm><a:off x="0" y="0"/><a:ext cx="=cx" cy="=cy"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>'
    '<a:ln w="9525"><a:noFill/><a:headEnd/><a:tailEnd/></a:ln></pic:spPr></pic:pic>'
    "</a:graphicData></a:graphic></wp:inline></w:drawing>"
)


#: A table's properties as pandoc writes them: the full width of the text, laid out by its grid, the
#: first row the heading. And the grid within the text: no column narrower than a fifth of an inch,
#: and all of them within the 6.5 inches between the margins: a table wider than the page, or a
#: column too narrow to read, changes what a reader sees while the text stays the same (found while
#: closing the fifth Codex review of 2026-10-04).
TABLE = ET.fromstring(
    f'<w:tblPr xmlns:w="{W}"><w:tblStyle w:val="Table"/><w:tblW w:type="pct" w:w="5000"/>'
    '<w:tblLayout w:type="fixed"/><w:tblLook w:firstRow="1" w:lastRow="0" w:firstColumn="0" '
    'w:lastColumn="0" w:noHBand="0" w:noVBand="0" w:val="0020"/></w:tblPr>'
)
NARROWEST, TEXT_WIDTH = 288, 9360  # twentieths of a point
#: The height of the text area (the reference document's letter page less its margins), and the
#: drawing unit (EMU) in twentieths of a point.
TEXT_HEIGHT, EMU_PER_TWIP = 12960, 635


def _matches(element: ET.Element, template: ET.Element, bound: dict[str, str]) -> bool:
    """``element`` has ``template``'s form: the same elements, attributes and values, and no text."""
    if (
        element.tag != template.tag
        or set(element.attrib) != set(template.attrib)
        or len(element) != len(template)
        or (element.text or "").strip()
        or (element.tail or "").strip()
    ):
        return False
    for key, want in template.attrib.items():
        got = element.attrib[key]
        if want.startswith("="):
            if bound.setdefault(want, got) != got:
                return False
        elif want != "*" and got != want:
            return False
    return all(_matches(a, b, bound) for a, b in zip(element, template, strict=True))


def _local(tag: str) -> str:
    return tag[len(W) + 2 :] if tag.startswith("{" + W + "}") else tag


def _on(element: ET.Element | None) -> bool:
    """A toggle property that is present and not switched off."""
    return element is not None and element.get(w("val"), "true") not in ("0", "false", "off")


def validate_body(body: ET.Element) -> list[Problem]:
    """Every element and property of the body against :data:`ALLOWED` and :data:`PROPERTIES`."""
    problems: list[Problem] = []
    unread: list[str] = []
    properties: list[str] = []
    attributed: list[str] = []

    def attributes(element: ET.Element, name: str) -> None:
        odd = set(element.attrib) - BODY_ATTRIBUTES.get(name, frozenset())
        if odd or element.get(XML_SPACE, "preserve") != "preserve":
            attributed.append(f"{name} {sorted(_local(k) for k in element.attrib)}")
        # A list's number as pandoc writes it: "00" is the number 0 to a reader, and removes the
        # list's numbering, but not to a lookup by name (Codex review of 2026-10-04).
        if name in ("numId", "ilvl") and not CANONICAL.fullmatch(element.get(w("val"), "")):
            attributed.append(f"{name} {element.get(w('val'))!r}")

    def props(element: ET.Element, kind: str) -> None:
        # A property given twice (two paragraph styles, say) is read here as the first and may be
        # read by Word as the last; a grid's columns and the section (compared with the reference
        # document's) excepted (found while closing the eighth Codex review of 2026-10-04).
        if kind not in ("tblGrid", "sectPr"):
            twice = collections.Counter(_local(child.tag) for child in element)
            properties.extend(f"{name} twice in {kind}" for name, n in twice.items() if n > 1)
        for child in element:
            name = _local(child.tag)
            if kind not in ("tblPr", "sectPr") and name in PROPERTIES[kind]:
                attributes(child, name)
            if name in _HIDING or name == "pageBreakBefore":
                continue  # reported as hidden text and as a page break, below
            if kind == "pPr" and name == "sectPr":
                problems.append(
                    Problem("structure", "page breaks", "a section break in a paragraph")
                )
                continue
            if name not in PROPERTIES[kind]:
                properties.append(f"{name} in {kind}")
            elif name in PROPERTIES:
                props(child, name)
            elif len(child):
                properties.append(f"children of {name}")

    def walk(element: ET.Element, kind: str) -> None:
        for child in element:
            name = _local(child.tag)
            if name not in ALLOWED[kind]:
                unread.append(f"{name} in {kind}")
                continue
            if name not in ("drawing", "sectPr", "tblPr"):
                attributes(child, name)
            if name in PROPERTIES:
                props(child, name)
                continue
            if name == "br" and child.get(w("type"), "textWrapping") != "textWrapping":
                problems.append(
                    Problem("structure", "page breaks", "a page or column break inside a paragraph")
                )
            if name == "drawing" and not _matches(child, PICTURE, {}):
                problems.append(
                    Problem("structure", "pictures", "a picture not of the form pandoc writes")
                )
            if name == "tbl":
                columns = len(child.findall(f"{w('tblGrid')}/{w('gridCol')}"))
                if any(len(row.findall(w("tc"))) != columns for row in child.findall(w("tr"))):
                    problems.append(
                        Problem(
                            "structure", "table grid", "a table whose rows do not fill its grid"
                        )
                    )
                widths = [_int(g.get(w("w"))) for g in child.iter(w("gridCol"))]
                table_props = child.find(w("tblPr"))
                if (
                    table_props is None
                    or not _matches(table_props, TABLE, {})
                    or not widths
                    or min(widths) < NARROWEST
                    or sum(widths) > TEXT_WIDTH
                ):
                    problems.append(
                        Problem(
                            "structure",
                            "table layout",
                            f"a table not laid out as pandoc lays one out: columns {widths}",
                        )
                    )
            if name == "tc":
                # A cell of a pipe table is one paragraph in the Compact style, as pandoc writes it:
                # the comparison joins a cell's paragraphs, so a cell set as a paragraph a word
                # (Codex review of 2026-10-04: 107 of them, a row pages long, passed) or in another
                # style (the Title's two inches above it) shows what the words compared do not.
                paragraphs = child.findall(w("p"))
                style = paragraphs[0].find(f"{w('pPr')}/{w('pStyle')}") if paragraphs else None
                if len(paragraphs) != 1 or style is None or style.get(w("val")) != "Compact":
                    cells.append(len(paragraphs))
            if name in _CONTAINERS:
                walk(child, name)

    cells: list[int] = []
    walk(body, "body")
    if cells:
        problems.append(
            Problem(
                "structure",
                "table cells",
                f"{len(cells)} table cells not one paragraph in the Compact style "
                f"(paragraphs: {sorted(set(cells))[:4]})",
            )
        )
    if unread:
        problems.append(
            Problem(
                "structure",
                "unread content",
                "elements outside what the .docx may hold: " + ", ".join(sorted(set(unread))[:6]),
            )
        )
    if properties:
        problems.append(
            Problem(
                "structure",
                "properties",
                "properties outside what the .docx may carry: "
                + ", ".join(sorted(set(properties))[:6]),
            )
        )
    if attributed:
        problems.append(
            Problem(
                "structure",
                "attributes",
                "attributes outside what the .docx may carry: "
                + ", ".join(sorted(set(attributed))[:6]),
            )
        )
    if any(_local(e.tag) in _HIDING and _on(e) for e in body.iter()):
        problems.append(Problem("structure", "hidden text", "text hidden by direct formatting"))
    if any(_local(e.tag) == "pageBreakBefore" for e in body.iter()):
        problems.append(Problem("structure", "page breaks", "a page break set on a paragraph"))
    return problems


#: The paragraph styles that may break the page before themselves.
BREAKING_STYLES = frozenset({"Page Break", "Abstract Title", "Title Repeat"})


def _on_attr(value: str | None) -> bool:
    """An attribute toggle (``w:default``, say) that is present and not switched off."""
    return value is not None and value not in ("0", "false", "off")


#: A number as pandoc writes one: no sign, no leading zero, nothing around it.
CANONICAL = re.compile(r"0|[1-9][0-9]*")


def _int(value: str | None) -> int:
    """An XML integer as a reader takes it (a sign and white space around it allowed), or 0.

    Python's ``int`` would also take "1_0" as ten; a reader would not.
    """
    text = (value or "").strip()
    return int(text) if re.fullmatch(r"[+-]?[0-9]+", text) else 0


def _name(style: ET.Element) -> str:
    name = style.find(w("name"))
    return name.get(w("val"), "") if name is not None else ""


class Sheet:
    """The styles of a ``.docx``, by identifier, with what each inherits."""

    def __init__(self, data: bytes | None) -> None:
        self.root = ET.fromstring(data) if data else ET.Element(w("styles"))
        self.by_id: dict[str, ET.Element] = {}
        self.default: dict[str, str] = {}  # type -> the identifier of that type's default style
        for style in self.root.findall(w("style")):
            self.by_id.setdefault(style.get(w("styleId"), ""), style)
            if _on_attr(style.get(w("default"))):
                self.default.setdefault(style.get(w("type"), ""), style.get(w("styleId"), ""))

    def chain(self, style_id: str) -> list[ET.Element]:
        """The style and those it is based on, nearest first; a loop or a missing style ends it."""
        out: list[ET.Element] = []
        seen: set[str] = set()
        while style_id in self.by_id and style_id not in seen:
            seen.add(style_id)
            out.append(self.by_id[style_id])
            based = self.by_id[style_id].find(w("basedOn"))
            style_id = based.get(w("val"), "") if based is not None else ""
        return out

    def nearest(self, style_ids: list[str], path: str, attribute: str) -> str | None:
        """The value of ``attribute`` on the nearest ``path`` that sets it, through the styles in the
        order Word applies them (the first identifier wins), and then the document defaults.

        Each attribute is inherited on its own: a style that sets only the rule of the line takes
        the line's height from further up (Codex review of 2026-10-04: an exact rule set alone on
        the Figure Image style, under the defaults' line of 24 points, passed, as the rule was read
        only beside the height). A property given twice is reported by :func:`_style_properties`.
        """
        kind = path.split("}", 1)[1].split("{", 1)[0].rstrip("/")  # rPr or pPr
        places = [s for style_id in style_ids for s in self.chain(style_id)]
        places += self.root.findall(f"{w('docDefaults')}/{w(kind + 'Default')}")
        for place in places:
            for found in place.findall(path):
                if found.get(w(attribute)) is not None:
                    return found.get(w(attribute))
        return None


def validate_styles(sheet: Sheet, body: ET.Element) -> tuple[list[Problem], set[str]]:
    """No style hides its text, each has one identity, and exactly the expected styles break the page.

    The check reads paragraphs by their style names, so what a style does is part of what it checks
    (Codex reviews of 2026-10-04: hiding the Body Text style, taking the break off Page Break, turning
    it off with ``w:val="0"``, basing another style on Page Break, or setting a copy of Page Break,
    under its name, before the original whose break was then switched off, each passed). Whether a
    style breaks the page is resolved through its ``basedOn`` chain and the paragraph defaults, and
    the identifiers of the styles that do are returned, so that the paragraphs that break the page
    are counted by what their style does, not by its name.
    """
    problems: list[Problem] = []
    root = sheet.root
    if any(_local(e.tag) in _HIDING and _on(e) for e in root.iter()):
        problems.append(Problem("structure", "hidden text", "a style or the defaults hide text"))
    styles = root.findall(w("style"))
    ids = collections.Counter(s.get(w("styleId"), "") for s in styles)
    names = collections.Counter(_name(s).casefold() for s in styles)
    twice = sorted({k for k, n in ids.items() if n > 1} | {k for k, n in names.items() if n > 1})
    if twice:
        problems.append(
            Problem(
                "structure", "styles", f"styles that share an identifier or a name: {twice[:4]}"
            )
        )
    default_break = _on(
        root.find(f"{w('docDefaults')}/{w('pPrDefault')}/{w('pPr')}/{w('pageBreakBefore')}")
    )

    def breaks(style_id: str) -> bool:
        for style in sheet.chain(style_id):
            own = style.find(f"{w('pPr')}/{w('pageBreakBefore')}")
            if own is not None:
                return _on(own)
        return default_break

    breaking = {
        style_id
        for style_id, style in sheet.by_id.items()
        if style.get(w("type")) == "paragraph" and breaks(style_id)
    }
    named = {_name(sheet.by_id[style_id]) or style_id for style_id in breaking}
    if named != BREAKING_STYLES or default_break:
        problems.append(
            Problem(
                "structure",
                "page breaks",
                f"the styles that break the page are {sorted(named)}, not {sorted(BREAKING_STYLES)}",
            )
        )
    problems += _style_properties(sheet, body)
    return problems, breaking


#: What the styles the body uses, and the document defaults, may carry, by parent: the few
#: properties a readable page needs, which are those ``reference.docx`` sets (Codex review of
#: 2026-10-04: Body Text set in white passed). A property listed here holds only the listed
#: children; any other is a leaf. Hiding and page breaks are reported on their own, above.
STYLE_PROPERTIES: dict[str, frozenset[str]] = {
    "style": frozenset(
        {
            "name",
            "basedOn",
            "next",
            "link",
            "qFormat",
            "semiHidden",
            "unhideWhenUsed",
            "uiPriority",
            "pPr",
            "rPr",
            "tblPr",
            "trPr",
            "tcPr",
            "tblStylePr",
        }
    ),
    "docDefaults": frozenset({"rPrDefault", "pPrDefault"}),
    "rPrDefault": frozenset({"rPr"}),
    "pPrDefault": frozenset({"pPr"}),
    "pPr": frozenset(
        {"ind", "jc", "keepNext", "keepLines", "outlineLvl", "spacing", "widowControl"}
    ),
    "rPr": frozenset({"rFonts", "b", "bCs", "i", "iCs", "sz", "szCs", "color", "lang"}),
    "tblPr": frozenset({"tblInd", "tblBorders", "tblCellMar"}),
    "tblBorders": frozenset({"top", "bottom", "left", "right", "insideH", "insideV"}),
    "tblCellMar": frozenset({"top", "bottom", "left", "right"}),
    # The heading row's conditional formatting (``w:type="firstRow"``, the only kind allowed), which
    # sets it in bold with a rule beneath: what applies to a row is not read into the sizes and
    # lines below, so it may carry nothing that changes them (Codex review of 2026-10-04: a heading
    # row set at one point, and one in an exact line of a twentieth of a point, each passed).
    "tblStylePr": frozenset({"rPr", "tcPr"}),
    "tblStylePr/rPr": frozenset({"b", "bCs"}),
    "trPr": frozenset({"cantSplit"}),
    "tcPr": frozenset({"tcBorders", "vAlign"}),
    "tcBorders": frozenset({"top", "bottom", "left", "right", "insideH", "insideV"}),
}
#: The colours text may be set in: black, and the blue of a link.
COLOURS = frozenset(
    {(("val", "auto"),), (("val", "000000"),), (("themeColor", "accent1"), ("val", "4F81BD"))}
)
#: The faces text may be set in: the text's and the code's.
FONTS = frozenset({"Times New Roman", "Courier New"})
#: The smallest size text may be set at, in half-points (8 pt), and the least exact line (12 pt).
SMALLEST, LEAST_LINE = 16, 240
#: The deepest indent and the widest gap before or after a paragraph a style may set, in twentieths
#: of a point (one inch and two inches; reference.docx sets at most half an inch and two inches),
#: and lines set no closer than single: a style can otherwise push text off the page, open pages
#: of nothing between paragraphs, or lay its lines over one another.
DEEPEST_INDENT, WIDEST_GAP = 1440, 2880
#: The widest line, in 240ths of a line for "auto" (double spacing, as the defaults set) and in
#: twentieths of a point for an exact or least line (36 pt); the largest size, in half-points
#: (24 pt; the styles the body uses set at most 12); and the widest table indent and cell margin
#: (a fifth of an inch). Codex review of 2026-10-04: a gap of a thousand lines (beforeLines) and
#: a line of 417 lines each passed, as no upper bound held them.
WIDEST_LINE, TALLEST_LINE, LARGEST, WIDEST_MARGIN = 480, 720, 48, 288


def _spacing_odd(spacing: dict[str, str]) -> bool:
    """A paragraph style's spacing a readable page does not have: an attribute other than the gap
    before and after and the line (``beforeLines`` and the rest are not read here), a rule other
    than Word's three, or a gap over :data:`WIDEST_GAP`. The line is bounded where it takes effect,
    in :func:`_style_properties`, as its height and its rule are each inherited on their own."""
    return bool(
        set(spacing) - {"before", "after", "line", "lineRule"}
        or spacing.get("lineRule", "auto") not in ("auto", "exact", "atLeast")
        or any(not 0 <= _int(spacing.get(k)) <= WIDEST_GAP for k in ("before", "after"))
    )


def _style_properties(sheet: Sheet, body: ET.Element) -> list[Problem]:
    """The styles the body uses carry only :data:`STYLE_PROPERTIES`, in :data:`COLOURS` and
    :data:`FONTS`, with indents and gaps within :data:`DEEPEST_INDENT` and :data:`WIDEST_GAP` and no
    line closer than single; and no text or picture is set below :data:`SMALLEST` or in an exact
    line under :data:`LEAST_LINE` (the spacer styles, Page Break and After Table, are both, and hold
    nothing)."""
    odd: list[str] = []
    used = {
        e.get(w("val"), "") for tag in ("pStyle", "rStyle", "tblStyle") for e in body.iter(w(tag))
    }
    odd += [
        f"the style {u!r}, which the .docx does not define" for u in sorted(used - set(sheet.by_id))
    ]
    closure = {
        id(style): style
        for style_id in used | set(sheet.default.values())
        for style in sheet.chain(style_id)
    }

    def walk(element: ET.Element, kind: str) -> None:
        # A property given twice is read by this check as the first, and may be read by Word as the
        # last (found while closing the eighth Codex review of 2026-10-04).
        twice = collections.Counter(_local(child.tag) for child in element)
        odd.extend(f"{name} twice in {kind}" for name, n in twice.items() if n > 1)
        for child in element:
            name = _local(child.tag)
            if name in _HIDING or name == "pageBreakBefore":
                continue
            attributes = tuple(sorted((_local(k), v) for k, v in child.attrib.items()))
            inner = f"{kind}/{name}" if f"{kind}/{name}" in STYLE_PROPERTIES else name
            if name not in STYLE_PROPERTIES[kind]:
                odd.append(f"{name} in {kind}")
            elif name == "tblStylePr" and attributes != (("type", "firstRow"),):
                odd.append(f"the conditional formatting {dict(attributes)}")
            elif inner in STYLE_PROPERTIES:
                walk(child, inner)
            elif len(child):
                odd.append(f"children of {name}")
            elif name == "color" and attributes not in COLOURS:
                odd.append(f"the colour {dict(attributes)}")
            elif name == "rFonts" and any(
                k not in ("ascii", "hAnsi", "eastAsia", "cs", "hint")
                or (k != "hint" and v not in FONTS)
                for k, v in attributes
            ):
                odd.append(f"the face {dict(attributes)}")
            elif name == "ind" and any(
                k not in ("left", "right", "hanging", "firstLine")
                or not 0 <= _int(v) <= DEEPEST_INDENT
                for k, v in attributes
            ):
                odd.append(f"the indent {dict(attributes)}")
            elif name == "spacing" and kind == "pPr" and _spacing_odd(dict(attributes)):
                odd.append(f"the spacing {dict(attributes)}")
            elif name in ("sz", "szCs") and _int(child.get(w("val"))) > LARGEST:
                odd.append(f"the size {dict(attributes)}")
            elif (kind == "tblCellMar" or name == "tblInd") and (
                set(dict(attributes)) != {"w", "type"}
                or dict(attributes)["type"] != "dxa"
                or not 0 <= _int(dict(attributes)["w"]) <= WIDEST_MARGIN
            ):
                odd.append(f"the table's {name} {dict(attributes)}")

    for style in closure.values():
        walk(style, "style")
    defaults = sheet.root.find(w("docDefaults"))
    if defaults is not None:
        walk(defaults, "docDefaults")
    table_of: dict[int, str] = {}
    for table in body.iter(w("tbl")):
        style = table.find(f"{w('tblPr')}/{w('tblStyle')}")
        table_style = (
            style.get(w("val"), "") if style is not None else sheet.default.get("table", "")
        )
        table_of.update({id(p): table_style for p in table.iter(w("p"))})
    spacing = f"{w('pPr')}/{w('spacing')}"
    for paragraph in body.iter(w("p")):
        style = paragraph.find(f"{w('pPr')}/{w('pStyle')}")
        own = style.get(w("val"), "") if style is not None else sheet.default.get("paragraph", "")
        # A paragraph in a table is read with its own style over the table's and the other way
        # round, so that neither can hide what the other sets, whichever Word applies last.
        table = table_of.get(id(paragraph))
        for chain in [[own, table], [table, own]] if table is not None else [[own]]:
            # The height of the line and its rule, each inherited on its own (single spacing when
            # no style sets them), and bounded as they take effect together: an auto line within
            # single to double spacing, an exact or least one from nothing to TALLEST_LINE. Bounded
            # where each is set, a least line of 35 points under a rule "auto" set elsewhere spaced
            # lines nearly three apart, and a line of 417 under an exact rule, a page a line.
            rule = sheet.nearest(chain, spacing, "lineRule") or "auto"
            line = _int(sheet.nearest(chain, spacing, "line") or "240")
            if (rule == "auto" and not LEAST_LINE <= line <= WIDEST_LINE) or (
                rule != "auto" and not 0 <= line <= TALLEST_LINE
            ):
                odd.append(f"a paragraph set in a line of {line} ({rule})")
            exact = line if rule == "exact" else None
            for run in paragraph.iter(w("r")):
                shown = "".join(t.text or "" for t in run.iter(w("t"))).strip()
                picture = run.find(w("drawing")) is not None
                if not shown and not picture:
                    continue
                character = run.find(f"{w('rPr')}/{w('rStyle')}")
                size = sheet.nearest(
                    ([character.get(w("val"), "")] if character is not None else []) + chain,
                    f"{w('rPr')}/{w('sz')}",
                    "val",
                )
                points = _int(size) if size is not None else 20  # Word's own default
                # An exact line clips what is taller than it: a picture in any exact line (Codex
                # review of 2026-10-04: a figure in a 12-point exact line passed), text in one
                # under its size.
                clipped = exact is not None and (picture or exact < max(LEAST_LINE, points * 10))
                if clipped or points < SMALLEST:
                    odd.append(f"text or a picture set too small to read: {shown[:40]!r}")
    if odd:
        return [
            Problem(
                "structure",
                "styles",
                "what the styles the body uses may not carry: " + "; ".join(sorted(set(odd))[:4]),
            )
        ]
    return []


#: What a header or footer may hold: one paragraph with the page number field, and nothing else
#: (Codex reviews of 2026-10-04: an equation in the header, a field whose instruction quoted a
#: sentence while its cached result read "1", and the cached "1" left as plain text with the field
#: taken away, each passed).
HEADER_ALLOWED = frozenset(
    {"hdr", "ftr", "p", "pPr", "jc", "spacing", "r", "fldChar", "instrText", "t"}
)
PAGE_FIELD = [
    ("fldChar", "begin"),
    ("instrText", "PAGE"),
    ("fldChar", "separate"),
    ("t", "1"),
    ("fldChar", "end"),
]


def validate_header(name: str, data: bytes) -> list[Problem]:
    root = ET.fromstring(data)
    odd = sorted({_local(e.tag) for e in root.iter() if _local(e.tag) not in HEADER_ALLOWED})
    sequence = [
        (
            _local(node.tag),
            node.get(w("fldCharType"), "")
            if _local(node.tag) == "fldChar"
            else (node.text or "").strip(),
        )
        for run in root.iter(w("r"))
        for node in run
    ]
    if odd or len(root) != 1 or root[0].tag != w("p") or sequence != PAGE_FIELD:
        return [Problem("structure", "header", f"{name} holds {odd or sequence}")]
    return []


BULLET = chr(0x2022)
#: The bullets pandoc writes, each with the face that draws it as one; a label of any other form is
#: read as the text it is.
BULLETS = frozenset({(chr(0xF0B7), "Symbol"), ("o", "Courier New"), (chr(0xF0A7), "Wingdings")})
#: What ``numbering.xml`` may hold, by parent, as pandoc writes it: a property listed here holds only
#: the listed children, any other is a leaf.
NUMBERING: dict[str, frozenset[str]] = {
    "numbering": frozenset({"abstractNum", "num"}),
    "abstractNum": frozenset({"nsid", "multiLevelType", "lvl"}),
    "lvl": frozenset({"start", "numFmt", "lvlText", "lvlJc", "pPr", "rPr"}),
    "pPr": frozenset({"ind"}),
    "rPr": frozenset({"rFonts"}),
    "num": frozenset({"abstractNumId", "lvlOverride"}),
    "lvlOverride": frozenset({"startOverride"}),
}
#: The attributes each of them may carry, as pandoc writes them (Codex review of 2026-10-04:
#: ``w:null="1"`` on a level's text, which suppresses its label, passed).
NUMBERING_ATTRIBUTES: dict[str, frozenset[str]] = {
    "abstractNum": frozenset({"abstractNumId"}),
    "nsid": frozenset({"val"}),
    "multiLevelType": frozenset({"val"}),
    "lvl": frozenset({"ilvl"}),
    "start": frozenset({"val"}),
    "numFmt": frozenset({"val"}),
    "lvlText": frozenset({"val"}),
    "lvlJc": frozenset({"val"}),
    "ind": frozenset({"left", "hanging", "firstLine"}),
    "rFonts": frozenset({"ascii", "hAnsi", "cs", "eastAsia", "hint"}),
    "num": frozenset({"numId"}),
    "abstractNumId": frozenset({"val"}),
    "lvlOverride": frozenset({"ilvl"}),
    "startOverride": frozenset({"val"}),
}
#: The attributes that hold a number, which must be written as pandoc writes one (:data:`CANONICAL`).
NUMBERED = frozenset(
    {
        ("abstractNum", "abstractNumId"),
        ("num", "numId"),
        ("abstractNumId", "val"),
        ("lvl", "ilvl"),
        ("lvlOverride", "ilvl"),
        ("start", "val"),
        ("startOverride", "val"),
    }
)
#: The attribute that identifies each element of numbering.xml that may stand more than once.
IDENTIFIER = {"abstractNum": "abstractNumId", "num": "numId", "lvl": "ilvl", "lvlOverride": "ilvl"}
#: The labels main.md's list markers give, and so the only ones a list may draw: a bullet, or a
#: number and a period. Anything else, white space included, changes the page while the words
#: compared stay the same (Codex review of 2026-10-04: a label of 200 em spaces and a bullet passed,
#: and an empty one would indent a paragraph main.md does not list).
LABEL = re.compile(BULLET + r"|[1-9][0-9]*\.")


def _value(element: ET.Element | None, tag: str) -> str:
    found = element.find(w(tag)) if element is not None else None
    return found.get(w("val"), "") if found is not None else ""


def _start(level: ET.Element | None) -> int:
    return _int(_value(level, "start")) if level is not None else 0


def _label(definition: dict[int, ET.Element], level: int, count: dict[int, int]) -> str:
    """What Word draws before a paragraph at ``level`` of a list, at the counts ``count``."""
    lvl = definition[level]
    text = _value(lvl, "lvlText")
    face = lvl.find(f"{w('rPr')}/{w('rFonts')}")
    face_name = face.get(w("ascii")) if face is not None else None
    if _value(lvl, "numFmt") == "bullet":
        return BULLET if (text, face_name) in BULLETS else text

    def number(match: re.Match[str]) -> str:
        k = int(match.group(1)) - 1
        kind = _value(definition.get(k), "numFmt") or "decimal"
        n = count.get(k, _start(definition.get(k)))
        return str(n) if kind == "decimal" else f"({kind} {n})"

    label = re.sub(r"%([1-9])", number, text)
    return label if face is None else f"{label} (in {face_name})"


def list_labels(body: ET.Element, numbering: bytes | None) -> tuple[dict[int, str], list[Problem]]:
    """The label Word draws before each numbered paragraph of the body, by the paragraph's ``id()``.

    Numbering draws text of its own -- a bullet, a number, or whatever its level's ``w:lvlText``
    holds -- that is in no run (Codex review of 2026-10-04: a list level whose text read "The
    primary effect was 99.9 percent. %1" passed, unread). So the label is computed as Word counts --
    per abstract definition, a ``w:startOverride`` restarting its level at the first paragraph of its
    list, a level's count restarting under a shallower one -- and becomes part of the paragraph's
    text, which main.md's list markers give on the other side: a bullet pandoc writes reads as "•",
    a number as itself and a period, and anything else as the text it is -- and is reported, as a
    label must be one of :data:`LABEL`. What numbering.xml may hold beyond that is
    :data:`NUMBERING`.
    """
    labels: dict[int, str] = {}
    if numbering is None:
        return labels, []
    root = ET.fromstring(numbering)
    odd: list[str] = []

    def walk(element: ET.Element, kind: str) -> None:
        # Each element once, but the definitions, the lists, their levels and their overrides, each
        # under its own identifier: one given twice is read here as one copy and may be read by Word
        # as the other (found while closing the eighth Codex review of 2026-10-04).
        names = collections.Counter(_local(child.tag) for child in element)
        odd.extend(
            f"{name} twice in {kind}"
            for name, n in names.items()
            if n > 1 and name not in ("abstractNum", "num", "lvl", "lvlOverride")
        )
        ids = collections.Counter(
            (_local(child.tag), child.get(w(IDENTIFIER[_local(child.tag)])))
            for child in element
            if _local(child.tag) in IDENTIFIER
        )
        odd.extend(f"{name} {value!r} twice in {kind}" for (name, value), n in ids.items() if n > 1)
        for child in element:
            name = _local(child.tag)
            if {_local(k) for k in child.attrib} - NUMBERING_ATTRIBUTES.get(name, frozenset()):
                odd.append(f"the attributes of {name} {sorted(_local(k) for k in child.attrib)}")
            odd.extend(
                f"the number {value!r} of {name}"
                for key, value in child.attrib.items()
                if (name, _local(key)) in NUMBERED and not CANONICAL.fullmatch(value)
            )
            if name not in NUMBERING[kind]:
                odd.append(f"{name} in {kind}")
            elif name in NUMBERING:
                walk(child, name)
            elif len(child):
                odd.append(f"children of {name}")

    walk(root, "numbering")
    # Each level's label stands where pandoc sets it: its indent, the hanging part, and the alignment
    # (Codex review of 2026-10-04: left 0 with a hanging indent of 4.5 inches, which sets the label
    # off the page, passed, each value being within its own bound).
    for definition in root.findall(w("abstractNum")):
        for lvl in definition.findall(w("lvl")):
            level = _int(lvl.get(w("ilvl")))
            indent = lvl.find(f"{w('pPr')}/{w('ind')}")
            place = {_local(k): v for k, v in indent.attrib.items()} if indent is not None else {}
            if place != {"left": str(720 * (level + 1)), "hanging": "360"} or (
                _value(lvl, "lvlJc") != "left"
            ):
                odd.append(f"the place of level {level}'s label {place}")
    levels: dict[str, dict[int, ET.Element]] = {
        a.get(w("abstractNumId"), ""): {
            _int(lvl.get(w("ilvl"))): lvl for lvl in a.findall(w("lvl"))
        }
        for a in root.findall(w("abstractNum"))
    }
    lists: dict[str, tuple[str, dict[int, int]]] = {}
    for num in root.findall(w("num")):
        ref = num.find(w("abstractNumId"))
        restart = {
            _int(o.get(w("ilvl"))): _int(_value(o, "startOverride"))
            for o in num.findall(w("lvlOverride"))
            if o.find(w("startOverride")) is not None
        }
        lists[num.get(w("numId"), "")] = (ref.get(w("val"), "") if ref is not None else "", restart)
    counts: dict[str, dict[int, int]] = {}
    begun: set[tuple[str, int]] = set()
    for paragraph in body.iter(w("p")):
        numbered = paragraph.find(f"{w('pPr')}/{w('numPr')}")
        if numbered is None:
            continue
        list_id = _value(numbered, "numId")
        level = _int(_value(numbered, "ilvl"))
        if list_id == "0" or list_id not in lists or level not in levels.get(lists[list_id][0], {}):
            continue  # numId 0 removes numbering, and numbering that is not defined draws nothing
        abstract, restart = lists[list_id]
        definition, count = levels[abstract], counts.setdefault(abstract, {})
        if (list_id, level) not in begun and level in restart:
            count[level] = restart[level]
        elif level in count:
            count[level] += 1
        else:
            count[level] = _start(definition[level])
        begun.add((list_id, level))
        for deeper in [k for k in count if k > level]:
            del count[deeper]
        labels[id(paragraph)] = _label(definition, level, count)
        if not LABEL.fullmatch(labels[id(paragraph)]):
            odd.append(f"the label {labels[id(paragraph)][:24]!r}")
    if odd:
        return labels, [
            Problem(
                "structure",
                "numbering",
                "numbering outside what pandoc writes: " + ", ".join(sorted(set(odd))[:6]),
            )
        ]
    return labels, []


#: The parts pandoc writes for this document. Every other part is the reference document's, copied,
#: and must be its bytes (Codex review of 2026-10-04: a header renamed, with its relationship and
#: content type, passed with a sentence in it).
WRITTEN = frozenset(
    {
        "[Content_Types].xml",
        "_rels/.rels",
        "docProps/core.xml",
        "docProps/custom.xml",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/_rels/footnotes.xml.rels",
        "word/comments.xml",
        "word/footnotes.xml",
        "word/numbering.xml",
        "word/settings.xml",
        "word/styles.xml",
    }
)
#: The pictures, the only parts pandoc adds to the reference document's.
MEDIA = re.compile(r"word/media/[A-Za-z0-9_-]+\.png")
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS = "word/_rels/document.xml.rels"


def _canon(element: ET.Element) -> tuple[Any, ...]:
    """An element as a reader takes it: the order of its attributes and the white space between
    elements do not count."""
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or "").strip(),
        (element.tail or "").strip(),
        tuple(_canon(child) for child in element),
    )


def _same(a: bytes, b: bytes) -> bool:
    return _canon(ET.fromstring(a)) == _canon(ET.fromstring(b))


def _styles_against(mine: bytes, theirs: bytes, body: ET.Element) -> list[Problem]:
    """Every style of the reference document, and its defaults, as it has them; a style pandoc adds
    (the highlighting styles) is a character style that is no type's default and that nothing uses."""
    ours, reference = ET.fromstring(mine), ET.fromstring(theirs)
    odd: list[str] = []
    for kind in ("docDefaults", "latentStyles"):
        a, b = ours.find(w(kind)), reference.find(w(kind))
        if (a is None) != (b is None) or (
            a is not None and b is not None and _canon(a) != _canon(b)
        ):
            odd.append(kind)
    odd += [
        _local(c.tag) for c in ours if _local(c.tag) not in ("docDefaults", "latentStyles", "style")
    ]
    first: dict[str, ET.Element] = {}
    for style in ours.findall(w("style")):
        first.setdefault(style.get(w("styleId"), ""), style)
    given = {s.get(w("styleId"), ""): s for s in reference.findall(w("style"))}
    odd += [i for i, s in given.items() if i not in first or _canon(first[i]) != _canon(s)]
    used = {
        e.get(w("val"), "") for tag in ("pStyle", "rStyle", "tblStyle") for e in body.iter(w(tag))
    }
    used |= {
        e.get(w("val"), "")
        for style in ours.findall(w("style"))
        for tag in ("basedOn", "link", "next")
        for e in style.findall(w(tag))
    }
    for style in ours.findall(w("style")):
        style_id = style.get(w("styleId"), "")
        if style_id not in given and (
            style.get(w("type")) != "character"
            or _on_attr(style.get(w("default")))
            or style_id in used
        ):
            odd.append(style_id)
    if odd:
        return [
            Problem(
                "package",
                "word/styles.xml",
                f"styles that are not the reference document's: {odd[:4]}",
            )
        ]
    return []


def _settings_against(mine: bytes, theirs: bytes) -> list[Problem]:
    """Each setting is the reference document's; pandoc may leave one out, but adds and changes none."""
    given = {c.tag: c for c in ET.fromstring(theirs)}
    ours = list(ET.fromstring(mine))
    odd = [_local(c.tag) for c in ours if c.tag not in given or _canon(c) != _canon(given[c.tag])]
    if odd or len({c.tag for c in ours}) != len(ours):
        return [
            Problem(
                "package", "word/settings.xml", f"settings not the reference document's: {odd[:4]}"
            )
        ]
    return []


def _separators_against(mine: bytes, theirs: bytes) -> list[Problem]:
    """The footnote separators are the reference document's (a footnote of the text's own is
    reported with the Author Note)."""

    def separators(data: bytes) -> list[tuple[Any, ...]]:
        return sorted(
            _canon(n)
            for n in ET.fromstring(data).findall(w("footnote"))
            if n.get(w("type")) is not None
        )

    if separators(mine) != separators(theirs):
        return [Problem("package", "word/footnotes.xml", "separators not the reference document's")]
    return []


def _types_against(parts: dict[str, bytes], theirs: bytes) -> list[Problem]:
    """The reference document's content types, one for each picture, and a default only for an
    extension no part has."""

    def read(data: bytes) -> tuple[list[tuple[str, str]], list[tuple[str, str]], int]:
        root = ET.fromstring(data)
        defaults = [
            (d.get("Extension", "").lower(), d.get("ContentType", ""))
            for d in root.findall(f"{{{CT}}}Default")
        ]
        overrides = [
            (o.get("PartName", ""), o.get("ContentType", ""))
            for o in root.findall(f"{{{CT}}}Override")
        ]
        return defaults, overrides, len(root) - len(defaults) - len(overrides)

    defaults, overrides, other = read(parts["[Content_Types].xml"])
    given_defaults, given_overrides, _ = read(theirs)
    media = {("/" + n, "image/png") for n in parts if MEDIA.fullmatch(n)}
    extensions = {n.rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower() for n in parts}
    added = [d for d in set(defaults) - set(given_defaults) if d[0] in extensions]
    names = [name for name, _ in overrides]
    if (
        other
        or added
        or set(given_defaults) - set(defaults)
        or len(set(names)) != len(names)
        or set(overrides) != set(given_overrides) | media
    ):
        return [
            Problem("package", "[Content_Types].xml", "content types not the reference document's")
        ]
    return []


def _relationships_against(parts: dict[str, bytes], theirs: bytes) -> list[Problem]:
    """The reference document's relationships to the parts it gives, each picture once, as a part of
    the package, and each link external (Codex reviews of 2026-10-04: a picture's relationship marked
    external, and a link's not, each passed)."""
    ours, given = ET.fromstring(parts[RELS]), ET.fromstring(theirs)
    picture, link = f"{R}/image", f"{R}/hyperlink"

    def fixed(root: ET.Element) -> list[tuple[str, str, str]]:
        return sorted(
            (r.get("Type", ""), r.get("Target", ""), r.get("TargetMode", ""))
            for r in root
            if r.get("Type") not in (picture, link)
        )

    odd: list[str] = []
    ids = [r.get("Id", "") for r in ours]
    if len(set(ids)) != len(ids):
        odd.append("an identifier used twice")
    if fixed(ours) != fixed(given):
        odd.append("the relationships to the parts the reference document gives")
    pictures: collections.Counter[str] = collections.Counter()
    for rel in ours:
        target, mode = rel.get("Target", ""), rel.get("TargetMode", "")
        if rel.get("Type") == link and mode != "External":
            odd.append(f"a link not marked external: {target}")
        if rel.get("Type") == picture:
            pictures["word/" + target] += 1
            if (
                mode not in ("", "Internal")
                or not MEDIA.fullmatch("word/" + target)
                or "word/" + target not in parts
            ):
                odd.append(f"a picture not a part of the .docx: {target}")
    odd += [
        f"{n} is the target of {pictures[n]} relationships"
        for n in parts
        if MEDIA.fullmatch(n) and pictures[n] != 1
    ]
    if odd:
        return [Problem("package", RELS, "; ".join(odd[:4]))]
    return []


def _section(document: bytes, rels: bytes) -> tuple[Any, ...] | None:
    """The body's one section, last in the body, with each relationship named by its target."""
    body = ET.fromstring(document).find(w("body"))
    sections = body.findall(w("sectPr")) if body is not None else []
    if body is None or len(sections) != 1 or body[-1] is not sections[0]:
        return None
    targets = {r.get("Id"): r.get("Target") for r in ET.fromstring(rels)}
    section = copy.deepcopy(sections[0])
    for element in section.iter():
        rid = element.get(f"{{{R}}}id")
        if rid is not None:
            element.set(f"{{{R}}}id", f"-> {targets.get(rid)}")
    return _canon(section)


def validate_package(
    parts: dict[str, bytes], reference: dict[str, bytes], body: ET.Element
) -> list[Problem]:
    """The parts, the copied parts, the styles, settings, footnote separators, content types,
    relationships and section against the reference document (see the module's docstring)."""
    problems: list[Problem] = []
    extra = sorted(n for n in set(parts) - set(reference) if not MEDIA.fullmatch(n))
    missing = sorted(set(reference) - set(parts))
    if extra or missing:
        problems.append(
            Problem(
                "package",
                "parts",
                f"parts the reference document does not have {extra[:4]}, and parts of it missing {missing[:4]}",
            )
        )
    both = set(parts) & set(reference)
    for name in sorted(both - WRITTEN):
        if parts[name] != reference[name]:
            problems.append(Problem("package", name, "not the reference document's bytes"))
    # Which part is the document is the package's relationships' to say.
    if "_rels/.rels" in both and not _same(parts["_rels/.rels"], reference["_rels/.rels"]):
        problems.append(Problem("package", "_rels/.rels", "not the reference document's"))
    # pandoc gives the footnotes the document's links too; no footnote uses them, and they may be
    # nothing else.
    notes = "word/_rels/footnotes.xml.rels"
    if notes in parts and any(
        r.get("Type") != f"{R}/hyperlink" or r.get("TargetMode") != "External"
        for r in ET.fromstring(parts[notes])
    ):
        problems.append(Problem("package", notes, "relationships other than external links"))
    if "word/styles.xml" in both:
        problems += _styles_against(parts["word/styles.xml"], reference["word/styles.xml"], body)
    if "word/settings.xml" in both:
        problems += _settings_against(parts["word/settings.xml"], reference["word/settings.xml"])
    if "word/footnotes.xml" in both:
        problems += _separators_against(
            parts["word/footnotes.xml"], reference["word/footnotes.xml"]
        )
    if "[Content_Types].xml" in both:
        problems += _types_against(parts, reference["[Content_Types].xml"])
    if RELS in both:
        problems += _relationships_against(parts, reference[RELS])
    if {"word/document.xml", RELS} <= both:
        mine = _section(parts["word/document.xml"], parts[RELS])
        if mine is None or mine != _section(reference["word/document.xml"], reference[RELS]):
            problems.append(
                Problem(
                    "package",
                    "sectPr",
                    "the section's page and header are not the reference document's",
                )
            )
    return problems


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _runs(
    element: ET.Element,
    names: dict[str, str],
    runs: list[tuple[str, str]],
    images: list[str],
    links: list[tuple[str, str]],
) -> None:
    for child in element:
        name = _local(child.tag)
        if name == "r":
            style_el = child.find(f"{w('rPr')}/{w('rStyle')}")
            style = (
                names.get(style_el.get(w("val"), ""), style_el.get(w("val"), ""))
                if style_el is not None
                else ""
            )
            parts: list[str] = []
            for node in child:
                if node.tag == w("t"):
                    # Without xml:space="preserve", a reader drops the spaces at either end.
                    text = node.text or ""
                    parts.append(
                        text if node.get(XML_SPACE) == "preserve" else text.strip(" \t\r\n")
                    )
                elif node.tag == w("tab"):
                    parts.append("\t")
                elif node.tag == w("br") and node.get(w("type"), "textWrapping") == "textWrapping":
                    parts.append("\n")
                elif node.tag == w("drawing"):
                    for blip in node.iter(f"{{{A}}}blip"):
                        images.append(blip.get(f"{{{R}}}embed", ""))
            if parts:
                runs.append(("".join(parts), style))
        elif name == "hyperlink":
            inner: list[tuple[str, str]] = []
            _runs(child, names, inner, images, links)
            runs.extend(inner)
            links.append((child.get(f"{{{R}}}id", ""), "".join(t for t, _ in inner)))
        # Anything else is reported by validate_body and not read.


def _para(
    element: ET.Element,
    index: int,
    names: dict[str, str],
    bookmarks: list[str],
    labels: dict[int, str],
) -> DPara:
    style_el = element.find(f"{w('pPr')}/{w('pStyle')}")
    style_id = style_el.get(w("val"), "") if style_el is not None else ""
    style = names.get(style_id, style_id) if style_id else "Normal"
    runs: list[tuple[str, str]] = []
    images: list[str] = []
    links: list[tuple[str, str]] = []
    # The label numbering draws is the first text of the paragraph, as the page shows it.
    if labels.get(id(element)):
        runs.append((labels[id(element)] + "\t", LABEL_STYLE))
    _runs(element, names, runs, images, links)
    return DPara(index, style, runs, images, bookmarks, links)


def _table_rows(
    table: ET.Element, index: int, names: dict[str, str], labels: dict[int, str]
) -> list[list[DPara]]:
    rows = []
    for row in table.findall(w("tr")):
        cells = []
        for cell in row.findall(w("tc")):
            paragraphs = [_para(p, index, names, [], labels) for p in cell.findall(w("p"))]
            runs = [r for p in paragraphs for r in [*p.runs, (" ", JOIN_STYLE)]]
            cells.append(
                DPara(
                    index,
                    "cell",
                    runs[:-1] if runs else [],
                    [i for p in paragraphs for i in p.images],
                    [],
                    [link for p in paragraphs for link in p.links],
                )
            )
        rows.append(cells)
    return rows


def _part_text(data: bytes) -> str:
    return "".join(t.text or "" for t in ET.fromstring(data).iter(w("t")))


def read_docx(data: bytes, reference: dict[str, bytes]) -> Docx:
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {name: archive.read(name) for name in archive.namelist()}
    names = _style_names(parts)
    document = ET.fromstring(parts["word/document.xml"])
    body = document.find(w("body"))
    if body is None:
        raise ValueError("word/document.xml has no body")
    early: list[Problem] = []
    # A name the archive holds twice is read here as its last copy, and may be read elsewhere as its
    # first; and the document holds its body and nothing else (a page colour, say, set beside it).
    if len(set(archive.namelist())) != len(archive.namelist()):
        early.append(Problem("package", "parts", "a part the archive holds twice"))
    if [child.tag for child in document] != [w("body")]:
        early.append(
            Problem("structure", "document", "the document holds something beside its body")
        )
    media: dict[str, str] = {}
    sizes: dict[str, tuple[int, int] | None] = {}
    links: dict[str, str] = {}
    targets: dict[str, str] = {}
    rels = ET.fromstring(parts[RELS]) if RELS in parts else ET.Element("Relationships")
    for rel in rels:
        rid, target = rel.get("Id", ""), rel.get("Target", "")
        targets[rid] = target
        # A picture is the part an internal image relationship names (Codex review of 2026-10-04:
        # one marked external passed); a link, an external hyperlink (a DOI relationship without
        # TargetMode="External" passed).
        if (
            rel.get("Type") == f"{R}/image"
            and rel.get("TargetMode", "Internal") == "Internal"
            and MEDIA.fullmatch("word/" + target)
            and "word/" + target in parts
        ):
            media[rid] = hashlib.sha256(parts["word/" + target]).hexdigest()
            sizes[rid] = _png_size(parts["word/" + target])
        if rel.get("Type") == f"{R}/hyperlink" and rel.get("TargetMode") == "External":
            links[rid] = target
    problems = early + validate_body(body)
    problems += validate_package(parts, reference, body)
    sheet = Sheet(parts.get("word/styles.xml"))
    style_problems, breaking = validate_styles(sheet, body)
    problems += style_problems
    labels, numbering_problems = list_labels(body, parts.get("word/numbering.xml"))
    problems += numbering_problems
    blocks: list[DPara | DTable] = []
    pending: list[str] = []
    # Every bookmark of the body, in paragraphs and table cells too (Codex review of 2026-10-04: a
    # second ref-cds59 inside a table cell passed).
    bookmarks = [b.get(w("name"), "") for b in body.iter(w("bookmarkStart"))]
    opened: dict[str, str] = {}  # bookmark id -> name
    for index, child in enumerate(body):
        if child.tag == w("bookmarkStart"):
            pending.append(child.get(w("name"), ""))
            opened[child.get(w("id"), "")] = child.get(w("name"), "")
        elif child.tag == w("bookmarkEnd"):
            # A bookmark that closes before any paragraph opens marks nothing: it is not given to
            # the paragraph that follows.
            name = opened.pop(child.get(w("id"), ""), None)
            if name in pending:
                pending.remove(name)
        elif child.tag == w("p"):
            blocks.append(_para(child, index, names, pending, labels))
            pending = []
        elif child.tag == w("tbl"):
            blocks.append(DTable(index, _table_rows(child, index, names, labels), pending))
            pending = []
    if any(True for _ in document.iter(w("txbxContent"))):
        problems.append(Problem("structure", "unread content", "a text box"))
    # The paragraphs that break the page are counted wherever they stand, title pages and table
    # cells included (Codex review of 2026-10-04: a break after the title, and one in a cell,
    # passed), and by what their style does, not by its name (a copy of Page Break set before the
    # original, whose break was then switched off, passed).
    broken: collections.Counter[str] = collections.Counter()
    for p in body.iter(w("p")):
        style = p.find(f"{w('pPr')}/{w('pStyle')}")
        style_id = (
            style.get(w("val"), "") if style is not None else sheet.default.get("paragraph", "")
        )
        if style_id in breaking:
            broken[names.get(style_id, style_id)] += 1
    break_count = sum(
        n for name, n in broken.items() if name not in ("Abstract Title", "Title Repeat")
    )
    if broken["Abstract Title"] != 1 or broken["Title Repeat"] != 1:
        problems.append(
            Problem(
                "structure",
                "page breaks",
                "the abstract title or the repeated title is not set once",
            )
        )
    # A picture is shown at its own proportions, at a readable width, and within the text area of the
    # page (Codex review of 2026-10-04: a figure drawn twice its size, off the page, passed).
    for drawing in body.iter(w("drawing")):
        extent = drawing.find(f".//{{{WP}}}extent")
        blip = drawing.find(f".//{{{A}}}blip")
        size = sizes.get(blip.get(f"{{{R}}}embed", "")) if blip is not None else None
        try:
            cx, cy = int(extent.get("cx", "0")), int(extent.get("cy", "0"))  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            cx = cy = 0
        if (
            not size
            or not cy
            or cx < 1828800
            or cx > TEXT_WIDTH * EMU_PER_TWIP
            or cy > TEXT_HEIGHT * EMU_PER_TWIP
            or abs(cx / cy - size[0] / size[1]) > 0.01 * size[0] / size[1]
        ):
            problems.append(
                Problem(
                    "structure",
                    "pictures",
                    f"a picture not shown at its own proportions: {cx}x{cy}, {size}",
                )
            )
    # A paragraph that shows nothing still takes a line, and a hundred of them a page (Codex review
    # of 2026-10-04: 150 empty paragraphs after the title passed). Only the spacers may be empty: a
    # Page Break (counted above), an After Table right after its table, and a cell's only paragraph.
    blank = 0
    for parent in body.iter():
        children = list(parent)
        for position, p in enumerate(children):
            if p.tag != w("p") or labels.get(id(p)):
                continue
            if any((t.text or "").strip() for t in p.iter(w("t"))) or any(
                True for _ in p.iter(w("drawing"))
            ):
                continue
            style = p.find(f"{w('pPr')}/{w('pStyle')}")
            name = names.get(style.get(w("val"), ""), "") if style is not None else ""
            after_table = position > 0 and children[position - 1].tag == w("tbl")
            only_in_cell = parent.tag == w("tc") and len(parent.findall(w("p"))) == 1
            if not (
                name == "Page Break" or (name == "After Table" and after_table) or only_in_cell
            ):
                blank += 1
    if blank:
        problems.append(
            Problem("structure", "empty paragraphs", f"{blank} paragraphs that show nothing")
        )
    # The header and footer each section shows: the parts its references name, whatever those are
    # called (Codex review of 2026-10-04: a header renamed word/running-head.xml went unread).
    for reference_to in body.iter():
        if _local(reference_to.tag) in ("headerReference", "footerReference"):
            part = "word/" + targets.get(reference_to.get(f"{{{R}}}id", ""), "")
            if part in parts:
                problems += validate_header(part, parts[part])
            else:
                problems.append(Problem("structure", "header", f"{part} is not in the .docx"))
    for name, part in parts.items():
        if name == "word/comments.xml" and any(
            True for _ in ET.fromstring(part).iter(w("comment"))
        ):
            problems.append(Problem("structure", "unread content", "comments"))
        if name == "word/endnotes.xml":
            notes = [
                n
                for n in ET.fromstring(part).iter(w("endnote"))
                if n.get(w("type"))
                not in ("separator", "continuationSeparator", "continuationNotice")
            ]
            if any(_part_text(ET.tostring(n)).strip() for n in notes):
                problems.append(Problem("structure", "unread content", "endnotes"))
    footnotes: list[str] = []
    if "word/footnotes.xml" in parts:
        for note in ET.fromstring(parts["word/footnotes.xml"]).iter(w("footnote")):
            if note.get(w("type")) in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            runs: list[tuple[str, str]] = []
            _runs(note, names, runs, [], [])
            for p in note.iter(w("p")):
                _runs(p, names, runs, [], [])
            footnotes.append("".join(t for t, _ in runs))
    return Docx(blocks, media, links, footnotes, parts, bookmarks, problems, break_count)


# --------------------------------------------------------------------------------------------------
# Inputs


@dataclass
class Inputs:
    root: Path
    manuscript: Manuscript
    refs: list[dict[str, Any]]
    cff: dict[str, Any]
    tmlr_rows: list[list[str]]
    apa_rows: list[list[str]]
    figures: dict[str, Any]
    contract: dict[str, Any]
    reference: dict[str, bytes]  # the parts of reference.docx, by name


def load_cff(path: Path) -> dict[str, Any]:
    import yaml  # noqa: PLC0415  (in the locked environment; the workflow supplies the pinned version)

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_inputs(
    root: Path, figures: Path | None, contract: Path | None, reference: bytes
) -> Inputs:
    refs = json.loads((root / REFS).read_text(encoding="utf-8"))
    manuscript = read_manuscript((root / MAIN).read_text(encoding="utf-8"), refs)
    tmlr = [
        line.split("\t")
        for line in (root / TMLR_CITATIONS).read_text(encoding="utf-8").splitlines()[1:]
    ]
    apa_path = root / APA_CITATIONS
    apa = (
        [line.split("\t") for line in apa_path.read_text(encoding="utf-8").splitlines()[1:]]
        if apa_path.is_file()
        else []
    )
    return Inputs(
        root,
        manuscript,
        refs,
        load_cff(root / CFF),
        tmlr,
        apa,
        json.loads(figures.read_text(encoding="utf-8")) if figures else {"figures": []},
        json.loads(contract.read_text(encoding="utf-8")) if contract else {},
        _package(reference),
    )


def _package(data: bytes) -> dict[str, bytes]:
    archive = zipfile.ZipFile(io.BytesIO(data))
    return {name: archive.read(name) for name in archive.namelist()}


# --------------------------------------------------------------------------------------------------
# The two streams of text compared word for word


@dataclass
class Item:
    key: str  # "H<level>|text" for a heading, "P|text" for anything else; normalised
    where: int  # main.md line, or the index of the .docx block
    cites: list[int] = field(default_factory=list)  # main: citation numbers; .docx: group indices
    block: Any = None
    generated: bool = False
    page_break: int = 0  # .docx: how many page-break paragraphs stand right before it


#: The reference list, in the text compared word for word, where it stands.
BIBLIOGRAPHY_KEY = "P|" + chr(0x27E6) + "BIBLIOGRAPHY" + chr(0x27E7)


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.split("\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def main_stream(m: Manuscript) -> list[Item]:
    """The text the ``.docx`` body must carry, block by block, from ``main.md``."""
    offsets = _line_offsets(m.text)
    by_block: dict[int, list[MCite]] = {}
    for cite in m.cites:
        by_block.setdefault(cite.block, []).append(cite)
    items: list[Item] = []
    for index, block in enumerate(m.blocks):
        if block.kind in ("footnote", "note", "marker", "rule"):
            continue
        if block.kind == "references":
            items.append(Item(BIBLIOGRAPHY_KEY, block.line, [], block))
            continue
        if block.kind == "figure":
            items.append(Item(f"P|\u27e6FIGURE {block.number}\u27e7", block.line, [], block))
            continue
        if block.kind == "table":
            items.append(
                Item(f"P|\u27e6TABLE {block.number}\u27e7", block.line, [], block, block.generated)
            )
            continue
        if block.kind == "code":
            items.append(Item("P|" + norm(block.raw), block.line, [], block, block.generated))
            continue
        a, b = offsets[block.line - 1], offsets[block.last] - 1
        cites = by_block.get(index, [])
        pieces, cursor = [], a
        for cite in cites:
            pieces.append(m.text[cursor : cite.start])
            pieces.append(
                " " + PLACEHOLDER_CITE + " " if cite.kind != "narrative" else PLACEHOLDER_CITE + " "
            )
            cursor = cite.end
        pieces.append(m.text[cursor:b])
        raw = "".join(pieces)
        if block.kind == "heading":
            raw = re.sub(r"^#+ ", "", raw)
            key = f"H{block.level}|" + norm(inline(raw))
        else:
            if block.kind == "item":
                # The label a list draws is text on the page, so it is text here too: a bullet as
                # "•", a number as itself and a period (see list_labels).
                raw = re.sub(
                    r"^(?:([-+*])|(\d+\.)) ",
                    lambda x: (BULLET if x.group(1) else x.group(2)) + " ",
                    raw,
                )
            key = "P|" + norm(inline(raw))
        items.append(Item(_tidy(key), block.line, [c.k for c in cites], block, block.generated))
    return items


def _tidy(key: str) -> str:
    """A placeholder stands where the citation stood: no space between it and punctuation after it."""
    key = re.sub(r" ?" + PLACEHOLDER_CITE + r" ?", " " + PLACEHOLDER_CITE + " ", key)
    key = re.sub(PLACEHOLDER_CITE + r" (?=[.,;:)])", PLACEHOLDER_CITE, key)
    key = re.sub(r"(?<=[(]) " + PLACEHOLDER_CITE, PLACEHOLDER_CITE, key)
    return " ".join(key.split()).replace("| ", "|", 1)


@dataclass
class DocView:
    head: list[DPara]
    items: list[Item]
    groups: list[tuple[str, int]]  # (text, index of the .docx block) per citation, in order
    figures: dict[int, dict[str, Any]]
    tables: dict[int, dict[str, Any]]
    bibliography: list[DPara]
    problems: list[Problem]


def _text_with_groups(para: DPara, groups: list[tuple[str, int]]) -> tuple[str, list[int]]:
    out: list[str] = []
    mine: list[int] = []
    current: list[str] | None = None
    for text, style in para.runs:
        if style == CITATION_STYLE:
            if current is None:
                current = []
            current.append(text)
            continue
        if current is not None:
            groups.append(("".join(current), para.index))
            mine.append(len(groups) - 1)
            out.append(" " + PLACEHOLDER_CITE + " ")
            current = None
        out.append(text)
    if current is not None:
        groups.append(("".join(current), para.index))
        mine.append(len(groups) - 1)
        out.append(" " + PLACEHOLDER_CITE + " ")
    return "".join(out), mine


def docx_view(doc: Docx) -> DocView:
    blocks = doc.blocks
    problems: list[Problem] = []
    repeat = next(
        (i for i, b in enumerate(blocks) if isinstance(b, DPara) and b.style == "Title Repeat"),
        None,
    )
    if repeat is None:
        problems.append(
            Problem(
                "head",
                "title repeated",
                "no paragraph in the style 'Title Repeat' ends the title pages",
            )
        )
        repeat = next(
            (
                i - 1
                for i, b in enumerate(blocks)
                if isinstance(b, DPara) and b.style.startswith("heading")
            ),
            -1,
        )
    # The title pages hold paragraphs only: a table or a picture there is in no contract (Codex
    # review of 2026-10-04: a table placed before the repeated title passed unread).
    for block in blocks[: repeat + 1]:
        if isinstance(block, DTable) or block.images:
            problems.append(
                Problem("head", "title pages", f"docx block {block.index} is a table or a picture")
            )
    head = [b for b in blocks[: repeat + 1] if isinstance(b, DPara) and b.text.strip()]
    groups: list[tuple[str, int]] = []
    items: list[Item] = []
    figures: dict[int, dict[str, Any]] = {}
    tables: dict[int, dict[str, Any]] = {}
    bibliography: list[DPara] = []
    pending_break = 0
    in_bibliography = False

    def add(item: Item) -> None:
        nonlocal pending_break, in_bibliography
        item.page_break = pending_break
        pending_break = 0
        in_bibliography = item.key == BIBLIOGRAPHY_KEY
        items.append(item)

    i = repeat + 1
    while i < len(blocks):
        block = blocks[i]
        if isinstance(block, DTable):
            problems.append(
                Problem(
                    "table", f"docx block {block.index}", "a table with no 'Table N' label above it"
                )
            )
            add(Item("P|\u27e6TABLE ?\u27e7", block.index, [], block))
            i += 1
            continue
        if block.style == "Page Break":
            pending_break += 1
            if not block.text.strip() and not block.images:
                i += 1
                continue
            # A page-break paragraph shows what it holds; it is read like any other paragraph.
            problems.append(
                Problem(
                    "structure", "page breaks", f"docx block {block.index}: a page break holds text"
                )
            )
        elif not block.text.strip() and not block.images:
            i += 1
            continue
        if block.style in ("Figure Number", "Table Number"):
            kind = block.style.split()[0]
            label = re.fullmatch(kind + r" (\d+)", norm(block.text))
            if not label:
                problems.append(
                    Problem(
                        kind.lower(),
                        f"docx block {block.index}",
                        f"a label that is not '{kind} N': {block.text!r}",
                    )
                )
                i += 1
                continue
            number = int(label.group(1))
            group: dict[str, Any] = {"label": block, "title": None, "body": None}
            j = i + 1
            if (
                j < len(blocks)
                and isinstance(blocks[j], DPara)
                and blocks[j].style == f"{kind} Title"
            ):
                group["title"] = blocks[j]
                j += 1
            if (
                kind == "Figure"
                and j < len(blocks)
                and isinstance(blocks[j], DPara)
                and blocks[j].style == "Figure Image"
            ):
                group["body"] = blocks[j]
                j += 1
            if kind == "Table" and j < len(blocks) and isinstance(blocks[j], DTable):
                group["body"] = blocks[j]
                j += 1
            target = figures if kind == "Figure" else tables
            if number in target:
                problems.append(Problem(kind.lower(), f"{kind} {number}", "the label occurs twice"))
            target[number] = group
            add(Item(f"P|\u27e6{kind.upper()} {number}\u27e7", block.index, [], block))
            i = j
            continue
        if block.style == "Bibliography":
            # The reference list stands in the text as one placeholder, where it is; a reference
            # set anywhere else adds a second one (Codex review of 2026-10-04).
            if not in_bibliography:
                add(Item(BIBLIOGRAPHY_KEY, block.index, [], block))
            bibliography.append(block)
            i += 1
            continue
        if block.style in HEAD_STYLES:
            problems.append(
                Problem(
                    "head",
                    f"docx block {block.index}",
                    f"a paragraph in the style {block.style!r} after the title pages",
                )
            )
        text, mine = _text_with_groups(block, groups)
        heading = re.fullmatch(r"heading (\d)", block.style)
        key = (f"H{heading.group(1)}|" if heading else "P|") + norm(text)
        add(Item(_tidy(key), block.index, mine, block))
        i += 1
    # A break left after the last of the text is counted by the total in check_text.
    return DocView(head, items, groups, figures, tables, bibliography, problems)


def align(
    main_items: list[Item], doc_items: list[Item]
) -> tuple[list[Problem], list[tuple[int, int]]]:
    """Compare the two streams block by block, and word by word where blocks differ."""
    problems: list[Problem] = []
    pairs: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(
        None, [x.key for x in main_items], [x.key for x in doc_items], autojunk=False
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            pairs.extend(zip(range(i1, i2), range(j1, j2), strict=True))
            continue
        paired = min(i2 - i1, j2 - j1) if tag == "replace" else 0
        for k in range(paired):
            mine, theirs = main_items[i1 + k], doc_items[j1 + k]
            pairs.append((i1 + k, j1 + k))
            a, b = mine.key.split(), theirs.key.split()
            words = difflib.SequenceMatcher(None, a, b, autojunk=False)
            changes = [
                f"{' '.join(a[x1:x2]) or '(nothing)'} -> {' '.join(b[y1:y2]) or '(nothing)'}"
                for op, x1, x2, y1, y2 in words.get_opcodes()
                if op != "equal"
            ]
            problems.append(
                Problem(
                    "fulltext",
                    f"main.md:{mine.where}",
                    "the .docx differs: " + "; ".join(changes[:4]),
                )
            )
        for k in range(i1 + paired, i2):
            problems.append(
                Problem(
                    "fulltext",
                    f"main.md:{main_items[k].where}",
                    f"missing from the .docx: {main_items[k].key[:90]!r}",
                )
            )
        for k in range(j1 + paired, j2):
            # A block set twice is reported at the block it repeats, whichever copy the matcher took.
            neighbours = [
                main_items[x] for x in (i1 + paired - 1, i1 + paired) if 0 <= x < len(main_items)
            ]
            twin = next((x for x in neighbours if x.key == doc_items[k].key), None)
            if twin is not None:
                problems.append(
                    Problem(
                        "fulltext",
                        f"main.md:{twin.where}",
                        f"the .docx sets this block twice: {twin.key[:90]!r}",
                    )
                )
                continue
            after = main_items[i1 + paired - 1].where if i1 + paired > 0 else 0
            problems.append(
                Problem(
                    "fulltext",
                    f"main.md:{after}",
                    f"the .docx has, after this line, what main.md does not: {doc_items[k].key[:90]!r}",
                )
            )
    return problems, pairs


# --------------------------------------------------------------------------------------------------
# The items of the contract

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _ordinal(number: int) -> str:
    suffix = (
        "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    )
    return f"{number}{suffix}"


def reference_fields(item: dict[str, Any]) -> list[tuple[str, str]]:
    """What an entry of the reference list prints, field by field and in order, from ``refs.json``.

    The order is APA 7's for each type, as the vendored style sets it: authors, year, title, then
    the source (a web page: when it was read and where; a preprint: its number and archive; a book:
    its edition and publisher; an article or paper: container, volume and issue, pages or article
    number), then the DOI or the URL.
    """
    fields: list[tuple[str, str]] = []
    for author in item["author"]:
        fields.append(("author", author.get("literal") or f"{author['family']}, {author['given']}"))
    year = f"({item['issued']['date-parts'][0][0]})" if "issued" in item else "(n.d.)"
    fields.append(("year", year))
    fields.append(("title", item["title"]))
    if item["type"] == "webpage":
        y, mo, d = item["accessed"]["date-parts"][0]
        fields.append(("accessed", f"Retrieved {MONTHS[mo - 1]} {d}, {y}"))
        fields.append(("URL", item["URL"]))
        return fields
    if item.get("container-title"):
        fields.append(("container-title", item["container-title"]))
    if item.get("volume"):
        fields.append(
            ("volume", item["volume"] + (f"({item['issue']})" if item.get("issue") else ""))
        )
    if item.get("page"):
        fields.append(("page", item["page"]))
    if item.get("number"):
        fields.append(
            (
                "number",
                f"({item['number']})" if item["type"] == "article" else f"Article {item['number']}",
            )
        )
    if item.get("edition"):
        fields.append(("edition", f"({_ordinal(int(item['edition']))} ed.)"))
    if item.get("publisher") and item["type"] in ("article", "book"):
        fields.append(("publisher", item["publisher"]))
    if item.get("DOI"):
        fields.append(("DOI", f"https://doi.org/{item['DOI']}"))
    elif item.get("URL"):
        fields.append(("URL", item["URL"]))
    return fields


#: What stands between two fields of an entry, as the APA style sets them, and what may end one.
#: Nothing else is allowed there: not a digit, not a word, not a lone point (Codex reviews of
#: 2026-10-04: a volume 98 or .8 for 8, and an invented entry appended to a paragraph, each passed a
#: looser reading).
SEPARATORS = frozenset({"", " ", ", ", ", & ", ". ", ", from "})
ENDINGS = frozenset({"", "."})


def _quotes_alike(text: str) -> str:
    """Normalised, with single and double quotation marks made one: citeproc requotes a title's
    ‘…’ as “…”, which is the one change of quotation it makes. No character is removed."""
    return norm(text).replace('"', "'")


def entry_problems(item: dict[str, Any], text: str) -> list[str]:
    """Read an entry as its fields in order, with only the APA separators between them."""
    entry = _quotes_alike(text)
    cursor = 0
    problems: list[str] = []
    for name, value in reference_fields(item):
        want = _quotes_alike(value)
        at = entry.find(want, cursor)
        if at < 0:
            problems.append(f"no {name} {value!r} after {entry[max(0, cursor - 20) : cursor]!r}")
            continue
        if entry[cursor:at] not in SEPARATORS:
            problems.append(f"{entry[cursor:at]!r} stands before the {name} {value!r}")
        cursor = at + len(want)
    if entry[cursor:] not in ENDINGS:
        problems.append(f"{entry[cursor:]!r} follows the last field")
    return problems


def entry_link(item: dict[str, Any]) -> str:
    """The one link an entry carries: its DOI as a URL, or its URL."""
    return f"https://doi.org/{item['DOI']}" if item.get("DOI") else item["URL"]


def _sort_key(item: dict[str, Any]) -> tuple[tuple[str, ...], int]:
    """APA 7's order of the reference list: by the authors' names in turn, then by year."""

    def plain(name: str) -> str:
        decomposed = unicodedata.normalize("NFKD", name)
        return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()

    names = tuple(plain(a.get("family") or a.get("literal")) for a in item["author"])
    return names, item["issued"]["date-parts"][0][0] if "issued" in item else 0


def check_bibliography(inp: Inputs, view: DocView, doc: Docx) -> list[Problem]:
    problems: list[Problem] = []
    entries: dict[int, DPara] = {}
    order: list[int] = []
    for para in view.bibliography:
        ids = [int(x) for name in para.bookmarks for x in re.findall(r"^ref-cds(\d+)$", name)]
        if not ids:
            problems.append(
                Problem("bibliography", f"docx block {para.index}", "an entry with no identifier")
            )
            continue
        if len(ids) > 1:
            problems.append(
                Problem("bibliography", f"[{ids[-1]}]", f"the entry carries identifiers {ids}")
            )
        if ids[-1] in entries:
            problems.append(Problem("bibliography", f"[{ids[-1]}]", "the entry occurs twice"))
        entries[ids[-1]] = para
        order.append(ids[-1])
    # Each identifier names one entry (Codex review of 2026-10-04: a second bookmark of [43] set
    # around another entry passed).
    names = [b for b in doc.bookmarks if b.startswith("ref-cds")]
    twice = sorted({b for b in names if names.count(b) > 1})
    if twice:
        problems.append(Problem("bibliography", "bookmarks", f"identifiers used twice: {twice}"))
    known = {item["x-cds"]["n"]: item for item in inp.refs}
    for n, item in known.items():
        if n not in entries:
            problems.append(
                Problem("bibliography", f"[{n}]", "not in the reference list of the .docx")
            )
            continue
        para = entries[n]
        found = entry_problems(item, para.text)
        # The link's destination as well as its text (Codex review of 2026-10-04: a DOI link that
        # showed the right DOI and led to another passed).
        link = entry_link(item)
        destinations = [(doc.links.get(rid, ""), norm(shown)) for rid, shown in para.links]
        if destinations != [(link, link)]:
            found.append(f"its links are {destinations}, not one to {link}")
        if found:
            problems.append(Problem("bibliography", f"[{n}]", "; ".join(found)))
    for n in sorted(set(entries) - set(known)):
        problems.append(Problem("bibliography", f"[{n}]", "an entry refs.json does not hold"))
    listed = [n for n in order if n in known]
    if listed != sorted(listed, key=lambda n: _sort_key(known[n])):
        problems.append(
            Problem("bibliography", "order", f"the entries are not in APA order: {listed}")
        )
    # One list, right after its heading (Codex review of 2026-10-04: a reference moved into the
    # introduction, bookmark and all, was still found by its identifier).
    places = [i for i, x in enumerate(view.items) if x.key == BIBLIOGRAPHY_KEY]
    heading = [i for i, x in enumerate(view.items) if x.key.endswith("|References")]
    if len(places) != 1 or len(heading) != 1 or places[0] != heading[0] + 1:
        problems.append(
            Problem(
                "bibliography",
                "location",
                f"the references stand at {len(places)} place(s), not as one list under the heading",
            )
        )
    cited = {n for c in inp.manuscript.cites for n in c.ids}
    if cited != set(known):
        problems.append(
            Problem(
                "bibliography",
                "cited",
                f"cited but not listed {sorted(cited - set(known))}, listed but not cited {sorted(set(known) - cited)}",
            )
        )
    return problems


def expected_links(inp: Inputs) -> list[tuple[str, str]]:
    """(text shown, destination) of every link main.md writes, outside code, once per occurrence."""
    text = _blank_code(inp.manuscript.text)
    pairs = [(m.group(1), m.group(1)) for m in re.finditer(r"<(https?://[^>\s]+)>", text)]
    pairs += [
        (norm(_plain(m.group(1))), m.group(2))
        for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text)
    ]
    return pairs


def check_links(inp: Inputs, view: DocView, doc: Docx) -> list[Problem]:
    """The links outside the reference list are those main.md writes: each shown and led where it
    says, none added and none lost (Codex review of 2026-10-04: an ORCID link unwrapped into plain
    text passed, since only the links that remained were looked at)."""
    expected = collections.Counter(expected_links(inp))
    bibliography = {id(p) for p in view.bibliography}
    found: collections.Counter[tuple[str, str]] = collections.Counter()
    for para in _all_paragraphs(doc):
        if id(para) not in bibliography:
            found.update((norm(shown), doc.links.get(rid, "")) for rid, shown in para.links)
    problems = [
        Problem("link", shown[:60], f"a link to {target!r} that main.md does not have")
        for (shown, target) in found - expected
    ]
    problems += [
        Problem("link", shown[:60], f"the link to {target!r} main.md has is not in the .docx")
        for (shown, target) in expected - found
    ]
    return problems


def _first_author_and_year(item: dict[str, Any]) -> tuple[str, str]:
    first = item["author"][0]
    year = str(item["issued"]["date-parts"][0][0]) if "issued" in item else "n.d."
    return first.get("family") or first.get("literal"), year


def check_citations(
    inp: Inputs, view: DocView, main_items: list[Item], pairs: list[tuple[int, int]]
) -> list[Problem]:
    m = inp.manuscript
    problems: list[Problem] = []
    mine = [[c.context, ", ".join(map(str, c.ids)), c.mode] for c in m.cites]
    if mine != inp.tmlr_rows:
        if len(mine) != len(inp.tmlr_rows):
            problems.append(
                Problem(
                    "citation",
                    "record",
                    f"{TMLR_CITATIONS} has {len(inp.tmlr_rows)} citations, main.md {len(mine)}",
                )
            )
        for c, row in zip(m.cites, inp.tmlr_rows, strict=False):
            if [c.context, ", ".join(map(str, c.ids)), c.mode] != row:
                problems.append(
                    Problem(
                        "citation",
                        f"citation {c.k}",
                        f"main.md:{c.line} reads differently from {TMLR_CITATIONS}: {row}",
                    )
                )
    if len(inp.apa_rows) != len(m.cites):
        problems.append(
            Problem(
                "citation",
                "fixture",
                f"{APA_CITATIONS} has {len(inp.apa_rows)} rows, main.md {len(m.cites)} citations",
            )
        )
    by_id = {item["x-cds"]["n"]: item for item in inp.refs}
    for c, row in zip(m.cites, inp.apa_rows, strict=False):
        where = f"citation {c.k}"
        if len(row) != 4 or row[:3] != [c.context, ", ".join(map(str, c.ids)), c.kind]:
            problems.append(
                Problem("citation", where, f"the fixture row {row[:3]} is not main.md:{c.line}")
            )
            continue
        text = norm(row[3])
        for n in c.ids:
            name, year = _first_author_and_year(by_id[n])
            if name not in text or year not in text:
                problems.append(
                    Problem(
                        "citation",
                        where,
                        f"the fixture's {text!r} does not name [{n}] as {name}, {year}",
                    )
                )
        if c.kind == "narrative" and not (
            text.startswith(_first_author_and_year(by_id[c.ids[0]])[0]) and text.endswith(")")
        ):
            problems.append(Problem("citation", where, f"a narrative citation set as {text!r}"))
        if c.kind == "parenthetical" and not (text.startswith("(") and text.endswith(")")):
            problems.append(Problem("citation", where, f"a parenthetical citation set as {text!r}"))
        if c.kind == "in-parentheses" and not (
            text.startswith("(" + norm(c.prefix)) and text.endswith(norm(c.suffix) + ")")
        ):
            problems.append(
                Problem("citation", where, f"the text around the citation is not kept in {text!r}")
            )
    expected = {
        c.k: norm(row[3]) for c, row in zip(m.cites, inp.apa_rows, strict=False) if len(row) == 4
    }
    seen: set[int] = set()
    for mi, di in pairs:
        ks, gs = main_items[mi].cites, view.items[di].cites
        if len(ks) != len(gs):
            # Always reported, whatever the text comparison says: a literal placeholder in the text
            # would otherwise stand in for a citation (Codex review of 2026-10-04).
            for k in ks[len(gs) :] or ks:
                problems.append(
                    Problem(
                        "citation",
                        f"citation {k}",
                        f"main.md:{m.cites[k - 1].line}: the .docx paragraph sets {len(gs)} "
                        f"citation(s) where main.md has {len(ks)}",
                    )
                )
            if not ks:
                problems.append(
                    Problem(
                        "citation",
                        f"main.md:{main_items[mi].where}",
                        f"the .docx paragraph sets {len(gs)} citation(s) where main.md has none",
                    )
                )
            continue
        for k, g in zip(ks, gs, strict=True):
            seen.add(g)
            got = norm(view.groups[g][0])
            if k in expected and got != expected[k]:
                problems.append(
                    Problem(
                        "citation",
                        f"citation {k}",
                        f"main.md:{m.cites[k - 1].line}: the .docx sets {got!r}, the fixture {expected[k]!r}",
                    )
                )
    for g, (text, index) in enumerate(view.groups):
        if g not in seen and not any(g in view.items[di].cites for _, di in pairs):
            problems.append(
                Problem(
                    "citation",
                    f"docx block {index}",
                    f"a citation the text comparison did not place: {text!r}",
                )
            )
    return problems


def preprint(cff: dict[str, Any]) -> str | None:
    found = [
        i
        for i in cff.get("identifiers") or []
        if str(i.get("description", "")).startswith("Preprint of an earlier version")
    ]
    return str(found[0]["value"]) if len(found) == 1 else None


def expected_head(inp: Inputs) -> list[tuple[str, str, str]]:
    """(style, name, text) of every paragraph of the title page and the abstract page, in order."""
    m = inp.manuscript
    rows = m.rows
    seq = [
        ("Title", "title", m.title),
        ("Author", "author", inline(rows["Author"][1])),
        ("Affiliation", "affiliation", inline(rows["Affiliation"][1])),
        ("Author Note Heading", "author note heading", "Author Note"),
    ]
    seq += [("Author Note", label, f"{label}: {inline(rows[label][1])}") for label in NOTE_BEFORE]
    doi = preprint(inp.cff)
    if doi:
        seq.append(
            (
                "Author Note",
                "Preprint",
                f"Preprint: an earlier version is available at https://doi.org/{doi}.",
            )
        )
    seq.append(("Author Note", "AI disclosure", inline(m.ai.raw)))
    seq += [("Author Note", label, f"{label}: {inline(rows[label][1])}") for label in NOTE_AFTER]
    seq += [
        ("Abstract Title", "abstract title", "Abstract"),
        ("Abstract", "abstract", m.abstract),
        ("Keywords", "keywords", "Keywords: " + ", ".join(inp.cff.get("keywords") or [])),
        ("Title Repeat", "title repeated", m.title),
    ]
    return seq


def check_head(inp: Inputs, view: DocView, doc: Docx) -> list[Problem]:
    m, cff = inp.manuscript, inp.cff
    problems: list[Problem] = []
    author = (cff.get("authors") or [{}])[0]
    for name, ours, theirs in (
        ("title", m.title, cff.get("title", "")),
        (
            "author",
            inline(m.rows["Author"][1]),
            f"{author.get('given-names', '')} {author.get('family-names', '')}",
        ),
        ("affiliation", inline(m.rows["Affiliation"][1]), author.get("affiliation", "")),
        ("ORCID", inline(m.rows["ORCID"][1]), str(author.get("orcid", "")).rsplit("/", 1)[-1]),
        ("abstract", m.abstract, str(cff.get("abstract", ""))),
    ):
        if norm(ours) != norm(theirs):
            problems.append(
                Problem(
                    "head",
                    name,
                    f"main.md has {norm(ours)[:60]!r}, CITATION.cff {norm(theirs)[:60]!r}",
                )
            )
    expected = expected_head(inp)
    for index, (style, name, text) in enumerate(expected):
        check = "author-note" if style == "Author Note" else "head"
        if index >= len(view.head):
            problems.append(Problem(check, name, "missing from the title pages"))
            continue
        para = view.head[index]
        if para.style != style or norm(para.text) != norm(text):
            problems.append(
                Problem(
                    check,
                    name,
                    f"expected {style}: {norm(text)[:70]!r}, the .docx has {para.style}: {norm(para.text)[:70]!r}",
                )
            )
    for para in view.head[len(expected) :]:
        problems.append(
            Problem(
                "head",
                f"docx block {para.index}",
                f"an extra paragraph on the title pages: {para.text[:60]!r}",
            )
        )
    ai = norm(inline(m.ai.raw))
    label = norm(inline(m.ai.raw.split("**")[1])) if m.ai.raw.count("**") >= 2 else ai
    holders = [p for p in _all_paragraphs(doc) if ai in norm(p.text) or label in norm(p.text)]
    stray = [p for p in holders if p.style != "Author Note"]
    if stray:
        problems.append(
            Problem(
                "author-note",
                "AI disclosure",
                f"also outside the Author Note, in docx block(s) {[p.index for p in stray]}: it must be moved, not copied",
            )
        )
    if doc.footnotes and any(t.strip() for t in doc.footnotes):
        problems.append(
            Problem(
                "author-note",
                "footnotes",
                f"the .docx carries {len(doc.footnotes)} footnote(s); the disclosure is in the Author Note",
            )
        )
    return problems


def _all_paragraphs(doc: Docx) -> list[DPara]:
    out: list[DPara] = []
    for block in doc.blocks:
        if isinstance(block, DPara):
            out.append(block)
        else:
            out.extend(cell for row in block.rows for cell in row)
    return out


def code_blocks(
    view: DocView, main_items: list[Item], pairs: list[tuple[int, int]]
) -> list[tuple[DPara, MBlock]]:
    """The paragraphs of the .docx that main.md's code blocks were matched to, each with its block."""
    return [
        (view.items[di].block, main_items[mi].block)
        for mi, di in pairs
        if isinstance(main_items[mi].block, MBlock)
        and main_items[mi].block.kind == "code"
        and isinstance(view.items[di].block, DPara)
    ]


def check_line_breaks(doc: Docx, code: list[tuple[DPara, MBlock]]) -> list[Problem]:
    """A line break only in the paragraph a code block of main.md became, and its lines are main.md's.

    A break shows as a new line, and a hundred of them as a page, while the words compared stay the
    same (Codex reviews of 2026-10-04: 150 line breaks after the title passed; then a paragraph set
    in the code style with 150 breaks, and a code block whose breaks were moved to its end, passed
    a check that went by the style and counted the breaks). So the breaks are allowed by the
    manuscript, not by the style, and a code block is compared line by line, spaces and all.
    """
    problems: list[Problem] = []
    allowed = {id(para) for para, _ in code}
    broken = sorted(
        {p.index for p in _all_paragraphs(doc) if "\n" in p.text and id(p) not in allowed}
    )
    if broken:
        problems.append(
            Problem(
                "structure", "line breaks", f"line breaks outside code, in docx blocks {broken[:4]}"
            )
        )
    for para, block in code:
        if para.text.split("\n") != block.raw.split("\n"):
            problems.append(
                Problem(
                    "structure",
                    "line breaks",
                    f"main.md:{block.line}: the code's lines are not main.md's",
                )
            )
    return problems


def check_whitespace(inp: Inputs, doc: Docx, code: list[tuple[DPara, MBlock]]) -> list[Problem]:
    """White space as main.md has it, outside the code blocks (compared line by line above).

    The comparison of words collapses white space on both sides, so twenty thousand spaces, or an
    em space, where main.md has one space passed it (Codex review of 2026-10-04). Here no run of
    white space may be longer than the longest in a code span of main.md (one space, for this
    manuscript, which sets prose with single spaces), and no space character may be one main.md
    does not use. The code blocks are left out by the manuscript, not by the style (Codex review of
    2026-10-04: a paragraph of prose set in the code style, with 20,000 spaces, passed). A line
    break is the business of check_line_breaks; a list's label, of :func:`list_labels`.
    """
    text = inp.manuscript.text
    spans = re.findall(r"`([^`\n]*)`", re.sub(r"```.*?```", "", text, flags=re.S))
    longest = max([1, *(len(m) for span in spans for m in re.findall(r"\s+", span))])
    spaces = {c for c in text if _is_space(c) and c not in " \n"}
    allowed = {id(para) for para, _ in code}
    odd: list[int] = []
    for para in _all_paragraphs(doc):
        if id(para) in allowed:
            continue
        shown = "".join(t for t, style in para.runs if style not in (LABEL_STYLE, JOIN_STYLE))
        if any(_is_space(c) and c not in " \n" and c not in spaces for c in shown) or any(
            len(m) > longest for m in re.findall(r"[^\S\n]+", shown)
        ):
            odd.append(para.index)
    if odd:
        return [
            Problem(
                "structure",
                "whitespace",
                f"white space main.md does not have, in docx blocks {sorted(set(odd))[:4]}",
            )
        ]
    return []


def _is_space(c: str) -> bool:
    return c.isspace() or unicodedata.category(c) == "Zs"


def check_figures(inp: Inputs, view: DocView, doc: Docx) -> list[Problem]:
    problems: list[Problem] = []
    manifest = {f["name"]: f for f in inp.figures.get("figures", [])}
    wanted = [b for b in inp.manuscript.blocks if b.kind == "figure"]
    for block in wanted:
        where = f"Figure {block.number}"
        group = view.figures.get(block.number)
        record = manifest.get(block.name)
        if record is None or record.get("number") != block.number:
            problems.append(
                Problem(
                    "figure",
                    where,
                    f"the figure manifest does not record {block.name} as figure {block.number}",
                )
            )
        if group is None:
            problems.append(Problem("figure", where, "no 'Figure N' label in the .docx"))
            continue
        title = group["title"]
        if title is None or norm(title.text) != norm(inline(block.caption)):
            problems.append(
                Problem("figure", where, f"the title is not main.md:{block.line}'s caption")
            )
        body = group["body"]
        if body is None or len(body.images) != 1:
            problems.append(
                Problem(
                    "figure",
                    where,
                    f"the label is not followed by exactly one picture ({0 if body is None else len(body.images)})",
                )
            )
            continue
        if body.text.strip():
            # The picture's paragraph is checked for the picture, so it must hold nothing else
            # (Codex review of 2026-10-04: text set beside a figure passed unread).
            problems.append(
                Problem("figure", where, f"the picture's paragraph holds text: {body.text[:50]!r}")
            )
        sha = doc.media.get(body.images[0])
        if record is not None and sha != record.get("sha256"):
            other = [f["name"] for f in manifest.values() if f.get("sha256") == sha]
            problems.append(
                Problem(
                    "figure",
                    where,
                    f"the picture is not the PNG of {block.name} ({(sha or 'none')[:12]}; it is that of {other or 'no figure'})",
                )
            )
    for number in sorted(set(view.figures) - {b.number for b in wanted}):
        problems.append(Problem("figure", f"Figure {number}", "a label main.md does not have"))
    placed = {id(g["body"]) for g in view.figures.values() if g["body"] is not None}
    for para in _all_paragraphs(doc):
        if para.images and id(para) not in placed:
            problems.append(
                Problem("figure", f"docx block {para.index}", "a picture outside a figure")
            )
    return problems


def check_tables(inp: Inputs, view: DocView) -> list[Problem]:
    problems: list[Problem] = []
    wanted = [b for b in inp.manuscript.blocks if b.kind == "table"]
    for block in wanted:
        where = f"Table {block.number}"
        group = view.tables.get(block.number)
        if group is None:
            problems.append(Problem("table", where, "no 'Table N' label in the .docx"))
            continue
        if group["title"] is None or norm(group["title"].text) != norm(inline(block.caption)):
            problems.append(
                Problem(
                    "table", where, f"the title is not the caption of main.md:{block.caption_line}"
                )
            )
        table = group["body"]
        if table is None:
            problems.append(Problem("table", where, "the label is not followed by a table"))
            continue
        want = [[norm(inline(cell, cell=True)) for cell in row] for row in block.rows]
        have = [[norm(cell.text) for cell in row] for row in table.rows]
        if [len(r) for r in want] != [len(r) for r in have]:
            problems.append(
                Problem(
                    "table",
                    where,
                    f"{len(have)} rows of {[len(r) for r in have][:3]}... cells, main.md:{block.line} has {len(want)} of {[len(r) for r in want][:3]}...",
                )
            )
            continue
        for r, (mine, theirs) in enumerate(zip(want, have, strict=True)):
            for c, (a, b) in enumerate(zip(mine, theirs, strict=True)):
                if a != b:
                    problems.append(
                        Problem(
                            "table",
                            where,
                            f"row {r + 1}, column {c + 1}: {b[:50]!r}, main.md:{block.line} has {a[:50]!r}",
                        )
                    )
                    break
            else:
                continue
            break
    for number in sorted(set(view.tables) - {b.number for b in wanted}):
        problems.append(Problem("table", f"Table {number}", "a label main.md does not have"))
    return problems


def check_drops(inp: Inputs, doc: Docx) -> list[Problem]:
    m = inp.manuscript
    everything = " ".join(norm(p.text) for p in _all_paragraphs(doc))
    problems: list[Problem] = []
    lead = norm(inline(m.lead[2]))
    if lead and lead in everything:
        problems.append(
            Problem(
                "drop",
                "author table lead",
                "the lead paragraph of the author table reached the .docx",
            )
        )
    if norm(inline(m.note.raw)) in everything:
        problems.append(
            Problem(
                "drop",
                "note after the references",
                "the note on reference numbers reached the .docx",
            )
        )
    if "<!--" in everything or "TMLR:" in everything:
        problems.append(Problem("drop", "markers", "a marker of main.md reached the .docx"))
    return problems


def _prose(para: DPara) -> str:
    return "".join(t for t, style in para.runs if style != CODE_STYLE)


def _where(para_index: int, located: dict[int, Item]) -> str:
    item = located.get(para_index)
    if item is not None and isinstance(item.block, MBlock):
        return f"main.md:{item.where}"
    return f"docx block {para_index}"


def check_text(
    inp: Inputs, view: DocView, doc: Docx, main_items: list[Item], pairs: list[tuple[int, int]]
) -> list[Problem]:
    """British spellings, characters at risk, citation residue and §K, on the text of the .docx."""
    problems: list[Problem] = []
    located = {view.items[di].where: main_items[mi] for mi, di in pairs}
    bibliography = {id(p) for p in view.bibliography}
    for block in doc.blocks:
        paragraphs = [block] if isinstance(block, DPara) else [c for row in block.rows for c in row]
        for para in paragraphs:
            if id(para) in bibliography:
                continue
            item = located.get(para.index)
            if item is not None and item.generated:
                continue
            prose = _prose(para)
            british = sorted({x.group(0) for x in BRITISH.finditer(prose)})
            if british:
                problems.append(
                    Problem("british", _where(para.index, located), f"British spelling {british}")
                )
            # The placeholders the comparison uses are reserved: one in the text itself could stand
            # in for what it replaces (Codex review of 2026-10-04).
            residue = sorted(
                {
                    x.group(0)
                    for x in re.finditer(
                        r"\[@[^\]]*\]|@cds\d+|\?\?\?|\[\d+(?:,\s*\d+)*\]|[" + RESERVED + "]", prose
                    )
                }
            )
            if residue:
                problems.append(
                    Problem("residue", _where(para.index, located), f"citation residue {residue}")
                )
    everything = "".join(p.text for p in _all_paragraphs(doc))
    for glyph, name in REQUIRED_GLYPHS:
        if glyph not in everything:
            problems.append(Problem("glyph", name, f"{glyph!r} is nowhere in the .docx"))
    k_heading = next(
        (b for b in inp.manuscript.blocks if b.kind == "heading" and b.raw.startswith("K. ")), None
    )
    if k_heading is not None:
        key = f"H{k_heading.level}|{norm(inline(k_heading.raw))}"
        at = next((i for i, x in enumerate(view.items) if x.key == key), None)
        if at is None or at + 1 >= len(view.items) or not view.items[at + 1].key.startswith("P|"):
            problems.append(
                Problem(
                    "structure",
                    "§K",
                    "the AI usage disclosure appendix is not in the .docx with its text",
                )
            )
    # A page break before the references and before each appendix, and nowhere else in the text
    # (Codex review of 2026-10-04: removing every break passed, since only the record was compared).
    wanted = {
        str(b.line)
        for b in inp.manuscript.blocks
        if b.kind == "heading" and (b.raw == "References" or (b.appendix and b.level == 1))
    }
    to_main = {di: main_items[mi] for mi, di in pairs}
    found: dict[str, int] = {}
    for di, item in enumerate(view.items):
        if item.page_break:
            mine = to_main.get(di)
            place = str(mine.where) if mine is not None else f"docx block {item.where}"
            found[place] = found.get(place, 0) + item.page_break
    # One break each, counted: two breaks in a row leave an empty page (Codex review of 2026-10-04);
    # and none anywhere else, on the title pages or in a table cell.
    if found != dict.fromkeys(wanted, 1) or doc.break_count != len(wanted):
        problems.append(
            Problem(
                "structure",
                "page breaks",
                f"breaks before {sorted(found.items())}, expected one before each of {sorted(wanted)}",
            )
        )
    return problems


def check_contract(inp: Inputs) -> list[Problem]:
    """The converter's record of what it changed must be what this check enumerates on its own."""
    c, m = inp.contract, inp.manuscript
    if not c:
        return [Problem("contract", "record", "no record of the conversion was given")]
    problems: list[Problem] = []

    def differ(section: str, ours: Any, theirs: Any) -> None:
        if ours != theirs:
            problems.append(
                Problem(
                    "contract",
                    section,
                    f"make_docx_source.py recorded {str(theirs)[:160]}, this check reads {str(ours)[:160]}",
                )
            )

    differ("source", hashlib.sha256(m.text.encode("utf-8")).hexdigest(), c.get("source_sha256"))
    differ(
        "citations",
        [[x.k, x.line, list(x.ids), x.kind, x.removed, x.prefix, x.suffix] for x in m.cites],
        [
            [x["k"], x["line"], x["ids"], x["kind"], x["removed"], x["prefix"], x["suffix"]]
            for x in c.get("citations", [])
        ],
    )
    figures = [b for b in m.blocks if b.kind == "figure"]
    differ(
        "figures",
        [[b.number, b.name, [b.line - 1, b.last + 1]] for b in figures],
        [[x["number"], x["name"], x["lines"]] for x in c.get("figures", [])],
    )
    tables = [b for b in m.blocks if b.kind == "table"]
    differ(
        "tables",
        [[b.number, [b.line, b.last], b.caption_line] for b in tables],
        [[x["number"], x["lines"], x["caption_line"]] for x in c.get("tables", [])],
    )
    doi = preprint(inp.cff)
    note = [[label, [m.rows[label][0]] * 2] for label in NOTE_BEFORE]
    note += [["Preprint", []]] if doi else []
    note += [["AI disclosure", [m.ai.line, m.ai.last]]]
    note += [[label, [m.rows[label][0]] * 2] for label in NOTE_AFTER]
    differ("author_note", note, [[x["what"], x["lines"]] for x in c.get("author_note", [])])
    head = c.get("head", {})
    differ(
        "head",
        [
            m.title,
            m.rows["Author"][1],
            m.rows["Affiliation"][1],
            list(m.abstract_lines),
            list(inp.cff.get("keywords") or []),
            doi,
        ],
        [
            head.get("title"),
            head.get("author"),
            head.get("affiliation"),
            head.get("abstract_lines"),
            head.get("keywords"),
            head.get("preprint_doi"),
        ],
    )
    references = next(b for b in m.blocks if b.kind == "references")
    differ(
        "bibliography",
        [[references.line, references.last], [item["x-cds"]["n"] for item in inp.refs]],
        [c.get("bibliography", {}).get("lines"), c.get("bibliography", {}).get("ids")],
    )
    breaks = [
        b.line
        for b in m.blocks
        if b.kind == "heading" and (b.raw == "References" or (b.appendix and b.level == 1))
    ]
    differ("page_breaks", breaks, c.get("page_breaks"))
    drops = {("author table, left out", tuple(m.dropped_lines))}
    drops.add(("AI disclosure, moved to the Author Note", (m.ai.line - 1, m.ai.last + 1)))
    drops |= {("marker", (b.line, b.line)) for b in m.blocks if b.kind == "marker"}
    drops |= {("rule", (b.line, b.line)) for b in m.blocks if b.kind == "rule"}
    drops.add(("note after the references", (m.note.line, m.note.last)))
    differ(
        "drops", sorted(drops), sorted((x["what"], tuple(x["lines"])) for x in c.get("drops", []))
    )
    return problems


def run_checks(inp: Inputs, data: bytes) -> tuple[list[Problem], dict[str, Any]]:
    """Every check on one ``.docx``. Returns the problems and what the mutation test targets."""
    doc = read_docx(data, inp.reference)
    view = docx_view(doc)
    main_items = main_stream(inp.manuscript)
    problems = doc.problems + view.problems
    fulltext, pairs = align(main_items, view.items)
    problems += fulltext
    problems += check_contract(inp)
    problems += check_citations(inp, view, main_items, pairs)
    problems += check_bibliography(inp, view, doc)
    problems += check_links(inp, view, doc)
    problems += check_head(inp, view, doc)
    problems += check_figures(inp, view, doc)
    problems += check_tables(inp, view)
    code = code_blocks(view, main_items, pairs)
    problems += check_line_breaks(doc, code)
    problems += check_whitespace(inp, doc, code)
    problems += check_drops(inp, doc)
    problems += check_text(inp, view, doc, main_items, pairs)
    state = {"doc": doc, "view": view, "main_items": main_items, "pairs": pairs}
    return sorted(set(problems)), state


def docx_text(doc: Docx) -> str:
    """The text of the .docx in document order, one paragraph per line, for the claim-boundary check."""
    lines: list[str] = []
    for block in doc.blocks:
        if isinstance(block, DPara):
            lines.append(block.text)
        else:
            lines.extend(" | ".join(cell.text for cell in row) for row in block.rows)
    return "\n\n".join(line for line in lines if line.strip()) + "\n"


def write_apa_fixture(inp: Inputs, state: dict[str, Any]) -> int:
    """Write citations-apa.tsv from what citeproc set in the .docx, citation by citation."""
    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    found: dict[int, str] = {}
    for mi, di in pairs:
        for k, g in zip(main_items[mi].cites, view.items[di].cites, strict=False):
            found[k] = norm(view.groups[g][0])
    missing = [c.k for c in inp.manuscript.cites if c.k not in found]
    if missing:
        raise SystemExit(
            f"[docx-check] cannot write the fixture: citations {missing} were not placed"
        )
    rows = [
        f"{c.context}\t{', '.join(map(str, c.ids))}\t{c.kind}\t{found[c.k]}\n"
        for c in inp.manuscript.cites
    ]
    (inp.root / APA_CITATIONS).write_text(
        APA_HEADER + "".join(rows), encoding="utf-8", newline="\n"
    )
    return len(rows)


def figure_text_problems(root: Path, directory: Path) -> list[Problem]:
    """Each figure's numbers, row by row, in the text read back from its standalone PDF."""
    from make_figures import expected_rows  # noqa: PLC0415

    problems: list[Problem] = []
    for name, rows in expected_rows(root).items():
        path = directory / f"fig-{name}.txt"
        if not path.is_file():
            problems.append(Problem("figure", name, f"{path} is missing"))
            continue
        page = path.read_text(encoding="utf-8")
        missing = [label for label, values in rows if not row_on_page(page, label, values)]
        if missing:
            problems.append(
                Problem(
                    "figure",
                    name,
                    f"{len(missing)} of {len(rows)} rows are not in the standalone PDF as drawn, e.g. {missing[:3]}",
                )
            )
    return problems


# --------------------------------------------------------------------------------------------------
# Mutations: break a copy of a .docx one way, and require exactly the diagnostics that way should give


class NoTarget(Exception):
    """The document offers nothing to mutate this way; the test fails rather than skipping it."""


Expectation = set[tuple[str, str]]
Mutation = Callable[
    [bytes, dict[str, Any], dict[str, Any]], tuple[bytes, dict[str, Any], Expectation]
]


def _rewrite(
    data: bytes, edit: Callable[[ET.Element], None], part: str = "word/document.xml"
) -> bytes:
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {name: archive.read(name) for name in archive.namelist()}
    source = parts[part].decode("utf-8")
    for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', source):
        # ElementTree names the namespaces it writes ns0, ns1, ... and refuses those as names to
        # register; a part it wrote before keeps them as they are.
        if not re.fullmatch(r"ns\d+", prefix):
            ET.register_namespace(prefix, uri)
    root = ET.fromstring(parts[part])
    edit(root)
    parts[part] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name in archive.namelist():
            out.writestr(name, parts[name])
    return buffer.getvalue()


def _body(root: ET.Element) -> ET.Element:
    body = root.find(w("body"))
    if body is None:
        raise NoTarget("no body")
    return body


def _target(state: dict[str, Any], *, needs: str = "") -> tuple[int, int]:
    """A plain body paragraph of main.md without citations: (index of the .docx block, main.md line)."""
    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    keys = [x.key for x in main_items]
    for mi, di in pairs:
        mine, theirs = main_items[mi], view.items[di]
        block = mine.block
        if not (
            isinstance(block, MBlock)
            and block.kind == "para"
            and not block.generated
            and not mine.cites
        ):
            continue
        if keys.count(mine.key) != 1 or len(mine.key.split()) < 12 or needs not in mine.key:
            continue
        if needs and sum(x.key.count(needs) for x in view.items) < 2 and needs == "\u2265":
            continue
        if isinstance(theirs.block, DPara) and theirs.block.style in (
            "Body Text",
            "First Paragraph",
        ):
            return theirs.where, mine.where
    raise NoTarget(f"no plain paragraph{' with ' + needs if needs else ''}")


def _texts(element: ET.Element) -> list[ET.Element]:
    return [t for t in element.iter(w("t")) if t.text]


def m_drop_paragraph(data, contract, state):
    index, line = _target(state)
    return (
        _rewrite(data, lambda r: _body(r).remove(list(_body(r))[index])),
        contract,
        {("fulltext", f"main.md:{line}")},
    )


def m_double_paragraph(data, contract, state):
    index, line = _target(state)

    def edit(root):
        body = _body(root)
        body.insert(index + 1, copy.deepcopy(list(body)[index]))

    return _rewrite(data, edit), contract, {("fulltext", f"main.md:{line}")}


def m_change_number(data, contract, state):
    index, line = _target(state, needs="0")

    def edit(root):
        for node in _texts(list(_body(root))[index]):
            digit = re.search(r"\d", node.text)
            if digit:
                new = str((int(digit.group(0)) + 1) % 10)
                node.text = node.text[: digit.start()] + new + node.text[digit.end() :]
                return
        raise NoTarget("no digit")

    return _rewrite(data, edit), contract, {("fulltext", f"main.md:{line}")}


def m_flip_sign(data, contract, state):
    index, line = _target(state, needs="\u2265")

    def edit(root):
        for node in _texts(list(_body(root))[index]):
            if "\u2265" in node.text:
                node.text = node.text.replace("\u2265", "\u2264", 1)
                return
        raise NoTarget("no sign")

    return _rewrite(data, edit), contract, {("fulltext", f"main.md:{line}")}


def _figure_image(state: dict[str, Any], number: int) -> int:
    group = state["view"].figures.get(number)
    if not group or group["body"] is None:
        raise NoTarget(f"no Figure {number}")
    return group["body"].index


def _blips(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{{{A}}}blip"))


def m_drop_figure(data, contract, state):
    index = _figure_image(state, 1)
    return (
        _rewrite(data, lambda r: _body(r).remove(list(_body(r))[index])),
        contract,
        {("figure", "Figure 1")},
    )


def m_swap_figures(data, contract, state):
    first, second = _figure_image(state, 1), _figure_image(state, 2)

    def edit(root):
        body = list(_body(root))
        a, b = _blips(body[first])[0], _blips(body[second])[0]
        key = f"{{{R}}}embed"
        ea, eb = a.get(key), b.get(key)
        a.set(key, eb)
        b.set(key, ea)

    # Each picture is now also drawn at the other's proportions.
    return (
        _rewrite(data, edit),
        contract,
        {("figure", "Figure 1"), ("figure", "Figure 2"), ("structure", "pictures")},
    )


def m_double_figure(data, contract, state):
    first, second = _figure_image(state, 1), _figure_image(state, 2)

    def edit(root):
        body = list(_body(root))
        key = f"{{{R}}}embed"
        _blips(body[second])[0].set(key, _blips(body[first])[0].get(key))

    return (
        _rewrite(data, edit),
        contract,
        {("figure", "Figure 2"), ("structure", "pictures")},
    )


def _entry(state: dict[str, Any], position: int) -> tuple[int, int]:
    bibliography = state["view"].bibliography
    if len(bibliography) <= position:
        raise NoTarget("too few references")
    para = bibliography[position]
    ids = [int(x) for name in para.bookmarks for x in re.findall(r"^ref-cds(\d+)$", name)]
    return para.index, ids[-1]


def m_drop_reference(data, contract, state):
    index, n = _entry(state, 0)
    return (
        _rewrite(data, lambda r: _body(r).remove(list(_body(r))[index])),
        contract,
        {("bibliography", f"[{n}]")},
    )


def m_move_year(data, contract, state):
    dated = [p for p in state["view"].bibliography if re.search(r"\(\d{4}\)", p.text)]
    if len(dated) < 2:
        raise NoTarget("too few dated references")
    index, n = _entry(state, state["view"].bibliography.index(dated[1]))

    def edit(root):
        for node in _texts(list(_body(root))[index]):
            year = re.search(r"\((\d{4})\)", node.text)
            if year:
                node.text = node.text.replace(year.group(0), f"({int(year.group(1)) + 1})", 1)
                return
        raise NoTarget("no year")

    return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}


def m_rename_author(data, contract, state):
    """The last author of a reference renamed: an author list that kept its length but lost a name."""
    for position, para in enumerate(state["view"].bibliography):
        if " & " in para.text:
            index, n = _entry(state, position)

            def edit(root, index=index):
                for node in _texts(list(_body(root))[index]):
                    named = re.search(r"& ([^,]+),", node.text)
                    if named:
                        node.text = (
                            node.text[: named.start(1)] + "Nobody" + node.text[named.end(1) :]
                        )
                        return
                raise NoTarget("the ampersand and the name are not in one run")

            return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}
    raise NoTarget("no reference with two authors or more")


def _citation_runs(paragraph: ET.Element) -> list[list[ET.Element]]:
    groups: list[list[ET.Element]] = []
    current: list[ET.Element] | None = None
    for run in paragraph.iter(w("r")):
        style = run.find(f"{w('rPr')}/{w('rStyle')}")
        if style is not None and style.get(w("val")) == CITATION_STYLE:
            if current is None:
                current = []
                groups.append(current)
            current.append(run)
        elif any(t.text for t in run.iter(w("t"))):
            current = None
    return groups


def m_repoint_citation(data, contract, state):
    """A citation set as another entry's, with as many entries: what a wrong identifier would print."""
    inp: Inputs = state["inputs"]
    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    single = [c for c in inp.manuscript.cites if len(c.ids) == 1]
    for mi, di in pairs:
        for position, k in enumerate(main_items[mi].cites):
            cite = inp.manuscript.cites[k - 1]
            other = next((c for c in single if c.ids != cite.ids and c.kind == cite.kind), None)
            if len(cite.ids) != 1 or other is None:
                continue
            index = view.items[di].where
            replacement = inp.apa_rows[other.k - 1][3]

            def edit(root, index=index, position=position, replacement=replacement):
                runs = _citation_runs(list(_body(root))[index])[position]
                texts = [t for run in runs for t in run.iter(w("t"))]
                texts[0].text = replacement
                for node in texts[1:]:
                    node.text = ""

            return _rewrite(data, edit), contract, {("citation", f"citation {k}")}
    raise NoTarget("no two single citations of one kind")


def m_move_cell_boundary(data, contract, state):
    view = state["view"]
    for number in sorted(view.tables):
        table = view.tables[number]["body"]
        if table is None:
            continue
        for r, row in enumerate(table.rows[1:], start=1):
            for c in range(len(row) - 1):
                if len(row[c].text.split()) >= 2 and row[c + 1].text.strip():

                    def edit(root, index=table.index, r=r, c=c):
                        rows = list(list(_body(root))[index].iter(w("tr")))
                        cells = rows[r].findall(w("tc"))
                        left, right = _texts(cells[c]), _texts(cells[c + 1])
                        word = left[-1].text.rstrip().rsplit(" ", 1)
                        if len(word) != 2:
                            raise NoTarget("the last run of the cell holds one word")
                        left[-1].text = word[0]
                        right[0].text = word[1] + " " + right[0].text

                    return _rewrite(data, edit), contract, {("table", f"Table {number}")}
    raise NoTarget("no table cell of two words beside another")


def _append(data: bytes, index: int, text: str) -> bytes:
    def edit(root):
        nodes = _texts(list(_body(root))[index])
        nodes[-1].text = nodes[-1].text + text
        nodes[-1].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    return _rewrite(data, edit)


def m_british(data, contract, state):
    index, line = _target(state)
    return (
        _append(data, index, " analysed"),
        contract,
        {("british", f"main.md:{line}"), ("fulltext", f"main.md:{line}")},
    )


def _disclosure(state: dict[str, Any]) -> int:
    for para in state["view"].head:
        if para.style == "Author Note" and "AI assistance" in para.text:
            return para.index
    raise NoTarget("no AI disclosure in the Author Note")


def m_change_disclosure(data, contract, state):
    index = _disclosure(state)

    def edit(root):
        for node in _texts(list(_body(root))[index]):
            if "substantial" in node.text:
                node.text = node.text.replace("substantial", "considerable", 1)
                return
        raise NoTarget("the disclosure does not say 'substantial'")

    return _rewrite(data, edit), contract, {("author-note", "AI disclosure")}


def m_leave_disclosure(data, contract, state):
    index = _disclosure(state)
    m: Manuscript = state["inputs"].manuscript
    heading = next(b for b in m.blocks if b.kind == "heading" and b.raw.startswith("K. "))
    key = f"H{heading.level}|{norm(inline(heading.raw))}"
    target = next(x.where for x in state["view"].items if x.key == key)

    def edit(root):
        body = _body(root)
        children = list(body)
        copied = copy.deepcopy(children[index])
        style = copied.find(f"{w('pPr')}/{w('pStyle')}")
        if style is not None:
            style.set(w("val"), "BodyText")
        body.insert(children.index(children[target]) + 1, copied)

    return (
        _rewrite(data, edit),
        contract,
        {("author-note", "AI disclosure"), ("fulltext", f"main.md:{heading.line}")},
    )


def m_change_abstract(data, contract, state):
    para = next((p for p in state["view"].head if p.style == "Abstract"), None)
    if para is None:
        raise NoTarget("no abstract")

    def edit(root):
        node = _texts(list(_body(root))[para.index])[0]
        node.text = "Altered " + node.text.split(" ", 1)[-1]

    return _rewrite(data, edit), contract, {("head", "abstract")}


def m_keep_note(data, contract, state):
    bibliography = state["view"].bibliography
    if not bibliography:
        raise NoTarget("no reference list")
    m: Manuscript = state["inputs"].manuscript
    note = norm(inline(m.note.raw))
    # Reported after the reference list, which stands in the comparison where its block stands.
    references = next(b for b in m.blocks if b.kind == "references")

    def edit(root):
        body = _body(root)
        children = list(body)
        last = children[bibliography[-1].index]
        para = ET.Element(w("p"))
        run = ET.SubElement(para, w("r"))
        ET.SubElement(run, w("t")).text = note
        body.insert(children.index(last) + 1, para)

    return (
        _rewrite(data, edit),
        contract,
        {("drop", "note after the references"), ("fulltext", f"main.md:{references.line}")},
    )


def m_residue(data, contract, state):
    index, line = _target(state)
    return (
        _append(data, index, " [@cds44]"),
        contract,
        {("residue", f"main.md:{line}"), ("fulltext", f"main.md:{line}")},
    )


# The ways past the check that the Codex review of 2026-10-04 found, each kept as a mutation.


def m_volume(data, contract, state):
    """A reference's volume changed so that the old value still occurs inside the new one (8 → 98)."""
    for position, para in enumerate(state["view"].bibliography):
        index, n = _entry(state, position)

        def edit(root, index=index):
            for node in _texts(list(_body(root))[index]):
                if re.fullmatch(r"\d+", node.text):
                    node.text = "9" + node.text
                    return
            raise NoTarget("no volume of its own run")

        try:
            return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}
        except NoTarget:
            continue
    raise NoTarget("no reference with a volume")


def m_append_reference(data, contract, state):
    """An invented entry appended to an existing reference's paragraph, in a run of its own after
    the link (so that the link's text is unchanged and only the reading of the entry can see it)."""
    index, n = _entry(state, 0)

    def edit(root):
        run = ET.SubElement(list(_body(root))[index], w("r"))
        node = ET.SubElement(run, w("t"))
        node.text = " Invented, A. (2020). An invented title. Nowhere, 1, 1–2."
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}


def m_placeholder(data, contract, state):
    """A citation replaced by unstyled text that reads as the comparison's own placeholder."""
    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    for mi, di in pairs:
        if len(main_items[mi].cites) != 1:
            continue
        k, index, line = main_items[mi].cites[0], view.items[di].where, main_items[mi].where

        def edit(root, index=index):
            runs = _citation_runs(list(_body(root))[index])[0]
            for run in runs:
                props = run.find(w("rPr"))
                if props is not None:
                    run.remove(props)
            texts = [t for run in runs for t in run.iter(w("t"))]
            texts[0].text = PLACEHOLDER_CITE
            for node in texts[1:]:
                node.text = ""

        return (
            _rewrite(data, edit),
            contract,
            {("citation", f"citation {k}"), ("residue", f"main.md:{line}")},
        )
    raise NoTarget("no paragraph with one citation")


def _break_before_references(state: dict[str, Any]) -> tuple[int, int]:
    """(.docx block of the page break before References, main.md line of the block before it)."""
    view, main_items = state["view"], state["main_items"]
    heading = next(x for x in view.items if x.key.endswith("|References"))
    blocks = state["doc"].blocks
    at = next(i for i, b in enumerate(blocks) if isinstance(b, DPara) and b.index == heading.where)
    page_break = blocks[at - 1]
    if not (isinstance(page_break, DPara) and page_break.style == "Page Break"):
        raise NoTarget("no page break before References")
    mine = next(i for i, x in enumerate(main_items) if x.key.endswith("|References"))
    return page_break.index, main_items[mine - 1].where


def m_drop_break(data, contract, state):
    index, _ = _break_before_references(state)
    return (
        _rewrite(data, lambda r: _body(r).remove(list(_body(r))[index])),
        contract,
        {("structure", "page breaks")},
    )


def m_text_in_break(data, contract, state):
    index, before = _break_before_references(state)

    def edit(root):
        para = list(_body(root))[index]
        run = ET.SubElement(para, w("r"))
        ET.SubElement(run, w("t")).text = "The primary effect was 99.9 percent."

    return (
        _rewrite(data, edit),
        contract,
        # Page Break is a spacer one point high: what it holds is also too small to read.
        {("structure", "page breaks"), ("structure", "styles"), ("fulltext", f"main.md:{before}")},
    )


def m_text_beside_figure(data, contract, state):
    index = _figure_image(state, 1)

    def edit(root):
        para = list(_body(root))[index]
        run = ET.SubElement(para, w("r"))
        ET.SubElement(run, w("t")).text = "The primary effect was 99.9 percent."

    return _rewrite(data, edit), contract, {("figure", "Figure 1")}


def m_table_on_title_page(data, contract, state):
    table = next((b for b in state["doc"].blocks if isinstance(b, DTable)), None)
    if table is None:
        raise NoTarget("no table")

    def edit(root):
        body = _body(root)
        body.insert(1, copy.deepcopy(list(body)[table.index]))

    return _rewrite(data, edit), contract, {("head", "title pages")}


def m_move_reference(data, contract, state):
    """The first reference, with its identifying bookmark, moved into the introduction."""
    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    first = view.bibliography[0].index
    heading = next(i for i, x in enumerate(main_items) if x.key.startswith("H1|1. "))
    target = next(
        (view.items[di].where, main_items[mi].where) for mi, di in pairs if mi == heading + 1
    )

    def edit(root):
        body = _body(root)
        children = list(body)
        moved = [children[first]]
        k = first - 1
        while k >= 0 and children[k].tag == w("bookmarkStart"):
            moved.insert(0, children[k])
            k -= 1
        for element in moved:
            body.remove(element)
        at = list(body).index(children[target[0]]) + 1
        for offset, element in enumerate(moved):
            body.insert(at + offset, element)

    return (
        _rewrite(data, edit),
        contract,
        {("fulltext", f"main.md:{target[1]}"), ("bibliography", "location")},
    )


def m_content_control(data, contract, state):
    """A paragraph set a second time inside a content control (w:sdt)."""
    index, line = _target(state)

    def edit(root):
        body = _body(root)
        sdt = ET.Element(w("sdt"))
        ET.SubElement(sdt, w("sdtPr"))
        content = ET.SubElement(sdt, w("sdtContent"))
        content.append(copy.deepcopy(list(body)[index]))
        body.insert(index + 1, sdt)

    return _rewrite(data, edit), contract, {("structure", "unread content")}


def m_hidden(data, contract, state):
    """A run of a paragraph hidden: its text is in the file, not on the page."""
    index, _ = _target(state)

    def edit(root):
        run = next(r for r in list(_body(root))[index].iter(w("r")) if _texts(r))
        props = run.find(w("rPr"))
        if props is None:
            props = ET.Element(w("rPr"))
            run.insert(0, props)
        ET.SubElement(props, w("vanish"))

    return _rewrite(data, edit), contract, {("structure", "hidden text")}


# Found by the second review of 2026-10-04, or next to what it was trying.


def m_row_in_content_control(data, contract, state):
    """A table row set a second time, inside a content control around the row."""
    view = state["view"]
    number = min(view.tables)
    table = view.tables[number]["body"]
    if table is None or len(table.rows) < 2:
        raise NoTarget("no table with a body row")

    def edit(root):
        element = list(_body(root))[table.index]
        rows = element.findall(w("tr"))
        sdt = ET.Element(w("sdt"))
        ET.SubElement(sdt, w("sdtPr"))
        content = ET.SubElement(sdt, w("sdtContent"))
        content.append(copy.deepcopy(rows[1]))
        element.insert(list(element).index(rows[1]) + 1, sdt)

    return _rewrite(data, edit), contract, {("structure", "unread content")}


def m_inline_page_break(data, contract, state):
    """A page break set inside a paragraph, as a run, rather than as a page-break paragraph."""
    index, _ = _target(state)

    def edit(root):
        run = ET.SubElement(list(_body(root))[index], w("r"))
        ET.SubElement(run, w("br")).set(w("type"), "page")

    return _rewrite(data, edit), contract, {("structure", "page breaks")}


def m_alt_chunk(data, contract, state):
    """Another document imported into the body (w:altChunk), whose text is in no part read here."""
    index, _ = _target(state)

    def edit(root):
        chunk = ET.Element(w("altChunk"))
        chunk.set(f"{{{R}}}id", "rIdImportedChunk")
        _body(root).insert(index + 1, chunk)

    return _rewrite(data, edit), contract, {("structure", "unread content")}


# Found by the third review of 2026-10-04.

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _bib_with(state: dict[str, Any], test: Callable[[DPara], bool]) -> tuple[int, int, DPara]:
    for position, para in enumerate(state["view"].bibliography):
        if test(para):
            index, n = _entry(state, position)
            return index, n, para
    raise NoTarget("no such reference")


def m_volume_point(data, contract, state):
    """A reference's volume 8 written .8: a point is punctuation, but not a separator there."""
    index, n, _ = _bib_with(state, lambda p: any(re.fullmatch(r"\d+", t) for t, _ in p.runs))

    def edit(root):
        node = next(t for t in _texts(list(_body(root))[index]) if re.fullmatch(r"\d+", t.text))
        node.text = "." + node.text

    return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}


def m_doi_apostrophe(data, contract, state):
    """An apostrophe inside a reference's DOI, in the text shown."""
    index, n, _ = _bib_with(state, lambda p: "https://doi.org/" in p.text)

    def edit(root):
        node = next(
            t for t in _texts(list(_body(root))[index]) if t.text.startswith("https://doi.org/")
        )
        node.text = node.text[:20] + "'" + node.text[20:]

    return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}


def _last_run(paragraph: ET.Element) -> ET.Element:
    runs = [r for r in paragraph.findall(w("r")) if _texts(r)]
    if not runs:
        raise NoTarget("no run")
    return runs[-1]


def m_alternate_content(data, contract, state):
    """A run moved into alternate content, with a choice and a fallback of it."""
    index, line = _target(state)

    def edit(root):
        paragraph = list(_body(root))[index]
        run = _last_run(paragraph)
        position = list(paragraph).index(run)
        paragraph.remove(run)
        alternate = ET.Element(f"{{{MC}}}AlternateContent")
        ET.SubElement(alternate, f"{{{MC}}}Choice").append(run)
        ET.SubElement(alternate, f"{{{MC}}}Fallback").append(copy.deepcopy(run))
        paragraph.insert(position, alternate)

    return (
        _rewrite(data, edit),
        contract,
        {("structure", "unread content"), ("fulltext", f"main.md:{line}")},
    )


def m_equation(data, contract, state):
    """An equation set in a paragraph, carrying a number of its own."""
    index, _ = _target(state)

    def edit(root):
        math = ET.SubElement(list(_body(root))[index], f"{{{MATH}}}oMath")
        ET.SubElement(ET.SubElement(math, f"{{{MATH}}}r"), f"{{{MATH}}}t").text = "p < 0.001"

    return _rewrite(data, edit), contract, {("structure", "unread content")}


def m_symbol(data, contract, state):
    """A symbol set in a run."""
    index, _ = _target(state)

    def edit(root):
        sym = ET.SubElement(_last_run(list(_body(root))[index]), w("sym"))
        sym.set(w("font"), "Symbol")
        sym.set(w("char"), "F0B3")

    return _rewrite(data, edit), contract, {("structure", "unread content")}


def m_field(data, contract, state):
    """A run wrapped in a field whose instruction says something else."""
    index, line = _target(state)

    def edit(root):
        paragraph = list(_body(root))[index]
        run = _last_run(paragraph)
        position = list(paragraph).index(run)
        paragraph.remove(run)
        field_ = ET.Element(w("fldSimple"))
        field_.set(w("instr"), 'QUOTE "The primary effect was 99.9 percent."')
        field_.append(run)
        paragraph.insert(position, field_)

    return (
        _rewrite(data, edit),
        contract,
        {("structure", "unread content"), ("fulltext", f"main.md:{line}")},
    )


def _style(root: ET.Element, style_id: str) -> ET.Element:
    for style in root.iter(w("style")):
        if style.get(w("styleId")) == style_id:
            return style
    raise NoTarget(f"no style {style_id}")


def m_style_hidden(data, contract, state):
    """The Body Text style made to hide its text."""

    def edit(root):
        style = _style(root, "BodyText")
        props = style.find(w("rPr"))
        if props is None:
            props = ET.SubElement(style, w("rPr"))
        ET.SubElement(props, w("vanish"))

    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("structure", "hidden text"), ("package", "word/styles.xml")},
    )


def m_style_without_break(data, contract, state):
    """The Page Break style without its break."""

    def edit(root):
        style = _style(root, "PageBreak")
        for parent in style.iter():
            for child in list(parent):
                if child.tag == w("pageBreakBefore"):
                    parent.remove(child)

    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("structure", "page breaks"), ("package", "word/styles.xml")},
    )


def m_double_break(data, contract, state):
    """The page break before References set twice, which leaves an empty page."""
    index, _ = _break_before_references(state)

    def edit(root):
        body = _body(root)
        body.insert(index + 1, copy.deepcopy(list(body)[index]))

    return _rewrite(data, edit), contract, {("structure", "page breaks")}


def m_trailing_break(data, contract, state):
    """A page break after the last of the text."""
    index, _ = _break_before_references(state)

    def edit(root):
        body = _body(root)
        children = list(body)
        at = len(children) - (1 if children and children[-1].tag == w("sectPr") else 0)
        body.insert(at, copy.deepcopy(children[index]))

    return _rewrite(data, edit), contract, {("structure", "page breaks")}


def m_link_target(data, contract, state):
    """A reference's link showing its DOI but leading to another."""
    _, n, para = _bib_with(state, lambda p: bool(p.links))
    rid = para.links[0][0]

    def edit(root):
        for rel in root:
            if rel.get("Id") == rid:
                target = rel.get("Target", "")
                rel.set("Target", target[:-1] + ("0" if target[-1:] != "0" else "1"))
                return
        raise NoTarget("no relationship")

    return (
        _rewrite(data, edit, "word/_rels/document.xml.rels"),
        contract,
        {("bibliography", f"[{n}]")},
    )


def m_extra_bookmark(data, contract, state):
    """A reference given, besides its own, the identifier another reference carries."""
    bibliography = state["view"].bibliography
    if len(bibliography) < 2:
        raise NoTarget("too few references")
    _, first = _entry(state, 0)
    index, second = _entry(state, 1)

    def edit(root):
        body = _body(root)
        children = list(body)
        k = index
        while k > 0 and children[k - 1].tag == w("bookmarkStart"):
            k -= 1
        start = ET.Element(w("bookmarkStart"))
        start.set(w("id"), "9999")
        start.set(w("name"), f"ref-cds{first}")
        end = ET.Element(w("bookmarkEnd"))
        end.set(w("id"), "9999")
        body.insert(list(body).index(children[index]) + 1, end)
        body.insert(list(body).index(children[k]), start)

    return (
        _rewrite(data, edit),
        contract,
        {("bibliography", "bookmarks"), ("bibliography", f"[{second}]")},
    )


def m_container_apostrophe(data, contract, state):
    """An apostrophe inside a reference's journal or proceedings title, where no link repeats it."""
    inp: Inputs = state["inputs"]
    containers = {
        item["x-cds"]["n"]: item["container-title"]
        for item in inp.refs
        if item.get("container-title")
    }
    for position, para in enumerate(state["view"].bibliography):
        index, n = _entry(state, position)
        if n not in containers or not any(t == containers[n] for t, _ in para.runs):
            continue

        def edit(root, index=index, title=containers[n]):
            node = next(t for t in _texts(list(_body(root))[index]) if t.text == title)
            node.text = node.text[:3] + "'" + node.text[3:]

        return _rewrite(data, edit), contract, {("bibliography", f"[{n}]")}
    raise NoTarget("no reference whose container title is a run of its own")


def m_link_outside_references(data, contract, state):
    """A link outside the reference list leading somewhere main.md does not say."""
    view = state["view"]
    bibliography = {id(p) for p in view.bibliography}
    for para in _all_paragraphs(state["doc"]):
        if id(para) in bibliography or not para.links:
            continue
        rid, shown = para.links[0]

        def edit(root, rid=rid):
            for rel in root:
                if rel.get("Id") == rid:
                    rel.set("Target", "https://example.com/elsewhere")
                    return
            raise NoTarget("no relationship")

        return (
            _rewrite(data, edit, "word/_rels/document.xml.rels"),
            contract,
            {("link", norm(shown)[:60])},
        )
    raise NoTarget("no link outside the reference list")


# Found by the fourth review of 2026-10-04.


def m_style_break_off(data, contract, state):
    """The Page Break style's break switched off with w:val="0"."""

    def edit(root):
        style = _style(root, "PageBreak")
        node = next(e for e in style.iter() if e.tag == w("pageBreakBefore"))
        node.set(w("val"), "0")

    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("structure", "page breaks"), ("package", "word/styles.xml")},
    )


def m_style_based_on_break(data, contract, state):
    """The Body Text style based on Page Break, so that every body paragraph breaks the page."""

    def edit(root):
        style = _style(root, "BodyText")
        for old in style.findall(w("basedOn")):
            style.remove(old)
        based = ET.Element(w("basedOn"))
        based.set(w("val"), "PageBreak")
        style.insert(1, based)

    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        # Body Text, based on the spacer, is set too small to read as well.
        {("structure", "page breaks"), ("structure", "styles"), ("package", "word/styles.xml")},
    )


def m_break_after_title(data, contract, state):
    """A page break set on the title page, where the text is not compared."""
    index, _ = _break_before_references(state)

    def edit(root):
        body = _body(root)
        body.insert(1, copy.deepcopy(list(body)[index]))

    return _rewrite(data, edit), contract, {("structure", "page breaks")}


def _first_table(state: dict[str, Any]) -> int:
    table = next((b for b in state["doc"].blocks if isinstance(b, DTable)), None)
    if table is None:
        raise NoTarget("no table")
    return table.index


def m_break_in_cell(data, contract, state):
    """A page break set inside a table cell."""
    index, _ = _break_before_references(state)
    table = _first_table(state)

    def edit(root):
        body = list(_body(root))
        cell = body[table].find(f"{w('tr')}/{w('tc')}")
        cell.append(copy.deepcopy(body[index]))

    # The cell is no longer one paragraph either.
    return (
        _rewrite(data, edit),
        contract,
        {("structure", "page breaks"), ("structure", "table cells")},
    )


def m_section_break(data, contract, state):
    """A section break, starting a new page, set on a paragraph."""
    index, _ = _target(state)

    def edit(root):
        paragraph = list(_body(root))[index]
        props = paragraph.find(w("pPr"))
        if props is None:
            props = ET.Element(w("pPr"))
            paragraph.insert(0, props)
        section = ET.SubElement(props, w("sectPr"))
        ET.SubElement(section, w("type")).set(w("val"), "nextPage")

    return _rewrite(data, edit), contract, {("structure", "page breaks")}


def m_grid_span(data, contract, state):
    """A heading cell spanning two columns of a grid one column wider: the headings shift."""
    table = _first_table(state)

    def edit(root):
        element = list(_body(root))[table]
        ET.SubElement(element.find(w("tblGrid")), w("gridCol"))
        cell = element.find(f"{w('tr')}/{w('tc')}")
        props = cell.find(w("tcPr"))
        if props is None:
            props = ET.Element(w("tcPr"))
            cell.insert(0, props)
        ET.SubElement(props, w("gridSpan")).set(w("val"), "2")

    return (
        _rewrite(data, edit),
        contract,
        # The added grid column has no width: the layout is reported as well.
        {("structure", "properties"), ("structure", "table grid"), ("structure", "table layout")},
    )


def m_row_height(data, contract, state):
    """A body row set one twip high, which clips what it holds."""
    table = _first_table(state)

    def edit(root):
        row = list(_body(root))[table].findall(w("tr"))[1]
        props = row.find(w("trPr"))
        if props is None:
            props = ET.Element(w("trPr"))
            row.insert(0, props)
        height = ET.SubElement(props, w("trHeight"))
        height.set(w("val"), "1")
        height.set(w("hRule"), "exact")

    return _rewrite(data, edit), contract, {("structure", "properties")}


def m_crop(data, contract, state):
    """Figure 1's picture cropped to its last tenth; the PNG is unchanged."""
    index = _figure_image(state, 1)

    def edit(root):
        fill = next(e for e in list(_body(root))[index].iter() if e.tag == f"{{{PIC}}}blipFill")
        crop = ET.Element(f"{{{A}}}srcRect")
        crop.set("l", "90000")
        fill.insert(1, crop)

    return _rewrite(data, edit), contract, {("structure", "pictures")}


def m_transparent(data, contract, state):
    """Figure 1's picture made fully transparent; the PNG is unchanged."""
    index = _figure_image(state, 1)

    def edit(root):
        blip = _blips(list(_body(root))[index])[0]
        ET.SubElement(blip, f"{{{A}}}alphaModFix").set("amt", "0")

    return _rewrite(data, edit), contract, {("structure", "pictures")}


def _header(data: bytes) -> str:
    names = [
        n
        for n in zipfile.ZipFile(io.BytesIO(data)).namelist()
        if re.fullmatch(r"word/header\d*\.xml", n)
    ]
    if not names:
        raise NoTarget("no header")
    return names[0]


def m_header_equation(data, contract, state):
    """An equation set in the header, which shows on every page."""
    part = _header(data)

    def edit(root):
        math = ET.SubElement(root.find(w("p")), f"{{{MATH}}}oMath")
        ET.SubElement(ET.SubElement(math, f"{{{MATH}}}r"), f"{{{MATH}}}t").text = "p < 0.001"

    return (
        _rewrite(data, edit, part),
        contract,
        {("structure", "header"), ("package", "word/header1.xml")},
    )


def m_header_field(data, contract, state):
    """The header's page-number field turned into one that quotes a sentence, its cache still 1."""
    part = _header(data)

    def edit(root):
        node = next(root.iter(w("instrText")))
        node.text = ' QUOTE "The primary effect was 99.9 percent." '

    return (
        _rewrite(data, edit, part),
        contract,
        {("structure", "header"), ("package", "word/header1.xml")},
    )


def m_link_mode(data, contract, state):
    """A reference's link relationship without TargetMode="External"."""
    _, n, para = _bib_with(state, lambda p: bool(p.links))
    rid = para.links[0][0]

    def edit(root):
        for rel in root:
            if rel.get("Id") == rid:
                del rel.attrib["TargetMode"]
                return
        raise NoTarget("no relationship")

    return (
        _rewrite(data, edit, "word/_rels/document.xml.rels"),
        contract,
        {("bibliography", f"[{n}]"), ("package", "word/_rels/document.xml.rels")},
    )


def m_unwrap_link(data, contract, state):
    """A link outside the reference list unwrapped into plain runs: the text stays, the link goes."""
    view = state["view"]
    bibliography = {id(p) for p in view.bibliography}
    para = next(
        (p for p in _all_paragraphs(state["doc"]) if id(p) not in bibliography and p.links), None
    )
    if para is None:
        raise NoTarget("no link outside the reference list")
    shown = norm(para.links[0][1])
    index = para.index

    def edit(root):
        paragraph = list(_body(root))[index]
        link = paragraph.find(w("hyperlink"))
        position = list(paragraph).index(link)
        paragraph.remove(link)
        for offset, run in enumerate(list(link)):
            paragraph.insert(position + offset, run)

    return _rewrite(data, edit), contract, {("link", shown[:60])}


def m_bookmark_in_cell(data, contract, state):
    """A second bookmark of the first reference's identifier, inside a table cell."""
    _, first = _entry(state, 0)
    table = _first_table(state)

    def edit(root):
        paragraph = list(_body(root))[table].find(f"{w('tr')}/{w('tc')}/{w('p')}")
        start = ET.Element(w("bookmarkStart"))
        start.set(w("id"), "9998")
        start.set(w("name"), f"ref-cds{first}")
        end = ET.Element(w("bookmarkEnd"))
        end.set(w("id"), "9998")
        paragraph.insert(1, start)
        paragraph.append(end)

    return _rewrite(data, edit), contract, {("bibliography", "bookmarks")}


def m_added_link(data, contract, state):
    """A plain run of a body paragraph made into a link that main.md does not have."""
    index, _ = _target(state)
    rid = "rIdAddedLink"

    def add_relationship(root):
        rel = ET.SubElement(root, f"{{{PKG}}}Relationship")
        rel.set("Id", rid)
        rel.set("Type", f"{R}/hyperlink")
        rel.set("Target", "https://example.com/added")
        rel.set("TargetMode", "External")

    shown: list[str] = []

    def wrap(root):
        paragraph = list(_body(root))[index]
        run = _last_run(paragraph)
        position = list(paragraph).index(run)
        paragraph.remove(run)
        link = ET.Element(w("hyperlink"))
        link.set(f"{{{R}}}id", rid)
        link.append(run)
        paragraph.insert(position, link)
        shown.append("".join(t.text or "" for t in run.iter(w("t"))))

    mutated = _rewrite(_rewrite(data, add_relationship, "word/_rels/document.xml.rels"), wrap)
    return mutated, contract, {("link", norm(shown[0])[:60])}


# Found by the fifth review of 2026-10-04.


def _picture_part(state: dict[str, Any], local: str) -> Callable[[ET.Element], ET.Element]:
    """The first ``a:<local>`` of Figure 1's picture, in a parsed document.xml."""
    index = _figure_image(state, 1)
    return lambda root: next(
        e for e in list(_body(root))[index].iter() if e.tag == f"{{{A}}}{local}"
    )


def m_picture_mirrored(data, contract, state):
    """Figure 1's picture mirrored left to right; the PNG is unchanged."""
    find = _picture_part(state, "xfrm")
    return (
        _rewrite(data, lambda root: find(root).set("flipH", "1")),
        contract,
        {("structure", "pictures")},
    )


def m_picture_turned(data, contract, state):
    """Figure 1's picture turned upside down; the PNG is unchanged."""
    find = _picture_part(state, "xfrm")
    return (
        _rewrite(data, lambda root: find(root).set("rot", "10800000")),
        contract,
        {("structure", "pictures")},
    )


def m_picture_squeezed(data, contract, state):
    """Figure 1's picture squeezed into the last tenth of its frame; the PNG is unchanged."""
    find = _picture_part(state, "fillRect")
    return (
        _rewrite(data, lambda root: find(root).set("l", "90000")),
        contract,
        {("structure", "pictures")},
    )


def m_picture_inner_size(data, contract, state):
    """Figure 1's picture drawn a tenth as wide as its frame; the frame is unchanged."""
    find = _picture_part(state, "xfrm")

    def edit(root):
        size = find(root).find(f"{{{A}}}ext")
        size.set("cx", str(int(size.get("cx", "0")) // 10))

    return _rewrite(data, edit), contract, {("structure", "pictures")}


def _body_text_property(tag: str, **attributes: str) -> Callable[[ET.Element], None]:
    def edit(root: ET.Element) -> None:
        style = _style(root, "BodyText")
        props = style.find(w("rPr"))
        if props is None:
            props = ET.SubElement(style, w("rPr"))
        element = ET.SubElement(props, w(tag))
        for key, value in attributes.items():
            element.set(w(key), value)

    return edit


def m_style_white(data, contract, state):
    """The Body Text style set in white, on the white page."""
    edit = _body_text_property("color", val="FFFFFF")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_style_tiny(data, contract, state):
    """The Body Text style set at two points."""
    edit = _body_text_property("sz", val="4")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_style_face(data, contract, state):
    """The Body Text style set in a face of symbols."""
    edit = _body_text_property("rFonts", ascii="Wingdings", hAnsi="Wingdings")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_style_struck(data, contract, state):
    """The Body Text style struck through."""
    edit = _body_text_property("strike")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_style_twin(data, contract, state):
    """A copy of Page Break, under its name, set before the original, whose break is then switched off."""

    def edit(root):
        original = _style(root, "PageBreak")
        twin = copy.deepcopy(original)
        twin.set(w("styleId"), "PageBreakCopy")
        root.insert(list(root).index(original), twin)
        next(e for e in original.iter() if e.tag == w("pageBreakBefore")).set(w("val"), "0")

    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("structure", "styles"), ("package", "word/styles.xml"), ("structure", "page breaks")},
    )


def _first_list(data: bytes) -> tuple[str, str, str, set[int]]:
    """The first list of the body: its numId, its abstract definition, its level, and the indices of
    the body's paragraphs at that level of that definition."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    numbering = ET.fromstring(archive.read("word/numbering.xml"))
    body = _body(ET.fromstring(archive.read("word/document.xml")))
    abstract_of = {
        n.get(w("numId")): _value(n, "abstractNumId") for n in numbering.findall(w("num"))
    }
    items = [
        (i, _value(numbered, "numId"), _value(numbered, "ilvl"))
        for i, p in enumerate(body)
        if (numbered := p.find(f"{w('pPr')}/{w('numPr')}")) is not None
    ]
    if not items:
        raise NoTarget("no list")
    _, num_id, level = items[0]
    abstract = abstract_of.get(num_id, "")
    return (
        num_id,
        abstract,
        level,
        {i for i, n, lv in items if abstract_of.get(n) == abstract and lv == level},
    )


def m_list_label(data, contract, state):
    """The first list's label made a sentence, which Word draws before each of its items."""
    _, abstract, level, indices = _first_list(data)

    def edit(root):
        for definition in root.findall(w("abstractNum")):
            if definition.get(w("abstractNumId")) == abstract:
                for lvl in definition.findall(w("lvl")):
                    if lvl.get(w("ilvl")) == level:
                        lvl.find(w("lvlText")).set(
                            w("val"), "The primary effect was 99.9 percent. %1"
                        )

    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    lines = {
        main_items[mi].where
        for mi, di in pairs
        if isinstance(view.items[di].block, DPara) and view.items[di].block.index in indices
    }
    if not lines:
        raise NoTarget("no list item in the comparison")
    # A label is also one of those main.md's markers give, or reported (the eighth review).
    return (
        _rewrite(data, edit, "word/numbering.xml"),
        contract,
        {("fulltext", f"main.md:{line}") for line in lines} | {("structure", "numbering")},
    )


def m_list_redefined(data, contract, state):
    """A level redefined inside the first list, to draw numbers where its definition draws bullets."""
    num_id, _, level, _ = _first_list(data)

    def edit(root):
        num = next(n for n in root.findall(w("num")) if n.get(w("numId")) == num_id)
        override = ET.SubElement(num, w("lvlOverride"))
        override.set(w("ilvl"), level)
        lvl = ET.SubElement(override, w("lvl"))
        lvl.set(w("ilvl"), level)
        ET.SubElement(lvl, w("numFmt")).set(w("val"), "decimal")
        ET.SubElement(lvl, w("lvlText")).set(w("val"), "%1.")

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def _repack(data: bytes, change: Callable[[dict[str, bytes]], None]) -> bytes:
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {name: archive.read(name) for name in archive.namelist()}
    change(parts)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, part in parts.items():
            out.writestr(name, part)
    return buffer.getvalue()


def m_header_renamed(data, contract, state):
    """The header renamed word/running-head.xml, its relationship and content type with it, and a
    sentence set in it."""
    old = _header(data)

    def change(parts):
        root = ET.fromstring(parts.pop(old))
        paragraph = ET.SubElement(root, w("p"))
        ET.SubElement(
            ET.SubElement(paragraph, w("r")), w("t")
        ).text = "The primary effect was 99.9 percent."
        parts["word/running-head.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        parts[RELS] = parts[RELS].replace(old.removeprefix("word/").encode(), b"running-head.xml")
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            f"/{old}".encode(), b"/word/running-head.xml"
        )

    return (
        _repack(data, change),
        contract,
        {
            ("package", "parts"),
            ("package", "[Content_Types].xml"),
            ("package", RELS),
            ("package", "sectPr"),
            ("structure", "header"),
        },
    )


def m_picture_external(data, contract, state):
    """Figure 1's picture relationship marked external, while its drawing still embeds it."""
    index = _figure_image(state, 1)
    para = next(b for b in state["doc"].blocks if isinstance(b, DPara) and b.index == index)
    rid = para.images[0]

    def edit(root):
        for rel in root:
            if rel.get("Id") == rid:
                rel.set("TargetMode", "External")
                return
        raise NoTarget("no relationship")

    return (
        _rewrite(data, edit, RELS),
        contract,
        {("package", RELS), ("figure", "Figure 1"), ("structure", "pictures")},
    )


def m_header_literal(data, contract, state):
    """The header's field taken away, its cached "1" left as plain text on every page."""
    part = _header(data)

    def edit(root):
        paragraph = root.find(w("p"))
        for run in list(paragraph.findall(w("r"))):
            if run.find(w("t")) is None:
                paragraph.remove(run)

    return _rewrite(data, edit, part), contract, {("structure", "header"), ("package", part)}


def m_style_squeezed(data, contract, state):
    """The Body Text style set in an exact line one point high, which clips what it holds."""

    def edit(root):
        style = _style(root, "BodyText")
        props = style.find(w("pPr"))
        if props is None:
            props = ET.Element(w("pPr"))
            style.insert(list(style).index(style.find(w("name"))) + 1, props)
        spacing = ET.SubElement(props, w("spacing"))
        spacing.set(w("line"), "20")
        spacing.set(w("lineRule"), "exact")

    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_settings(data, contract, state):
    """A setting the reference document does not have: even pages with headers of their own, which
    the .docx does not give, so that half the pages lose their number."""
    return (
        _rewrite(
            data, lambda root: ET.SubElement(root, w("evenAndOddHeaders")), "word/settings.xml"
        ),
        contract,
        {("package", "word/settings.xml")},
    )


def m_separator_text(data, contract, state):
    """A sentence set in the footnote separator."""

    def edit(root):
        note = next(n for n in root.findall(w("footnote")) if n.get(w("type")) == "separator")
        ET.SubElement(
            note.find(f"{w('p')}/{w('r')}"), w("t")
        ).text = "The primary effect was 99.9 percent."

    return _rewrite(data, edit, "word/footnotes.xml"), contract, {("package", "word/footnotes.xml")}


def _add_relationship(kind: str, target: str) -> Callable[[ET.Element], None]:
    def edit(root: ET.Element) -> None:
        rel = ET.SubElement(root, f"{{{PKG}}}Relationship")
        rel.set("Id", "rIdAdded")
        rel.set("Type", kind)
        rel.set("Target", target)

    return edit


def m_footnote_relationship(data, contract, state):
    """A relationship of the footnotes to something other than an external link."""
    edit = _add_relationship(f"{R}/image", "media/added.png")
    return (
        _rewrite(data, edit, "word/_rels/footnotes.xml.rels"),
        contract,
        {("package", "word/_rels/footnotes.xml.rels")},
    )


def m_package_relationship(data, contract, state):
    """A relationship of the package the reference document does not have."""
    edit = _add_relationship(
        "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail",
        "docProps/thumbnail.png",
    )
    return _rewrite(data, edit, "_rels/.rels"), contract, {("package", "_rels/.rels")}


def m_table_wide(data, contract, state):
    """The first table set fifty thousand twips wide, past the edge of the page."""
    table = _first_table(state)

    def edit(root):
        size = list(_body(root))[table].find(f"{w('tblPr')}/{w('tblW')}")
        size.set(w("type"), "dxa")
        size.set(w("w"), "50000")

    return _rewrite(data, edit), contract, {("structure", "table layout")}


def m_column_narrow(data, contract, state):
    """The first table's first column set one point wide."""
    table = _first_table(state)

    def edit(root):
        list(_body(root))[table].find(f"{w('tblGrid')}/{w('gridCol')}").set(w("w"), "20")

    return _rewrite(data, edit), contract, {("structure", "table layout")}


def m_columns_wide(data, contract, state):
    """The first table's first column set wider than the text, so the grid runs past the margin."""
    table = _first_table(state)

    def edit(root):
        list(_body(root))[table].find(f"{w('tblGrid')}/{w('gridCol')}").set(w("w"), "9000")

    return _rewrite(data, edit), contract, {("structure", "table layout")}


def m_column_underscore(data, contract, state):
    """The first table's first column set "2_000" wide: a number to Python, not to a reader."""
    table = _first_table(state)

    def edit(root):
        list(_body(root))[table].find(f"{w('tblGrid')}/{w('gridCol')}").set(w("w"), "2_000")

    return _rewrite(data, edit), contract, {("structure", "table layout")}


def m_page_colour(data, contract, state):
    """A black page colour set beside the body."""

    def edit(root):
        colour = ET.Element(w("background"))
        colour.set(w("color"), "000000")
        root.insert(0, colour)

    return _rewrite(data, edit), contract, {("structure", "document")}


def m_twin_entry(data, contract, state):
    """A second word/document.xml in the archive, before the real one, with a paragraph dropped: a
    reader that takes the first copy reads a different document from one that takes the last."""
    index, _ = _target(state)
    dropped = _rewrite(data, lambda root: _body(root).remove(list(_body(root))[index]))
    archive = zipfile.ZipFile(io.BytesIO(data))
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns of the duplicate name it is asked to write
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr(
                "word/document.xml", zipfile.ZipFile(io.BytesIO(dropped)).read("word/document.xml")
            )
            for name in archive.namelist():
                out.writestr(name, archive.read(name))
    return buffer.getvalue(), contract, {("package", "parts")}


# Found by the sixth review of 2026-10-04.


def _body_text_paragraph_property(tag: str, **attributes: str) -> Callable[[ET.Element], None]:
    def edit(root: ET.Element) -> None:
        style = _style(root, "BodyText")
        props = style.find(w("pPr"))
        if props is None:
            props = ET.Element(w("pPr"))
            style.insert(list(style).index(style.find(w("name"))) + 1, props)
        element = ET.SubElement(props, w(tag))
        for key, value in attributes.items():
            element.set(w(key), value)

    return edit


def m_style_compressed(data, contract, state):
    """The Body Text style's lines set a tenth of single spacing apart, over one another."""
    edit = _body_text_paragraph_property("spacing", line="24", lineRule="auto")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_style_indent(data, contract, state):
    """The Body Text style indented twenty thousand twips, off the page."""
    edit = _body_text_paragraph_property("ind", left="20000")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_style_gap(data, contract, state):
    """The Body Text style set twenty thousand twips below the paragraph before it: a blank page."""
    edit = _body_text_paragraph_property("spacing", before="20000")
    return (
        _rewrite(data, edit, "word/styles.xml"),
        contract,
        {("package", "word/styles.xml"), ("structure", "styles")},
    )


def m_label_suppressed(data, contract, state):
    """The first list's level made to draw no label, by w:null on its text."""
    _, abstract, level, _ = _first_list(data)

    def edit(root):
        for definition in root.findall(w("abstractNum")):
            if definition.get(w("abstractNumId")) == abstract:
                for lvl in definition.findall(w("lvl")):
                    if lvl.get(w("ilvl")) == level:
                        lvl.find(w("lvlText")).set(w("null"), "1")

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def m_list_unnumbered(data, contract, state):
    """The first list's instance renumbered 0, which removes numbering, and its items with it."""
    num_id, _, _, _ = _first_list(data)
    body = _body(ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml")))
    indices = {
        i
        for i, p in enumerate(body)
        if (numbered := p.find(f"{w('pPr')}/{w('numPr')}")) is not None
        and _value(numbered, "numId") == num_id
    }

    def renumber(root):
        for num in root.findall(w("num")):
            if num.get(w("numId")) == num_id:
                num.set(w("numId"), "0")

    def unnumber(root):
        for i in indices:
            list(_body(root))[i].find(f"{w('pPr')}/{w('numPr')}/{w('numId')}").set(w("val"), "0")

    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    lines = {
        main_items[mi].where
        for mi, di in pairs
        if isinstance(view.items[di].block, DPara) and view.items[di].block.index in indices
    }
    return (
        _rewrite(_rewrite(data, renumber, "word/numbering.xml"), unnumber),
        contract,
        {("fulltext", f"main.md:{line}") for line in lines},
    )


def _edge_space(state: dict[str, Any], data: bytes) -> tuple[int, int, int]:
    """A plain paragraph of main.md whose .docx paragraph has a text node that begins with, or is,
    the space between two words: (index of the .docx block, position of that node, main.md line)."""
    body = _body(ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml")))
    view, main_items, pairs = state["view"], state["main_items"], state["pairs"]
    for mi, di in pairs:
        mine, theirs = main_items[mi], view.items[di]
        if not (
            isinstance(mine.block, MBlock)
            and mine.block.kind == "para"
            and not mine.block.generated
            and not mine.cites
            and isinstance(theirs.block, DPara)
        ):
            continue
        nodes = list(list(body)[theirs.block.index].iter(w("t")))
        texts = [n.text or "" for n in nodes] + [""]
        for k in range(1, len(nodes)):
            before, text, after = texts[k - 1], texts[k], texts[k + 1]
            # pandoc sets the space between two runs as a node of its own, or at a node's start.
            if text[:1] == " " and before[-1:].strip() and (text.strip() or after[:1].strip()):
                return theirs.block.index, k, mine.where
    raise NoTarget("no text node beginning with a space")


def m_space_unpreserved(data, contract, state):
    """A text node's xml:space="preserve" taken off, so that the space it begins with is dropped."""
    index, k, line = _edge_space(state, data)

    def edit(root):
        node = list(list(_body(root))[index].iter(w("t")))[k]
        del node.attrib[XML_SPACE]

    return _rewrite(data, edit), contract, {("fulltext", f"main.md:{line}")}


def m_space_default(data, contract, state):
    """A text node's xml:space set to "default", so that the space it begins with is dropped."""
    index, k, line = _edge_space(state, data)

    def edit(root):
        list(list(_body(root))[index].iter(w("t")))[k].set(XML_SPACE, "default")

    return (
        _rewrite(data, edit),
        contract,
        {("fulltext", f"main.md:{line}"), ("structure", "attributes")},
    )


def m_picture_large(data, contract, state):
    """Figure 1's picture and its frame drawn twice the size, past the edge of the page."""
    index = _figure_image(state, 1)

    def edit(root):
        for e in list(_body(root))[index].iter():
            if e.tag in (f"{{{WP}}}extent", f"{{{A}}}ext"):
                e.set("cx", str(int(e.get("cx", "0")) * 2))
                e.set("cy", str(int(e.get("cy", "0")) * 2))

    return _rewrite(data, edit), contract, {("structure", "pictures")}


def _block_of_style(state: dict[str, Any], style: str) -> int:
    block = next(
        (b for b in state["doc"].blocks if isinstance(b, DPara) and b.style == style), None
    )
    if block is None:
        raise NoTarget(f"no paragraph in the style {style!r}")
    return block.index


def m_blank_paragraphs(data, contract, state):
    """A hundred and fifty empty paragraphs after the title: pages with nothing on them."""
    index = _block_of_style(state, "Title")

    def edit(root):
        body = _body(root)
        for _ in range(150):
            body.insert(index + 1, ET.Element(w("p")))

    return _rewrite(data, edit), contract, {("structure", "empty paragraphs")}


def m_cell_blank(data, contract, state):
    """Twenty empty paragraphs added to a table cell: a row pages high."""
    table = _first_table(state)

    def edit(root):
        cell = list(_body(root))[table].find(f"{w('tr')}/{w('tc')}")
        for _ in range(20):
            cell.append(ET.Element(w("p")))

    # The cell is no longer one paragraph either.
    return (
        _rewrite(data, edit),
        contract,
        {("structure", "empty paragraphs"), ("structure", "table cells")},
    )


def m_after_table_repeated(data, contract, state):
    """The spacer after the first table set a hundred and fifty times: pages of nothing below it."""
    table = _first_table(state)

    def edit(root):
        body = _body(root)
        spacer = list(body)[table + 1]
        if spacer.tag != w("p"):
            raise NoTarget("no spacer after the table")
        for _ in range(150):
            body.insert(table + 2, copy.deepcopy(spacer))

    return _rewrite(data, edit), contract, {("structure", "empty paragraphs")}


def m_line_breaks(data, contract, state):
    """A hundred and fifty line breaks added to the title's run."""
    index = _block_of_style(state, "Title")

    def edit(root):
        run = list(_body(root))[index].find(w("r"))
        for _ in range(150):
            ET.SubElement(run, w("br"))

    return _rewrite(data, edit), contract, {("structure", "line breaks")}


def m_code_breaks(data, contract, state):
    """Three line breaks added to the end of a code block: lines its code does not have."""
    index = _block_of_style(state, "Source Code")

    def edit(root):
        run = list(list(_body(root))[index].iter(w("r")))[-1]
        for _ in range(3):
            ET.SubElement(run, w("br"))

    return _rewrite(data, edit), contract, {("structure", "line breaks")}


# Found by the seventh review of 2026-10-04.


def m_list_zero_padded(data, contract, state):
    """The first list renumbered "00", which a reader takes for 0, with its items."""
    num_id, _, _, _ = _first_list(data)

    def renumber(root):
        for num in root.findall(w("num")):
            if num.get(w("numId")) == num_id:
                num.set(w("numId"), "00")

    def refer(root):
        for element in root.iter(w("numId")):
            if element.get(w("val")) == num_id:
                element.set(w("val"), "00")

    return (
        _rewrite(_rewrite(data, renumber, "word/numbering.xml"), refer),
        contract,
        {("structure", "numbering"), ("structure", "attributes")},
    )


def _first_level(data: bytes) -> Callable[[ET.Element], ET.Element]:
    _, abstract, level, _ = _first_list(data)

    def find(root: ET.Element) -> ET.Element:
        definition = next(
            d for d in root.findall(w("abstractNum")) if d.get(w("abstractNumId")) == abstract
        )
        return next(lvl for lvl in definition.findall(w("lvl")) if lvl.get(w("ilvl")) == level)

    return find


def m_label_offset(data, contract, state):
    """The first list's label set four and a half inches left of the text, off the page."""
    find = _first_level(data)

    def edit(root):
        indent = find(root).find(f"{w('pPr')}/{w('ind')}")
        indent.set(w("left"), "0")
        indent.set(w("hanging"), "6480")

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def m_label_right(data, contract, state):
    """The first list's label aligned right, into the margin."""
    find = _first_level(data)

    def edit(root):
        find(root).find(w("lvlJc")).set(w("val"), "right")

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def m_prose_as_code(data, contract, state):
    """A paragraph of prose set in the code style, with a hundred and fifty line breaks."""
    index, _ = _target(state)

    def edit(root):
        paragraph = list(_body(root))[index]
        paragraph.find(f"{w('pPr')}/{w('pStyle')}").set(w("val"), "SourceCode")
        run = list(paragraph.iter(w("r")))[-1]
        for _ in range(150):
            ET.SubElement(run, w("br"))

    return _rewrite(data, edit), contract, {("structure", "line breaks")}


def m_code_lines_moved(data, contract, state):
    """A code block's line breaks turned into spaces and set again at its end: its lines run on."""
    index = _block_of_style(state, "Source Code")

    def edit(root):
        paragraph = list(_body(root))[index]
        moved = 0
        for run in paragraph.iter(w("r")):
            for position, node in enumerate(list(run)):
                if node.tag == w("br"):
                    run.remove(node)
                    space = ET.Element(w("t"))
                    space.set(XML_SPACE, "preserve")
                    space.text = " "
                    run.insert(position, space)
                    moved += 1
        if not moved:
            raise NoTarget("a code block of one line")
        last = list(paragraph.iter(w("r")))[-1]
        for _ in range(moved):
            ET.SubElement(last, w("br"))

    return _rewrite(data, edit), contract, {("structure", "line breaks")}


def m_spaces_run(data, contract, state):
    """The title's first space made twenty thousand."""
    index = _block_of_style(state, "Title")

    def edit(root):
        node = next(t for t in list(_body(root))[index].iter(w("t")) if " " in (t.text or ""))
        node.text = node.text.replace(" ", " " * 20000, 1)

    return _rewrite(data, edit), contract, {("structure", "whitespace")}


def m_em_space(data, contract, state):
    """A space of a body paragraph set as an em space."""
    index, _ = _target(state)

    def edit(root):
        node = next(t for t in list(_body(root))[index].iter(w("t")) if " " in (t.text or ""))
        node.text = node.text.replace(" ", chr(0x2003), 1)

    return _rewrite(data, edit), contract, {("structure", "whitespace")}


def _add_to_style(
    style_id: str, path: tuple[str, ...], tag: str, **attributes: str
) -> Callable[[ET.Element], None]:
    """Add ``tag`` with ``attributes`` to the style, under ``path`` (made where it is missing)."""

    def edit(root: ET.Element) -> None:
        parent = _style(root, style_id)
        for step in path:
            found = parent.find(w(step))
            parent = found if found is not None else ET.SubElement(parent, w(step))
        element = ET.SubElement(parent, w(tag))
        for key, value in attributes.items():
            element.set(w(key), value)

    return edit


STYLES_SEEN = {("package", "word/styles.xml"), ("structure", "styles")}


def m_style_lines_gap(data, contract, state):
    """The Body Text style set a thousand lines below the paragraph before it, by beforeLines."""
    edit = _add_to_style("BodyText", ("pPr",), "spacing", beforeLines="100000")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_style_line_wide(data, contract, state):
    """The Body Text style's lines set four hundred lines apart."""
    edit = _add_to_style("BodyText", ("pPr",), "spacing", line="100000", lineRule="auto")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_style_line_tall(data, contract, state):
    """The Body Text style set in an exact line of a thousand points."""
    edit = _add_to_style("BodyText", ("pPr",), "spacing", line="20000", lineRule="exact")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_figure_exact(data, contract, state):
    """The Figure Image style set in an exact line of twelve points, which clips the picture."""
    edit = _add_to_style("FigureImage", ("pPr",), "spacing", line="240", lineRule="exact")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_style_exact_short(data, contract, state):
    """The Body Text style set at 20 points in an exact line of 15, which clips its text."""

    def edit(root):
        _add_to_style("BodyText", ("pPr",), "spacing", line="300", lineRule="exact")(root)
        _add_to_style("BodyText", ("rPr",), "sz", val="40")(root)

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_style_huge(data, contract, state):
    """The Body Text style set at a thousand points."""
    edit = _add_to_style("BodyText", ("rPr",), "sz", val="2000")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_cell_margin(data, contract, state):
    """The table style's left cell margin set nine thousand twips wide, squeezing out its text."""
    edit = _add_to_style("Table", ("tblPr", "tblCellMar"), "left", w="9000", type="dxa")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_table_indent(data, contract, state):
    """The table style indented nine thousand twips, off the page."""
    edit = _add_to_style("Table", ("tblPr",), "tblInd", w="9000", type="dxa")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


# Found by the eighth review of 2026-10-04, and while closing it.


def m_prose_code_spaces(data, contract, state):
    """A paragraph of prose set in the code style, its first space made twenty thousand."""
    index, _ = _target(state)

    def edit(root):
        paragraph = list(_body(root))[index]
        paragraph.find(f"{w('pPr')}/{w('pStyle')}").set(w("val"), "SourceCode")
        node = next(t for t in paragraph.iter(w("t")) if " " in (t.text or ""))
        node.text = node.text.replace(" ", " " * 20000, 1)
        node.set(XML_SPACE, "preserve")

    return _rewrite(data, edit), contract, {("structure", "whitespace")}


def m_label_em_spaces(data, contract, state):
    """The first list's label set as 200 em spaces before a bullet, in no face of its own."""
    find = _first_level(data)

    def edit(root):
        level = find(root)
        level.find(w("lvlText")).set(w("val"), chr(0x2003) * 200 + BULLET)
        face = level.find(w("rPr"))
        if face is not None:
            level.remove(face)

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def m_level_text_twice(data, contract, state):
    """The first list's level given a second text, which a reader may take for the first."""
    find = _first_level(data)

    def edit(root):
        level = find(root)
        twin = ET.Element(w("lvlText"))
        twin.set(w("val"), "%1 of the effects")
        level.insert(list(level).index(level.find(w("lvlText"))) + 1, twin)

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def m_list_defined_twice(data, contract, state):
    """The first list's definition given again before it, under its identifier, drawing numbers."""
    _, abstract, _, _ = _first_list(data)

    def edit(root):
        definition = next(
            d for d in root.findall(w("abstractNum")) if d.get(w("abstractNumId")) == abstract
        )
        twin = copy.deepcopy(definition)
        for lvl in twin.findall(w("lvl")):
            lvl.find(w("numFmt")).set(w("val"), "decimal")
            lvl.find(w("lvlText")).set(w("val"), "%1.")
        root.insert(list(root).index(definition), twin)

    return _rewrite(data, edit, "word/numbering.xml"), contract, {("structure", "numbering")}


def m_paragraph_style_twice(data, contract, state):
    """A body paragraph given a second style, the Title's, which a reader may take for its own."""
    index, _ = _target(state)

    def edit(root):
        properties = list(_body(root))[index].find(w("pPr"))
        twin = ET.Element(w("pStyle"))
        twin.set(w("val"), "Title")
        properties.insert(1, twin)

    return _rewrite(data, edit), contract, {("structure", "properties")}


def _plain_cell(state: dict[str, Any]) -> tuple[int, int, int]:
    """A body cell of a table, of two words or more in plain runs: (block index, row, column)."""
    for block in state["doc"].blocks:
        if not isinstance(block, DTable):
            continue
        for r, row in enumerate(block.rows[1:], start=1):
            for c, cell in enumerate(row):
                if len(cell.text.split()) >= 2 and all(style == "" for _, style in cell.runs):
                    return block.index, r, c
    raise NoTarget("no table cell of two plain words")


def m_cell_split(data, contract, state):
    """A table cell set as one paragraph a word: a row as many lines high."""
    table, r, c = _plain_cell(state)

    def edit(root):
        cell = list(_body(root))[table].findall(w("tr"))[r].findall(w("tc"))[c]
        paragraph = cell.find(w("p"))
        words = "".join(t.text or "" for t in paragraph.iter(w("t"))).split()
        position = list(cell).index(paragraph)
        cell.remove(paragraph)
        for offset, word in enumerate(words):
            one = ET.Element(w("p"))
            one.append(copy.deepcopy(paragraph.find(w("pPr"))))
            ET.SubElement(ET.SubElement(one, w("r")), w("t")).text = word
            cell.insert(position + offset, one)

    return _rewrite(data, edit), contract, {("structure", "table cells")}


def m_cell_title(data, contract, state):
    """A table cell's paragraph set in the Title style, two inches below the row above."""
    table, r, c = _plain_cell(state)

    def edit(root):
        cell = list(_body(root))[table].findall(w("tr"))[r].findall(w("tc"))[c]
        cell.find(f"{w('p')}/{w('pPr')}/{w('pStyle')}").set(w("val"), "Title")

    return _rewrite(data, edit), contract, {("structure", "table cells")}


def _first_row_format(root: ET.Element) -> ET.Element:
    """The table style's formatting of its heading row (made where it is missing)."""
    style = _style(root, "Table")
    found = next(
        (c for c in style.findall(w("tblStylePr")) if c.get(w("type")) == "firstRow"), None
    )
    if found is None:
        found = ET.SubElement(style, w("tblStylePr"))
        found.set(w("type"), "firstRow")
    return found


def _child(parent: ET.Element, tag: str) -> ET.Element:
    found = parent.find(w(tag))
    return found if found is not None else ET.SubElement(parent, w(tag))


def m_heading_row_tiny(data, contract, state):
    """The table style's heading row set at one point."""

    def edit(root):
        ET.SubElement(_child(_first_row_format(root), "rPr"), w("sz")).set(w("val"), "2")

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_heading_row_exact(data, contract, state):
    """The table style's heading row set in an exact line of a twentieth of a point."""

    def edit(root):
        spacing = ET.SubElement(_child(_first_row_format(root), "pPr"), w("spacing"))
        spacing.set(w("line"), "1")
        spacing.set(w("lineRule"), "exact")

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_banded_rows(data, contract, state):
    """The table style's every other row set in bold, by a formatting of horizontal bands."""

    def edit(root):
        band = ET.SubElement(_style(root, "Table"), w("tblStylePr"))
        band.set(w("type"), "band1Horz")
        ET.SubElement(ET.SubElement(band, w("rPr")), w("b"))

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def _defaults_spacing(root: ET.Element) -> ET.Element:
    """The document defaults' spacing of a paragraph (made where it is missing)."""
    defaults = root.find(w("docDefaults"))
    if defaults is None:
        defaults = ET.Element(w("docDefaults"))
        root.insert(0, defaults)
    return _child(_child(_child(defaults, "pPrDefault"), "pPr"), "spacing")


def m_figure_rule_alone(data, contract, state):
    """The Figure Image style given an exact rule alone, its height from further up."""
    edit = _add_to_style("FigureImage", ("pPr",), "spacing", lineRule="exact")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_rule_from_defaults(data, contract, state):
    """The Figure Image style given a line of 12 points, the exact rule from the defaults."""

    def edit(root):
        _defaults_spacing(root).set(w("lineRule"), "exact")
        _add_to_style("FigureImage", ("pPr",), "spacing", line="240")(root)

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_line_auto_inherited(data, contract, state):
    """Body Text given the rule "auto" alone, under the defaults' least line of 35 points: lines
    nearly three apart."""

    def edit(root):
        spacing = _defaults_spacing(root)
        spacing.set(w("line"), "700")
        spacing.set(w("lineRule"), "atLeast")
        _add_to_style("BodyText", ("pPr",), "spacing", lineRule="auto")(root)

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_line_auto_close(data, contract, state):
    """Body Text given the rule "auto" alone, under the defaults' least line of five points: its
    lines set over one another."""

    def edit(root):
        spacing = _defaults_spacing(root)
        spacing.set(w("line"), "100")
        spacing.set(w("lineRule"), "atLeast")
        _add_to_style("BodyText", ("pPr",), "spacing", lineRule="auto")(root)

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_line_rule_elsewhere(data, contract, state):
    """A table cell's lines a page apart: Compact given a line of 417 (as single spacing would read
    it), the table style an exact rule with no height of its own."""

    def edit(root):
        _add_to_style("Compact", ("pPr",), "spacing", line="100000")(root)
        spacing = _child(_child(_style(root, "Table"), "pPr"), "spacing")
        spacing.attrib.pop(w("line"), None)
        spacing.set(w("lineRule"), "exact")

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_style_line_negative(data, contract, state):
    """The Body Text style set in a least line of minus twelve points."""
    edit = _add_to_style("BodyText", ("pPr",), "spacing", line="-240", lineRule="atLeast")
    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_table_size_reversed(data, contract, state):
    """The table style set at one point, under a Compact style that names 12."""

    def edit(root):
        _add_to_style("Compact", ("rPr",), "sz", val="24")(root)
        table = _child(_style(root, "Table"), "rPr")
        for size in table.findall(w("sz")):
            table.remove(size)
        ET.SubElement(table, w("sz")).set(w("val"), "2")

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_style_size_twice(data, contract, state):
    """The Body Text style given its size twice, 12 points and then one."""

    def edit(root):
        _add_to_style("BodyText", ("rPr",), "sz", val="24")(root)
        _add_to_style("BodyText", ("rPr",), "sz", val="2")(root)

    return _rewrite(data, edit, "word/styles.xml"), contract, set(STYLES_SEEN)


def m_contract(data, contract, state):
    changed = copy.deepcopy(contract)
    narrative = next((c for c in changed.get("citations", []) if c["kind"] == "narrative"), None)
    if narrative is None:
        raise NoTarget("no narrative citation in the record")
    narrative["removed"] = "Somebody Else"
    return data, changed, {("contract", "citations")}


MUTATIONS: tuple[tuple[str, Mutation], ...] = (
    ("a paragraph dropped", m_drop_paragraph),
    ("a paragraph doubled", m_double_paragraph),
    ("a number changed", m_change_number),
    ("a sign turned (>= to <=)", m_flip_sign),
    ("a figure's picture dropped", m_drop_figure),
    ("the pictures of two figures swapped", m_swap_figures),
    ("one figure's picture set under another", m_double_figure),
    ("a reference dropped", m_drop_reference),
    ("a reference's year changed", m_move_year),
    ("a reference's author renamed", m_rename_author),
    ("a citation set as another entry's", m_repoint_citation),
    ("a table cell's boundary moved", m_move_cell_boundary),
    ("a British spelling", m_british),
    ("the AI disclosure changed", m_change_disclosure),
    ("the AI disclosure also left in §K", m_leave_disclosure),
    ("the abstract changed", m_change_abstract),
    ("the note after the references kept", m_keep_note),
    ("a citation left unresolved", m_residue),
    ("the record of the conversion altered", m_contract),
    ("a reference's volume changed (8 to 98)", m_volume),
    ("an invented entry appended to a reference", m_append_reference),
    ("a citation replaced by the placeholder's text", m_placeholder),
    ("the page break before References dropped", m_drop_break),
    ("text set in a page-break paragraph", m_text_in_break),
    ("text set beside a figure's picture", m_text_beside_figure),
    ("a table set on the title pages", m_table_on_title_page),
    ("a reference moved into the text", m_move_reference),
    ("a paragraph set again inside a content control", m_content_control),
    ("a run of a paragraph hidden", m_hidden),
    ("a table row set again inside a content control", m_row_in_content_control),
    ("a page break set inside a paragraph", m_inline_page_break),
    ("another document imported into the body", m_alt_chunk),
    ("a reference volume written with a point before it", m_volume_point),
    ("an apostrophe inside a DOI", m_doi_apostrophe),
    ("a run moved into alternate content", m_alternate_content),
    ("an equation set in a paragraph", m_equation),
    ("a symbol set in a run", m_symbol),
    ("a run wrapped in a field", m_field),
    ("the Body Text style hiding its text", m_style_hidden),
    ("the Page Break style without its break", m_style_without_break),
    ("the page break before References set twice", m_double_break),
    ("a page break after the last of the text", m_trailing_break),
    ("a DOI link leading to another DOI", m_link_target),
    ("a reference carrying another one bookmark", m_extra_bookmark),
    ("an apostrophe inside a container title", m_container_apostrophe),
    ("a link outside the references leading elsewhere", m_link_outside_references),
    ("the Page Break style's break switched off", m_style_break_off),
    ("the Body Text style based on Page Break", m_style_based_on_break),
    ("a page break set on the title page", m_break_after_title),
    ("a page break set in a table cell", m_break_in_cell),
    ("a section break set on a paragraph", m_section_break),
    ("a heading cell spanning two grid columns", m_grid_span),
    ("a table row set one twip high", m_row_height),
    ("a picture cropped", m_crop),
    ("a picture made transparent", m_transparent),
    ("an equation set in the header", m_header_equation),
    ("the header's field quoting a sentence", m_header_field),
    ("a reference link not marked external", m_link_mode),
    ("a link outside the references unwrapped", m_unwrap_link),
    ("a reference identifier repeated in a table cell", m_bookmark_in_cell),
    ("a link added that main.md does not have", m_added_link),
    ("a picture mirrored", m_picture_mirrored),
    ("a picture turned upside down", m_picture_turned),
    ("a picture squeezed into a tenth of its frame", m_picture_squeezed),
    ("a picture drawn a tenth as wide as its frame", m_picture_inner_size),
    ("the Body Text style set in white", m_style_white),
    ("the Body Text style set at two points", m_style_tiny),
    ("the Body Text style set in a face of symbols", m_style_face),
    ("the Body Text style struck through", m_style_struck),
    ("a copy of Page Break under its name, the original's break off", m_style_twin),
    ("a list's label made a sentence", m_list_label),
    ("a list level redefined inside the list", m_list_redefined),
    ("the header renamed, with a sentence in it", m_header_renamed),
    ("a picture's relationship marked external", m_picture_external),
    ("the header's field taken away, its 1 left", m_header_literal),
    ("the Body Text style set in an exact line one point high", m_style_squeezed),
    ("a setting the reference document does not have", m_settings),
    ("a sentence set in the footnote separator", m_separator_text),
    ("a footnote relationship that is not a link", m_footnote_relationship),
    ("a package relationship the reference does not have", m_package_relationship),
    ("a table set wider than the page", m_table_wide),
    ("a table column set one point wide", m_column_narrow),
    ("a table column set wider than the text", m_columns_wide),
    ("a black page colour set beside the body", m_page_colour),
    ("a second document.xml in the archive", m_twin_entry),
    ("a list's label suppressed by w:null", m_label_suppressed),
    ("a list renumbered 0", m_list_unnumbered),
    ("a text node's preserved space taken off", m_space_unpreserved),
    ("a text node's space set to default", m_space_default),
    ("a picture drawn twice its size", m_picture_large),
    ("150 empty paragraphs after the title", m_blank_paragraphs),
    ("20 empty paragraphs in a table cell", m_cell_blank),
    ("the spacer after a table set 150 times", m_after_table_repeated),
    ("150 line breaks in the title", m_line_breaks),
    ("three line breaks added to a code block", m_code_breaks),
    ("the Body Text style's lines set over one another", m_style_compressed),
    ("the Body Text style indented off the page", m_style_indent),
    ("the Body Text style set a page below the paragraph before", m_style_gap),
    ("a list renumbered 00", m_list_zero_padded),
    ("a list's label set off the page", m_label_offset),
    ("a list's label aligned right", m_label_right),
    ("a paragraph of prose set as code with 150 line breaks", m_prose_as_code),
    ("a code block's line breaks moved to its end", m_code_lines_moved),
    ("the title's first space made 20,000", m_spaces_run),
    ("a space set as an em space", m_em_space),
    ("the Body Text style a thousand lines below by beforeLines", m_style_lines_gap),
    ("the Body Text style's lines 400 lines apart", m_style_line_wide),
    ("the Body Text style in an exact line of 1,000 points", m_style_line_tall),
    ("the Figure Image style in an exact line of 12 points", m_figure_exact),
    ("the Body Text style at 20 points in an exact line of 15", m_style_exact_short),
    ("the Body Text style at 1,000 points", m_style_huge),
    ("the table style's cell margin 9,000 twips", m_cell_margin),
    ("the table style indented 9,000 twips", m_table_indent),
    ("a table column set 2_000 wide", m_column_underscore),
    ("a paragraph of prose set as code with 20,000 spaces", m_prose_code_spaces),
    ("a list's label set as 200 em spaces and a bullet", m_label_em_spaces),
    ("a list's level given a second text", m_level_text_twice),
    ("a list's definition given again before it", m_list_defined_twice),
    ("a body paragraph given a second style", m_paragraph_style_twice),
    ("a table cell set as one paragraph a word", m_cell_split),
    ("a table cell set in the Title style", m_cell_title),
    ("the table style's heading row at one point", m_heading_row_tiny),
    ("the table style's heading row in an exact line of 1/20 point", m_heading_row_exact),
    ("the table style's every other row in bold", m_banded_rows),
    ("the Figure Image style given an exact rule alone", m_figure_rule_alone),
    ("the Figure Image style's line exact by the defaults' rule", m_rule_from_defaults),
    ("Body Text's rule auto over a least line of 35 points", m_line_auto_inherited),
    ("Body Text's rule auto over a least line of 5 points", m_line_auto_close),
    ("Compact's line of 417 under the table style's exact rule", m_line_rule_elsewhere),
    ("the Body Text style in a least line of minus 12 points", m_style_line_negative),
    ("the table style at one point under a Compact of 12", m_table_size_reversed),
    ("the Body Text style given its size twice", m_style_size_twice),
)


def mutation_test(inp: Inputs, data: bytes) -> list[str]:
    """Run every mutation on a copy of ``data``; return what went wrong (empty when all is well)."""
    failures: list[str] = []
    control, state = run_checks(inp, data)
    if control:
        return ["control: the unmutated .docx does not pass: " + "; ".join(map(str, control[:5]))]
    state["inputs"] = inp
    for name, mutate in MUTATIONS:
        try:
            mutated, contract, expected = mutate(data, inp.contract, state)
        except NoTarget as reason:
            failures.append(f"{name}: no target ({reason})")
            continue
        found, _ = run_checks(Inputs(**{**inp.__dict__, "contract": contract}), mutated)
        keys = {p.key() for p in found}
        if keys != expected:
            failures.append(
                f"{name}: expected {sorted(expected)}, got {sorted(keys)}"
                + (f" -- e.g. {found[0]}" if found else "")
            )
    return failures


# --------------------------------------------------------------------------------------------------
# The synthetic manuscript and the .docx it should become


SYNTHETIC_REFS: list[dict[str, Any]] = [
    {
        "id": "cds1",
        "type": "article-journal",
        "author": [{"family": "Alpha", "given": "A."}, {"family": "Beta", "given": "B."}],
        "title": "A first title",
        "container-title": "Journal of Tests",
        "volume": "1",
        "issue": "2",
        "page": "3–4",
        "DOI": "10.0000/one",
        "issued": {"date-parts": [[2020]]},
        "x-cds": {"n": 1},
    },
    {
        "id": "cds2",
        "type": "book",
        "author": [{"family": "Zeta", "given": "Z."}],
        "title": "A book of tests",
        "edition": "2",
        "publisher": "Test Press",
        "DOI": "10.0000/two",
        "issued": {"date-parts": [[2019]]},
        "x-cds": {"n": 2},
    },
    {
        "id": "cds3",
        "type": "webpage",
        "author": [{"literal": "Center for Open Science"}],
        "title": "Registered Reports",
        "URL": "https://example.org/rr",
        "accessed": {"date-parts": [[2026, 10, 3]]},
        "x-cds": {"n": 3},
    },
    {
        "id": "cds4",
        "type": "article",
        "author": [
            {"family": "Gamma", "given": "G."},
            {"family": "Delta", "given": "D."},
            {"family": "Epsilon", "given": "E."},
        ],
        "title": "A preprint about tests",
        "publisher": "arXiv",
        "number": "arXiv:2301.00001",
        "URL": "https://arxiv.org/abs/2301.00001",
        "issued": {"date-parts": [[2023]]},
        "x-cds": {"n": 4, "et-al-after": 1},
    },
]

SYNTHETIC_APA = (
    "(Alpha & Beta, 2020; Zeta, 2019)",
    "Alpha and Beta (2020)",
    "Gamma et al. (2023)",
    "(§2.3, and Center for Open Science, n.d. on why a power figure cannot help)",
)

SYNTHETIC_CFF = """cff-version: 1.2.0
title: "A synthetic manuscript for the self-test"
abstract: >-
  We test the check on a synthetic manuscript of three sections and
  one appendix.
authors:
  - family-names: "Example"
    given-names: "Ada"
    orcid: "https://orcid.org/0000-0000-0000-0001"
    affiliation: "Nowhere Institute"
keywords:
  - testing
  - synthetic manuscripts
"""

SYNTHETIC_MAIN = """# A synthetic manuscript for the self-test

<!-- TMLR:DROP -->

**A bold lead that the .docx leaves out.** It is dropped with the table.

| | |
|---|---|
| Author | Ada Example |
| ORCID | [0000-0000-0000-0001](https://orcid.org/0000-0000-0000-0001) |
| Affiliation | Nowhere Institute |
| Correspondence | via the submission system |
| Code and data | <https://example.org/repo> |
| License | Code: MIT. Text: CC BY 4.0 |
| Protocol status | Sealed before the data, with 12 checks |

---
<!-- /TMLR:DROP -->

## Abstract

We test the check on a synthetic manuscript of three sections and
one appendix.

---

## 1. Introduction

A pre-registered evaluation has to settle what a null is worth [1, 2]. Alpha and Beta [1] argue that
a margin of 0.10 is small, and Gamma and colleagues [4] disagree with them on seven of nine counts.

The power gate reads a surrogate whose value of 0.921 exceeds the threshold of 0.8 at the margin, and
the entropy floor of 0.5 bit admits eight of eight contexts in the completed run.

Symbols the page depends on: § → λ α ∧ ∨ ≥ ≤ ≈, and the names Cvetković, Tomašević and Törnberg; a
second sign, ≥, stands here as well so that one of them can be turned.

- the **first** gate reads one quantity;
- the second gate reads another.

<!-- REPORTED-BRANCH: R4 -->

<!-- TMLR:FIGURE first -->
**Figure 1.** The first figure, drawn from the shipped data.
<!-- /TMLR:FIGURE -->

<!-- TMLR:FIGURE second -->
**Figure 2.** The second figure, with `code` in its caption.
<!-- /TMLR:FIGURE -->

| Gate | What it reads | Value |
|---|---|---|
| Power gate | The power of a pooled surrogate | `0.921` |
| Entropy floor | The entropy of each context | 0.5 bit |

Table: The gates and what each reads.

---

## 2. Method

The estimate does not bear on the completed run (§2.3, and [3] on why a power figure cannot help).

```
alpha = 0.05
beta  = 0.20
```

## References

REFERENCES

Reference numbers are permanent identifiers assigned in the author's central bibliography and are
not renumbered between manuscripts.

<!-- TMLR:APPENDIX -->

The appendices hold the record of the sealed protocol.

## A. The rules

The block reproduces the sealed text exactly, spelling included.

<!-- BEGIN GENERATED FROM seal/rules.json -- DO NOT EDIT BY HAND -->

**Estimand.** The mean distance, computed after renormalising over the five zones.

<!-- END GENERATED FROM seal/rules.json -->

The identifier `self_hash_canonicalisation` is code and keeps its spelling.

## K. AI usage disclosure

<!-- TMLR:FOOTNOTE -->
**Use of AI assistance.** This work was developed with substantial AI assistance. No AI system is an
author, and every output was reviewed by the author.
<!-- /TMLR:FOOTNOTE -->

This work was developed with substantial AI assistance, disclosed here in full.
"""


def write_synthetic(root: Path) -> None:
    """Lay out the synthetic inputs under ``root`` as the repository holds the real ones."""
    from render_references import render  # noqa: PLC0415

    (root / "manuscript" / "tmlr").mkdir(parents=True)
    (root / "manuscript" / "docx").mkdir(parents=True)
    (root / REFS).write_text(
        json.dumps(SYNTHETIC_REFS, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = SYNTHETIC_MAIN.replace("REFERENCES", render(SYNTHETIC_REFS))
    (root / MAIN).write_text(text, encoding="utf-8", newline="\n")
    (root / CFF).write_text(SYNTHETIC_CFF, encoding="utf-8", newline="\n")
    m = read_manuscript(text, SYNTHETIC_REFS)
    (root / TMLR_CITATIONS).write_text(
        "# context (last four words before the marker)\tidentifiers\tmode\n"
        + "".join(f"{c.context}\t{', '.join(map(str, c.ids))}\t{c.mode}\n" for c in m.cites),
        encoding="utf-8",
        newline="\n",
    )
    if len(m.cites) != len(SYNTHETIC_APA):
        raise SystemExit(
            f"[docx-check] the synthetic manuscript has {len(m.cites)} citations, not {len(SYNTHETIC_APA)}"
        )
    (root / APA_CITATIONS).write_text(
        APA_HEADER
        + "".join(
            f"{c.context}\t{', '.join(map(str, c.ids))}\t{c.kind}\t{a}\n"
            for c, a in zip(m.cites, SYNTHETIC_APA, strict=True)
        ),
        encoding="utf-8",
        newline="\n",
    )


def _style_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name.title() if name.startswith("heading") else name)


def write_docx(paragraphs: list[tuple[Any, ...]], media: dict[str, bytes]) -> bytes:
    """A minimal WordprocessingML package of the shape pandoc writes, for the self-test.

    ``paragraphs`` holds ``("p", style, [(text, character style)], picture or None, [bookmarks])``,
    with a sixth element, the list's ``numId``, for a list item, and ``("tbl", [[cell text]])``.
    Every style named is declared, by name, in ``styles.xml``. The package has the parts, the
    relationships, the section and the content types pandoc gives it, and a picture is written as
    pandoc writes one.
    """
    from xml.sax.saxutils import escape  # noqa: PLC0415

    styles: dict[str, str] = {}
    body: list[str] = []
    rels: list[str] = []
    for entry in paragraphs:
        if entry[0] == "tbl":
            rows = []
            for row in entry[1]:
                cells = "".join(
                    f'<w:tc><w:p><w:pPr><w:pStyle w:val="Compact"/></w:pPr>{_xml_runs(cell, styles, escape, rels)}</w:p></w:tc>'
                    for cell in row
                )
                rows.append(f"<w:tr>{cells}</w:tr>")
            styles["Compact"] = "paragraph"
            # As pandoc lays a table out: the text's full width, by its grid, the first row the
            # heading.
            width = 7920 // len(entry[1][0])
            grid = "".join(f'<w:gridCol w:w="{width}"/>' for _ in entry[1][0])
            body.append(
                '<w:tbl><w:tblPr><w:tblStyle w:val="Table"/><w:tblW w:type="pct" w:w="5000"/>'
                '<w:tblLayout w:type="fixed"/><w:tblLook w:firstRow="1" w:lastRow="0" '
                'w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="0" w:val="0020"/>'
                f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>" + "".join(rows) + "</w:tbl>"
            )
            styles["Table"] = "table"
            continue
        _, style, runs, picture, bookmarks = entry[:5]
        numbered = (
            f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{entry[5]}"/></w:numPr>'
            if len(entry) > 5
            else ""
        )
        # As pandoc writes them: each bookmark opens before its paragraph and closes after it.
        marks = [(f"{len(body)}{number}", name) for number, name in enumerate(bookmarks)]
        for mark, name in marks:
            body.append(f'<w:bookmarkStart w:id="{mark}" w:name="{name}"/>')
        styles[style] = "paragraph"
        drawing = ""
        if picture is not None:
            rid = f"rIdImage{len(rels)}"
            rels.append(f'<Relationship Id="{rid}" Type="{R}/image" Target="media/{picture}"/>')
            width, height = _png_size(media[picture]) or (1, 1)
            cx = 5486400  # six inches, at the picture's own proportions
            cy = cx * height // width
            n = 2 * len(body) + 10
            drawing = (
                f'<w:r><w:drawing><wp:inline><wp:extent cx="{cx}" cy="{cy}"/>'
                '<wp:effectExtent b="0" l="0" r="0" t="0"/>'
                f'<wp:docPr descr="" title="" id="{n}" name="Picture"/>'
                '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                f'<pic:pic><pic:nvPicPr><pic:cNvPr descr="figs/{picture}" id="{n + 1}" name="Picture"/>'
                '<pic:cNvPicPr><a:picLocks noChangeArrowheads="1" noChangeAspect="1"/></pic:cNvPicPr>'
                f'</pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/>'
                '</a:stretch></pic:blipFill><pic:spPr bwMode="auto"><a:xfrm><a:off x="0" y="0"/>'
                f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                '<a:noFill/><a:ln w="9525"><a:noFill/><a:headEnd/><a:tailEnd/></a:ln></pic:spPr>'
                "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
            )
        body.append(
            f'<w:p><w:pPr><w:pStyle w:val="{_style_id(style)}"/>{numbered}</w:pPr>'
            f"{_xml_runs(runs, styles, escape, rels)}{drawing}</w:p>"
        )
        body.extend(f'<w:bookmarkEnd w:id="{mark}"/>' for mark, _ in marks)
    rels += [
        f'<Relationship Id="rIdStyles" Type="{R}/styles" Target="styles.xml"/>',
        f'<Relationship Id="rIdNumbering" Type="{R}/numbering" Target="numbering.xml"/>',
        f'<Relationship Id="rIdFootnotes" Type="{R}/footnotes" Target="footnotes.xml"/>',
        f'<Relationship Id="rIdHeader" Type="{R}/header" Target="header1.xml"/>',
        f'<Relationship Id="rIdSettings" Type="{R}/settings" Target="settings.xml"/>',
    ]
    # pandoc gives the footnotes the document's links as well.
    notes = [rel for rel in rels if "/hyperlink" in rel]
    body.append(
        '<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader"/>'
        '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
        'w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        "<w:body>" + "".join(body) + "</w:body></w:document>"
    )
    style_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{W}">'
        + "".join(
            f'<w:style w:type="{kind}" w:styleId="{_style_id(name)}"><w:name w:val="{name}"/>'
            + (
                # As reference.docx sets it: a spacer, one point high, that breaks the page.
                '<w:pPr><w:pageBreakBefore/><w:spacing w:line="20" w:lineRule="exact"/></w:pPr>'
                '<w:rPr><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr>'
                if name == "Page Break"
                else "<w:pPr><w:pageBreakBefore/></w:pPr>"
                if name in BREAKING_STYLES
                else ""
            )
            + "</w:style>"
            for name, kind in styles.items()
        )
        + "</w:styles>"
    )
    footnotes = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:footnotes xmlns:w="{W}">'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote></w:footnotes>'
    )
    # pandoc's bullet list: the Symbol face's bullet at the first level.
    numbering = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:numbering xmlns:w="{W}">'
        '<w:abstractNum w:abstractNumId="991"><w:multiLevelType w:val="multilevel"/>'
        f'<w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/><w:lvlText w:val="{chr(0xF0B7)}"/>'
        '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>'
        '<w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:cs="Symbol" w:hint="default"/></w:rPr>'
        '</w:lvl></w:abstractNum><w:num w:numId="1001"><w:abstractNumId w:val="991"/></w:num>'
        "</w:numbering>"
    )
    package = "http://schemas.openxmlformats.org/package/2006/content-types"
    word = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    overrides = [
        ("/word/document.xml", f"{word}.document.main+xml"),
        ("/word/styles.xml", f"{word}.styles+xml"),
        ("/word/numbering.xml", f"{word}.numbering+xml"),
        ("/word/footnotes.xml", f"{word}.footnotes+xml"),
        ("/word/header1.xml", f"{word}.header+xml"),
        ("/word/settings.xml", f"{word}.settings+xml"),
    ] + [(f"/word/media/{name}", "image/png") for name in media]
    types = (
        f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="{package}">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + "".join(f'<Override PartName="{n}" ContentType="{t}"/>' for n, t in overrides)
        + "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("[Content_Types].xml", types)
        out.writestr(
            "_rels/.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
            f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        out.writestr(
            "word/settings.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><w:settings xmlns:w="{W}">'
            '<w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/></w:settings>',
        )
        out.writestr(
            "word/_rels/footnotes.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
            + "".join(notes)
            + "</Relationships>",
        )
        out.writestr("word/document.xml", document)
        out.writestr("word/styles.xml", style_xml)
        out.writestr("word/numbering.xml", numbering)
        out.writestr("word/footnotes.xml", footnotes)
        out.writestr(
            "word/header1.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><w:hdr xmlns:w="{W}"><w:p><w:pPr>'
            '<w:jc w:val="right"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:hdr>',
        )
        out.writestr(
            "word/_rels/document.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
            + "".join(rels)
            + "</Relationships>",
        )
        for name, data in media.items():
            out.writestr(f"word/media/{name}", data)
    return buffer.getvalue()


def synthetic_reference(data: bytes) -> bytes:
    """The reference document the synthetic .docx stands for: its parts without the pictures, the
    pictures' content types and relationships, and the links' relationships -- what pandoc adds to a
    reference document, taken off the unbroken synthetic .docx before any mutation."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {n: archive.read(n) for n in archive.namelist() if not MEDIA.fullmatch(n)}

    def drop(part: str, keep: Callable[[ET.Element], bool]) -> None:
        root = ET.fromstring(parts[part])
        for child in [c for c in root if not keep(c)]:
            root.remove(child)
        parts[part] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    drop(RELS, lambda r: r.get("Type") not in (f"{R}/image", f"{R}/hyperlink"))
    drop("[Content_Types].xml", lambda o: not o.get("PartName", "").startswith("/word/media/"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, part in parts.items():
            out.writestr(name, part)
    return buffer.getvalue()


def _xml_runs(
    runs: Any, styles: dict[str, str], escape: Callable[[str], str], rels: list[str]
) -> str:
    """Runs of ``(text, character style)``; a run in the style Hyperlink is a link to its third
    element, or to its own text."""
    if isinstance(runs, str):
        runs = [(runs, "")]
    out = []
    for run in runs:
        text, style = run[0], run[1]
        if style:
            styles[style] = "character"
        props = f'<w:rPr><w:rStyle w:val="{_style_id(style)}"/></w:rPr>' if style else ""
        # A line of a code block ends in a line break, as pandoc sets one.
        lines = "<w:br/>".join(
            f'<w:t xml:space="preserve">{escape(line)}</w:t>' for line in text.split("\n")
        )
        xml = f"<w:r>{props}{lines}</w:r>"
        if style == "Hyperlink":
            rid = f"rIdLink{len(rels)}"
            target = run[2] if len(run) > 2 else text
            rels.append(
                f'<Relationship Id="{rid}" Type="{R}/hyperlink" Target="{escape(target)}" '
                'TargetMode="External"/>'
            )
            xml = f'<w:hyperlink r:id="{rid}">{xml}</w:hyperlink>'
        out.append(xml)
    return "".join(out)


#: The .docx the synthetic manuscript should become, written out by hand as pandoc and citeproc set
#: such a manuscript -- not derived from what this check expects, so that a check that expects the
#: wrong thing is not handed a document made to its own expectation. ``("p", style, runs, picture,
#: bookmarks)`` with runs of ``(text, character style)``, and ``("tbl", rows of cells of runs)``.
_C, _V = CITATION_STYLE, CODE_STYLE
SYNTHETIC_DOCX: list[tuple[Any, ...]] = [
    ("p", "Title", [("A synthetic manuscript for the self-test", "")], None, []),
    ("p", "Author", [("Ada Example", "")], None, []),
    ("p", "Affiliation", [("Nowhere Institute", "")], None, []),
    ("p", "Author Note Heading", [("Author Note", "")], None, []),
    (
        "p",
        "Author Note",
        [
            ("ORCID: ", ""),
            ("0000-0000-0000-0001", "Hyperlink", "https://orcid.org/0000-0000-0000-0001"),
        ],
        None,
        [],
    ),
    (
        "p",
        "Author Note",
        [("Protocol status: Sealed before the data, with 12 checks", "")],
        None,
        [],
    ),
    (
        "p",
        "Author Note",
        [("Code and data: ", ""), ("https://example.org/repo", "Hyperlink")],
        None,
        [],
    ),
    ("p", "Author Note", [("License: Code: MIT. Text: CC BY 4.0", "")], None, []),
    (
        "p",
        "Author Note",
        [
            ("Use of AI assistance.", ""),
            (
                " This work was developed with substantial AI assistance. No AI system is an author, and every",
                "",
            ),
            (" output was reviewed by the author.", ""),
        ],
        None,
        [],
    ),
    ("p", "Author Note", [("Correspondence: via the submission system", "")], None, []),
    ("p", "Abstract Title", [("Abstract", "")], None, []),
    (
        "p",
        "Abstract",
        [("We test the check on a synthetic manuscript of three sections and one appendix.", "")],
        None,
        [],
    ),
    ("p", "Keywords", [("Keywords:", ""), (" testing, synthetic manuscripts", "")], None, []),
    ("p", "Title Repeat", [("A synthetic manuscript for the self-test", "")], None, []),
    ("p", "heading 1", [("1. Introduction", "")], None, ["introduction"]),
    (
        "p",
        "First Paragraph",
        [
            ("A pre-registered evaluation has to settle what a null is worth ", ""),
            ("(Alpha & Beta, 2020; Zeta, 2019)", _C),
            (". ", ""),
            ("Alpha and Beta (2020)", _C),
            (" argue that a margin of 0.10 is small, and ", ""),
            ("Gamma et al. (2023)", _C),
            (" disagree with them on seven of nine counts.", ""),
        ],
        None,
        [],
    ),
    (
        "p",
        "Body Text",
        [
            (
                "The power gate reads a surrogate whose value of 0.921 exceeds the threshold of 0.8 at the margin,",
                "",
            ),
            (
                " and the entropy floor of 0.5 bit admits eight of eight contexts in the completed run.",
                "",
            ),
        ],
        None,
        [],
    ),
    (
        "p",
        "Body Text",
        [
            (
                "Symbols the page depends on: § → λ α ∧ ∨ ≥ ≤ ≈, and the names Cvetković, Tomašević and Törnberg;",
                "",
            ),
            (" a second sign, ≥, stands here as well so that one of them can be turned.", ""),
        ],
        None,
        [],
    ),
    (
        "p",
        "Compact",
        [("the ", ""), ("first", ""), (" gate reads one quantity;", "")],
        None,
        [],
        "1001",
    ),
    ("p", "Compact", [("the second gate reads another.", "")], None, [], "1001"),
    ("p", "Figure Number", [("Figure 1", "")], None, []),
    ("p", "Figure Title", [("The first figure, drawn from the shipped data.", "")], None, []),
    ("p", "Figure Image", [], "fig-first.png", []),
    ("p", "Figure Number", [("Figure 2", "")], None, []),
    (
        "p",
        "Figure Title",
        [("The second figure, with ", ""), ("code", _V), (" in its caption.", "")],
        None,
        [],
    ),
    ("p", "Figure Image", [], "fig-second.png", []),
    ("p", "Table Number", [("Table 1", "")], None, []),
    ("p", "Table Title", [("The gates and what each reads.", "")], None, []),
    (
        "tbl",
        [
            [[("Gate", "")], [("What it reads", "")], [("Value", "")]],
            [[("Power gate", "")], [("The power of a pooled surrogate", "")], [("0.921", _V)]],
            [[("Entropy floor", "")], [("The entropy of each context", "")], [("0.5 bit", "")]],
        ],
    ),
    ("p", "After Table", [], None, []),
    ("p", "heading 1", [("2. Method", "")], None, ["method"]),
    (
        "p",
        "First Paragraph",
        [
            ("The estimate does not bear on the completed run ", ""),
            ("(§2.3, and Center for Open Science, n.d. on why a power figure cannot help)", _C),
            (".", ""),
        ],
        None,
        [],
    ),
    ("p", "Source Code", [("alpha = 0.05\nbeta  = 0.20", _V)], None, []),
    ("p", "Page Break", [], None, []),
    ("p", "heading 1", [("References", "")], None, ["references"]),
    (
        "p",
        "Bibliography",
        [
            ("Alpha, A., & Beta, B. (2020). A first title. ", ""),
            ("Journal of Tests", ""),
            (", ", ""),
            ("1", ""),
            ("(2), 3–4. ", ""),
            ("https://doi.org/10.0000/one", "Hyperlink"),
        ],
        None,
        ["refs", "ref-cds1"],
    ),
    (
        "p",
        "Bibliography",
        [
            ("Center for Open Science. (n.d.). ", ""),
            ("Registered Reports", ""),
            (". Retrieved October 3, 2026, from ", ""),
            ("https://example.org/rr", "Hyperlink"),
        ],
        None,
        ["ref-cds3"],
    ),
    (
        "p",
        "Bibliography",
        [
            ("Gamma, G., Delta, D., & Epsilon, E. (2023). ", ""),
            ("A preprint about tests", ""),
            (" (arXiv:2301.00001). arXiv. ", ""),
            ("https://arxiv.org/abs/2301.00001", "Hyperlink"),
        ],
        None,
        ["ref-cds4"],
    ),
    (
        "p",
        "Bibliography",
        [
            ("Zeta, Z. (2019). ", ""),
            ("A book of tests", ""),
            (" (2nd ed.). Test Press. ", ""),
            ("https://doi.org/10.0000/two", "Hyperlink"),
        ],
        None,
        ["ref-cds2"],
    ),
    (
        "p",
        "First Paragraph",
        [("The appendices hold the record of the sealed protocol.", "")],
        None,
        [],
    ),
    ("p", "Page Break", [], None, []),
    ("p", "heading 1", [("A. The rules", "")], None, ["a.-the-rules"]),
    (
        "p",
        "First Paragraph",
        [("The block reproduces the sealed text exactly, spelling included.", "")],
        None,
        [],
    ),
    (
        "p",
        "Body Text",
        [
            ("Estimand.", ""),
            (" The mean distance, computed after renormalising over the five zones.", ""),
        ],
        None,
        [],
    ),
    (
        "p",
        "Body Text",
        [
            ("The identifier ", ""),
            ("self_hash_canonicalisation", _V),
            (" is code and keeps its spelling.", ""),
        ],
        None,
        [],
    ),
    ("p", "Page Break", [], None, []),
    ("p", "heading 1", [("K. AI usage disclosure", "")], None, ["k.-ai-usage-disclosure"]),
    (
        "p",
        "First Paragraph",
        [("This work was developed with substantial AI assistance, disclosed here in full.", "")],
        None,
        [],
    ),
]


def _png(width: int, height: int, shade: int) -> bytes:
    """A small grey PNG of the given size, for the synthetic figures."""
    import struct  # noqa: PLC0415
    import zlib  # noqa: PLC0415

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + bytes([shade]) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def self_test() -> list[str]:
    """Build the synthetic .docx, require it to pass, and require every mutation to be named."""
    import make_docx_source  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_synthetic(root)
        pictures = {"first": _png(30, 10, 60), "second": _png(20, 15, 160)}
        figures = {
            "figures": [
                {
                    "number": n,
                    "name": name,
                    "png": f"fig-{name}.png",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for n, (name, data) in enumerate(pictures.items(), start=1)
            ]
        }
        (root / "figures.json").write_text(json.dumps(figures), encoding="utf-8")
        _, record = make_docx_source.build(root, no_preprint=True)
        (root / "contract.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        data = write_docx(
            SYNTHETIC_DOCX, {f"fig-{name}.png": png for name, png in pictures.items()}
        )
        inp = load_inputs(
            root, root / "figures.json", root / "contract.json", synthetic_reference(data)
        )
        return mutation_test(inp, data)


# --------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("docx", type=Path, nargs="?", help="the .docx to check")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--contract", type=Path, help="make_docx_source.py's record of the conversion"
    )
    parser.add_argument(
        "--figures", type=Path, help="the manifest of the figures' PNGs (figures.json)"
    )
    parser.add_argument(
        "--reference", type=Path, help="the reference document pandoc built the .docx from"
    )
    parser.add_argument("--write-text", type=Path, help="also write the text of the .docx here")
    parser.add_argument(
        "--mutation-test",
        action="store_true",
        help="also break copies of the .docx and require each break to be named",
    )
    parser.add_argument(
        "--write-citations-apa",
        action="store_true",
        help=f"rewrite {APA_CITATIONS} from the .docx instead of comparing",
    )
    parser.add_argument(
        "--figure-text",
        type=Path,
        help="check the figures' numbers in the text of their standalone PDFs",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the checks on a synthetic .docx and its mutations",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        failures = self_test()
        if failures:
            print("[docx-check] SELF-TEST FAIL", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(
            f"[docx-check] self-test OK: the synthetic .docx passes, and each of {len(MUTATIONS)} mutations is reported with exactly its diagnostics"
        )
        return 0
    if args.figure_text:
        problems = figure_text_problems(args.repo_root, args.figure_text)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        if problems:
            print("[docx-check] FAIL: the figures' numbers", file=sys.stderr)
            return 1
        print("[docx-check] OK: every figure's numbers stand, row by row, in its standalone PDF")
        return 0
    if args.docx is None or args.contract is None or args.figures is None or args.reference is None:
        parser.error("checking a .docx needs the .docx, --contract, --figures and --reference")

    inp = load_inputs(args.repo_root, args.figures, args.contract, args.reference.read_bytes())
    data = args.docx.read_bytes()
    problems, state = run_checks(inp, data)
    if args.write_citations_apa:
        count = write_apa_fixture(inp, state)
        print(
            f"[docx-check] wrote {APA_CITATIONS} ({count} citations); read the diff before committing it"
        )
        return 0
    if args.write_text:
        args.write_text.write_text(docx_text(state["doc"]), encoding="utf-8", newline="\n")
    if problems:
        print(f"[docx-check] FAIL: {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    m = inp.manuscript
    print(
        f"[docx-check] OK: {len(state['main_items'])} blocks of text match main.md word for word; "
        f"{len(m.cites)} citations, {len(inp.refs)} references, "
        f"{sum(1 for b in m.blocks if b.kind == 'figure')} figures and {sum(1 for b in m.blocks if b.kind == 'table')} tables "
        "are each as the contract says; the title pages, the Author Note and what was left out are as recorded"
    )
    if args.mutation_test:
        failures = mutation_test(inp, data)
        if failures:
            print("[docx-check] MUTATION TEST FAIL", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(
            f"[docx-check] mutation test OK: each of {len(MUTATIONS)} breaks of this .docx is reported with exactly its diagnostics"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
