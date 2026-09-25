#!/usr/bin/env python3
"""Read a built PDF back and fail if anything in it identifies the author.

**A PDF is not its text.** Reading the extracted text is not enough and reading the page is not
enough either, because the two places identity actually survives a build are neither:

* the **document information dictionary** and any **XMP** packet, which carry a title, an author
  and a creator tool that no reader ever sees on the page;
* **link annotations**, which store their target URI as plain ASCII beside the visible text. On the
  named build of this manuscript these are the whole of the problem: one Info field, no XMP packet,
  and nine link annotations carrying the repository URL and the ORCID. That is the channel to
  watch, and it is the one a reader of the page never sees.

Text drawn on the page is a third case and the least legible one: a subsetted font maps glyphs
through a custom encoding, so an author's name can be perfectly visible on the page while the byte
string ``Mikoto`` appears nowhere in the file. **So pass ``--text`` with the ``pdftotext`` output.**
Without it this script cannot see the page at all, and the failure is worse than a gap: it reports
a count of zero, which reads as *absent* when it means *invisible from here*. That happened. The
first anonymous build reported the upstream project name appearing zero times in the file while
the page carried it plainly, and only reading the extracted text by hand caught it.

**Everything is searched after inflating.** A PDF of version 1.5 or later puts most indirect
objects -- the information dictionary and the annotation dictionaries included -- inside compressed
object streams, so a scanner that reads only the file as it sits on disk finds no annotations at
all. That is not a clean result; it is a scanner looking in the wrong place. Measured on the named
build of this manuscript: zero annotations before inflating, eight identifying URIs after.

The patterns come from ``make_anonymous_bundle`` so that the bundle and the PDF are held to one
list. Both scripts are kept out of the bundle they build: they are the two files that must contain
the strings they remove.

Usage:  python analysis/scripts/check_pdf_identity.py build/paper.pdf --text build/extracted.txt
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_anonymous_bundle import (  # noqa: E402
    ACCEPTED_EXPOSURES,
    ALLOWED,
    CITED_DOIS,
    LEAK_PATTERNS,
)

#: Strings the supplement has to keep but the anonymous PDF must not carry (``.steering`` DA-C-4 and
#: DA-C-5, user rulings of 2026-09-26). The upstream project's name is an accepted exposure of the
#: bundle, because the provenance checks compare bytes against that project; the PDF has no such
#: constraint, and ``make_pdf_source.py --anonymous`` replaces it. The title of the author's own
#: prior preprint would resolve to the author through any search; the anonymous bibliography
#: withholds it. Both fail this check rather than being counted, because on the page they are a
#: choice, not a constraint.
PDF_WITHHELD: tuple[tuple[str, str], ...] = (
    (ACCEPTED_EXPOSURES[0][0], ACCEPTED_EXPOSURES[0][1]),
    ("the title of the author's own prior preprint", r"two-plane\s+determinism"),
)

#: Keys of the document information dictionary that carry free text.
INFO_KEYS: tuple[str, ...] = (
    "/Title",
    "/Author",
    "/Creator",
    "/Producer",
    "/Subject",
    "/Keywords",
)


def _decompressed(raw: bytes) -> bytes:
    """Return the raw bytes with every inflatable stream appended.

    Annotations and metadata are usually uncompressed, but nothing guarantees it, so the streams
    are expanded and searched too. A stream that will not inflate is skipped rather than fatal:
    fonts and images are not text and are not what this is looking for.
    """
    parts = [raw]
    for match in re.finditer(rb"stream\r?\n", raw):
        start = match.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        try:
            parts.append(zlib.decompress(raw[start:end]))
        except zlib.error:
            continue
    return b"".join(parts)


def _mask(text: str) -> str:
    """Blank the strings that are allowed to match, so the patterns can stay broad.

    ``CITED_DOIS`` is here for the same reason it is in the bundle builder: the DOI pattern cannot
    tell the author's own deposit from a reference, so every reference is declared by hand instead
    of the pattern being narrowed. Both lists come from that module, so there is one of each.
    """
    for allowed in (*ALLOWED, *CITED_DOIS):
        text = text.replace(allowed, "")
    return text


#: A kerning gap inside a TJ array, as pdflatex writes one between two runs of a string: ``)-50(``.
_TJ_GAP = re.compile(r"\)\s*-?\d+(?:\.\d+)?\s*\(")


def is_cited_doi_fragment(found: str) -> bool:
    """Whether a DOI-shaped match is a piece of a DOI declared as someone else's.

    The TMLR bibliography sets DOIs through ``\\url``, which lets them break across lines and kerns
    them: in the inflated streams a cited DOI arrives as ``10.1007/s10462-)-50(025-...``, and on
    the page as ``10.1016/j.spl.`` with the rest on the next line. Neither is masked by the exact
    comparison in :func:`_mask`, and the first TMLR build failed this check on seven cited DOIs
    for that reason alone. A match is accepted only if, with the kerning gaps removed, it is a
    prefix of a declared citation that runs past the registrant prefix -- so a fragment of the
    author's own deposit, whose prefix no citation shares, still fails.
    """
    cleaned = _TJ_GAP.sub("", found).rstrip(").,;:")
    registrant = cleaned.split("/", 1)[0] + "/"
    if len(cleaned) <= len(registrant):
        return False
    return any(doi.startswith(cleaned) for doi in CITED_DOIS)


def _decode_pdf_string(raw: bytes) -> str:
    """Decode one PDF string object into text.

    Three encodings have to be handled, and missing any of them turns this scanner into one that
    reports zero because it could not look:

    * a literal string in parentheses, with backslash escapes and octal byte escapes;
    * a hexadecimal string in angle brackets, which is what some producers emit;
    * either of those carrying a UTF-16BE byte-order mark, which is what ``hyperref`` switches to
      the moment a field contains a single non-ASCII character -- an em dash in a title is enough.

    A review probe found the last two invisible to the previous version: ``/Author <FEFF004D...>``
    and a UTF-16BE author line both scanned as absent.
    """
    if raw.startswith(b"<") and raw.endswith(b">"):
        digits = re.sub(rb"[^0-9A-Fa-f]", b"", raw[1:-1])
        if len(digits) % 2:
            digits += b"0"
        body = bytes.fromhex(digits.decode("ascii"))
    else:
        body = raw[1:-1] if raw.startswith(b"(") else raw
        body = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), body)
        body = re.sub(rb"\\(.)", rb"\1", body)
    if body.startswith(b"\xfe\xff"):
        return body[2:].decode("utf-16-be", "replace")
    return body.decode("latin-1")


def _balanced_string(blob: bytes, start: int) -> bytes | None:
    """Read one parenthesised PDF string starting at ``start``, honouring nesting and escapes.

    A regular expression cannot do this. ``(Mikoto Miura (ORCID))`` is a single valid string with a
    balanced pair inside it, and the previous pattern simply failed to match it -- reporting the
    field as absent rather than as a leak.
    """
    if blob[start : start + 1] != b"(":
        return None
    depth = 0
    index = start
    while index < len(blob):
        char = blob[index : index + 1]
        if char == b"\\":
            index += 2
            continue
        if char == b"(":
            depth += 1
        elif char == b")":
            depth -= 1
            if depth == 0:
                return blob[start : index + 1]
        index += 1
    return None


def _bracketed(blob: bytes, key: bytes) -> list[str]:
    """Every ``key <value>`` and ``key (value)`` pair in ``blob``, decoded to text."""
    values: list[str] = []
    for match in re.finditer(re.escape(key) + rb"\s*", blob):
        at = match.end()
        if blob[at : at + 1] == b"<":
            end = blob.find(b">", at)
            if end != -1:
                values.append(_decode_pdf_string(blob[at : end + 1]))
        else:
            literal = _balanced_string(blob, at)
            if literal is not None:
                values.append(_decode_pdf_string(literal))
    return values


def uris(blob: bytes) -> list[str]:
    """Every link-annotation target. Pass the inflated blob, not the file."""
    return _bracketed(blob, b"/URI")


def info_fields(blob: bytes) -> list[tuple[str, str]]:
    return [(key, value) for key in INFO_KEYS for value in _bracketed(blob, key.encode())]


def xmp_packets(blob: bytes) -> list[str]:
    return [
        block.decode("utf-8", "replace")
        for block in re.findall(rb"<x:xmpmeta.*?</x:xmpmeta>", blob, re.S)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument(
        "--text",
        type=Path,
        help="The pdftotext output for this PDF. Without it the page itself is unreadable here, "
        "because a subsetted font encodes its own glyphs, and the counts below would understate "
        "what a reader can see.",
    )
    args = parser.parse_args(argv)

    if not args.pdf.is_file():
        print(f"[pdf-identity] FAIL: no such file: {args.pdf}", file=sys.stderr)
        return 1

    raw = args.pdf.read_bytes()
    # Everything below reads the inflated blob. See the note in the module docstring: on this
    # document, scanning the file as it sits on disk finds no annotations whatsoever.
    blob = _decompressed(raw)
    haystacks: list[tuple[str, str]] = []

    for key, value in info_fields(blob):
        haystacks.append((f"info dictionary {key}", value))
    for index, packet in enumerate(xmp_packets(blob)):
        haystacks.append((f"XMP packet {index}", packet))
    for uri in uris(blob):
        haystacks.append(("link annotation", uri))
    haystacks.append(("raw bytes and inflated streams", blob.decode("latin-1")))
    # The same bytes read as UTF-16BE. A producer that switched a metadata field to UTF-16 hides
    # every ASCII pattern above from the latin-1 view; reading both costs nothing.
    haystacks.append(("raw bytes read as UTF-16BE", blob.decode("utf-16-be", "ignore")))

    page_text: str | None = None
    if args.text is not None:
        if not args.text.is_file():
            print(f"[pdf-identity] FAIL: no extracted text at {args.text}", file=sys.stderr)
            return 1
        page_text = args.text.read_text(encoding="utf-8", errors="replace")
        haystacks.append(("the page, as pdftotext reads it", page_text))

    problems: list[str] = []
    for where, text in haystacks:
        masked = _mask(text)
        for label, pattern in (*LEAK_PATTERNS, *PDF_WITHHELD):
            for match in re.finditer(pattern, masked, re.IGNORECASE):
                if label == "a DOI" and is_cited_doi_fragment(match.group(0)):
                    continue
                problems.append(f"{where}: {label}: {match.group(0)!r}")

    print(f"[pdf-identity] {args.pdf.name}: {len(raw):,} bytes, {len(blob):,} after inflating")
    print(f"[pdf-identity]   info dictionary fields: {len(info_fields(blob))}")
    print(f"[pdf-identity]   XMP packets: {len(xmp_packets(blob))}")
    print(f"[pdf-identity]   link annotations: {len(uris(blob))}")
    print(
        "[pdf-identity]   page text: "
        + (f"{len(page_text):,} characters" if page_text is not None else "NOT READ (--text absent)")
    )

    if problems:
        print(f"[pdf-identity] FAIL: {len(problems)} identifying item(s)", file=sys.stderr)
        for problem in dict.fromkeys(problems):
            print(f"  - {problem}", file=sys.stderr)
        return 1

    for label, _ in PDF_WITHHELD:
        print(f"[pdf-identity]   WITHHELD: {label} -- 0 occurrences, in the bytes and on the page")

    where = "the metadata, the XMP, the link annotations, and the inflated streams"
    if page_text is None:
        print(
            f"[pdf-identity] OK: no leak pattern in {where}. **The page itself was not read.** "
            "Pass --text with the pdftotext output; a subsetted font encodes its own glyphs, so "
            "the absence of a name in these bytes says nothing about what the page shows.",
        )
    else:
        print(f"[pdf-identity] OK: no leak pattern in {where}, nor in the page as pdftotext "
              "reads it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
