#!/usr/bin/env python3
"""Compare the numbers the manuscript quotes with the frozen inputs they come from.

The manuscript states that its numbers are taken from the extraction script rather than copied by
hand. **Stating it is not checking it.** That an extraction script exists, and that the prose agrees
with what it produces, are two different facts; asserting the second on the strength of the first is
the error this script removes.

The method is plain. Each quantity is read from the frozen JSON **by key** -- direct subscripting,
never a default -- so a key absent from the file raises rather than returning something plausible.
The resulting literal must then appear in the manuscript.

What this establishes: for the quantities listed below, the literal produced from the frozen record
**occurs** in the manuscript, and in the README for the subset the README quotes.

What it does not, stated precisely because an earlier version of this file overstated it: the test
is occurrence, not uniqueness. Several of these values appear at more than one place in the
manuscript, so altering one occurrence while leaving another intact does **not** fail the run. The
claim "a single altered digit fails the run" holds only for a quantity that occurs exactly once,
and this script does not check which those are. Nor does it cover the correctness of every number
in the document: its scope is the quantities obtainable mechanically from the frozen inputs.

This script also holds the one claim in the repository that is neither a number nor generated:
**which decision branch the manuscript reports.** Step 13 of ``repro.sh`` compares that claim
against the branch the sealed rules reach, but it is guarded on
``manuscript/reported-branch.txt`` existing -- and when the file is absent the step passes the
evaluator no expectation at all, so it runs, prints a branch, and exits 0 having compared
nothing. A green run and a checked run are different facts. :func:`check_reported_branch` makes
the absence a failure once there is something to report, and requires the file to be what the
manuscript renders to rather than a second, hand-written statement of the same claim.

Usage:  python analysis/scripts/check_manuscript_numbers.py
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import shutil
import sys
import tempfile
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402
from render_reported_branch import (  # noqa: E402
    MarkerError,
    find_marker,
    render,
    sealed_branch_ids,
)
from verify_data_hashes import PROSPECTIVE_OUTPUTS  # noqa: E402
import check_crossrefs  # noqa: E402

#: (label, input file, key path, how to render the literal).
#: The key path walks dictionaries only.
REQUIRED: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("verdict", "cproper-verdict.json", ("verdict",), "str"),
    ("rho_hat", "cproper-verdict.json", ("rho_hat",), "repr"),
    ("power", "cproper-verdict.json", ("power",), "repr"),
    ("tv_bar", "cproper-verdict.json", ("tv_bar",), "repr"),
    ("permutation_p_value", "cproper-verdict.json", ("permutation_p_value",), "repr"),
    (
        "none_rate_max_observed",
        "cproper-verdict.json",
        ("none_rate_max_observed",),
        "repr",
    ),
    ("thresholds.alpha", "cproper-verdict.json", ("thresholds", "alpha"), "repr"),
    (
        "thresholds.delta_tv_min",
        "cproper-verdict.json",
        ("thresholds", "delta_tv_min"),
        "two_dp",
    ),
    (
        "thresholds.h_min_bits",
        "cproper-verdict.json",
        ("thresholds", "h_min_bits"),
        "repr",
    ),
    (
        "thresholds.none_rate_max",
        "cproper-verdict.json",
        ("thresholds", "none_rate_max"),
        "repr",
    ),
    (
        "thresholds.power_min",
        "cproper-verdict.json",
        ("thresholds", "power_min"),
        "repr",
    ),
    ("thresholds.rho_min", "cproper-verdict.json", ("thresholds", "rho_min"), "repr"),
    ("thresholds.seed", "cproper-verdict.json", ("thresholds", "seed"), "int"),
    ("run.seed", "cproper-manifest.json", ("run", "seed"), "int"),
    ("run.k_contexts", "cproper-manifest.json", ("run", "k_contexts"), "int"),
    ("run.m_draws", "cproper-manifest.json", ("run", "m_draws"), "int"),
    (
        "env_pins.qwen3_model_digest",
        "cproper-manifest.json",
        ("env_pins", "qwen3_model_digest"),
        "str",
    ),
    (
        "env_pins.ollama_version",
        "cproper-manifest.json",
        ("env_pins", "ollama_version"),
        "str",
    ),
    ("d_loco", "es3-verdict-forensic.json", ("d_loco",), "repr"),
    ("ci_lower", "es3-verdict-forensic.json", ("ci_lower",), "repr"),
    ("ci_upper", "es3-verdict-forensic.json", ("ci_upper",), "repr"),
    ("amp_floor", "es3-verdict-forensic.json", ("amp_floor",), "two_dp"),
    (
        "zone_function_d_loco",
        "es3-verdict-forensic.json",
        ("zone_function_d_loco",),
        "repr",
    ),
    (
        "ablation_max_abs_diff",
        "es3-verdict-forensic.json",
        ("ablation_max_abs_diff",),
        "repr",
    ),
)

#: Mix-ups that must not appear -- the numeric counterpart of guard G10: the point estimate
#: carrying the positive control's value, or the other way round.
MISLABEL_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "the positive control's value written as the point estimate",
        "d_loco = 7.401486830834377e-17",
    ),
    (
        "the point estimate written as the positive control's value",
        "zone_function_d_loco = 0.04682681825722385",
    ),
)


def literal_of(value: Any, how: str) -> str:
    if how == "str":
        return str(value)
    if how == "int":
        return str(int(value))
    if how == "two_dp":
        # Quantities written as `0.10` rather than `0.1` (declared margins and floors).
        return f"{float(value):.2f}"
    if how in ("min", "max"):
        # The endpoints of a per-context map. The manuscript quotes the *range* of
        # ``per_context_h`` rather than eight separate values, and a range transcribed by hand is
        # exactly what `manuscript/CLAIM-BOUNDARY.md` section 4 says is covered by nothing. The
        # endpoint is taken from the map rather than from a named context, so the check stays
        # correct if the extremum ever sits somewhere else.
        return repr(min(value.values()) if how == "min" else max(value.values()))
    return repr(value)


#: Quantities the manuscript quotes that are **derived** rather than frozen: they are recomputed
#: from the shipped annotation by ``collapse_and_floor.py`` on every run, and read here from its
#: output. Keeping them checked matters more than for the frozen values, not less -- these are the
#: numbers the reframed claim rests on, and they exist nowhere in ``data/raw``.
DERIVED_REQUIRED: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("null_mean_tv_bar", "collapse-and-floor.json", ("null_mean_tv_bar",), "repr"),
    ("null_p95_tv_bar", "collapse-and-floor.json", ("null_p95_tv_bar",), "repr"),
    (
        "power_at_one_hundredth_of_margin",
        "collapse-and-floor.json",
        ("power_at_one_hundredth_of_margin",),
        "repr",
    ),
)


#: Quantities the manuscript quotes from the **landed prospective verdicts**. Until this table
#: existed they were covered by nothing: step 13 reads only the predicates of the rules it
#: reaches, so a number quoted in the results section could drift from the verdict it came from
#: without any step noticing. That gap was found in review rather than by a failing check, and
#: section I.5 of the manuscript states the part of it that remains.
#:
#: **Only literals distinctive enough for an occurrence test are listed.** ``rho_hat`` is `1.0`
#: in two of these files and `0.0` in the third, and a check that `'1.0' in text` passes on
#: prose that never mentions the quantity at all. Listing such a value here would add a line of
#: output and no coverage, and this repository has a name for that. Those quantities are guarded
#: instead by :func:`check_third_finding_support`, which compares the sources against each other
#: rather than against the prose.
PROSPECTIVE_REQUIRED: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("control.tv_bar", "control-verdict.json", ("tv_bar",), "repr"),
    (
        "control.permutation_p_value",
        "control-verdict.json",
        ("permutation_p_value",),
        "repr",
    ),
    (
        "control.none_rate_max_observed",
        "control-verdict.json",
        ("none_rate_max_observed",),
        "repr",
    ),
    (
        "primary.none_rate_max_observed",
        "primary-verdict.json",
        ("none_rate_max_observed",),
        "repr",
    ),
    ("primary.per_context_h min", "primary-verdict.json", ("per_context_h",), "min"),
    ("primary.per_context_h max", "primary-verdict.json", ("per_context_h",), "max"),
)


#: Quantities the manuscript quotes from the **deposit witness**. These would otherwise be
#: transcribed by hand, and `manuscript/CLAIM-BOUNDARY.md` section 4 says plainly that a
#: hand-transcribed number is covered by nothing -- so the honest options were to add this value
#: to that disclosure or to bring it under a check. It is mechanically available in a shipped
#: file, so it is checked.
#:
#: The anchor is the one number the manuscript quotes from outside this repository, which is
#: exactly why leaving it unchecked would be the wrong trade.
WITNESS_REQUIRED: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("witness.latest_server_time", ("latest_server_time",), "str"),
    ("witness.version_doi", ("version_doi",), "str"),
    ("witness.concept_doi", ("concept_doi",), "str"),
)


#: The subset of :data:`REQUIRED` that the README quotes in its "Key quantities" tables.
#: The README asserts that its values come from the extraction output and are enforced by
#: ``repro.sh``. Until this list existed that assertion was false: the check read only the
#: manuscript, so the README's numbers were covered by nothing.
README_QUANTITIES: frozenset[str] = frozenset(
    {
        "d_loco",
        "ci_lower",
        "amp_floor",
        "zone_function_d_loco",
        "ablation_max_abs_diff",
        "verdict",
        "tv_bar",
        "rho_hat",
        "power",
        "permutation_p_value",
        "thresholds.delta_tv_min",
    }
)


def check_reported_branch(repo_root: Path) -> list[str]:
    """Bind the branch the manuscript reports to the file step 13 compares against.

    Five states, and only one of them is uninteresting:

    * **nothing landed, nothing claimed** -- guarded absence, not a failure. The arms have not
      run. Freezing "this has not happened yet" into a check is how a check becomes false later,
      which is why this is a condition on files rather than on a date;
    * **both verdicts landed, no branch claimed** -- a failure. Step 13 would run, re-derive a
      branch, compare it with nothing, and exit 0. That is the hole this function closes;
    * **a branch claimed before both verdicts have landed** -- a failure, and a different one.
      §E of the protocol says the authors do not predict which branch will occur; a branch
      standing in the repository while the arms have not finished is that prediction, written
      down. Nothing can establish that the author did not see the evaluator's output before
      writing the marker, but this state is *observable*, so it is refused;
    * **a branch claimed, and the rendered file disagrees or is missing** -- a failure. The file
      is generated from the marker; a hand-edit is the drift the generation exists to prevent;
    * **a file with no marker behind it** -- a failure. It would be compared by step 13 while
      corresponding to nothing in the manuscript.
    """
    main_md = repo_root / "manuscript" / "main.md"
    out_path = repo_root / "manuscript" / "reported-branch.txt"
    raw_dir = repo_root / "data" / "raw"
    landed = sorted(
        name for name in PROSPECTIVE_OUTPUTS if (raw_dir / name).is_file()
    )
    # Non-emptiness is required as well as completeness: with an empty set of prospective
    # outputs the equality alone would hold vacuously, and every state below would read as
    # "the run has finished". The self-check exercises exactly that case.
    complete = bool(PROSPECTIVE_OUTPUTS) and len(landed) == len(PROSPECTIVE_OUTPUTS)

    try:
        branch_ids = sealed_branch_ids(repo_root)
        branch = find_marker(main_md.read_text(encoding="utf-8"), branch_ids)
    except MarkerError as exc:
        return [f"manuscript/main.md: {exc}"]

    problems: list[str] = []

    if (branch is not None or out_path.is_file()) and not complete:
        claimed = f"main.md reports branch {branch}" if branch else "reported-branch.txt exists"
        problems.append(
            f"{claimed}, but only {len(landed)} of {len(PROSPECTIVE_OUTPUTS)} prospective "
            "verdicts have landed in data/raw/. A branch standing in the repository before its "
            "inputs do is a prediction, and §E of the protocol says the authors do not predict "
            "which branch will occur. Land both verdicts first; "
            "manuscript/REPORTED-BRANCH.md gives the procedure"
        )

    if branch is None:
        if complete:
            problems.append(
                "the prospective verdicts have landed but manuscript/main.md carries no "
                "<!-- REPORTED-BRANCH: ... --> marker. Step 13 would re-derive a branch and "
                "compare it against nothing, and exit 0 having checked nothing. "
                "manuscript/REPORTED-BRANCH.md gives the procedure"
            )
        if out_path.is_file():
            problems.append(
                "manuscript/reported-branch.txt exists but no marker in main.md generates it. "
                "Step 13 would compare against a claim the manuscript does not make"
            )
        if not problems:
            print(
                "[numbers] -- the manuscript names no reported branch, and "
                f"{len(landed)} of {len(PROSPECTIVE_OUTPUTS)} prospective verdicts have "
                "landed, so step 13 has nothing to compare yet"
            )
        return problems

    expected = render(branch)
    if not out_path.is_file():
        problems.append(
            f"main.md reports branch {branch}, but manuscript/reported-branch.txt is missing. "
            "Step 13 reads that file; without it the comparison silently disappears. "
            "Generate it with analysis/scripts/render_reported_branch.py"
        )
    else:
        actual = out_path.read_text(encoding="utf-8")
        if actual != expected:
            problems.append(
                f"main.md reports branch {branch}, but manuscript/reported-branch.txt holds "
                f"{actual!r} rather than {expected!r}. That file is generated from the marker; "
                "regenerate it rather than editing it"
            )
        else:
            print(
                f"[numbers] OK reported branch{'':<17}= {branch}  "
                "(main.md marker, and the file step 13 reads, agree)"
            )

    if complete:
        problems.extend(check_hand_derivation(repo_root, branch))
    return problems


#: Rows of the record table in `manuscript/REPORTED-BRANCH.md` that carry decision content, as
#: opposed to the working it is shown in. Matched on the start of the label so the emphasis and
#: the code spans around it can be changed without silently disabling the check.
HAND_BRANCH_LABEL = "Branch reached by hand"
R2_SIDE_LABEL = "If the branch is R2"

#: Where the record lives, relative to the repository root.
RELATIVE_RECORD = Path("manuscript") / "REPORTED-BRANCH.md"

#: Markdown decoration stripped from a cell before it is read.
_CELL_DECORATION = "*` "

#: The rule whose identifier does not determine the outcome. See `REPORTED-BRANCH.md`.
AMBIGUOUS_BRANCH = "R2"


def table_cell(text: str, label: str) -> str | None:
    """The second cell of the row whose first cell starts with ``label``.

    ``None`` when there is no such row, which is different from an empty cell: one means the
    record has lost the field, the other that it has not been filled in, and the two get
    different messages.
    """
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip(_CELL_DECORATION).strip() for cell in line.split("|")]
        # cells[0] is the empty string before the leading pipe.
        if len(cells) >= 3 and cells[1].startswith(label):
            return cells[2]
    return None


def check_record_template(repo_root: Path) -> list[str]:
    """Check that the record still carries the rows the checks below read.

    Unconditional, and separate from :func:`check_hand_derivation`, because the failure it
    catches is invisible to the sweep. The self-check builds its fixtures from literals that
    match this module's labels, so a fixture and a checker that agree with each other will keep
    agreeing however the shipped template is worded. An independent review found exactly that:
    the labels here and the row in `REPORTED-BRANCH.md` had drifted apart, every fixture passed,
    and the drift would have surfaced only on the day the verdicts landed -- as a check that
    could never be satisfied.

    Checking the shipped file itself, on every run, is the only version of this that does not
    depend on a fixture agreeing with the thing it was copied from.
    """
    record = repo_root / RELATIVE_RECORD
    if not record.is_file():
        return [f"{RELATIVE_RECORD.as_posix()} is missing; it is where the branch is recorded"]
    text = record.read_text(encoding="utf-8")
    missing = [
        label
        for label in (HAND_BRANCH_LABEL, R2_SIDE_LABEL)
        if table_cell(text, label) is None
    ]
    if missing:
        return [
            f"{RELATIVE_RECORD.as_posix()} has no row whose label starts with {missing!r}. "
            "The checks that read the hand derivation would then have nothing to read, and "
            "would fail only once the verdicts had landed"
        ]
    print(
        f"[numbers] OK record template{'':<19}= both machine-read rows present in "
        f"{RELATIVE_RECORD.as_posix()}"
    )
    return []


def check_hand_derivation(repo_root: Path, branch: str) -> list[str]:
    """Require the double-entry record to have been filled in, and to agree.

    The branch is meant to be derived by hand from the two verdicts and the sealed rules, written
    down, and only then compared with the evaluator. Prose cannot enforce that. What can be
    enforced is that the record exists and names the same branch the manuscript does -- so a
    marker written without the derivation behind it fails, rather than passing quietly.

    **This does not establish that the derivation was done first**, or honestly, or at all; a
    single field can be filled in after the fact. It establishes that the claim appears in two
    places that were written separately and that they agree. `REPORTED-BRANCH.md` states that
    limit rather than leaving it to be found.

    The second row exists because the sealed evaluator returns the rule identifier, and ``R2``
    stops on both of its outcomes: satisfied is the non-replication finding, unsatisfied is the
    ``UNREACHABLE`` defect condition that must not be interpreted. ``--expect-branch R2`` cannot
    tell them apart and `apply_decision_rules.py` is sealed, so the disambiguation is required
    here, in writing.
    """
    record = repo_root / "manuscript" / "REPORTED-BRANCH.md"
    if not record.is_file():
        return [f"{record} is missing; it is where the hand derivation is recorded"]
    text = record.read_text(encoding="utf-8")

    recorded = table_cell(text, HAND_BRANCH_LABEL)
    if recorded is None:
        return [
            f"manuscript/REPORTED-BRANCH.md has no {HAND_BRANCH_LABEL!r} row, so the hand "
            "derivation cannot be compared with the branch main.md reports"
        ]
    if not recorded:
        return [
            f"main.md reports branch {branch}, but the 'Branch reached by hand' row of "
            "manuscript/REPORTED-BRANCH.md is empty. The branch is meant to be derived from the "
            "verdicts and the sealed rules and written down before step 13 compares it"
        ]
    if recorded != branch:
        return [
            f"main.md reports branch {branch}, but the hand derivation in "
            f"manuscript/REPORTED-BRANCH.md reached {recorded!r}. One of them is wrong, and "
            "which is not something a check can decide"
        ]

    problems: list[str] = []
    if branch == AMBIGUOUS_BRANCH:
        value = table_cell(text, R2_SIDE_LABEL) or ""
        if value not in {"true", "false"}:
            problems.append(
                f"the branch is {AMBIGUOUS_BRANCH}, which the sealed evaluator reports for both "
                "the non-replication finding and the UNREACHABLE defect condition. Evaluate "
                f"{AMBIGUOUS_BRANCH}'s own condition by hand from the landed verdicts and record "
                f"it as true or false in {RELATIVE_RECORD.as_posix()} (found {value!r}). Not from "
                "data/derived/decision-report.json: step 13 writes that after this check runs, "
                "so it holds either nothing or the previous run's answer"
            )
        else:
            meaning = "the non-replication finding" if value == "true" else "the UNREACHABLE defect"
            print(f"[numbers] OK R2 disambiguated{'':<15}= {value} ({meaning})")
    if not problems:
        print(
            f"[numbers] OK hand derivation{'':<18}= {recorded}  "
            "(REPORTED-BRANCH.md and the main.md marker agree)"
        )
    return problems


#: Fixture text for the self-check. Literals throughout: a fixture derived from the constants
#: under test follows them wherever they move, and reports success against anything.
_FIXTURE_RULES = '{"schema": "x", "rules": [{"id": "R1"}, {"id": "R2"}]}\n'
_FIXTURE_MAIN_NO_MARKER = "# fixture\n\nNo branch is named here.\n"
_FIXTURE_MAIN_R1 = "# fixture\n\n<!-- REPORTED-BRANCH: R1 -->\n\nThe results.\n"
_FIXTURE_MAIN_TWO = (
    "# fixture\n\n<!-- REPORTED-BRANCH: R1 -->\n\n<!-- REPORTED-BRANCH: R2 -->\n"
)
_FIXTURE_MAIN_UNKNOWN = "# fixture\n\n<!-- REPORTED-BRANCH: R9 -->\n"
_FIXTURE_MAIN_R2 = "# fixture\n\n<!-- REPORTED-BRANCH: R2 -->\n\nThe results.\n"
_FIXTURE_MAIN_IN_GENERATED = (
    "# fixture\n\n"
    "<!-- BEGIN GENERATED FROM seal/decision-rules.json -- DO NOT EDIT BY HAND -->\n"
    "<!-- REPORTED-BRANCH: R1 -->\n"
    "<!-- END GENERATED FROM seal/decision-rules.json -->\n"
)

#: Record fixtures. Written out per branch rather than formatted from the case's own branch: a
#: record generated from the value it is supposed to corroborate would agree with anything.
#:
#: The row wording mirrors the shipped template. Matching is by label prefix, so a fixture left
#: at an older wording would keep passing while quietly documenting a procedure that had been
#: replaced -- which is how the label drift an independent review found got in. Wording drift
#: between these and the shipped file is caught by :func:`check_record_template`, which reads the
#: shipped file rather than anything here.
_FIXTURE_RECORD_R1 = "| **Branch reached by hand** | R1 |\n"
_FIXTURE_RECORD_R2_TRUE = (
    "| **Branch reached by hand** | R2 |\n"
    "| **If the branch is R2, its condition evaluated by hand** | true |\n"
)
_FIXTURE_RECORD_R2_BLANK = (
    "| **Branch reached by hand** | R2 |\n"
    "| **If the branch is R2, its condition evaluated by hand** |  |\n"
)
_FIXTURE_RECORD_EMPTY = "| **Branch reached by hand** |  |\n"


def _branch_fixture(
    root: Path,
    *,
    main_md: str,
    branch_file: str | None,
    landed: tuple[str, ...],
    record: str,
) -> Path:
    """Build a throwaway repository in the shape this check reads."""
    (root / "manuscript").mkdir(parents=True, exist_ok=True)
    (root / "seal").mkdir(parents=True, exist_ok=True)
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (root / "manuscript" / "main.md").write_text(main_md, encoding="utf-8", newline="\n")
    (root / "manuscript" / "REPORTED-BRANCH.md").write_text(
        record, encoding="utf-8", newline="\n"
    )
    (root / "seal" / "decision-rules.json").write_text(
        _FIXTURE_RULES, encoding="utf-8", newline="\n"
    )
    if branch_file is not None:
        (root / "manuscript" / "reported-branch.txt").write_text(
            branch_file, encoding="utf-8", newline="\n"
        )
    for name in landed:
        (root / "data" / "raw" / name).write_text('{"fixture": true}\n', encoding="utf-8")
    return root


def check_branch_guards_fire() -> list[str]:
    """Measure what :func:`check_reported_branch` actually catches, on every run.

    ``repro.sh`` is sealed, so a sweep cannot be added as a step, and this repository has no test
    suite; the reviewer's one command is where it has to run. ``check_claim_boundary.py`` carries
    its positive control the same way. Output from the cases is swallowed so that a fixture's
    ``OK`` line can never be read as a statement about this repository.
    """
    both = tuple(sorted(PROSPECTIVE_OUTPUTS))
    one = both[:1]
    # label, main.md, reported-branch.txt, landed verdicts, record, expected text (None = clean)
    cases: tuple[
        tuple[str, str, str | None, tuple[str, ...], str, str | None], ...
    ] = (
        (
            "P1 nothing landed, nothing claimed",
            _FIXTURE_MAIN_NO_MARKER,
            None,
            (),
            _FIXTURE_RECORD_EMPTY,
            None,
        ),
        (
            "P2 R1 claimed, rendered and recorded",
            _FIXTURE_MAIN_R1,
            "R1\n",
            both,
            _FIXTURE_RECORD_R1,
            None,
        ),
        # The R2 pair is what keeps the renderer honest. With only the R1 control above, a
        # render() that returned "R1\n" for every branch would pass every case.
        (
            "P3 R2 claimed, rendered, recorded and disambiguated",
            _FIXTURE_MAIN_R2,
            "R2\n",
            both,
            _FIXTURE_RECORD_R2_TRUE,
            None,
        ),
        (
            "M1 verdicts landed, no marker",
            _FIXTURE_MAIN_NO_MARKER,
            None,
            both,
            _FIXTURE_RECORD_EMPTY,
            "carries no <!-- REPORTED-BRANCH",
        ),
        (
            "M2 rendered file disagrees with the marker",
            _FIXTURE_MAIN_R1,
            "R2\n",
            both,
            _FIXTURE_RECORD_R1,
            "rather than",
        ),
        (
            "M3 R2 marker rendered as R1",
            _FIXTURE_MAIN_R2,
            "R1\n",
            both,
            _FIXTURE_RECORD_R2_TRUE,
            "rather than",
        ),
        (
            "M4 marker but no rendered file",
            _FIXTURE_MAIN_R1,
            None,
            both,
            _FIXTURE_RECORD_R1,
            "is missing",
        ),
        (
            "M5 rendered file with no marker behind it",
            _FIXTURE_MAIN_NO_MARKER,
            "R1\n",
            both,
            _FIXTURE_RECORD_EMPTY,
            "no marker in main.md generates it",
        ),
        (
            "M6 two markers",
            _FIXTURE_MAIN_TWO,
            "R1\n",
            both,
            _FIXTURE_RECORD_R1,
            "markers",
        ),
        (
            "M7 marker inside the generated block",
            _FIXTURE_MAIN_IN_GENERATED,
            "R1\n",
            both,
            _FIXTURE_RECORD_R1,
            "inside the block generated",
        ),
        (
            "M8 branch the sealed rules cannot reach",
            _FIXTURE_MAIN_UNKNOWN,
            "R9\n",
            both,
            _FIXTURE_RECORD_R1,
            "not one the sealed rules can reach",
        ),
        (
            "M9 trailing text makes the file a different token",
            _FIXTURE_MAIN_R1,
            "R1 # because the control arm held\n",
            both,
            _FIXTURE_RECORD_R1,
            "rather than",
        ),
        # The prediction states: a branch standing in the repository before its inputs.
        (
            "M10 branch claimed with nothing landed",
            _FIXTURE_MAIN_R1,
            "R1\n",
            (),
            _FIXTURE_RECORD_R1,
            "is a prediction",
        ),
        (
            "M11 branch claimed with one arm landed",
            _FIXTURE_MAIN_R1,
            "R1\n",
            one,
            _FIXTURE_RECORD_R1,
            "is a prediction",
        ),
        # The double-entry record.
        (
            "M12 hand derivation not filled in",
            _FIXTURE_MAIN_R1,
            "R1\n",
            both,
            _FIXTURE_RECORD_EMPTY,
            "is empty",
        ),
        (
            "M13 hand derivation reached a different branch",
            _FIXTURE_MAIN_R2,
            "R2\n",
            both,
            _FIXTURE_RECORD_R1,
            "reached 'R1'",
        ),
        (
            "M14 R2 reported without saying which R2",
            _FIXTURE_MAIN_R2,
            "R2\n",
            both,
            _FIXTURE_RECORD_R2_BLANK,
            "UNREACHABLE defect condition",
        ),
    )

    problems: list[str] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for label, main_md, branch_file, landed, record, expect in cases:
            with tempfile.TemporaryDirectory() as tmp:
                root = _branch_fixture(
                    Path(tmp) / "repo",
                    main_md=main_md,
                    branch_file=branch_file,
                    landed=landed,
                    record=record,
                )
                reported = check_reported_branch(root)
            joined = " | ".join(reported)
            if expect is None:
                if reported:
                    problems.append(
                        f"self-check {label}: expected to report nothing, got {reported!r}"
                    )
            elif not reported:
                problems.append(f"self-check {label}: expected to report a problem, got none")
            elif expect not in joined:
                problems.append(
                    f"self-check {label}: fired, but not for the expected reason "
                    f"(wanted text containing {expect!r}, got {joined!r})"
                )

    if not problems:
        mutations = sum(1 for case in cases if case[5] is not None)
        controls = len(cases) - mutations
        print(
            f"[numbers] OK self-check: {mutations} mutations caught, {controls} controls clean "
            "(the reported branch cannot go unstated, unrendered, predicted ahead of its "
            "inputs, or out of step with main.md and the hand derivation)"
        )
    return problems


#: The ops R4 uses. Kept to exactly those, so a rule edited to use an op this function does not
#: know is reported instead of being silently read as "not satisfied".
_PREDICATE_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "lt": lambda observed, value: observed < value,
    "gt": lambda observed, value: observed > value,
}


class PredicateError(Exception):
    """A sealed predicate this check cannot evaluate. Reported, never treated as a false."""


def _r4_satisfied(rule: dict[str, Any], verdict: dict[str, Any]) -> tuple[bool, list[str]]:
    """Evaluate R4's sealed predicates against one verdict, returning (satisfied, rendering)."""
    results: list[str] = []
    satisfied = False
    for predicate in rule["predicates"]:
        quantity = predicate["quantity"]
        op = predicate["op"]
        if op not in _PREDICATE_OPS:
            raise PredicateError(f"R4 uses an op this check does not know: {op!r}")
        observed = verdict[quantity]  # Raising on a missing key is correct; no default
        fired = bool(_PREDICATE_OPS[op](observed, predicate["value"]))
        satisfied = satisfied or fired
        results.append(f"{quantity} = {observed!r} {op} {predicate['value']!r} -> {fired}")
    return satisfied, results


