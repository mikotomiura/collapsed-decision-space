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
in a comment, hidden, or in an element it does not read -- is reported rather than skipped; content
controls are read through.

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
        [--write-text build/docx/paper-docx.txt] [--mutation-test] [--write-citations-apa]
    python analysis/scripts/check_docx_text.py --figure-text build/docx/figs
    python analysis/scripts/check_docx_text.py --self-test
"""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import io
import json
import re
import sys
import tempfile
import unicodedata
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


def _unquoted(text: str) -> str:
    """For a title that citeproc may requote: compare it with its quotation marks taken out."""
    return re.sub(r"[\"']", "", norm(text))


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
    hidden: bool = False  # a run with text is hidden (w:vanish)

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
    footnotes: list[str]
    parts: dict[str, bytes]
    problems: list[Problem] = field(default_factory=list)  # what the reader could not account for


def _style_names(parts: dict[str, bytes]) -> dict[str, str]:
    names: dict[str, str] = {}
    if "word/styles.xml" in parts:
        for style in ET.fromstring(parts["word/styles.xml"]).iter(w("style")):
            name = style.find(w("name"))
            names[style.get(w("styleId"), "")] = name.get(w("val"), "") if name is not None else ""
    return names


def _is_hidden(run: ET.Element) -> bool:
    vanish = run.find(f"{w('rPr')}/{w('vanish')}")
    return vanish is not None and vanish.get(w("val"), "true") not in ("0", "false", "off")


def _runs(
    element: ET.Element,
    names: dict[str, str],
    runs: list[tuple[str, str]],
    images: list[str],
    hidden: list[bool] | None = None,
) -> None:
    for child in element:
        tag = child.tag
        if tag in (w("pPr"), w("del"), w("rPr")):
            continue
        if tag == w("r"):
            style_el = child.find(f"{w('rPr')}/{w('rStyle')}")
            style = (
                names.get(style_el.get(w("val"), ""), style_el.get(w("val"), ""))
                if style_el is not None
                else ""
            )
            parts: list[str] = []
            for node in child:
                if node.tag == w("t"):
                    parts.append(node.text or "")
                elif node.tag == w("tab"):
                    parts.append("\t")
                elif (
                    node.tag in (w("br"), w("cr"))
                    and node.get(w("type"), "textWrapping") == "textWrapping"
                ):
                    parts.append("\n")
                elif node.tag == w("noBreakHyphen"):
                    parts.append("-")
                elif node.tag == w("drawing"):
                    for blip in node.iter(f"{{{A}}}blip"):
                        images.append(blip.get(f"{{{R}}}embed", ""))
            if parts:
                runs.append(("".join(parts), style))
                if hidden is not None and _is_hidden(child) and "".join(parts).strip():
                    hidden.append(True)
        else:
            _runs(child, names, runs, images, hidden)


def _para(element: ET.Element, index: int, names: dict[str, str], bookmarks: list[str]) -> DPara:
    style_el = element.find(f"{w('pPr')}/{w('pStyle')}")
    style_id = style_el.get(w("val"), "") if style_el is not None else ""
    style = names.get(style_id, style_id) if style_id else "Normal"
    runs: list[tuple[str, str]] = []
    images: list[str] = []
    hidden: list[bool] = []
    _runs(element, names, runs, images, hidden)
    return DPara(index, style, runs, images, bookmarks, bool(hidden))


#: Elements of the body (and of a table cell) that hold no text of their own, or none that shows.
_INERT = frozenset(
    w(tag) for tag in ("bookmarkStart", "bookmarkEnd", "sectPr", "proofErr", "permStart", "permEnd")
)


def _blocks(
    container: ET.Element,
    index: int | None,
    names: dict[str, str],
    out: list[DPara | DTable],
    problems: list[Problem],
    pending: list[str],
) -> list[str]:
    """Read the paragraphs and tables of a body or a content control, in order, into ``out``.

    A content control (``w:sdt``) and custom XML are read through, so that what they hold is checked
    like everything else; an element that carries text and is none of these is reported rather than
    skipped (Codex review of 2026-10-04: a paragraph inside a content control passed unread).
    """
    for position, child in enumerate(container):
        at = position if index is None else index
        if child.tag == w("bookmarkStart"):
            pending.append(child.get(w("name"), ""))
        elif child.tag == w("p"):
            out.append(_para(child, at, names, pending))
            pending = []
        elif child.tag == w("tbl"):
            out.append(DTable(at, _table_rows(child, at, names, problems), pending))
            pending = []
        elif child.tag in (w("sdt"), w("customXml")):
            content = child.find(w("sdtContent")) if child.tag == w("sdt") else child
            if content is not None:
                pending = _blocks(content, at, names, out, problems, pending)
        elif child.tag not in _INERT and any((t.text or "").strip() for t in child.iter(w("t"))):
            problems.append(
                Problem(
                    "structure",
                    "unread content",
                    f"an element the check does not read holds text: {child.tag}",
                )
            )
    return pending


def _table_rows(
    table: ET.Element, index: int, names: dict[str, str], problems: list[Problem]
) -> list[list[DPara]]:
    rows = []
    for row in table.findall(w("tr")):
        cells = []
        for cell in row.findall(w("tc")):
            inner: list[DPara | DTable] = []
            _blocks(cell, index, names, inner, problems, [])
            if any(isinstance(b, DTable) for b in inner):
                problems.append(
                    Problem("structure", "unread content", "a table nested in a table cell")
                )
            paragraphs = [b for b in inner if isinstance(b, DPara)]
            runs = [r for p in paragraphs for r in [*p.runs, (" ", "")]]
            cells.append(
                DPara(
                    index,
                    "cell",
                    runs[:-1] if runs else [],
                    [i for p in paragraphs for i in p.images],
                    [],
                    any(p.hidden for p in paragraphs),
                )
            )
        rows.append(cells)
    return rows


def _part_text(data: bytes) -> str:
    return "".join(t.text or "" for t in ET.fromstring(data).iter(w("t")))


def read_docx(data: bytes) -> Docx:
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {name: archive.read(name) for name in archive.namelist()}
    names = _style_names(parts)
    document = ET.fromstring(parts["word/document.xml"])
    body = document.find(w("body"))
    if body is None:
        raise ValueError("word/document.xml has no body")
    rels: dict[str, str] = {}
    if "word/_rels/document.xml.rels" in parts:
        for rel in ET.fromstring(parts["word/_rels/document.xml.rels"]):
            rels[rel.get("Id", "")] = rel.get("Target", "")
    media = {
        rid: hashlib.sha256(parts["word/" + target]).hexdigest()
        for rid, target in rels.items()
        if "word/" + target in parts and target.startswith("media/")
    }
    problems: list[Problem] = []
    blocks: list[DPara | DTable] = []
    _blocks(body, None, names, blocks, problems, [])
    # Text that shows on the page but is in no paragraph or table read above.
    if any(True for _ in document.iter(w("txbxContent"))):
        problems.append(Problem("structure", "unread content", "a text box"))
    for name, part in parts.items():
        if re.fullmatch(r"word/(header|footer)\d*\.xml", name) and _part_text(part).strip() not in (
            "",
            "1",
        ):
            problems.append(Problem("structure", "unread content", f"{name} carries text"))
        if name == "word/comments.xml" and any(
            True for _ in ET.fromstring(part).iter(w("comment"))
        ):
            problems.append(Problem("structure", "unread content", "comments"))
    for block in blocks:
        cells = [block] if isinstance(block, DPara) else [c for row in block.rows for c in row]
        if any(c.hidden for c in cells):
            problems.append(
                Problem("structure", "hidden text", f"docx block {block.index} holds hidden text")
            )
    footnotes: list[str] = []
    if "word/footnotes.xml" in parts:
        for note in ET.fromstring(parts["word/footnotes.xml"]).iter(w("footnote")):
            if note.get(w("type")) in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            runs: list[tuple[str, str]] = []
            _runs(note, names, runs, [])
            footnotes.append("".join(t for t, _ in runs))
    return Docx(blocks, media, footnotes, parts, problems)


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


def load_cff(path: Path) -> dict[str, Any]:
    import yaml  # noqa: PLC0415  (in the locked environment; the workflow supplies the pinned version)

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_inputs(root: Path, figures: Path | None, contract: Path | None) -> Inputs:
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
    )


# --------------------------------------------------------------------------------------------------
# The two streams of text compared word for word


@dataclass
class Item:
    key: str  # "H<level>|text" for a heading, "P|text" for anything else; normalised
    where: int  # main.md line, or the index of the .docx block
    cites: list[int] = field(default_factory=list)  # main: citation numbers; .docx: group indices
    block: Any = None
    generated: bool = False
    page_break: bool = False  # .docx: a page-break paragraph stands right before it


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
                raw = re.sub(r"^(?:[-+*]|\d+\.) ", "", raw)
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
    pending_break = False
    in_bibliography = False

    def add(item: Item) -> None:
        nonlocal pending_break, in_bibliography
        item.page_break = pending_break
        pending_break = False
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
            pending_break = True
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


#: What may stand between two fields of an entry, and after the last: punctuation, and the "from"
#: of "Retrieved …, from". Anything else -- a digit, a word -- is text the data does not explain
#: (Codex review of 2026-10-04: a volume "98" for 8 and an invented entry appended to a paragraph
#: both passed a check that looked for each field anywhere in the paragraph).
_GAP = re.compile(r"[\s.,;:&()]*(?:from[\s.,;:&()]*)?")


def entry_problems(item: dict[str, Any], text: str) -> list[str]:
    """Read an entry as its fields in order, with nothing but punctuation between them."""
    entry = _unquoted(text)
    cursor = 0
    problems: list[str] = []
    for name, value in reference_fields(item):
        want = _unquoted(value)
        at = entry.find(want, cursor)
        if at < 0:
            problems.append(f"no {name} {value!r} after {entry[max(0, cursor - 20) : cursor]!r}")
            continue
        if not _GAP.fullmatch(entry[cursor:at]):
            problems.append(f"{entry[cursor:at]!r} stands before the {name} {value!r}")
        cursor = at + len(want)
    if not _GAP.fullmatch(entry[cursor:]):
        problems.append(f"{entry[cursor:]!r} follows the last field")
    return problems


def _sort_key(item: dict[str, Any]) -> tuple[tuple[str, ...], int]:
    """APA 7's order of the reference list: by the authors' names in turn, then by year."""

    def plain(name: str) -> str:
        decomposed = unicodedata.normalize("NFKD", name)
        return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()

    names = tuple(plain(a.get("family") or a.get("literal")) for a in item["author"])
    return names, item["issued"]["date-parts"][0][0] if "issued" in item else 0


def check_bibliography(inp: Inputs, view: DocView) -> list[Problem]:
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
        if ids[-1] in entries:
            problems.append(Problem("bibliography", f"[{ids[-1]}]", "the entry occurs twice"))
        entries[ids[-1]] = para
        order.append(ids[-1])
    known = {item["x-cds"]["n"]: item for item in inp.refs}
    for n, item in known.items():
        if n not in entries:
            problems.append(
                Problem("bibliography", f"[{n}]", "not in the reference list of the .docx")
            )
            continue
        found = entry_problems(item, entries[n].text)
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
    found = set()
    for di, item in enumerate(view.items):
        if item.page_break:
            mine = to_main.get(di)
            found.add(str(mine.where) if mine is not None else f"docx block {item.where}")
    if found != wanted:
        problems.append(
            Problem(
                "structure",
                "page breaks",
                f"missing before main.md lines {sorted(wanted - found)}, extra before {sorted(found - wanted)}",
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
    doc = read_docx(data)
    view = docx_view(doc)
    main_items = main_stream(inp.manuscript)
    problems = doc.problems + view.problems
    fulltext, pairs = align(main_items, view.items)
    problems += fulltext
    problems += check_contract(inp)
    problems += check_citations(inp, view, main_items, pairs)
    problems += check_bibliography(inp, view)
    problems += check_head(inp, view, doc)
    problems += check_figures(inp, view, doc)
    problems += check_tables(inp, view)
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

    return _rewrite(data, edit), contract, {("figure", "Figure 1"), ("figure", "Figure 2")}


def m_double_figure(data, contract, state):
    first, second = _figure_image(state, 1), _figure_image(state, 2)

    def edit(root):
        body = list(_body(root))
        key = f"{{{R}}}embed"
        _blips(body[second])[0].set(key, _blips(body[first])[0].get(key))

    return _rewrite(data, edit), contract, {("figure", "Figure 2")}


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
    """An invented entry appended to an existing reference's paragraph."""
    index, n = _entry(state, 0)
    return (
        _append(data, index, " Invented, A. (2020). An invented title. Nowhere, 1, 1–2."),
        contract,
        {("bibliography", f"[{n}]")},
    )


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
        {("structure", "page breaks"), ("fulltext", f"main.md:{before}")},
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

    return _rewrite(data, edit), contract, {("fulltext", f"main.md:{line}")}


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

    ``paragraphs`` holds ``("p", style, [(text, character style)], picture or None, [bookmarks])``
    and ``("tbl", [[cell text]])``. Every style named is declared, by name, in ``styles.xml``.
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
                    f'<w:tc><w:p><w:pPr><w:pStyle w:val="Compact"/></w:pPr>{_xml_runs(cell, styles, escape)}</w:p></w:tc>'
                    for cell in row
                )
                rows.append(f"<w:tr>{cells}</w:tr>")
            styles["Compact"] = "paragraph"
            body.append(
                '<w:tbl><w:tblPr><w:tblStyle w:val="Table"/></w:tblPr>' + "".join(rows) + "</w:tbl>"
            )
            continue
        _, style, runs, picture, bookmarks = entry
        for number, name in enumerate(bookmarks):
            body.append(f'<w:bookmarkStart w:id="{len(body)}{number}" w:name="{name}"/>')
        styles[style] = "paragraph"
        drawing = ""
        if picture is not None:
            rid = f"rIdImage{len(rels)}"
            rels.append(f'<Relationship Id="{rid}" Type="{R}/image" Target="media/{picture}"/>')
            drawing = (
                f"<w:r><w:drawing><wp:inline><a:graphic><a:graphicData><pic:pic><pic:blipFill>"
                f'<a:blip r:embed="{rid}"/></pic:blipFill></pic:pic></a:graphicData></a:graphic>'
                f"</wp:inline></w:drawing></w:r>"
            )
        body.append(
            f'<w:p><w:pPr><w:pStyle w:val="{_style_id(style)}"/></w:pPr>{_xml_runs(runs, styles, escape)}{drawing}</w:p>'
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
            f'<w:style w:type="{kind}" w:styleId="{_style_id(name)}"><w:name w:val="{name}"/></w:style>'
            for name, kind in styles.items()
        )
        + "</w:styles>"
    )
    footnotes = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:footnotes xmlns:w="{W}">'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote></w:footnotes>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        out.writestr("word/document.xml", document)
        out.writestr("word/styles.xml", style_xml)
        out.writestr("word/footnotes.xml", footnotes)
        out.writestr(
            "word/_rels/document.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
            + "".join(rels)
            + "</Relationships>",
        )
        for name, data in media.items():
            out.writestr(f"word/media/{name}", data)
    return buffer.getvalue()


