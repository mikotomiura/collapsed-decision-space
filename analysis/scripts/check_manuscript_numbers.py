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
import contextlib
import io
import json
import shutil
import sys
import tempfile
from collections.abc import Callable
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
#: section 12.8 of the manuscript states the part of it that remains.
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
      §8 of the protocol says the authors do not predict which branch will occur; a branch
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
            "inputs do is a prediction, and §8 of the protocol says the authors do not predict "
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

    The manuscript reports that at the thresholds fixed in section 6.3 the measurability gate
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