def _rho_hat_identity(verdict: dict[str, Any]) -> tuple[int, float]:
    """Recompute `effective_k` and `rho_hat` from the per-context entropies and the floor.

    Neither quantity survives an occurrence test -- their literals are ``8``, ``0`` and ``1.0``.
    Recomputing them from the map they summarise is what puts the sentences that quote them
    ("every context clears that floor", "`effective_k` = 0 of 8") under a check at all.
    """
    per_context = verdict["per_context_h"]
    floor = verdict["thresholds"]["h_min_bits"]
    effective_k = sum(1 for value in per_context.values() if value >= floor)
    return effective_k, effective_k / len(per_context)


def check_third_finding_support(repo_root: Path) -> list[str]:
    """Compute the counterfactual the results section states, rather than asserting it.

    The manuscript reports that at the thresholds fixed in section C.4 the measurability gate
    does not flag the regime the paper is about: applied to the completed run and to the control
    arm, **neither** of R4's two conditions is met, while the base distribution the power
    calculation uses is missing zones. That is a claim about how three shipped records stand to
    the sealed rule, so it is checkable, and leaving it to the prose would put the paper's newest
    claim in the class `manuscript/CLAIM-BOUNDARY.md` section 4 calls covered by nothing.

    Three things are compared, because the sentence has three parts. R4's sealed predicates are
    evaluated against each record. Each record's ``effective_k`` and ``rho_hat`` are recomputed
    from its own per-context entropies against its own floor, which is what holds "every context
    clears that floor" and "effective_k = 0 of 8" -- neither survives an occurrence test, since
    their literals are ``1.0``, ``0.0`` and ``8`` and ``'1.0' in text`` is true of almost any page
    here. And the zero-probability zones must be **named** in the manuscript, because ``agora``
    and ``chashitsu`` are distinctive where "two of five" is not.

    The predicates come from `seal/decision-rules.json` rather than being restated here -- the
    same reason the rule *text* in the protocol is generated from the seal instead of written
    beside it -- and the self-check below mutates the seal to confirm that they really do.

    Absence of the prospective verdicts is not a failure: before the arms run there is nothing to
    compare, and a check that demanded them would freeze "the run has happened" into a step that
    ran before it had.
    """
    raw_dir = repo_root / "data" / "raw"
    rules_path = repo_root / "seal" / "decision-rules.json"
    derived_path = repo_root / "data" / "derived" / "collapse-and-floor.json"
    text = (repo_root / "manuscript" / "main.md").read_text(encoding="utf-8")

    landed = sorted(name for name in PROSPECTIVE_OUTPUTS if (raw_dir / name).is_file())
    if len(landed) != len(PROSPECTIVE_OUTPUTS) or not PROSPECTIVE_OUTPUTS:
        print(
            "[numbers] -- the prospective verdicts have not all landed, so the counterfactual "
            "reading of R4 is not compared"
        )
        return []
    if not derived_path.is_file():
        return [
            f"{derived_path} is missing; collapse_and_floor.py runs before this step in repro.sh"
        ]

    rules = load_json(rules_path)
    matching = [rule for rule in rules["rules"] if rule["id"] == "R4"]
    if len(matching) != 1:
        return [f"seal/decision-rules.json holds {len(matching)} rules with id R4; expected one"]
    r4 = matching[0]
    if r4["combine"] != "any":
        return [
            f"R4 combines its predicates with {r4['combine']!r}, not 'any'. The counterfactual "
            "below is written for a rule that fires when either condition holds"
        ]

    problems: list[str] = []

    # The two records the manuscript says the gate does not reach, and the one it does.
    expectations = (
        ("the completed run", "cproper-verdict.json", False),
        ("the control arm", "control-verdict.json", False),
        ("the primary arm", "primary-verdict.json", True),
    )
    # (label, file, does R4 fire, the k the manuscript quotes out of eight)
    expectations = (
        ("the completed run", "cproper-verdict.json", False, 8),
        ("the control arm", "control-verdict.json", False, 8),
        ("the primary arm", "primary-verdict.json", True, 0),
    )
    for label, filename, should_fire, stated_k in expectations:
        verdict = load_json(raw_dir / filename)
        try:
            satisfied, rendering = _r4_satisfied(r4, verdict)
        except PredicateError as exc:
            problems.append(f"{label} ({filename}): {exc}")
            continue
        if satisfied != should_fire:
            wanted = "satisfied" if should_fire else "not satisfied"
            problems.append(
                f"R4's sealed predicates are {'satisfied' if satisfied else 'not satisfied'} by "
                f"{label} ({filename}), but the results section reads them as {wanted}: "
                + "; ".join(rendering)
            )
        # The recorded summary must be the one its own per-context map produces. This is what
        # holds the sentences an occurrence test cannot -- "every context clears that floor" and
        # "`effective_k` = 0 of 8" -- and it is also what keeps `rho_hat` from drifting anywhere
        # inside the side of the threshold it sits on.
        recomputed_k, recomputed_rho = _rho_hat_identity(verdict)
        if recomputed_k != verdict["effective_k"] or recomputed_rho != verdict["rho_hat"]:
            problems.append(
                f"{label} ({filename}) records effective_k = {verdict['effective_k']!r} and "
                f"rho_hat = {verdict['rho_hat']!r}, but its own per-context entropies against "
                f"its own h_min_bits give {recomputed_k} and {recomputed_rho!r}"
            )
        elif recomputed_k != stated_k:
            problems.append(
                f"{label} ({filename}) admits {recomputed_k} of "
                f"{len(verdict['per_context_h'])} contexts, but the results section reads it as "
                f"{stated_k}"
            )

    # The other half of the sentence: the base the power calculation uses is missing zones. The
    # count is taken from the derived artefact, which computes it over the channel-off condition
    # -- the base of that calculation, and not the whole run.
    derived = load_json(derived_path)
    zero_count = derived["zero_support_count"]
    named = derived["zero_support_zones"]
    if zero_count != len(named):
        problems.append(
            f"data/derived/collapse-and-floor.json counts {zero_count} zero-probability zone(s) "
            f"in the channel-off base but names {len(named)}: {named}"
        )
    elif zero_count != 2:
        # Not a range check. The manuscript writes "two of the five zones" in several places, and
        # a count that moved would leave those sentences standing while this step still passed.
        problems.append(
            f"the channel-off base has {zero_count} zone(s) of probability zero, but the "
            "manuscript reads it as two"
        )
    else:
        # The names are distinctive enough for an occurrence test, which "two of five" is not.
        missing = [zone for zone in named if zone not in text]
        if missing:
            problems.append(
                f"the channel-off base never produces {named}, but main.md does not name "
                f"{missing}"
            )

    if not problems:
        print(
            "[numbers] OK counterfactual        = R4's sealed predicates are not satisfied by the "
            "completed run or the control arm, are satisfied by the primary arm, each arm's "
            f"effective_k and rho_hat follow from its own per-context entropies, and the "
            f"{zero_count} zone(s) of probability zero in the channel-off base are named in "
            "main.md"
        )
    return problems


