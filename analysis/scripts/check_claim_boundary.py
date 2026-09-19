#!/usr/bin/env python3
"""Enforce the claim guards of ``manuscript/CLAIM-BOUNDARY.md`` against the published text.

Four properties keep this check from passing vacuously, or from being unsatisfiable. Being green and
having been checked are different facts, and each property below was confirmed by breaking it
deliberately and watching the run fail.

1. **The patterns come from ``manuscript/CLAIM-BOUNDARY.md``, never from the text being checked.**
   A document carrying its own forbidden-phrase list and confirming it does not match itself would
   be checking nothing.
2. **Exactly twenty-eight guards, in order, must parse.** A parser that silently yields nothing
   reports "no hits" against any document whatsoever, so the count and the identifiers are pinned.
3. **A positive control accompanies the "zero hits is correct" check.**
   ``manuscript/_claim_boundary_positive_control.md`` trips every pattern on purpose, and the run
   fails unless **every individual pattern** fires against it. Per-guard would be too weak: a guard
   with two patterns would still pass with one of them broken, which is a case that was observed.
4. **A negative control keeps the patterns off sentences that must stay sayable.**
   ``manuscript/_claim_boundary_negative_control.md`` lists, by hand, sentences the seal fixes and
   sentences a correct account of the study needs, and the run fails if **any** pattern matches any
   of them, or if the list does not hold exactly the pinned number of items. The manuscript is
   scanned whole, including the block generated from the sealed rules, so a pattern that matched a
   sealed sentence could never be satisfied; the first version of one guard did exactly that. The
   list is never taken from the manuscript, for the reason property 1 gives.

A further hole is closed by requiring the manuscript to be non-vacuous — an empty or skeletal
manuscript would otherwise sail through on "no hits" — and by requiring its abstract to match the
citation metadata.

Files checked:
  - ``manuscript/main.md`` (English; the principal target)
  - ``README.md`` and ``README.ja.md``
  - ``CITATION.cff`` — its ``abstract`` is rendered by the GitHub citation widget, so it is a
    published claim surface like any other

**A limit worth stating.** The patterns in ``CLAIM-BOUNDARY.md`` are English regular expressions,
because English is the submission language. Against Japanese prose only the language-independent
parts can fire — identifiers, numerals, literals such as ``D_loco``. That is not nothing: it caught
a mislabelled value in the README on 2026-09-12. But an overreach written in Japanese prose would
pass. Adding a Japanese pattern set is outstanding work, and "the README was checked" should be read
with that qualification.

``CLAIM-BOUNDARY.md`` itself and the two fixtures are excluded from the scan of published files:
the first defines the patterns, including illustrative examples of them, the positive control exists
to trip them, and the negative control is checked the other way round, as above.

Usage:  python analysis/scripts/check_claim_boundary.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: A table row is a guard when its first cell is G<number>.
GUARD_ROW_RE = re.compile(r"^\|\s*(G\d+)\s*\|")

#: Split markdown cells, but not on the escaped pipes inside the patterns.
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

#: Pull the backtick-quoted patterns out of a cell.
BACKTICKED_RE = re.compile(r"`([^`]+)`")

#: The guards the source file must carry. Both the count and the order are pinned.
EXPECTED_GUARD_IDS: tuple[str, ...] = tuple(f"G{i}" for i in range(1, 29))

#: Items the negative-control fixture must hold. Pinned for the same reason the guard count is: a
#: list that quietly lost its sealed sentences would still report "no pattern matched".
EXPECTED_NEGATIVE_ITEMS = 23

#: One item of the negative-control fixture per line, each beginning with a dash.
NEGATIVE_ITEM_RE = re.compile(r"^- ", re.MULTILINE)

#: Preconditions for the manuscript being non-vacuous. Failing these means it is unfinished.
#: ``Level 6`` used to head this list and is deliberately gone. The level declaration belonged to
#: the registered-report route the manuscript no longer takes, and a required-anchor list that
#: demanded a phrase the manuscript should not carry would have become a reason to keep dead venue
#: prose alive. Guard G9, which forbids overclaiming that level, is kept -- see CLAIM-BOUNDARY.md.
MAIN_REQUIRED_ANCHORS: tuple[str, ...] = (
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "eligibility",
    "tv_bar",
    "delta_tv_min",
)

#: Same purpose: refuse to pass a skeletal manuscript.
MAIN_MIN_WORDS = 1500


@dataclass(frozen=True)
class Guard:
    """One claim guard — a single row of the table in CLAIM-BOUNDARY.md."""

    guard_id: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class Hit:
    """A pattern matching a published file."""

    guard_id: str
    pattern: str
    path: str
    line_no: int
    line: str


def parse_guards(boundary_path: Path) -> tuple[Guard, ...]:
    """Read G1-G28 and their patterns out of the table in CLAIM-BOUNDARY.md.

    Raises:
        SystemExit: if the guard count, identifiers or pattern count differ from what is expected.
    """
    guards: list[Guard] = []
    text = boundary_path.read_text(encoding="utf-8")

    for raw_line in text.splitlines():
        match = GUARD_ROW_RE.match(raw_line)
        if match is None:
            continue
        cells = [cell.strip() for cell in CELL_SPLIT_RE.split(raw_line)]
        # ['', 'G1', 'claim', 'reason', 'patterns', '']
        if len(cells) < 6:
            _die(
                f"{boundary_path}: too few cells in a guard row "
                f"({match.group(1)}, cells={len(cells)}): {raw_line}"
            )
        pattern_cell = cells[4]
        raw_patterns = BACKTICKED_RE.findall(pattern_cell)
        if not raw_patterns:
            _die(
                f"{boundary_path}: {match.group(1)} carries no search pattern: "
                f"{pattern_cell}"
            )
        compiled: list[re.Pattern[str]] = []
        for raw_pattern in raw_patterns:
            # Undo the pipe escaping the markdown table needed.
            pattern = raw_pattern.replace(r"\|", "|")
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as exc:
                _die(
                    f"{boundary_path}: {match.group(1)} carries an invalid regular "
                    f"expression: {pattern!r} ({exc})"
                )
        guards.append(Guard(match.group(1), tuple(compiled)))

    found_ids = tuple(guard.guard_id for guard in guards)
    if found_ids != EXPECTED_GUARD_IDS:
        _die(
            f"{boundary_path}: the guard identifiers are not what is expected. "
            f"expected={EXPECTED_GUARD_IDS} found={found_ids} "
            "(a parser that yields nothing would pass against any document, so stop here)"
        )
    return tuple(guards)


def normalise_whitespace(text: str) -> str:
    """Collapse line breaks and runs of spaces into a single space.

    The prose is hard-wrapped at around a hundred characters, so a forbidden phrase can easily
    straddle a line ending; scanning line by line misses those. The decision is therefore made on
    normalised text, and line numbers are reported as supplementary information.
    """
    return " ".join(text.split())


def label_for(path: Path, repo_root: Path) -> str:
    """Name a scanned file for reporting.

    Targets passed with --extra-target need not live under the repository root: the submission PDF
    is read back as text from wherever it was built. Fall back to the bare name rather than
    refusing, so a derived artefact cannot escape the check on a path technicality.
    """
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def scan(guards: tuple[Guard, ...], path: Path, repo_root: Path) -> list[Hit]:
    """Scan one file with every guard, including phrases that straddle a line ending."""
    hits: list[Hit] = []
    rel = label_for(path, repo_root)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    flat = normalise_whitespace(text)

    for guard in guards:
        for pattern in guard.patterns:
            for match in pattern.finditer(flat):
                start, end = match.span()
                excerpt = flat[max(0, start - 60) : end + 60]
                # Report a line number when the phrase fits on one line; otherwise 0, and the
                # excerpt locates it.
                line_no = 0
                for index, line in enumerate(lines, start=1):
                    if pattern.search(line):
                        line_no = index
                        break
                hits.append(
                    Hit(guard.guard_id, pattern.pattern, rel, line_no, excerpt)
                )
    return hits


def check_manuscript_not_vacuous(main_path: Path) -> list[str]:
    """Refuse an empty or skeletal manuscript, which would pass on 'no hits' alone."""
    problems: list[str] = []
    text = main_path.read_text(encoding="utf-8")
    word_count = len(text.split())
    if word_count < MAIN_MIN_WORDS:
        problems.append(
            f"{main_path.name}: {word_count} words, below the floor of {MAIN_MIN_WORDS}. "
            "This precondition exists so an unfinished manuscript cannot pass on 'no hits'"
        )
    lowered = text.lower()
    missing = [
        anchor for anchor in MAIN_REQUIRED_ANCHORS if anchor.lower() not in lowered
    ]
    if missing:
        problems.append(f"{main_path.name}: required anchors missing: {missing}")
    return problems


def _extract_main_abstract(main_path: Path) -> str | None:
    """Take the body of the ``## Abstract`` section out of main.md."""
    lines = main_path.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    in_abstract = False
    for line in lines:
        if line.startswith("## "):
            if in_abstract:
                break
            in_abstract = line.strip().lower() == "## abstract"
            continue
        if in_abstract:
            if line.strip() == "---":
                break
            body.append(line)
    text = " ".join(body).strip()
    return text or None


