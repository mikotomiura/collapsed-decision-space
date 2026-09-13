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
through a custom encoding, so an author's name can be perfectly visible on the page while the
byte string ``Mikoto`` appears nowhere in the file. Searching for names in the raw bytes therefore
proves nothing on its own, and this script says so rather than counting a zero as a pass. What it
can do exhaustively is the metadata and the annotations, and those are where the leaks were.

**Everything is searched after inflating.** A PDF of version 1.5 or later puts most indirect
objects -- the information dictionary and the annotation dictionaries included -- inside compressed
object streams, so a scanner that reads only the file as it sits on disk finds no annotations at
all. That is not a clean result; it is a scanner looking in the wrong place. Measured on the named
build of this manuscript: zero annotations before inflating, eight identifying URIs after.

The patterns come from ``make_anonymous_bundle`` so that the bundle and the PDF are held to one
list. Both scripts are kept out of the bundle they build: they are the two files that must contain
the strings they remove.

Usage:  python analysis/scripts/check_pdf_identity.py build/paper.pdf
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_anonymous_bundle import ACCEPTED_EXPOSURES, ALLOWED, LEAK_PATTERNS  # noqa: E402

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
    for allowed in ALLOWED:
        text = text.replace(allowed, "")
    return text


def _bracketed(blob: bytes, key: bytes) -> list[str]:
    """Every ``key (value)`` pair in ``blob``, with the parentheses stripped."""
    pattern = re.escape(key) + rb"\s*\((?:[^()\\]|\\.)*\)"
    return [
        match.group(0)[len(key) :].strip().strip(b"()").decode("latin-1")
        for match in re.finditer(pattern, blob)
    ]


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

    problems: list[str] = []
    for where, text in haystacks:
        masked = _mask(text)
        for label, pattern in LEAK_PATTERNS:
            for match in re.finditer(pattern, masked, re.IGNORECASE):
                problems.append(f"{where}: {label}: {match.group(0)!r}")

    print(f"[pdf-identity] {args.pdf.name}: {len(raw):,} bytes, {len(blob):,} after inflating")
    print(f"[pdf-identity]   info dictionary fields: {len(info_fields(blob))}")
    print(f"[pdf-identity]   XMP packets: {len(xmp_packets(blob))}")
    print(f"[pdf-identity]   link annotations: {len(uris(blob))}")

    if problems:
        print(f"[pdf-identity] FAIL: {len(problems)} identifying item(s)", file=sys.stderr)
        for problem in dict.fromkeys(problems):
            print(f"  - {problem}", file=sys.stderr)
        return 1

    inflated = blob.decode("latin-1")
    for label, pattern, _ in ACCEPTED_EXPOSURES:
        hits = len(re.findall(pattern, inflated, re.IGNORECASE))
        print(f"[pdf-identity]   DISCLOSED: {label} appears {hits} time(s) in the file")

    print(
        "[pdf-identity] OK: no leak pattern in the metadata, the XMP, the link annotations, or "
        "the inflated streams. Note the bound: page text is drawn through a subsetted font's own "
        "encoding, so an absence of a name in the bytes is not evidence that the page does not "
        "show it -- for that, read the page."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
