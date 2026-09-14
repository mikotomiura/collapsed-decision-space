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
import sys
import tempfile
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

    Four states, and only one of them is the interesting one:

    * **nothing landed, nothing claimed** -- guarded absence, not a failure. The arms have not
      run. Freezing "this has not happened yet" into a check is how a check becomes false later,
      which is why this is a condition on files rather than on a date;
    * **both verdicts landed, no branch claimed** -- a failure. Step 13 would run, re-derive a
      branch, compare it with nothing, and exit 0. That is the hole this function closes;
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

    try:
        branch_ids = sealed_branch_ids(repo_root)
        branch = find_marker(main_md.read_text(encoding="utf-8"), branch_ids)
    except MarkerError as exc:
        return [f"manuscript/main.md: {exc}"]

    problems: list[str] = []

    if branch is None:
        # `landed` is required to be non-empty as well as complete: with an empty set of
        # prospective outputs the equality below would hold vacuously and demand a marker for a
        # run that cannot have happened. The self-check exercises exactly that case.
        if landed and len(landed) == len(PROSPECTIVE_OUTPUTS):
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

    if len(landed) < len(PROSPECTIVE_OUTPUTS):
        print(
            f"[numbers] -- note: main.md reports {branch}, but only {len(landed)} of "
            f"{len(PROSPECTIVE_OUTPUTS)} prospective verdicts are in data/raw/. Step 13 stays "
            "guarded until both are, so the claim is not yet compared with anything"
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
_FIXTURE_MAIN_IN_GENERATED = (
    "# fixture\n\n"
    "<!-- BEGIN GENERATED FROM seal/decision-rules.json -- DO NOT EDIT BY HAND -->\n"
    "<!-- REPORTED-BRANCH: R1 -->\n"
    "<!-- END GENERATED FROM seal/decision-rules.json -->\n"
)


def _branch_fixture(
    root: Path, *, main_md: str, branch_file: str | None, landed: tuple[str, ...]
) -> Path:
    """Build a throwaway repository in the shape this check reads."""
    (root / "manuscript").mkdir(parents=True, exist_ok=True)
    (root / "seal").mkdir(parents=True, exist_ok=True)
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (root / "manuscript" / "main.md").write_text(main_md, encoding="utf-8", newline="\n")
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
    cases: tuple[tuple[str, str, str | None, tuple[str, ...], str | None], ...] = (
        # label, main.md, reported-branch.txt, landed verdicts, expected substring (None = clean)
        ("P1 nothing landed, nothing claimed", _FIXTURE_MAIN_NO_MARKER, None, (), None),
        ("P2 branch claimed and rendered", _FIXTURE_MAIN_R1, "R1\n", both, None),
        (
            "M1 verdicts landed, no marker",
            _FIXTURE_MAIN_NO_MARKER,
            None,
            both,
            "carries no <!-- REPORTED-BRANCH",
        ),
        (
            "M2 rendered file disagrees with the marker",
            _FIXTURE_MAIN_R1,
            "R2\n",
            both,
            "rather than",
        ),
        ("M3 marker but no rendered file", _FIXTURE_MAIN_R1, None, both, "is missing"),
        (
            "M4 rendered file with no marker behind it",
            _FIXTURE_MAIN_NO_MARKER,
            "R1\n",
            (),
            "no marker in main.md generates it",
        ),
        ("M5 two markers", _FIXTURE_MAIN_TWO, "R1\n", both, "markers"),
        (
            "M6 marker inside the generated block",
            _FIXTURE_MAIN_IN_GENERATED,
            "R1\n",
            both,
            "inside the block generated",
        ),
        (
            "M7 branch the sealed rules cannot reach",
            _FIXTURE_MAIN_UNKNOWN,
            "R9\n",
            both,
            "not one the sealed rules can reach",
        ),
        (
            "M8 trailing text makes the file a different token",
            _FIXTURE_MAIN_R1,
            "R1 # because the control arm held\n",
            both,
            "rather than",
        ),
    )

    problems: list[str] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for label, main_md, branch_file, landed, expect in cases:
            with tempfile.TemporaryDirectory() as tmp:
                root = _branch_fixture(
                    Path(tmp) / "repo",
                    main_md=main_md,
                    branch_file=branch_file,
                    landed=landed,
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
        mutations = sum(1 for case in cases if case[4] is not None)
        controls = len(cases) - mutations
        print(
            f"[numbers] OK self-check: {mutations} mutations caught, {controls} controls clean "
            "(the reported branch cannot go unstated, unrendered, or out of step with main.md)"
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

    problems.extend(check_reported_branch(repo_root))

    if problems:
        print("[numbers] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[numbers] OK: {len(REQUIRED)} frozen and {len(DERIVED_REQUIRED)} derived quantities "
        f"(plus {len(WITNESS_REQUIRED)} from the deposit witness, when one is present) "
        f"occur in main.md as their sources "
        f"render them, {covered_in_readme} of them also in README.md. The test is "
        "occurrence, not uniqueness: a value that appears more than once is not protected "
        "against one of its occurrences being altered. Numbers outside this list are not "
        "covered at all."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
