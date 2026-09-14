#!/usr/bin/env python3
"""Render ``manuscript/reported-branch.txt`` from the branch the manuscript names.

Step 13 of ``repro.sh`` re-derives the decision branch from the sealed rules and the recorded
quantities, and fails if it is not the branch this repository reports. The branch it compares
against is read from ``manuscript/reported-branch.txt``. Two things about that file shape this
script.

**It cannot hold a reason.** ``repro.sh`` is sealed and reads the file as
``--expect-branch "$(tr -d '[:space:]' < "$REPORTED_BRANCH")"`` -- the whole file with all
whitespace removed. A comment line does not annotate the branch; it becomes part of it. So the
file is one token, and everything else about the decision has to live somewhere else.

**It must not be a second statement of the claim.** The manuscript already says, in §8, why the
decision rules are generated from the sealed file rather than written out beside it: two
statements of the same thing drift, and one statement with a renderer cannot. The reported branch
is in exactly that position. If the results section named one branch and this file named another,
the run would still be green whenever the file happened to match the rules -- the disagreement
with the prose would be caught by nothing. So the file is **generated**, from a marker in
``manuscript/main.md``:

    <!-- REPORTED-BRANCH: R1 -->

placed in the results section, beside the claim it licenses. The marker is the single statement;
this file is its rendering; ``check_manuscript_numbers.py`` (step 9) fails if they disagree, or if
the verdicts have landed and no marker has been written.

**What this does not establish.** Nothing here shows that the marker was written before step 13
was run. The order cannot be checked: ``data/derived/`` is regenerated on every run and is not
tracked, and commit order is the author's to arrange. What it establishes is that the branch this
repository reports is the branch the sealed rules reach on the recorded quantities, and that the
manuscript and the compared file say the same thing. ``manuscript/REPORTED-BRANCH.md`` records the
procedure, and states this limit rather than leaving a reader to find it.

Usage:
    python analysis/scripts/render_reported_branch.py            # write the file
    python analysis/scripts/render_reported_branch.py --check    # compare, write nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402

#: The marker that names the branch. An HTML comment, so it does not appear in the rendered
#: manuscript: this binds the source a reviewer reads in the repository, not the page a reader
#: sees in the PDF. Stated here so the limit is not mistaken for a stronger one.
MARKER_RE = re.compile(r"<!--\s*REPORTED-BRANCH:\s*(?P<branch>[A-Za-z0-9_-]+)\s*-->")

#: The bounds of the block §8 generates from the sealed rules. A marker inside it would be
#: overwritten by the renderer that owns that block, and -- worse -- would look generated while
#: being the one part of the file that is a human claim.
GENERATED_BEGIN_RE = re.compile(r"<!--\s*BEGIN GENERATED FROM\b")
GENERATED_END_RE = re.compile(r"<!--\s*END GENERATED FROM\b")

RELATIVE_MAIN = Path("manuscript") / "main.md"
RELATIVE_OUT = Path("manuscript") / "reported-branch.txt"
RELATIVE_RULES = Path("seal") / "decision-rules.json"


class MarkerError(Exception):
    """The manuscript's branch marker is missing, duplicated, or not usable."""


def sealed_branch_ids(repo_root: Path) -> tuple[str, ...]:
    """The branch identifiers the sealed rules can reach.

    Read from the sealed file rather than listed here. A local list would be a second statement
    of the rule set, which is the thing this script exists to avoid.
    """
    rules = load_json(repo_root / RELATIVE_RULES)
    ids = tuple(str(rule["id"]) for rule in rules["rules"])
    if not ids:
        raise MarkerError(f"{RELATIVE_RULES.as_posix()} lists no rules")
    return ids


def generated_span(text: str) -> tuple[int, int] | None:
    """Character offsets of the generated block in ``text``, if it has one."""
    begin = GENERATED_BEGIN_RE.search(text)
    end = GENERATED_END_RE.search(text)
    if begin is None or end is None:
        return None
    return begin.start(), end.end()


def find_marker(text: str, branch_ids: tuple[str, ...]) -> str | None:
    """Return the branch the manuscript names, or ``None`` if it names none.

    Raises:
        MarkerError: if more than one marker is present, if a marker sits inside the generated
            block, or if the branch it names is not one the sealed rules can reach.
    """
    matches = list(MARKER_RE.finditer(text))
    if not matches:
        return None
    if len(matches) > 1:
        found = ", ".join(match.group("branch") for match in matches)
        raise MarkerError(
            f"{RELATIVE_MAIN.as_posix()} carries {len(matches)} REPORTED-BRANCH markers "
            f"({found}). The reported branch is one claim and has one statement"
        )

    match = matches[0]
    span = generated_span(text)
    if span is not None and span[0] <= match.start() < span[1]:
        raise MarkerError(
            "the REPORTED-BRANCH marker is inside the block generated from "
            "seal/decision-rules.json. It is a claim about the result, not generated text, and "
            "the renderer that owns that block would overwrite it"
        )

    branch = match.group("branch")
    if branch not in branch_ids:
        raise MarkerError(
            f"the manuscript names branch {branch!r}, which is not one the sealed rules can "
            f"reach ({', '.join(branch_ids)})"
        )
    return branch


def render(branch: str) -> str:
    """The exact bytes of ``manuscript/reported-branch.txt`` for ``branch``.

    One token and one newline. ``repro.sh`` strips all whitespace before comparing, so it would
    accept a sloppier file; this is the stricter form, because a file a human might have to read
    should not depend on that leniency.
    """
    return f"{branch}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the existing file against the manuscript instead of writing it",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root
    main_md = repo_root / RELATIVE_MAIN
    out_path = repo_root / RELATIVE_OUT

    if not main_md.is_file():
        print(f"[branch] FAIL: the manuscript is missing: {main_md}", file=sys.stderr)
        return 1

    try:
        branch_ids = sealed_branch_ids(repo_root)
        branch = find_marker(main_md.read_text(encoding="utf-8"), branch_ids)
    except MarkerError as exc:
        print(f"[branch] FAIL: {exc}", file=sys.stderr)
        return 1

    if branch is None:
        print(
            "[branch] the manuscript names no branch yet, so there is nothing to render. "
            "Write the marker into the results section once the arms have run; "
            "manuscript/REPORTED-BRANCH.md gives the procedure"
        )
        return 0

    rendered = render(branch)
    if args.check:
        if not out_path.is_file():
            print(
                f"[branch] FAIL: the manuscript names {branch} but "
                f"{RELATIVE_OUT.as_posix()} does not exist. Run this script without --check",
                file=sys.stderr,
            )
            return 1
        actual = out_path.read_text(encoding="utf-8")
        if actual != rendered:
            print(
                f"[branch] FAIL: {RELATIVE_OUT.as_posix()} holds {actual!r}, but the "
                f"manuscript names {branch} ({rendered!r}). The file is generated; do not edit "
                "it by hand",
                file=sys.stderr,
            )
            return 1
        print(f"[branch] OK {RELATIVE_OUT.as_posix()} is what the manuscript renders to ({branch})")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"[branch] wrote {RELATIVE_OUT.as_posix()} = {branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