class _NoOpMutation(Exception):
    """A mutation that did not change what it named. Counting one as caught would be a lie."""


def _mutate(payload: dict[str, Any], key: str, value: Any) -> Any:
    """Apply one mutation to a fixture payload, returning what stood there before.

    Three shapes are needed and each is spelled out rather than inferred, so that a path which
    silently matches nothing raises instead of leaving the fixture unmutated:

    * ``"field"`` and ``"thresholds.h_min_bits"`` -- a key, or a key inside a nested dictionary;
    * ``"R4.predicates.0.value"`` -- a field of a rule found by id, not by position;
    * ``"R4.combine"`` and ``"R4.duplicate"`` -- a rule's combinator, and a second copy of it.
    """
    if key.startswith("R4."):
        rules = payload["rules"]
        index = next(i for i, rule in enumerate(rules) if rule["id"] == "R4")
        rest = key[len("R4.") :]
        if rest == "duplicate":
            rules.insert(index + 1, json.loads(json.dumps(rules[index])))
            return None
        if rest == "combine":
            before = rules[index]["combine"]
            rules[index]["combine"] = value
            return before
        _, position, field = rest.split(".")
        predicate = rules[index]["predicates"][int(position)]
        before = predicate[field]
        predicate[field] = value
        return before
    node: Any = payload
    parts = key.split(".")
    for part in parts[:-1]:
        if part not in node:
            raise _NoOpMutation(f"the path {key!r} matches nothing in this fixture")
        node = node[part]
    if parts[-1] not in node:
        raise _NoOpMutation(f"the path {key!r} matches nothing in this fixture")
    before = node[parts[-1]]
    node[parts[-1]] = value
    return before