def check_abstract_consistency(main_path: Path, citation_path: Path) -> list[str]:
    """Require the manuscript abstract and the citation metadata to be the same text.

    Editing one without the other would leave the published citation widget quietly disagreeing
    with the manuscript.
    """
    import yaml  # noqa: PLC0415  (present only in the locked environment)

    manuscript_abstract = _extract_main_abstract(main_path)
    if manuscript_abstract is None:
        return [f"{main_path.name}: the `## Abstract` section is missing or empty"]

    citation = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    citation_abstract = citation.get("abstract")
    if not citation_abstract:
        return [
            f"{citation_path.name}: `abstract` is empty. With a manuscript in place, this "
            "must not be published blank"
        ]

    left = " ".join(manuscript_abstract.split())
    right = " ".join(str(citation_abstract).split())
    if left != right:
        return [
            f"the abstract in {main_path.name} differs from the one in {citation_path.name}; "
            "editing one without the other leaves the published metadata disagreeing with the "
            "manuscript\n"
            f"      main.md      : {left[:120]}…\n"
            f"      CITATION.cff : {right[:120]}…"
        ]
    print(
        f"[claim-boundary] OK: the abstract in {main_path.name} matches "
        f"{citation_path.name} ({len(left.split())} words)"
    )
    return []


def check_positive_control(guards: tuple[Guard, ...], fixture_path: Path) -> list[str]:
    """Require **every single pattern** to fire against the positive control.

    Per-guard would be too weak. In mutation testing one of G7's two patterns was broken and the
    check still passed, because the other one matched the fixture. Requiring it per pattern means a
    single broken pattern fails the run.
    """
    text = normalise_whitespace(fixture_path.read_text(encoding="utf-8"))
    silent = [
        f"{guard.guard_id}:{pattern.pattern}"
        for guard in guards
        for pattern in guard.patterns
        if not pattern.search(text)
    ]
    total = sum(len(guard.patterns) for guard in guards)
    if silent:
        return [
            f"{fixture_path.name}: patterns that did not fire against the positive control "
            f"({len(silent)}/{total}): {silent}. Either the checker is broken, or the pattern "
            "no longer catches the phrasing written for it"
        ]
    print(
        f"[claim-boundary] OK: {total}/{total} patterns fired against the positive control "
        f"({len(guards)} guards)"
    )
    return []