def _xml_runs(runs: Any, styles: dict[str, str], escape: Callable[[str], str]) -> str:
    if isinstance(runs, str):
        runs = [(runs, "")]
    out = []
    for text, style in runs:
        if style:
            styles[style] = "character"
        props = f'<w:rPr><w:rStyle w:val="{_style_id(style)}"/></w:rPr>' if style else ""
        out.append(f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')
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
    ("p", "Author Note", [("ORCID: ", ""), ("0000-0000-0000-0001", "Hyperlink")], None, []),
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
    ("p", "Compact", [("the ", ""), ("first", ""), (" gate reads one quantity;", "")], None, []),
    ("p", "Compact", [("the second gate reads another.", "")], None, []),
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
    ("p", "Source Code", [("alpha = 0.05", "")], None, []),
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


def self_test() -> list[str]:
    """Build the synthetic .docx, require it to pass, and require every mutation to be named."""
    import make_docx_source  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_synthetic(root)
        pictures = {"first": b"\x89PNG first figure", "second": b"\x89PNG second figure"}
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
        inp = load_inputs(root, root / "figures.json", root / "contract.json")
        data = write_docx(
            SYNTHETIC_DOCX, {f"fig-{name}.png": png for name, png in pictures.items()}
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
    if args.docx is None or args.contract is None or args.figures is None:
        parser.error("checking a .docx needs the .docx, --contract and --figures")

    inp = load_inputs(args.repo_root, args.figures, args.contract)
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