def check_third_finding_guards_fire(repo_root: Path) -> list[str]:
    """Break each half of :func:`check_third_finding_support` and require it to notice.

    Written against **copies of the real records**, not against invented ones: a fixture built
    from the checker's own constants can only confirm that the constants were applied. Every
    mutation moves one value across the threshold the sealed rule names, and the unmutated copy
    is carried as a positive control so that "nothing fired" is not the only observation.

    Two properties are exercised that an earlier version left to the reader. The **sealed rule
    itself** is mutated (M7-M9), because the docstring above claims the predicates come from the
    seal, and a suite that only ever rewrites verdicts cannot tell that claim from a
    reimplementation. And each expectation names the **rendering** the report should carry, not
    just the record it concerns, so a mutation that fires for the wrong reason is not counted as
    caught.
    """
    # `bool(...)` first, for the reason check_reported_branch gives: an empty set of prospective
    # outputs would make the `all` vacuously true and every mutation below run against nothing.
    if not PROSPECTIVE_OUTPUTS or not all(
        (repo_root / "data" / "raw" / name).is_file() for name in PROSPECTIVE_OUTPUTS
    ):
        print(
            "[numbers] -- the prospective verdicts have not all landed, so the counterfactual "
            "self-check has nothing to mutate"
        )
        return []

    # (label, file to rewrite, key, new value, text the report must contain; None = control)
    cases: tuple[tuple[str, str | None, str | None, Any, str | None], ...] = (
        ("C1 the records unaltered", None, None, None, None),
        (
            "M1 the completed run crosses the rho_hat condition",
            "cproper-verdict.json",
            "rho_hat",
            0.25,
            "rho_hat = 0.25 lt 0.5 -> True",
        ),
        (
            "M2 the completed run crosses the none-rate condition",
            "cproper-verdict.json",
            "none_rate_max_observed",
            0.75,
            "none_rate_max_observed = 0.75 gt 0.5 -> True",
        ),
        (
            "M3 the control arm crosses the rho_hat condition",
            "control-verdict.json",
            "rho_hat",
            0.25,
            "rho_hat = 0.25 lt 0.5 -> True",
        ),
        (
            "M4 the control arm crosses the none-rate condition",
            "control-verdict.json",
            "none_rate_max_observed",
            0.75,
            "none_rate_max_observed = 0.75 gt 0.5 -> True",
        ),
        (
            "M5 the primary arm stops crossing either condition",
            "primary-verdict.json",
            "rho_hat",
            1.0,
            "the primary arm",
        ),
        (
            "M6 the channel-off base loses an empty zone",
            "collapse-and-floor.json",
            "zero_support_count",
            1,
            "counts 1 zero-probability zone(s) in the channel-off base but names 2",
        ),
        # The sealed rule. Without these three the claim that the predicates are read from the
        # seal is untested: an implementation that hard-coded 0.5 would pass M1-M6 unchanged.
        (
            "M7 the sealed rho_hat threshold moves past the recorded value",
            "decision-rules.json",
            "R4.predicates.0.value",
            1.5,
            "rho_hat = 1.0 lt 1.5 -> True",
        ),
        (
            "M8 the sealed rule combines its predicates with all",
            "decision-rules.json",
            "R4.combine",
            "all",
            "not 'any'",
        ),
        (
            "M9 the seal carries two rules with id R4",
            "decision-rules.json",
            "R4.duplicate",
            True,
            "2 rules with id R4",
        ),
        # The summaries an occurrence test cannot hold.
        (
            "M10 the primary arm's effective_k stops following from its entropies",
            "primary-verdict.json",
            "effective_k",
            5,
            "records effective_k = 5",
        ),
        (
            "M11 the completed run's entropy floor admits only three contexts",
            "cproper-verdict.json",
            "thresholds.h_min_bits",
            0.68,
            "give 3 and 0.375",
        ),
        (
            "M12 a zone of probability zero goes unnamed in the manuscript",
            "collapse-and-floor.json",
            "zero_support_zones",
            ["agora", "vestibule"],
            "does not name ['vestibule']",
        ),
    )

    problems: list[str] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for label, filename, key, value, expect in cases:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "repo"
                (root / "data" / "raw").mkdir(parents=True)
                (root / "data" / "derived").mkdir(parents=True)
                (root / "seal").mkdir(parents=True)
                (root / "manuscript").mkdir(parents=True)
                shutil.copy2(
                    repo_root / "manuscript" / "main.md", root / "manuscript" / "main.md"
                )
                payloads = {
                    name: load_json(repo_root / "data" / "raw" / name)
                    for name in ("cproper-verdict.json", *sorted(PROSPECTIVE_OUTPUTS))
                }
                payloads["collapse-and-floor.json"] = load_json(
                    repo_root / "data" / "derived" / "collapse-and-floor.json"
                )
                payloads["decision-rules.json"] = load_json(
                    repo_root / "seal" / "decision-rules.json"
                )
                if filename is not None and key is not None:
                    try:
                        before = _mutate(payloads[filename], key, value)
                    except _NoOpMutation as exc:
                        problems.append(f"self-check {label}: {exc}")
                        continue
                    if before == value:
                        problems.append(
                            f"self-check {label}: the mutation is a no-op -- {key} already "
                            f"holds {value!r} in {filename}"
                        )
                        continue
                for name, payload in payloads.items():
                    if name == "decision-rules.json":
                        target = root / "seal" / name
                    elif name == "collapse-and-floor.json":
                        target = root / "data" / "derived" / name
                    else:
                        target = root / "data" / "raw" / name
                    target.write_text(json.dumps(payload), encoding="utf-8")
                reported = check_third_finding_support(root)
            joined = " | ".join(reported)
            if expect is None:
                if reported:
                    problems.append(
                        f"self-check {label}: expected to report nothing, got {reported!r}"
                    )
            elif not reported:
                problems.append(f"self-check {label}: expected to report a problem, got none")
            elif expect not in joined:
                problems.append(
                    f"self-check {label}: fired, but not for the expected reason "
                    f"(wanted text containing {expect!r}, got {joined!r})"
                )

    if not problems:
        mutations = sum(1 for case in cases if case[4] is not None)
        controls = len(cases) - mutations
        print(
            f"[numbers] OK self-check: {mutations} mutations caught, {controls} control clean "
            "(neither half of the counterfactual reading of R4 can drift from the records "
            "without this step saying so)"
        )
    return problems


#: Number words the manuscript uses in place of small integers. A literal table rather than a library
#: call, so that the rendering is visible in the checker and cannot drift with a dependency.
_NUMBER_WORDS: tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty",
)  # fmt: skip

#: The five zones, in the order the apparatus uses.
_ZONES: tuple[str, ...] = ("agora", "chashitsu", "garden", "peripatos", "study")

#: Where the rendered comparison reads its sources, relative to the repository root.
RENDER_SOURCES: tuple[str, ...] = (
    "manuscript/main.md",
    "data/derived/collapse-and-floor.json",
    "data/derived/power-curve.md",
    "data/raw/bank_annotation.jsonl",
    "data/prospective/control/run_annotation.jsonl",
    "data/prospective/primary/run_annotation.jsonl",
    "data/raw/cproper-verdict.json",
    "data/raw/control-verdict.json",
    "data/raw/primary-verdict.json",
    "analysis/heldout-stay/result.json",
    "analysis/heldout-stay/freeze.json",
    "data/attempts/control/attempts.jsonl",
    "data/attempts/control/run_records.partial.attempt1-interrupted.jsonl",
    "data/attempts/primary/attempts.jsonl",
    "data/posthoc/pipeline-summary.json",
    "data/posthoc/side-analyses.json",
    "data/posthoc/pipeline-replicates.tsv",
    "data/posthoc/manifest.json",
    "analysis/autopsy/DEVIATIONS.md",
)

#: Labels of the post hoc simulation's bases (B3), as the manuscript's tables write them.
_POSTHOC_BASE_LABELS: tuple[tuple[str, str], ...] = (
    ("C", "completed run, channel-off per context"),
    ("K", "control arm, channel-off per context"),
    ("Cs", "completed run, its two empty zones filled"),
    ("U", "near-uniform"),
    ("G", "degenerate"),
)
_POSTHOC_SEEDVAR = ("C|null|0|seedvar", "completed run, scorer seed varied per replicate")
_POSTHOC_NOT_REACHED = "not reached in the declared grid"

#: Labels the manuscript's tables use. Literals, and checked as part of the rendered row: a label
#: that drifted from the table would fail here rather than silently match nothing.
_RUN_LABELS: tuple[tuple[str, str, str], ...] = (
    ("completed run (`qwen3:8b`)", "data/raw/bank_annotation.jsonl", "cproper-verdict.json"),
    ("control arm (`qwen3:8b`)", "data/prospective/control/run_annotation.jsonl", "control-verdict.json"),
    ("primary arm (`llama3.1:8b`)", "data/prospective/primary/run_annotation.jsonl", "primary-verdict.json"),
)  # fmt: skip
_READ_LABELS: tuple[tuple[str, str], ...] = (
    ("completed run", "cproper-verdict.json"),
    ("control arm", "control-verdict.json"),
    ("primary arm", "primary-verdict.json"),
)
_ARM_LABELS: tuple[tuple[str, str], ...] = (
    ("control", "control (`qwen3:8b`)"),
    ("primary", "primary (`llama3.1:8b`)"),
)
_CLASS_LABELS: tuple[tuple[str, str], ...] = (
    ("N_str", 'the string `"null"`'),
    ("N_json", "a JSON `null`"),
    ("K", "no `destination_zone` key"),
    ("Z", "a valid zone name, with the plan rejected on another field"),
    ("S", "some other value"),
    ("F", "no usable JSON object"),
)
_BASE_LABELS: dict[str, str] = {
    "[0.2, 0.2, 0.2, 0.2, 0.2]": "near-uniform",
    "[0.96, 0.01, 0.01, 0.01, 0.01]": "degenerate",
}


def _word(n: int) -> str:
    """The English word for a small count, as the manuscript writes it."""
    if not 0 <= n < len(_NUMBER_WORDS):
        raise ValueError(f"no number word for {n}")
    return _NUMBER_WORDS[n]