def check_negative_control(
    guards: tuple[Guard, ...], fixture_path: Path, expected_items: int = EXPECTED_NEGATIVE_ITEMS
) -> list[str]:
    """Require **no** pattern to match the negative control, and its items to be all there.

    The positive control shows that each pattern can fire. This shows the opposite property, which
    the positive control cannot: that no pattern fires on a sentence the manuscript has to be able
    to say. A pattern broad enough to catch a sealed sentence would make the manuscript impossible
    to pass without editing the seal, and a pattern broad enough to catch a correct limitation
    would push the prose towards saying less than it should.
    """
    raw = fixture_path.read_text(encoding="utf-8")
    problems: list[str] = []
    items = len(NEGATIVE_ITEM_RE.findall(raw))
    if items != expected_items:
        problems.append(
            f"{fixture_path.name}: holds {items} items, but {expected_items} are expected. An item "
            "that drops out of this list stops holding its pattern away from a sentence the "
            "manuscript needs"
        )
    text = normalise_whitespace(raw)
    for guard in guards:
        for pattern in guard.patterns:
            match = pattern.search(text)
            if match is not None:
                start, end = match.span()
                problems.append(
                    f"{fixture_path.name}: {guard.guard_id} pattern={pattern.pattern!r} matches a "
                    f"sentence that must stay sayable: …{text[max(0, start - 60) : end + 60]}…"
                )
    if not problems:
        total = sum(len(guard.patterns) for guard in guards)
        print(
            f"[claim-boundary] OK: none of the {total} patterns matches the {items} sentences of "
            "the negative control"
        )
    return problems


