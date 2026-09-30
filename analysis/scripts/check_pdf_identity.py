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

**The generated source is read as well** (``--source``). The page loses a word the layout broke or
hyphenated across lines, so a withheld word can be on the page yet absent from its text; the
source the PDF was built from still has it whole. ``--mutation-test`` then puts each withheld word
back into copies of both, one at a time, and requires each to be reported under its own label.

Usage:  python analysis/scripts/check_pdf_identity.py build/paper.pdf --text build/extracted.txt \\
            --source build/paper-source.md --mutation-test
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
    # The title, allowing for pdftotext joining a word it found hyphenated at a line break
    # ("twoplane"), and the subtitle, which a search resolves as surely (TASK-POST review).
    ("the title of the author's own prior preprint", r"two-?\s*plane\s+determinism"),
    ("the subtitle of the author's own prior preprint", r"byte-?\s*exact\s+cross-?\s*platform"),
    # The repository's tags (TASK-POST review), the same list make_pdf_source.py withholds.
    ("a tag of the repository", r"autopsy-b3-declared|stage1-submitted"),
    # The venue this work was submitted to before (user ruling of 2026-09-26, DA-C-16).
    ("the earlier venue", r"PCI\s+Registered\s+Reports"),
    # The 2026-09-30 revision (``.steering`` DA-DR-16 and DA-TR-1). F01 = b: a prefix of the
    # upstream project that its name pattern above does not catch (an environment variable), and a
    # project-specific script name. Written with whitespace allowed where the layout can break a
    # phrase across lines.
    ("the upstream project's prefix", r"ERRE_"),
    ("a project-specific script name", r"paper02_"),
    ("public continuous integration", r"public\s+continuous\s+integration"),
    # This repository's name on its own, not only inside its URL (DA-C-18).
    ("the repository's name", r"collapsed-decision-space"),
    # F02 = c: no supplement is submitted, so the PDF must not promise or describe one. The word is
    # matched everywhere; only the PDF syntax ``/Supplement <n>`` is taken out of the raw bytes first
    # (:data:`_CMAP_SUPPLEMENT`), because every ToUnicode CMap pdflatex writes carries one.
    ("a supplement", r"supplement"),
    # The placeholders the bundle installs. On the page a URL would lead nowhere, and a deposit
    # identifier would point a reviewer at an archive (TASK-POST review). Matched before the mask
    # that lets the bundle's own scan accept them.
    ("a placeholder location", r"anonymous\.invalid"),
    ("a placeholder identifier", r"10\.0000/anonymous"),
    # The deposit's registration time, which a search of the archive would resolve (user ruling of
    # 2026-09-30, DA-TR-17).
    ("the deposit's registration time", r"2026-09-13T23:44:39"),
    # The de-identification tool, which names what the anonymous build was made from.
    ("the de-identification tool", r"make_anonymous_bundle"),
)

#: The one PDF construct the word "supplement" occurs in without being prose: the ``/Supplement``
#: entry of a CMap's ``/CIDSystemInfo`` (the previous submission's inflated bytes held 26 and no
#: other occurrence). Removed from the raw-bytes haystacks only; the page and the source are
#: searched as they are.
_CMAP_SUPPLEMENT = re.compile(r"/Supplement\s+\d+")

#: One sample per withheld word for ``--mutation-test``: put back into a copy of the real page text
#: and of the real generated source, each must be reported under its own label and no other. The
#: phrase that may break across lines is put back broken, which is the case a line-by-line check
#: would miss.
MUTATION_SAMPLES: dict[str, tuple[str, ...]] = {
    "the upstream project name": ("ERRE-Sandbox",),
    "the title of the author's own prior preprint": ("Two-plane determinism",),
    "the subtitle of the author's own prior preprint": ("byte-exact cross-platform",),
    "a tag of the repository": ("stage1-submitted",),
    "the earlier venue": ("PCI Registered Reports",),
    "the upstream project's prefix": ("ERRE_ZONE_BIAS_P",),
    "a project-specific script name": ("scripts/paper02_run_arms.py",),
    "public continuous integration": ("re-run by public\ncontinuous integration",),
    "the repository's name": ("collapsed-decision-space",),
    # The second sample is the case an exclusion of "/Supplement" would let through (TASK-POST).
    "a supplement": ("the review supplement", "files under manuscript/supplement/ are"),
    "a placeholder location": ("https://anonymous.invalid/repo",),
    "a placeholder identifier": ("10.0000/anonymous.concept",),
    "the deposit's registration time": ("2026-09-13T23:44:39.000Z",),
    "the de-identification tool": ("analysis/scripts/make_anonymous_bundle.py",),
}