def _attempt_events(path: Path) -> collections.Counter[str]:
    """How many of each event an append-only attempt log records."""
    return collections.Counter(
        json.loads(line)["event"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _captures_complete(path: Path) -> list[str]:
    """Require every capture event to be of the full sealed size, so "completed capture" is earned."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    starts = [row for row in rows if row["event"] == "start"]
    # M draws per condition, two conditions (channel on, channel off), K contexts.
    expected = {row["requested_k_contexts"] * row["requested_m_draws"] * 2 for row in starts}
    problems: list[str] = []
    for row in rows:
        if row["event"] != "captured":
            continue
        if expected != {row["llm_calls"]} or row["sub_sealed_scale"] is not False:
            problems.append(
                f"{path.parent.name} attempt log: a capture of {row['llm_calls']} calls "
                f"(sub_sealed_scale={row['sub_sealed_scale']!r}) against requested {sorted(expected)}"
            )
    return problems


def _stopped_partial(path: Path) -> tuple[int, int, list[str]]:
    """Count a stopped attempt's partial record: (complete lines, trailing bytes, problems).

    A complete line is one ending in a newline that parses as a JSON object. The count is taken
    from the bytes, never written by hand: it was once misread as 40 by counting the unterminated
    trailing fragment as a line and subtracting one (upstream DA-B1-1). The trailing fragment is
    required to be NUL bytes only, and the complete lines to carry call indices 1..n in order, so
    that a different shape is reported rather than counted.
    """
    data = path.read_bytes()
    body, _, tail = data.rpartition(b"\n")
    problems: list[str] = []
    indices: list[int] = []
    for number, line in enumerate(body.split(b"\n") if body else [], start=1):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            problems.append(f"{path.name}: line {number} is not JSON")
            continue
        indices.append(row.get("call_index") if isinstance(row, dict) else None)
    if tail.strip(b"\x00"):
        problems.append(f"{path.name}: the unterminated tail is not NUL bytes only")
    if indices != list(range(1, len(indices) + 1)):
        problems.append(f"{path.name}: call indices are not 1..{len(indices)} in order")
    return len(indices), len(tail), problems


def _annotation_summary(path: Path) -> dict[str, Any]:
    """Counts the prose quotes from a per-draw annotation: None by condition, support, cell sizes."""
    none: collections.Counter[str] = collections.Counter()
    totals: collections.Counter[str] = collections.Counter()
    pooled: dict[str, collections.Counter[str]] = {
        "on": collections.Counter(),
        "off": collections.Counter(),
    }
    cells: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    per_context: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        zone, condition, context = (
            row["pre_bias_destination_zone"],
            row["condition"],
            row["frozen_ctx_id"],
        )
        totals[condition] += 1
        if zone is None:
            none[condition] += 1
            per_context[context][condition] += 1
            continue
        pooled[condition][zone] += 1
        cells[(context, condition)].add(zone)
    sizes = [len(zones) for zones in cells.values()]
    return {
        "none": none,
        "totals": totals,
        "pooled": pooled,
        "cells": len(cells),
        "cell_min": min(sizes),
        "cell_max": max(sizes),
        "contexts": len({context for context, _ in cells}),
        "contexts_on_gt_off": sum(1 for c in per_context.values() if c["on"] > c["off"]),
    }


def _posthoc_rate(r: dict[str, Any]) -> str:
    return f"{r['k']}/{r['n']} = `{r['rate']!r}` [{r['wilson_low']!r}, {r['wilson_high']!r}]"


def posthoc_fragments(root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Rows and phrases of section 4.3 (B3) and of the sentences elsewhere that quote it.

    Rendered from ``data/posthoc/``. The summary is itself generated from the per-replicate record
    by ``analysis/autopsy/render.py``, and the manifest pins the digests of both; a summary edited
    by hand fails the digest comparison here before any of its numbers is looked at. The autopsy
    workflows tie the record to a recomputation of the declared grid. Statements the text makes in
    words rather than numbers are checked as problems against the same sources.
    """
    import hashlib  # noqa: PLC0415

    fragments: list[tuple[str, str]] = []
    problems: list[str] = []
    posthoc = root / "data" / "posthoc"
    manifest = load_json(posthoc / "manifest.json")
    for name, digest in manifest["outputs_sha256"].items():
        actual = hashlib.sha256((posthoc / name).read_bytes()).hexdigest()
        if actual != digest:
            problems.append(f"data/posthoc/{name} does not match the digest in its manifest")
    summary = load_json(posthoc / "pipeline-summary.json")
    side = load_json(posthoc / "side-analyses.json")
    cells = {c["id"]: c for c in summary["cells"]}
    rules = summary["reading_rules"]

    def stats(cell_id: str) -> dict[str, Any]:
        return cells[cell_id]["summary"]

    # Internal consistency the prose relies on: R2's split adds up, and nothing ended at R3 or in
    # an evaluator exit anywhere in the grid (the text says so).
    for cell in summary["cells"]:
        s = cell.get("summary")
        if not s or cell.get("alias_of"):
            continue
        split = s["r2_split"]
        if "branch_counts" in s:
            if split["reject_only"] + split["tv_bar_only"] + split["both"] != s["branch_counts"]["R2"]:
                problems.append(f"{cell['id']}: R2's split does not add up to its R2 count")
            if s["branch_counts"]["R3"] or s["branch_counts"]["die"] or s["branch_counts"]["none"]:
                problems.append(
                    f"R3/die phrase: {cell['id']} has replicates at R3 or an evaluator exit, "
                    "which the manuscript says never happened"
                )

    # Type-I, per base, both quantities, with the declared label.
    for base, label in _POSTHOC_BASE_LABELS:
        r2, test = rules["type_i"]["r2"][base], rules["type_i"]["test_reject"][base]
        fragments.append(
            (
                f"Type-I row, {label}",
                f"| {label} | {_posthoc_rate(r2)}, {r2['label']} | "
                f"{_posthoc_rate(test)}, {test['label']} |",
            )
        )
    sv = rules["type_i_with_per_replicate_scorer_seed"]
    fragments.append(
        (
            "Type-I row, scorer seed varied",
            f"| {_POSTHOC_SEEDVAR[1]} | {_posthoc_rate(sv['r2'])}, {sv['r2']['label']} | "
            f"{_posthoc_rate(sv['test_reject'])}, {sv['test_reject']['label']} |",
        )
    )
    gb = stats("G|null|0")["branch_counts"]
    fragments.append(
        (
            "degenerate-base null branch counts",
            f"On the degenerate base the branch counts under the null are R4 {gb['R4']:,}, "
            f"R3 {gb['R3']}, R1 {gb['R1']}, R2 {gb['R2']}",
        )
    )

    # The number of scorer calls: one line of the per-replicate record per call.
    record_lines = (posthoc / "pipeline-replicates.tsv").read_text(encoding="utf-8").count("\n") - 1
    fragments.append(("scorer-call count", f"The grid comes to {record_lines:,} scorer calls"))

    # The deviation ledger's entries.
    ledger = (root / "analysis" / "autopsy" / "DEVIATIONS.md").read_text(encoding="utf-8")
    entries = ledger.count("\n## DV-")
    fragments.append(("deviation count", f"That file holds {_word(entries)} entries"))

    # The registered delta on the completed run's base: one phrase, which holds only if every
    # feasible direction gives the same counts.
    registered = rules["registered_delta_on_C"]
    feasible = [r for r in registered if r["status"] == "run"]
    infeasible = [r["direction"] for r in registered if r["status"] != "run"]
    r2_counts = {(r["r2"]["k"], r["r2"]["n"]) for r in feasible}
    test_counts = {(r["test_reject"]["k"], r["test_reject"]["n"]) for r in feasible}
    if len(r2_counts) != 1 or len(test_counts) != 1:
        problems.append(
            "registered delta_tv phrase: the manuscript states one count for every feasible "
            f"direction, but the directions differ: {sorted(r2_counts)} / {sorted(test_counts)}"
        )
    else:
        (k2, n2), (kt, nt) = next(iter(r2_counts)), next(iter(test_counts))
        fragments.append(
            (
                "registered delta_tv phrase",
                f"reaches R2 in {k2:,} of {n2:,} replicates in each of the "
                f"{_word(len(feasible))} feasible directions "
                f"({', '.join(r['direction'] for r in feasible)}), and the test alone rejects in "
                f"{kt:,} of {nt:,}; {' and '.join(infeasible)} are infeasible there",
            )
        )
    # Why D4 and D6 are infeasible there: contexts whose channel-off `garden` share is below 0.10.
    garden: dict[str, list[int]] = {}
    with (root / "data" / "raw" / "bank_annotation.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["condition"] != "off" or row["pre_bias_destination_zone"] is None:
                continue
            counts = garden.setdefault(row["frozen_ctx_id"], [0, 0])
            counts[1] += 1
            counts[0] += row["pre_bias_destination_zone"] == "garden"
    short = sum(1 for g, n in garden.values() if g * 10 < n)
    fragments.append(
        ("garden phrase", f"because {_word(short)} context holds less than 0.10 in `garden`")
    )
    # D1 and D5 on that base: the same statistics from some delta upward.
    deltas = [c["delta"] for c in summary["cells"] if c["id"].startswith("C|D1|")]
    same_from = None
    for d in reversed(deltas):
        if stats(f"C|D1|{d}") == stats(f"C|D5|{d}"):
            same_from = d
        else:
            break
    if same_from is None:
        problems.append("D1/D5 phrase: D1 and D5 differ at every delta on the completed run's base")
    else:
        fragments.append(
            (
                "D1/D5 phrase",
                f"D1 and D5 give identical statistics there from `delta_tv` = {same_from} upward",
            )
        )

    # Where the surrogate and the test agree along the surrogate's own direction.
    surrogate = {(r["base"], r["delta_tv"]): r["surrogate_power"] for r in side["surrogate_alongside"]}
    agree_from = None
    for d in reversed(deltas):
        if stats(f"C|D1|{d}")["test_reject"]["rate"] == surrogate[("C", d)]:
            agree_from = d
        else:
            break
    if agree_from is None:
        problems.append("agreement phrase: the test never equals the surrogate along D1")
    else:
        fragments.append(
            ("agreement phrase, §4.3", f"they agree from `delta_tv` = {agree_from} upward and part below it")
        )
        fragments.append(
            (
                "agreement phrase, §1",
                f"equals the surrogate's {surrogate[('C', agree_from)]!r} from `delta_tv` = "
                f"{agree_from} upward along the surrogate's direction",
            )
        )
        if Fraction(agree_from) * 2 != Fraction("0.10"):
            problems.append(
                f"agreement phrase, Abstract and §6.2: the text says half the margin, but the "
                f"agreement starts at {agree_from}"
            )
        fragments.append(
            (
                "agreement phrase, Abstract",
                f"at the surrogate's {surrogate[('C', agree_from)]!r} from half the registered "
                "effect size upward",
            )
        )

    # The smallest declared delta reaching 0.8, every (base, direction).
    for row in rules["rate_surface"]:
        feasible_here = [
            c["delta"] for c in summary["cells"]
            if c["id"].startswith(f"{row['base']}|{row['direction']}|") and c["status"] != "infeasible"
        ]
        unreached = _POSTHOC_NOT_REACHED + (
            f" (feasible only at {', '.join(feasible_here)})"
            if len(feasible_here) < len(deltas) else ""
        )
        cols = []
        for q in ("r2", "test_reject"):
            e = row[q]
            cols.append(
                f"{e['smallest_delta_point_estimate_at_least_0_8'] or unreached} / "
                f"{e['smallest_delta_wilson_low_at_least_0_8'] or unreached}"
            )
        fragments.append(
            (
                f"smallest-delta row, {row['base']} {row['direction']}",
                f"| `{row['base']}` | {row['direction']} | {cols[0]} | {cols[1]} |",
            )
        )

    # Aliases, per base, in the order of the grid.
    aliases: dict[str, dict[str, set[str]]] = {}
    for cell in summary["cells"]:
        if cell.get("alias_of"):
            base, direction = cell["id"].split("|")[:2]
            aliases.setdefault(base, {}).setdefault(cell["alias_of"].split("|")[1], set()).add(direction)
    alias_text = "; ".join(
        f"on `{base}`, {' and '.join(sorted(dirs))} {'is' if len(dirs) == 1 else 'are'} {source}"
        for base, by_source in aliases.items()
        for source, dirs in sorted(by_source.items())
    )
    fragments.append(("alias phrase", f"Some directions are the same shift on a base: {alias_text}"))

    # The surrogate beside the pipeline, completed run's base, the surrogate's own direction.
    for cell in summary["cells"]:
        if cell["id"].startswith("C|D1|"):
            s = cell["summary"]
            fragments.append(
                (
                    f"surrogate row, delta_tv {cell['delta']}",
                    f"| `{cell['delta']}` | `{surrogate[('C', cell['delta'])]!r}` | "
                    f"{_posthoc_rate(s['r2'])} | {_posthoc_rate(s['test_reject'])} |",
                )
            )

    # The Abstract's sentence on the same comparison, at a tenth of the margin.
    tenth = stats("C|D1|0.01")["test_reject"]
    fragments.append(
        (
            "abstract surrogate-against-test phrase",
            f"at a tenth of the margin the surrogate returns {surrogate[('C', '0.01')]!r} where the "
            f"test rejects in {tenth['k']} of {tenth['n']:,} simulated replicates",
        )
    )

    # Two statements §4.3 makes in words about the degenerate base.
    g_surrogate = {d: v for (b, d), v in surrogate.items() if b == "G"}
    if not (g_surrogate["0.01"] < 1.0 and all(v == 1.0 for d, v in g_surrogate.items() if d != "0.01")):
        problems.append(
            "degenerate-base surrogate: the manuscript says the surrogate returns 1.0 from 0.02 "
            f"upward on that base, but side-analyses.json gives {g_surrogate!r}"
        )
    feasible_g = {
        direction: sorted(
            x["delta"] for x in summary["cells"]
            if x["id"].startswith(f"G|{direction}|") and x["status"] != "infeasible"
        )
        for direction in ("D4", "D6")
    }
    if any(v != ["0.01"] for v in feasible_g.values()):
        problems.append(
            "degenerate-base feasibility: the manuscript says D4 and D6 are feasible only at 0.01 "
            f"there, but the summary gives {feasible_g!r}"
        )

    # The degenerate base: the test alone against the pipeline.
    g = stats("G|D1|0.02")
    first = next(r for r in rules["rate_surface"] if r["base"] == "G" and r["direction"] == "D1")
    reach = first["r2"]["smallest_delta_point_estimate_at_least_0_8"]
    g_reach = stats(f"G|D1|{reach}")["r2"] if reach else None
    fragments.append(
        (
            "degenerate-base phrase",
            f"along D1, at `delta_tv` = 0.02 the test alone rejects in {g['test_reject']['k']} of "
            f"{g['test_reject']['n']} replicates (`{g['test_reject']['rate']!r}`) while the pipeline "
            f"stops at R4 in {g['branch_counts']['R4']} of {g['replicates']}",
        )
    )
    if g_reach is None:
        problems.append("degenerate-base phrase: P(R2) on the degenerate base never reaches 0.8")
    else:
        fragments.append(
            (
                "degenerate-base reach phrase",
                f"P(R2) first reaches 0.8 there at `delta_tv` = {reach} "
                f"({g_reach['k']} of {g_reach['n']})",
            )
        )
    # Replicates that stopped at R4 anywhere but the degenerate base.
    elsewhere = [
        (c["id"], c["summary"]["branch_counts"]["R4"], c["summary"]["replicates"])
        for c in summary["cells"]
        if c.get("summary") and not c.get("alias_of") and not c["id"].startswith("G|")
        and "branch_counts" in c["summary"] and c["summary"]["branch_counts"]["R4"]
    ]
    fragments.append(
        (
            "R4 elsewhere phrase",
            "Outside the degenerate base, replicates stopped at R4 only in "
            + ", ".join(f"`{cid}` ({k} of {n:,})" for cid, k, n in elsewhere)
            + "; none stopped at R3 or ended in an evaluator exit anywhere in the grid",
        )
    )

    # Side analyses.
    bounds = {(r["run"], r["zone"], r["scope"]): r for r in side["empty_cell_bounds"]}
    agora = bounds[("completed", "agora", "pooled channel-off")]
    chashitsu = bounds[("completed", "chashitsu", "pooled channel-off")]
    both = bounds[("completed", "chashitsu", "both conditions pooled")]
    if agora["upper_95_one_sided"] != chashitsu["upper_95_one_sided"]:
        problems.append("empty-cell bound phrase: the two zones' pooled bounds differ")
    fragments.append(
        (
            "empty-cell bound phrase",
            f"0 of {agora['n']:,} channel-off draws, a one-sided 95% upper bound of "
            f"`{agora['upper_95_one_sided']}` for each of `agora` and `chashitsu`; `chashitsu`, absent "
            f"from all {both['n']:,} parsed draws, has a bound of `{both['upper_95_one_sided']}`",
        )
    )
    smallest: list[str] = []
    for a in ("0", "0.01", "0.1", "0.5", "1", "2"):
        rows = [
            r for r in side["surrogate_sensitivity"]["pseudocount"]
            if r["run"] == "completed" and r["pseudocount"] == a and r["passes_gate"]
        ]
        smallest.append(f"`{min(float(r['delta_tv']) for r in rows)!r}` at {a}")
    fragments.append(("pseudocount phrase", "; ".join(smallest)))
    floors = side["surrogate_sensitivity"]["floor"]
    by_floor: dict[str, list[float]] = {}
    for r in floors:
        by_floor.setdefault(r["floor"], []).append(r["power"])
    if len({tuple(v) for v in by_floor.values()}) != 1:
        problems.append("floor phrase: the manuscript says every floor gives the same sweep")
    fragments.append(
        (
            "floor phrase",
            f"identical for every floor from `{min(by_floor, key=float)}` to "
            f"`{max(by_floor, key=float)}`",
        )
    )
    path = [r for r in side["concentration_and_null_mean"] if r["path"] == "uniform_to_C"]
    means = [r["null_mean_tv_bar"] for r in path]
    if any(later >= earlier for earlier, later in zip(means, means[1:])):
        problems.append("concentration phrase: the null expectation does not fall along the path")
    fragments.append(
        (
            "concentration phrase",
            f"falls at every declared point, from `{means[0]!r}` for the near-uniform base to "
            f"`{means[-1]!r}` at the completed run's base",
        )
    )
    return fragments, problems


def rendered_fragments(root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Render, from the sources, the rows and phrases the manuscript must carry.

    Returns ``(fragments, problems)``: each fragment is ``(what it is, the exact text)``, and the
    problems are inconsistencies between sources that no fragment could express -- a class count
    that the pinned golden value disagrees with, or a zone the prose says is absent turning up.
    Nothing here is read from the manuscript; the manuscript is only searched afterwards.
    """
    fragments: list[tuple[str, str]] = []
    problems: list[str] = []

    derived = load_json(root / "data" / "derived" / "collapse-and-floor.json")
    for zone in _ZONES:
        fragments.append(
            (
                f"support table row, {zone}",
                f"| `{zone}` | {derived['off_counts'][zone]} | "
                f"`{derived['off_distribution'][zone]!r}` |",
            )
        )
    fragments.append(
        ("channel-off parsed draws", f"({derived['off_total_draws']:,} draws that parsed)")
    )
    for row in derived["power_sweep"]:
        fraction = row["fraction_of_margin"]
        rendered = "1" if fraction == 1.0 else f"1/{round(1 / fraction)}"
        fragments.append(
            (
                f"sweep row, delta_tv {row['delta_tv']!r}",
                f"| `{row['delta_tv']!r}` | {rendered} | `{row['power']!r}` | "
                f"{'yes' if row['passes_gate'] else 'no'} |",
            )
        )

    for line in (root / "data" / "derived" / "power-curve.md").read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or not cells[1].startswith("`["):
            continue
        base = cells[1].strip("`")
        label = _BASE_LABELS.get(base)
        if label is None:
            problems.append(f"data/derived/power-curve.md has a base the manuscript does not name: {base}")
            continue
        fragments.append(
            (
                f"power table row, {label} at delta_tv {cells[2]}",
                f"| {label} `{base}` | `{float(cells[2]):.2f}` | `{cells[3]}` |",
            )
        )
        # §1, §3.2, §4.1 and §6.2 say in words that at the registered delta_tv the surrogate
        # returns 1.0 for both bases. The rows above hold the table; this holds the sentence.
        if float(cells[2]) == 0.1 and cells[3] != "1.0000":
            problems.append(
                f"the manuscript says the surrogate returns 1.0 for both bases at the registered "
                f"delta_tv, but data/derived/power-curve.md gives {cells[3]} for the {label} base"
            )

    verdicts = {
        name: load_json(root / "data" / "raw" / name)
        for name in ("cproper-verdict.json", "control-verdict.json", "primary-verdict.json")
    }
    summaries = {rel: _annotation_summary(root / rel) for _, rel, _ in _RUN_LABELS}

    completed = summaries["data/raw/bank_annotation.jsonl"]
    none_on, none_off = completed["none"]["on"], completed["none"]["off"]
    total = none_on + none_off
    fragments += [
        (
            "completed-run None counts",
            f"{none_off} of the {completed['totals']['off']:,} channel-off draws and {none_on} of "
            f"the {completed['totals']['on']:,} channel-on draws",
        ),
        (
            "completed-run contexts with more None under the channel",
            f"in {completed['contexts_on_gt_off']} of the {completed['contexts']} contexts",
        ),
        ("completed-run None total", f"All {total} are the same thing"),
        ("completed-run None total, all string null", f"all {total} `None` records are this string"),
        ("completed-run None total, in §1", f"all {total} dropped draws are the string"),
        ("completed-run None by condition, in §1", f"{none_on} against {none_off} in the completed run"),
    ]
    freeze = load_json(root / "analysis" / "heldout-stay" / "freeze.json")
    pinned = freeze["positive_control"]["records_classes"]
    if pinned != {"N_str": total}:
        problems.append(
            "analysis/heldout-stay/freeze.json pins the completed run's records classes as "
            f"{pinned!r}, but the manuscript says all {total} dropped draws are the string null"
        )

    for label, rel, verdict_name in _RUN_LABELS:
        summary = summaries[rel]
        off_support = sum(1 for z in _ZONES if summary["pooled"]["off"][z] > 0)
        on_support = sum(1 for z in _ZONES if summary["pooled"]["on"][z] > 0)
        fragments.append(
            (
                f"support row, {label}",
                f"| {label} | {off_support} of 5 | {on_support} of 5 | "
                f"{summary['cell_min']}–{summary['cell_max']} | "
                f"`{verdicts[verdict_name]['rho_hat']!r}` |",
            )
        )
    primary = summaries["data/prospective/primary/run_annotation.jsonl"]
    low, high = _word(primary["cell_min"]), _word(primary["cell_max"])
    fragments += [
        (
            "primary cells, in §1",
            f"each of its {primary['cells']} (context, condition) cells produced between {low} "
            f"and {high} zones",
        ),
        (
            "primary cells, in the results section",
            f"every one of the primary arm's {primary['cells']} (context, condition) cells "
            f"produces {low} or more zones, between {low} and {high}",
        ),
    ]
    control_off = summaries["data/prospective/control/run_annotation.jsonl"]["pooled"]["off"]
    absent = [zone for zone in ("agora", "chashitsu") if control_off[zone] != 0]
    if absent:
        problems.append(
            f"the manuscript says the control arm's channel-off base never produces agora or "
            f"chashitsu, but it produces {absent}"
        )
    fragments.append(
        (
            "control channel-off base",
            f"of its {sum(control_off.values()):,} parsed channel-off draws, `garden` has "
            f"{control_off['garden']:,}, `study` {control_off['study']:,} and `peripatos` "
            f"{control_off['peripatos']:,}",
        )
    )

    for label, name in _READ_LABELS:
        verdict = verdicts[name]
        if verdict["tv_bar"] is None:
            what = (
                f"`rho_hat` = {verdict['rho_hat']!r} (`effective_k` = {verdict['effective_k']} of "
                f"{verdict['n_contexts']}); no estimate formed"
            )
            made = "no"
        else:
            what = (
                f"`rho_hat` = {verdict['rho_hat']!r}, `power` = {verdict['power']!r}, "
                f"`tv_bar` = {verdict['tv_bar']!r}, "
                f"`permutation_reject` = {str(verdict['permutation_reject']).lower()}"
            )
            made = "yes"
        fragments.append(
            (f"read-across row, {label}", f"| {label} | `{verdict['verdict']}` | {what} | {made} |")
        )

    result = load_json(root / "analysis" / "heldout-stay" / "result.json")
    arms = result["arms"]
    for arm, label in _ARM_LABELS:
        fragments.append(
            (
                f"held-out count row, {arm}",
                f"| {label} | {arms[arm]['none']['on']} | {arms[arm]['none']['off']} | "
                f"{arms[arm]['test']['p_upper']} |",
            )
        )
    for key, label in _CLASS_LABELS:
        counts = [arms[arm]["classes"][key][condition] for arm in ("control", "primary") for condition in ("on", "off")]  # fmt: skip
        fragments.append(
            (f"held-out class row, {key}", f"| {label} | " + " | ".join(map(str, counts)) + " |")
        )
    c_none, p_none = arms["control"]["none"], arms["primary"]["none"]
    primary_f = arms["primary"]["classes"]["F"]
    empty = sum(
        arms[arm]["classes"][key][condition]
        for arm in ("control", "primary")
        for key in ("N_json", "K")
        for condition in ("on", "off")
    )
    dropped = sum(arms[arm]["none"][condition] for arm in ("control", "primary") for condition in ("on", "off"))  # fmt: skip
    fragments += [
        (
            "held-out counts, in the abstract",
            f"({c_none['on']} against {c_none['off']}; {p_none['on']} against {p_none['off']})",
        ),
        (
            "held-out counts, in §1",
            f"{c_none['on']} against {c_none['off']} in the control arm and {p_none['on']} against "
            f"{p_none['off']} in the primary arm",
        ),
        (
            "held-out excess of malformed JSON",
            f"{primary_f['on'] - primary_f['off']} of the primary arm's "
            f"{p_none['on'] - p_none['off']}-draw excess",
        ),
        (
            "held-out explicit-null p-values",
            f"*p* = {arms['control']['explicit_null_test']['p_upper']}, and not for the primary "
            f"arm, where it gives *p* = {arms['primary']['explicit_null_test']['p_upper']}",
        ),
        (
            "held-out six-category distance",
            f"is {arms['control']['tv6']['observed']} (permutation *p* = "
            f"{arms['control']['tv6']['p_value']}) in the control arm and "
            f"{arms['primary']['tv6']['observed']} (*p* = {arms['primary']['tv6']['p_value']}) "
            "in the primary arm",
        ),
        (
            "held-out freeze commit, in §1.3",
            f"Specification frozen at commit `{result['freeze_commit'][:7]}`, before the "
            "condition-wise counts",
        ),
        (
            "held-out freeze commit, in the results section",
            f"interpretation table were frozen at commit `{result['freeze_commit'][:7]}`",
        ),
        ("held-out row", f"row {result['row']['id']} of the frozen interpretation table"),
        ("held-out row, in §1", f"(row {result['row']['id']} of the held-out test's frozen interpretation table"),
        ("held-out row, in §1.3", f"Row {result['row']['id']} of its frozen table"),
        ("held-out level", f"at level {result['alpha']}"),
        ("held-out level, in §1.3", f"control first, α = {result['alpha']}"),
        (
            "empty destinations among the prospective None, in §1",
            f"for all but {_word(empty)} of the draws dropped in the prospective arms",
        ),
        (
            "empty destinations among the prospective None, before §E",
            f"all but {_word(empty)} of the {dropped}",
        ),
    ]
    attempts = root / "data" / "attempts"
    complete, tail, partial_problems = _stopped_partial(
        attempts / "control" / "run_records.partial.attempt1-interrupted.jsonl"
    )
    problems += partial_problems
    for arm in ("control", "primary"):
        events = _attempt_events(attempts / arm / "attempts.jsonl")
        if set(events) != {"start", "captured"}:
            problems.append(f"the {arm} attempt log records events {dict(events)!r}")
        problems += _captures_complete(attempts / arm / "attempts.jsonl")
        fragments.append(
            (
                f"{arm} attempt log",
                f"the {arm} arm's log records {_word(events['start'])} "
                f"start{'s' if events['start'] != 1 else ''} and {_word(events['captured'])} "
                f"completed capture{'s' if events['captured'] != 1 else ''}",
            )
        )
    fragments.append(
        (
            "stopped attempt's partial record",
            f"holds {complete} complete per-call lines (call indices 1 to {complete}) followed "
            f"by {tail} NUL bytes and no final newline",
        )
    )
    # Readings the prose states in words rather than numbers: both arms rejected, and the
    # explicit-null qualifier holds for the control arm only.
    confirmatory = result["confirmatory"]
    if not (confirmatory["control_rejected"] and confirmatory["primary_rejected"]):
        problems.append(f"the manuscript says both arms rejected, but result.json records {confirmatory!r}")
    modifiers = result["modifiers"]
    if (modifiers["control"]["explicit_null"], modifiers["primary"]["explicit_null"]) != (True, False):
        problems.append(
            "the manuscript says the explicit-null qualifier holds for the control arm and not for "
            f"the primary arm, but result.json records {modifiers!r}"
        )
    posthoc, posthoc_problems = posthoc_fragments(root)
    return fragments + posthoc, problems + posthoc_problems


def check_rendered_fragments(repo_root: Path) -> list[str]:
    """Require every rendered row and phrase to occur in the manuscript exactly once.

    For quantities whose literals are too common for an occurrence test -- ``2``, ``8``, ``1.0`` --
    the unit checked is the table row or the phrase that carries them, rendered from the source.
    **Exactly once**, not merely at least once: the occurrence test used for the other quantities
    does not protect a value quoted twice against one of its copies being altered, and an
    observation run on this check found exactly that for a phrase quoted in two sections. A
    rendered phrase is specific enough to be unique, so uniqueness can be required here.
    """
    missing = [rel for rel in RENDER_SOURCES if not (repo_root / rel).is_file()]
    if missing:
        return [f"the rendered comparison has no source at {missing}"]
    fragments, problems = rendered_fragments(repo_root)
    text = " ".join((repo_root / "manuscript" / "main.md").read_text(encoding="utf-8").split())
    for what, fragment in fragments:
        count = text.count(" ".join(fragment.split()))
        if count == 0:
            problems.append(f"{what}: main.md does not carry {fragment!r}")
        elif count > 1:
            problems.append(
                f"{what}: main.md carries {fragment!r} {count} times. A phrase quoted more than "
                "once is not protected against one of its copies being altered; render each "
                "occurrence as its own fragment"
            )
    if not problems:
        print(
            f"[numbers] OK rendered              = {len(fragments)} rows and phrases rendered from "
            "the annotations, the verdicts, the derived artefacts and the held-out result each "
            "occur in main.md exactly once"
        )
    return problems


def _rewrite_json(path: Path, edit: Callable[[Any], Any]) -> None:
    payload = load_json(path)
    before = json.dumps(payload, sort_keys=True)
    edit(payload)
    if json.dumps(payload, sort_keys=True) == before:
        raise _NoOpMutation(f"the edit to {path.name} changed nothing")
    path.write_text(json.dumps(payload), encoding="utf-8")


def _rewrite_first_row(path: Path, matches: Callable[[dict[str, Any]], bool], zone: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        row = json.loads(line)
        if matches(row):
            row["pre_bias_destination_zone"] = zone
            lines[index] = json.dumps(row)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise _NoOpMutation(f"no row of {path.name} matches the mutation")


def _drop_first_line(path: Path) -> None:
    data = path.read_bytes()
    head, newline, rest = data.partition(b"\n")
    if not newline:
        raise _NoOpMutation(f"{path.name} has no complete line to drop")
    path.write_bytes(rest)


def _replace_bytes(path: Path, old: bytes, new: bytes) -> None:
    data = path.read_bytes()
    if old not in data:
        raise _NoOpMutation(f"{path.name} does not contain {old!r}")
    path.write_bytes(data.replace(old, new, 1))


def _set(path: tuple[Any, ...], value: Any) -> Callable[[Any], None]:
    def edit(payload: Any) -> None:
        node = payload
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return edit


def check_rendered_fragments_fire(repo_root: Path) -> list[str]:
    """Alter one source at a time, on copies, and require the rendered comparison to notice.

    Each case names the diagnostic it must produce, so a case that fails for another reason is not
    counted as caught, and the unaltered copy is carried as a control. The sources are copies of
    the real files, not invented ones: a fixture built from this module's own constants could only
    confirm that the constants were applied.
    """
    if not all((repo_root / rel).is_file() for rel in RENDER_SOURCES):
        print("[numbers] -- a source of the rendered comparison is absent, so its self-check has nothing to alter")  # fmt: skip
        return []

    def off_none(row: dict[str, Any]) -> bool:
        return row["condition"] == "off" and row["pre_bias_destination_zone"] is None

    def off_zone(zone: str) -> Callable[[dict[str, Any]], bool]:
        return lambda row: row["condition"] == "off" and row["pre_bias_destination_zone"] == zone

    result = "analysis/heldout-stay/result.json"
    summary_json = "data/posthoc/pipeline-summary.json"
    side_json = "data/posthoc/side-analyses.json"

    def with_digests(path: str, edit: Callable[[Any], None]) -> Callable[[Path], None]:
        """Rewrite a posthoc JSON, then bring its manifest digest up to date.

        The digest comparison alone would catch any of these edits; updating it isolates the
        rendered comparison, so a case can only pass by the fragment path noticing.
        """

        def mutate(root: Path) -> None:
            import hashlib  # noqa: PLC0415

            _rewrite_json(root / path, edit)
            manifest_path = root / "data/posthoc/manifest.json"
            manifest = load_json(manifest_path)
            name = Path(path).name
            manifest["outputs_sha256"][name] = hashlib.sha256((root / path).read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        return mutate

    def cell_edit(cell_id: str, *keys: Any, value: Any) -> Callable[[Any], None]:
        def edit(payload: Any) -> None:
            node = next(c for c in payload["cells"] if c["id"] == cell_id)
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = value

        return edit

    def side_row(section: str, match: Callable[[dict[str, Any]], bool], key: str, value: Any) -> Callable[[Any], None]:  # fmt: skip
        def edit(payload: Any) -> None:
            node = payload
            for part in section.split("."):
                node = node[part]
            next(r for r in node if match(r))[key] = value

        return edit

    def surface(base: str, direction: str, quantity: str, value: Any) -> Callable[[Any], None]:
        def edit(payload: Any) -> None:
            row = next(
                r for r in payload["reading_rules"]["rate_surface"]
                if r["base"] == base and r["direction"] == direction
            )
            row[quantity]["smallest_delta_point_estimate_at_least_0_8"] = value

        return edit

    def all_registered(k: int) -> Callable[[Any], None]:
        def edit(payload: Any) -> None:
            for r in payload["reading_rules"]["registered_delta_on_C"]:
                if r["status"] == "run":
                    r["r2"]["k"] = k

        return edit

    posthoc_cases: tuple[tuple[str, Callable[[Path], None] | None, str | None], ...] = (
        ("M19 a Type-I count moves", with_digests(summary_json, _set(("reading_rules", "type_i", "r2", "C", "k"), 196)), "Type-I row, completed run, channel-off per context"),
        ("M20 one direction's count at the registered delta_tv moves", with_digests(summary_json, _set(("reading_rules", "registered_delta_on_C", 0, "r2", "k"), 999)), "registered delta_tv phrase"),
        ("M20b every direction's count at the registered delta_tv moves together", with_digests(summary_json, all_registered(999)), "registered delta_tv phrase: main.md does not carry"),
        ("M21 the surrogate beside the pipeline moves", with_digests(side_json, side_row("surrogate_alongside", lambda r: (r["base"], r["delta_tv"]) == ("C", "0.03"), "surrogate_power", 0.999)), "surrogate row, delta_tv 0.03"),
        ("M22 an empty-cell bound moves", with_digests(side_json, side_row("empty_cell_bounds", lambda r: (r["run"], r["zone"], r["scope"]) == ("completed", "agora", "pooled channel-off"), "upper_95_one_sided", "0.00131537")), "empty-cell bound phrase"),
        ("M23 one floor's sweep departs from the others", with_digests(side_json, side_row("surrogate_sensitivity.floor", lambda r: (r["floor"], r["delta_tv"]) == ("1e-3", "0.001"), "power", 0.5)), "floor phrase"),
        ("M24 the null expectation stops falling along the path", with_digests(side_json, side_row("concentration_and_null_mean", lambda r: r["point"] == "t=0.9", "null_mean_tv_bar", 0.07)), "concentration phrase"),
        ("M25 the per-replicate record changes under its summary", lambda root: _replace_bytes(root / "data/posthoc/pipeline-replicates.tsv", b"\tR1\t", b"\tR2\t"), "pipeline-replicates.tsv does not match the digest"),
        ("M26 the count the Abstract quotes moves", with_digests(summary_json, cell_edit("C|D1|0.01", "summary", "test_reject", "k", value=121)), "abstract surrogate-against-test phrase"),
        ("M27 a smallest-delta row moves", with_digests(summary_json, surface("C", "D3", "r2", "0.04")), "smallest-delta row, C D3"),
        ("M28 the degenerate base's test count moves", with_digests(summary_json, cell_edit("G|D1|0.02", "summary", "test_reject", "k", value=410)), "degenerate-base phrase"),
        ("M29 the degenerate base reaches 0.8 elsewhere", with_digests(summary_json, surface("G", "D1", "r2", "0.075")), "degenerate-base reach phrase"),
        ("M30 a pseudocount row stops passing", with_digests(side_json, side_row("surrogate_sensitivity.pseudocount", lambda r: (r["run"], r["pseudocount"], r["delta_tv"]) == ("completed", "2", "0.005"), "passes_gate", False)), "pseudocount phrase"),
        ("M31 the seed-varied Type-I count moves", with_digests(summary_json, _set(("reading_rules", "type_i_with_per_replicate_scorer_seed", "r2", "k"), 94)), "Type-I row, scorer seed varied"),
        ("M32 D4 becomes feasible at 0.02 on the degenerate base", with_digests(summary_json, cell_edit("G|D4|0.02", "status", value="run")), "degenerate-base feasibility"),
        ("M33 the surrogate falls below 1.0 at 0.02 on the degenerate base", with_digests(side_json, side_row("surrogate_alongside", lambda r: (r["base"], r["delta_tv"]) == ("G", "0.02"), "surrogate_power", 0.99)), "degenerate-base surrogate"),
        ("M34 the test stops matching the surrogate at 0.05", with_digests(summary_json, cell_edit("C|D1|0.05", "summary", "test_reject", "rate", value=0.999)), "agreement phrase, §4.3"),
        ("M35 a replicate stops at R4 under the null on the degenerate base less often", with_digests(summary_json, cell_edit("G|null|0", "summary", "branch_counts", "R4", value=3999)), "degenerate-base null branch counts"),
        ("M36 D5 departs from D1 at the registered delta_tv", with_digests(summary_json, cell_edit("C|D5|0.10", "summary", "mean_tv_bar", value=0.5)), "D1/D5 phrase"),
        ("M37 a direction stops being an alias", with_digests(summary_json, cell_edit("Cs|D2|0.10", "alias_of", value="Cs|D3|0.10")), "alias phrase"),
        ("M38 one more replicate stops at R4 outside the degenerate base", with_digests(summary_json, cell_edit("C|D4|0.075", "summary", "branch_counts", "R4", value=55)), "R4 elsewhere phrase"),
        ("M39 a replicate ends at R3", with_digests(summary_json, cell_edit("C|D1|0.01", "summary", "branch_counts", "R3", value=1)), "R3/die phrase"),
        ("M40 R2's split stops adding up", with_digests(summary_json, cell_edit("C|D1|0.01", "summary", "r2_split", "both", value=1)), "R2's split does not add up"),
        ("M41 the record has one call fewer", lambda root: _drop_first_line(root / "data/posthoc/pipeline-replicates.tsv"), "scorer-call count"),
        ("M42 the deviation ledger gains an entry", lambda root: (root / "analysis/autopsy/DEVIATIONS.md").write_text((root / "analysis/autopsy/DEVIATIONS.md").read_text(encoding="utf-8") + "\n## DV-3 — test\n", encoding="utf-8"), "deviation count"),
        ("M43 one more context falls short in garden", lambda root: [_rewrite_first_row(root / "data/raw/bank_annotation.jsonl", lambda row: row["frozen_ctx_id"] == "cproper-ctx-3" and row["condition"] == "off" and row["pre_bias_destination_zone"] == "garden", "study") for _ in range(2)] and None, "garden phrase"),
    )  # fmt: skip
    cases: tuple[tuple[str, Callable[[Path], None] | None, str | None], ...] = posthoc_cases + (
        ("C1 the sources unaltered", None, None),
        (
            "M1 a held-out count moves",
            lambda root: _rewrite_json(root / result, _set(("arms", "control", "none", "on"), 157)),
            "held-out count row, control",
        ),
        (
            "M2 a held-out class count moves",
            lambda root: _rewrite_json(root / result, _set(("arms", "primary", "classes", "F", "on"), 97)),
            "held-out class row, F",
        ),
        (
            "M3 a held-out p-value moves",
            lambda root: _rewrite_json(root / result, _set(("arms", "control", "test", "p_upper"), "3.415047e-05")),
            "held-out count row, control",
        ),
        (
            "M4 one more empty destination among the prospective None",
            lambda root: _rewrite_json(root / result, _set(("arms", "primary", "classes", "K", "off"), 1)),
            "empty destinations among the prospective None",
        ),
        (
            "M5 the completed run loses a None draw",
            lambda root: _rewrite_first_row(root / "data/raw/bank_annotation.jsonl", off_none, "study"),
            "completed-run None counts",
        ),
        (
            "M6 the primary arm's channel-off base gains a zone",
            lambda root: _rewrite_first_row(
                root / "data/prospective/primary/run_annotation.jsonl", off_zone("study"), "peripatos"
            ),
            "support row, primary arm",
        ),
        (
            "M7 a row of the power table moves",
            lambda root: (root / "data/derived/power-curve.md").write_text(
                (root / "data/derived/power-curve.md").read_text(encoding="utf-8").replace("0.9533", "0.9534"),
                encoding="utf-8",
            ),
            "power table row, degenerate at delta_tv 0.01",
        ),
        (
            "M8 a row of the sweep moves",
            lambda root: _rewrite_json(
                root / "data/derived/collapse-and-floor.json", _set(("power_sweep", 5, "power"), 0.92)
            ),
            "sweep row, delta_tv 0.001",
        ),
        (
            "M9 the control arm stops producing an estimate",
            lambda root: _rewrite_json(root / "data/raw/control-verdict.json", _set(("tv_bar",), None)),
            "read-across row, control arm",
        ),
        (
            "M10 the pinned classes of the completed run move",
            lambda root: _rewrite_json(
                root / "analysis/heldout-stay/freeze.json",
                _set(("positive_control", "records_classes", "N_str"), 329),
            ),
            "freeze.json pins the completed run's records classes",
        ),
        (
            "M11 the control arm's channel-off base moves",
            lambda root: _rewrite_first_row(
                root / "data/prospective/control/run_annotation.jsonl", off_zone("garden"), "study"
            ),
            "control channel-off base",
        ),
        (
            "M13 the surrogate stops returning 1.0 at the registered delta_tv",
            lambda root: (root / "data/derived/power-curve.md").write_text(
                (root / "data/derived/power-curve.md").read_text(encoding="utf-8").replace(
                    "| 0.1 | 1.0000 |", "| 0.1 | 0.9990 |", 1
                ),
                encoding="utf-8",
            ),
            "returns 1.0 for both bases at the registered delta_tv",
        ),
        (
            "M14 the stopped attempt's partial record loses a complete line",
            lambda root: _drop_first_line(
                root / "data/attempts/control/run_records.partial.attempt1-interrupted.jsonl"
            ),
            "stopped attempt's partial record",
        ),
        (
            "M15 the stopped attempt's tail is not NUL bytes",
            lambda root: _replace_bytes(
                root / "data/attempts/control/run_records.partial.attempt1-interrupted.jsonl",
                b"\x00\x00", b"\x00x",
            ),
            "the unterminated tail is not NUL bytes only",
        ),
        (
            "M16 the stopped attempt's first call index is not 1",
            lambda root: _replace_bytes(
                root / "data/attempts/control/run_records.partial.attempt1-interrupted.jsonl",
                b'"call_index": 1,', b'"call_index": 7,',
            ),
            "call indices are not 1..",
        ),
        (
            "M17 the control attempt log loses a start",
            lambda root: _drop_first_line(root / "data/attempts/control/attempts.jsonl"),
            "control attempt log",
        ),
        (
            "M18 the control arm's capture is one call short",
            lambda root: _replace_bytes(
                root / "data/attempts/control/attempts.jsonl",
                b'"llm_calls": 4800', b'"llm_calls": 4799',
            ),
            "a capture of 4799 calls",
        ),
        (
            "M12 a rendered row is quoted a second time",
            lambda root: (root / "manuscript/main.md").write_text(
                (root / "manuscript/main.md").read_text(encoding="utf-8")
                + "\n| control (`qwen3:8b`) | 156 | 94 | 3.415046e-05 |\n",
                encoding="utf-8",
            ),
            "held-out count row, control: main.md carries",
        ),
    )  # fmt: skip

    problems: list[str] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for label, mutate, expect in cases:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "repo"
                for rel in RENDER_SOURCES:
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(repo_root / rel, root / rel)
                if mutate is not None:
                    try:
                        mutate(root)
                    except _NoOpMutation as exc:
                        problems.append(f"self-check {label}: {exc}")
                        continue
                reported = check_rendered_fragments(root)
            joined = " | ".join(reported)
            if expect is None:
                if reported:
                    problems.append(f"self-check {label}: expected to report nothing, got {reported!r}")
            elif not reported:
                problems.append(f"self-check {label}: expected to report a problem, got none")
            elif expect not in joined:
                problems.append(
                    f"self-check {label}: fired, but not for the expected reason "
                    f"(wanted text containing {expect!r}, got {joined!r})"
                )
    if not problems:
        mutations = sum(1 for case in cases if case[2] is not None)
        print(
            f"[numbers] OK self-check: {mutations} mutations caught, {len(cases) - mutations} "
            "control clean (the rendered rows and phrases cannot drift from their sources "
            "without this step saying so)"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    main_md = repo_root / "manuscript" / "main.md"
    if not main_md.is_file():
        print(f"[numbers] FAIL: the manuscript is missing: {main_md}", file=sys.stderr)
        return 1
    text = main_md.read_text(encoding="utf-8")

    readme_md = repo_root / "README.md"
    if not readme_md.is_file():
        print(f"[numbers] FAIL: the README is missing: {readme_md}", file=sys.stderr)
        return 1
    readme_text = readme_md.read_text(encoding="utf-8")

    sources: dict[str, dict[str, Any]] = {}
    # Run the sweep first: a harness that has stopped catching its own mutations should say so
    # before it reports on anything else.
    problems: list[str] = check_branch_guards_fire()
    problems.extend(check_third_finding_guards_fire(repo_root))
    problems.extend(check_rendered_fragments_fire(repo_root))
    covered_in_readme = 0

    for label, filename, keys, how in REQUIRED:
        if filename not in sources:
            sources[filename] = load_json(repo_root / "data" / "raw" / filename)
        node: Any = sources[filename]
        for key in keys:
            node = node[key]  # Raising on a missing key is correct; no default
        literal = literal_of(node, how)
        if literal in text:
            print(f"[numbers] OK {label:<28} = {literal}")
        else:
            problems.append(
                f"{label}: the frozen value {literal!r} from {filename} does not appear "
                "in main.md. Bring the prose in line with the extraction output"
            )
        if label in README_QUANTITIES:
            covered_in_readme += 1
            if literal not in readme_text:
                problems.append(
                    f"{label}: the frozen value {literal!r} from {filename} does not "
                    "appear in README.md, which claims its quantities are enforced here"
                )

    derived_dir = repo_root / "data" / "derived"
    for label, filename, keys, how in DERIVED_REQUIRED:
        source_path = derived_dir / filename
        if not source_path.is_file():
            problems.append(
                f"{label}: {source_path} is missing. It is generated by "
                "collapse_and_floor.py, which repro.sh runs before this step"
            )
            continue
        node = load_json(source_path)
        for key in keys:
            node = node[key]
        literal = literal_of(node, how)
        if literal in text:
            print(f"[numbers] OK {label:<28} = {literal}  (derived)")
        else:
            problems.append(
                f"{label}: the derived value {literal!r} from {filename} does not appear "
                "in main.md"
            )

    # The landed prospective verdicts. Absent before the arms run, and their absence is not a
    # failure, for the same reason the witness block below gives.
    prospective_landed = all(
        (repo_root / "data" / "raw" / name).is_file() for name in PROSPECTIVE_OUTPUTS
    )
    if prospective_landed:
        for label, filename, keys, how in PROSPECTIVE_REQUIRED:
            if filename not in sources:
                sources[filename] = load_json(repo_root / "data" / "raw" / filename)
            node = sources[filename]
            for key in keys:
                node = node[key]
            literal = literal_of(node, how)
            if literal in text:
                print(f"[numbers] OK {label:<28} = {literal}  (prospective)")
            else:
                problems.append(
                    f"{label}: the landed value {literal!r} from {filename} does not appear "
                    "in main.md"
                )
    else:
        print(
            "[numbers] -- the prospective verdicts have not all landed, so the quantities the "
            "results section quotes from them are not compared"
        )

    # The deposit witness. Absent before a deposit exists, and its absence is not a failure --
    # the same existence guard steps 13 and 14 of repro.sh use, for the same reason: a check that
    # demanded the file would freeze "the deposit has happened" into a script that ran before it
    # had. Present-but-disagreeing is a failure.
    witness_path = repo_root / "seal" / "zenodo-witness.json"
    if witness_path.is_file():
        witness = load_json(witness_path)
        for label, keys, how in WITNESS_REQUIRED:
            node: Any = witness
            for key in keys:
                node = node[key]
            literal = literal_of(node, how)
            if literal in text:
                print(f"[numbers] OK {label:<28} = {literal}  (witness)")
            else:
                problems.append(
                    f"{label}: the deposit witness records {literal!r}, which does not appear "
                    "in main.md"
                )
    else:
        print("[numbers] -- no deposit witness present, so its anchor and DOIs are not compared")

    unknown = README_QUANTITIES - {label for label, _, _, _ in REQUIRED}
    if unknown:
        problems.append(
            f"README_QUANTITIES names quantities that are not in REQUIRED: {sorted(unknown)}"
        )

    for label, forbidden in MISLABEL_CHECKS:
        if forbidden in text:
            problems.append(f"mix-up: {label} -- {forbidden!r} appears in main.md")

    problems.extend(check_record_template(repo_root))
    problems.extend(check_reported_branch(repo_root))
    problems.extend(check_third_finding_support(repo_root))
    problems.extend(check_rendered_fragments(repo_root))
    # Section references. The manuscript was renumbered for submission (C, 2026-09-26), and
    # files that cannot change still cite the earlier numbers; see check_crossrefs.py. Run from
    # here so that step 9 of the sealed repro.sh covers it without the sealed file changing.
    problems.extend(check_crossrefs.check(repo_root))
    problems.extend(check_crossrefs.self_test(repo_root))

    if problems:
        print("[numbers] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[numbers] OK: {len(REQUIRED)} frozen and {len(DERIVED_REQUIRED)} derived quantities "
        f"(plus {len(PROSPECTIVE_REQUIRED)} from the landed prospective verdicts and "
        f"{len(WITNESS_REQUIRED)} from the deposit witness, when those are present) "
        f"occur in main.md as their sources "
        f"render them, {covered_in_readme} of them also in README.md. The test is "
        "occurrence, not uniqueness: a value that appears more than once is not protected "
        "against one of its occurrences being altered. Numbers outside this list are not "
        "covered at all -- including the prospective quantities whose literals are too common "
        "for an occurrence test to mean anything, which check_third_finding_support compares "
        "between sources instead."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