def check_negative_control_fires(fixture_path: Path) -> list[str]:
    """Break the negative-control check twice and require it to notice both times.

    A check whose only observed outcome is "nothing matched" has not been shown to be able to say
    anything else. Two cases, each with the diagnostic it must produce: a pattern that is too broad
    (it matches the sentence about the permutation test's power, which the manuscript must carry),
    and a fixture from which one item has been removed. Output from the cases is swallowed, so that
    a case's OK line is never read as a statement about the real fixture.
    """
    too_broad = (Guard("G0", (re.compile(r"power of the permutation test", re.IGNORECASE),)),)
    problems: list[str] = []
    with contextlib.redirect_stdout(io.StringIO()):
        broad = check_negative_control(too_broad, fixture_path)
        with tempfile.TemporaryDirectory() as tmp:
            lines = fixture_path.read_text(encoding="utf-8").splitlines(keepends=True)
            first_item = next(i for i, line in enumerate(lines) if line.startswith("- "))
            shortened = Path(tmp) / fixture_path.name
            shortened.write_text(
                "".join(lines[:first_item] + lines[first_item + 1 :]), encoding="utf-8"
            )
            dropped = check_negative_control((), shortened)
    for label, reported, expect in (
        ("an over-broad pattern", broad, "must stay sayable"),
        ("a dropped item", dropped, f"holds {EXPECTED_NEGATIVE_ITEMS - 1} items"),
    ):
        joined = " | ".join(reported)
        if expect not in joined:
            problems.append(
                f"self-check, {label}: the negative-control check did not report it for the "
                f"expected reason (wanted text containing {expect!r}, got {joined!r})"
            )
    if not problems:
        print(
            "[claim-boundary] OK self-check: an over-broad pattern and a dropped item are both "
            "reported by the negative-control check"
        )
    return problems


def _die(message: str) -> None:
    print(f"[claim-boundary] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--extra-target",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "additional file to scan for forbidden phrasing. Used for artefacts derived from the "
            "manuscript that are published in their own right -- the submission PDF, read back as "
            "text. A derived artefact is a claim surface too, and one that no other check reaches."
        ),
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    boundary_path = repo_root / "manuscript" / "CLAIM-BOUNDARY.md"
    main_path = repo_root / "manuscript" / "main.md"
    fixture_path = repo_root / "manuscript" / "_claim_boundary_positive_control.md"
    negative_path = repo_root / "manuscript" / "_claim_boundary_negative_control.md"
    citation_path = repo_root / "CITATION.cff"
    extra_targets: list[Path] = [p.resolve() for p in args.extra_target]
    targets = (
        main_path,
        repo_root / "README.md",
        repo_root / "README.ja.md",
        citation_path,
        *extra_targets,
    )

    for path in (boundary_path, main_path, fixture_path, negative_path, *targets):
        if not path.is_file():
            _die(f"a required file is missing: {path}")

    guards = parse_guards(boundary_path)
    print(f"[claim-boundary] {len(guards)} guards parsed from {boundary_path.name}")

    problems: list[str] = []
    problems.extend(check_manuscript_not_vacuous(main_path))
    problems.extend(check_abstract_consistency(main_path, citation_path))
    problems.extend(check_positive_control(guards, fixture_path))
    problems.extend(check_negative_control_fires(negative_path))
    problems.extend(check_negative_control(guards, negative_path))

    hits: list[Hit] = []
    for path in targets:
        hits.extend(scan(guards, path, repo_root))

    problems.extend(
        f"{hit.path}:{hit.line_no}: {hit.guard_id} matched "
        f"pattern={hit.pattern!r}: {hit.line}"
        for hit in hits
    )

    if problems:
        print("[claim-boundary] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\n  On a hit, fix the prose. Do not relax the check "
            "(CLAIM-BOUNDARY.md, section 2).",
            file=sys.stderr,
        )
        return 1

    scanned = ", ".join(label_for(path, repo_root) for path in targets)
    print(
        f"[claim-boundary] OK: no forbidden phrasing in {scanned} "
        "(patterns are English; against Japanese prose only language-independent "
        "literals can fire)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