#: A git commit identifier on the page (DA-C-15), abbreviated or full, either case. Read against
#: the page only: an inflated content stream is binary, and short runs of hexadecimal characters
#: occur in it by chance. The lookarounds keep a number in exponent form (``3.415046e-05``) and
#: a hyphenated identifier from matching.
COMMIT_ON_PAGE = re.compile(
    r"(?<![.\w])(?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*[0-9])[0-9a-fA-F]{7,40}(?![\w-])"
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


#: A SHA-256 digest that the layout broke in two: two hexadecimal runs separated by one whitespace
#: character whose lengths add up to 64. The manuscript sets content digests (a model's, a file's)
#: through ``\\seqsplit``, and pdftotext joins the pieces with a space (xpdf) or a newline (poppler,
#: which is what CI runs; the first CI run of this rule failed on exactly that); a piece of 11
#: characters is then commit-shaped. Only the exact length of a digest is accepted, so a commit
#: identifier is not.
_SPLIT_DIGEST = re.compile(r"(?<![0-9a-f])([0-9a-f]{8,63})\s([0-9a-f]{1,56})(?![0-9a-f])")


def mask_page(text: str) -> str:
    """Repair, for the page text only, the two ways the layout splits an inert identifier.

    A cited DOI broken at a line end arrives as ``10.1016/j.spl. 2023.109999``: each declared DOI is
    therefore also masked with whitespace allowed between any two of its characters -- that DOI and
    no other. And a digest broken the same way is masked where its two pieces make 64 characters.
    """
    for doi in CITED_DOIS:
        text = re.sub(r"\s*".join(re.escape(ch) for ch in doi), "", text)
    return _SPLIT_DIGEST.sub(
        lambda m: "" if len(m.group(1)) + len(m.group(2)) == 64 else m.group(0), text
    )


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


#: The gap between one string of a content stream and the next: the first closes, positioning and
#: font operators follow (no string of their own), and the next opens. ``\\url`` may break a DOI
#: across lines right after its registrant prefix, and the stream then reads
#: ``[(doi:10.1002/)]TJ -395.273 -11.956 Td [(9781119482260)]TJ`` -- the 2026-09-30 build did.
_STRING_GAP = re.compile(r"\)[^()]{0,160}?\(")
_DOI_PATTERN = dict(LEAK_PATTERNS)["a DOI"]


def rejoins_cited_doi(text: str, start: int) -> bool:
    """Whether the DOI that starts at ``start``, joined across up to three string gaps, is cited.

    A fragment that stops at the registrant prefix cannot be told apart by
    :func:`is_cited_doi_fragment`, since every declared citation of that registrant begins with
    it. Joined with the strings that follow it, one gap at a time, it is accepted only if some
    join reproduces a declared citation **exactly**. A fragment of the author's own deposit joins
    to a DOI no citation declares, and still fails.
    """
    window = text[start : start + 400]
    for _ in range(3):
        gap = _STRING_GAP.search(window)
        if gap is None:
            return False
        window = window[: gap.start()] + window[gap.end() :]
        match = re.match(_DOI_PATTERN, window)
        if match and match.group(0).rstrip(").,;:") in CITED_DOIS:
            return True
    return False


def doi_split_self_test() -> tuple[int, list[str]]:
    """Run :func:`scan` on synthetic content streams whose answer is known.

    Each case is ``(name, stream, expected label or None)``. A case expecting a label passes only if
    exactly one problem is reported, under that label; ``None`` is a control that must report
    nothing.
    """
    cited = "10.1002/9781119482260"
    registrant, rest = cited.split("/", 1)
    cases: tuple[tuple[str, str, str | None], ...] = (
        ("D1 a cited DOI broken across lines after its registrant",
         f"[(doi:{registrant}/)]TJ -395.273 -11.956 Td [({rest})]TJ/F38 9.9626 Tf [(.)]TJ", None),
        ("D2 a cited DOI kerned inside one TJ array",
         f"[(doi:{registrant}/97811)-50(19482260)]TJ", None),
        ("D3 a deposit at a registrant no citation shares, broken the same way",
         "[(doi:10.17605/)]TJ -395.273 -11.956 Td [(OSF.IO/ABCDE)]TJ", "a DOI"),
        ("D4 an undeclared DOI of a cited registrant broken the same way",
         f"[(doi:{registrant}/)]TJ -395.273 -11.956 Td [(9999999999999)]TJ", "a DOI"),
        ("D5 a cited registrant alone, with nothing after it",
         f"[(doi:{registrant}/)]TJ ET", "a DOI"),
    )  # fmt: skip
    failures: list[str] = []
    for name, stream, expected in cases:
        found = scan([("synthetic stream", stream)])
        if expected is None:
            if found:
                failures.append(f"{name}: the control reported {found}")
        elif not found:
            failures.append(f"{name}: not caught (no problem returned)")
        elif len(found) != 1 or f": {expected}: " not in found[0]:
            failures.append(f"{name}: caught for another reason: got {found}")
    return len(cases), failures


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


PAGE = "the page, as pdftotext reads it"
SOURCE = "the generated source (paper-source.md)"


def scan(haystacks: list[tuple[str, str]]) -> list[str]:
    """Every leak pattern and withheld word found in ``haystacks``, as ``where: label: match``.

    ``main`` and ``--mutation-test`` both call this one function, so the mutation test exercises
    the check that runs on the PDF rather than a copy of it.
    """
    problems: list[str] = []
    for where, text in haystacks:
        if where.startswith("raw bytes"):
            text = _CMAP_SUPPLEMENT.sub("", text)
        for label, pattern in PDF_WITHHELD:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                problems.append(f"{where}: {label}: {match.group(0)!r}")
        masked = _mask(text)
        for label, pattern in LEAK_PATTERNS:
            for match in re.finditer(pattern, masked, re.IGNORECASE):
                # A cited DOI split by the layout: accepted only where the split is visible -- a
                # kerning gap or a string end inside the match, or the line ending right after it.
                # A fragment that simply stops mid-line is not a line break and still fails.
                found = match.group(0)
                broken = (
                    _TJ_GAP.search(found) is not None
                    or found.endswith(")")
                    or masked[match.end() : match.end() + 1] in ("\n", "\r", "")
                )
                if label == "a DOI" and broken and (
                    is_cited_doi_fragment(found) or rejoins_cited_doi(masked, match.start())
                ):
                    continue
                problems.append(f"{where}: {label}: {match.group(0)!r}")
    return problems


def mutation_test(page_text: str, source_text: str) -> tuple[int, list[str]]:
    """Put each withheld word back into copies of the real page and source, one at a time.

    Returns the number of mutants run and what went wrong. The unmutated copies are the control
    and must report nothing. Each mutant must add exactly one problem, carrying its own label: a
    mutant reported under another label, or under several, has not shown that the check sees the
    word it is meant to see (a mutant not caught, and a mutant caught for another reason, are
    reported apart).
    """
    failures: list[str] = []
    labels = [label for label, _ in PDF_WITHHELD]
    if sorted(labels) != sorted(MUTATION_SAMPLES):
        failures.append(
            "MUTATION_SAMPLES does not hold samples for exactly the withheld words: "
            f"missing {sorted(set(labels) - set(MUTATION_SAMPLES))}, "
            f"extra {sorted(set(MUTATION_SAMPLES) - set(labels))}"
        )
    run = 0
    for where, text, prepare in (
        (PAGE, page_text, mask_page),
        (SOURCE, source_text, lambda t: t),
    ):
        control = scan([(where, prepare(text))])
        if control:
            failures.append(f"control ({where}) reported {control[:3]}")
            continue
        for label in labels:
            for sample in MUTATION_SAMPLES.get(label, ()):
                run += 1
                # Placed mid-document, between two paragraphs, rather than appended at the end.
                middle = text.find("\n\n", len(text) // 2)
                at = middle if middle != -1 else len(text)
                mutant = text[:at] + "\n\n" + sample + "\n\n" + text[at:]
                found = scan([(where, prepare(mutant))])
                name = f"{label} ({where}, {sample!r})"
                if not found:
                    failures.append(f"{name}: not caught (no problem returned)")
                elif len(found) != 1 or f"{where}: {label}: " not in found[0]:
                    failures.append(f"{name}: caught for another reason: got {found}")
    return run, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the scanner on synthetic content streams in which a DOI is broken across lines or "
        "kerned, whose answer is known, and nothing else.",
    )
    parser.add_argument(
        "--text",
        type=Path,
        help="The pdftotext output for this PDF. Without it the page itself is unreadable here, "
        "because a subsetted font encodes its own glyphs, and the counts below would understate "
        "what a reader can see.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="The paper-source.md the PDF was built from. The page text loses words that the layout "
        "hyphenated or broke across lines, so the withheld words are also looked for in the source.",
    )
    parser.add_argument(
        "--mutation-test",
        action="store_true",
        help="Also put each withheld word back into copies of the --text and --source files, one "
        "at a time, and require each to be reported under its own label. Requires both.",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        ran, failures = doi_split_self_test()
        if ran == 0 or failures:
            print(f"[pdf-identity] FAIL: self-test, {len(failures)} of {ran} cases", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(
            f"[pdf-identity] OK self-test: {ran} synthetic streams, a cited DOI broken across lines "
            "or kerned is accepted, and a broken DOI that is not a declared citation is reported"
        )
        return 0
    if args.pdf is None:
        parser.error("the PDF is required unless --self-test is given")
    if args.mutation_test and (args.text is None or args.source is None):
        parser.error("--mutation-test requires --text and --source")

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
        haystacks.append((PAGE, mask_page(page_text)))

    source_text: str | None = None
    if args.source is not None:
        if not args.source.is_file():
            print(f"[pdf-identity] FAIL: no generated source at {args.source}", file=sys.stderr)
            return 1
        source_text = args.source.read_text(encoding="utf-8", errors="replace")
        haystacks.append((SOURCE, source_text))

    problems = scan(haystacks)
    if page_text is not None:
        for match in COMMIT_ON_PAGE.finditer(mask_page(page_text)):
            problems.append(f"{PAGE}: a commit identifier: {match.group(0)!r}")

    print(f"[pdf-identity] {args.pdf.name}: {len(raw):,} bytes, {len(blob):,} after inflating")
    print(f"[pdf-identity]   info dictionary fields: {len(info_fields(blob))}")
    print(f"[pdf-identity]   XMP packets: {len(xmp_packets(blob))}")
    print(f"[pdf-identity]   link annotations: {len(uris(blob))}")
    print(
        "[pdf-identity]   page text: "
        + (f"{len(page_text):,} characters" if page_text is not None else "NOT READ (--text absent)")
    )
    print(
        "[pdf-identity]   generated source: "
        + (
            f"{len(source_text):,} characters"
            if source_text is not None
            else "NOT READ (--source absent)"
        )
    )

    if problems:
        print(f"[pdf-identity] FAIL: {len(problems)} identifying item(s)", file=sys.stderr)
        for problem in dict.fromkeys(problems):
            print(f"  - {problem}", file=sys.stderr)
        return 1

    places = "in the bytes" + (", on the page" if page_text is not None else "") + (
        " and in the generated source" if source_text is not None else ""
    )
    for label, _ in PDF_WITHHELD:
        print(f"[pdf-identity]   WITHHELD: {label} -- 0 occurrences, {places}")

    if args.mutation_test:
        assert page_text is not None and source_text is not None
        ran, failures = mutation_test(page_text, source_text)
        if ran == 0:
            print("[pdf-identity] FAIL: the mutation test ran 0 mutants", file=sys.stderr)
            return 1
        if failures:
            print(
                f"[pdf-identity] FAIL: mutation test, {len(failures)} of {ran} mutants",
                file=sys.stderr,
            )
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(
            f"[pdf-identity] OK mutation test: {ran} mutants ({len(PDF_WITHHELD)} withheld words, "
            "each sample put back into the page text and into the generated source) each reported "
            "under its own label and no other; the unmutated copies report nothing"
        )

    where = "the metadata, the XMP, the link annotations, and the inflated streams"
    if page_text is None:
        print(
            f"[pdf-identity] OK: no leak pattern in {where}. **The page itself was not read.** "
            "Pass --text with the pdftotext output; a subsetted font encodes its own glyphs, so "
            "the absence of a name in these bytes says nothing about what the page shows.",
        )
    else:
        also = ", nor in the generated source" if source_text is not None else ""
        print(f"[pdf-identity] OK: no leak pattern in {where}, nor in the page as pdftotext "
              f"reads it{also}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
