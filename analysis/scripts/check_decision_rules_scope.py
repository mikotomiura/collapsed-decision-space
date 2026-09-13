#!/usr/bin/env python3
"""Measure what the sealed decision rules actually catch, by mutating their inputs.

A rule file that is never exercised is a rule file that might be vacuous. Running the evaluator
once on the real record shows that it produces *an* answer; it does not show that a different
record would have produced a different one. This script supplies the difference.

Each case below is an **independently written literal**. None of them is derived from
``seal/decision-rules.json``, because a fixture generated from the thing it tests agrees with it by
construction and so measures nothing.

Two kinds of case are present, and both matter:

* mutations that **must** change the outcome -- a moved threshold, a flipped flag, a broken type;
* a **no-op** control that must *not* change it, so that a checker which simply fails on everything
  cannot pass this script.

What this establishes: for each listed mutation, the evaluator reaches the stated branch or exits
non-zero. What it does not: that the rules are the right rules. Whether the branch definitions
express the intended science is a question for the protocol, not for this file.

Usage:  python analysis/scripts/check_decision_rules_scope.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = REPO_ROOT / "analysis" / "scripts" / "apply_decision_rules.py"
RULES = REPO_ROOT / "seal" / "decision-rules.json"

#: The control arm as recorded by the completed run. Written out here as a literal rather than
#: read from data/raw, so that this file states what it assumes.
CONTROL_IN_BAND: dict[str, Any] = {
    "verdict": "NO_CHANNEL_CONFORMANCE",
    "rho_hat": 1.0,
    "power": 1.0,
    "tv_bar": 0.038065,
    "permutation_reject": False,
    "none_rate_max_observed": 0.123333,
}

#: A primary arm that reaches R1: valid apparatus, adequate power, estimate below the margin.
PRIMARY_R1: dict[str, Any] = {
    "verdict": "NO_CHANNEL_CONFORMANCE",
    "rho_hat": 0.875,
    "power": 0.95,
    "tv_bar": 0.052,
    "permutation_reject": False,
    "none_rate_max_observed": 0.2,
}


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    merged = dict(base)
    merged.update(changes)
    return merged


def _without(base: dict[str, Any], key: str) -> dict[str, Any]:
    merged = dict(base)
    del merged[key]
    return merged


#: (name, control, primary, expected branch or None for "must exit non-zero", why it matters)
CASES: tuple[tuple[str, dict[str, Any], dict[str, Any] | None, str | None, str], ...] = (
    # -- the control gate, one factor at a time -------------------------------------------- #
    (
        "R5 holds, primary reaches R1",
        CONTROL_IN_BAND,
        PRIMARY_R1,
        "R1",
        "the unmutated pair; if this does not reach R1 nothing below means anything",
    ),
    (
        "R5 fails on verdict",
        _with(CONTROL_IN_BAND, verdict="CHANNEL_CONFORMANCE_DETECTED"),
        PRIMARY_R1,
        "R5",
        "a differing control verdict must stop before the primary arm is read",
    ),
    (
        "R5 fails on rho_hat just below the band",
        _with(CONTROL_IN_BAND, rho_hat=0.7499),
        PRIMARY_R1,
        "R5",
        "the 0.75 bound is tighter than the 0.5 inside the scorer and must bite",
    ),
    (
        "R5 holds at rho_hat exactly on the bound",
        _with(CONTROL_IN_BAND, rho_hat=0.75),
        PRIMARY_R1,
        "R1",
        "the bound is inclusive; an off-by-one here would silently narrow the band",
    ),
    (
        "R5 fails on power",
        _with(CONTROL_IN_BAND, power=0.79),
        PRIMARY_R1,
        "R5",
        "the control arm's own power is part of the concordance band",
    ),
    (
        "R5 fails on the tv_bar tolerance while still below the margin",
        _with(CONTROL_IN_BAND, tv_bar=0.08),
        PRIMARY_R1,
        "R5",
        "0.08 < 0.10 but |0.08 - 0.038065| > 0.03: the tolerance is a separate condition "
        "from the margin, and collapsing the two would lose this case",
    ),
    (
        "R5 fails on tv_bar above the margin",
        _with(CONTROL_IN_BAND, tv_bar=0.15),
        PRIMARY_R1,
        "R5",
        "the margin condition must bite independently of the tolerance",
    ),
    (
        "R5 fails on permutation_reject",
        _with(CONTROL_IN_BAND, permutation_reject=True),
        PRIMARY_R1,
        "R5",
        "a control arm that rejects the nil null is not concordant",
    ),
    # -- the primary branches -------------------------------------------------------------- #
    (
        "R4 on collapsed support",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, rho_hat=0.375),
        "R4",
        "apparatus invalidity must be read before the estimate, not as a null",
    ),
    (
        "R4 on excessive none-rate",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, none_rate_max_observed=0.6),
        "R4",
        "the second disjunct of R4 must be reachable on its own",
    ),
    (
        "R3 on inadequate power",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, power=0.5),
        "R3",
        "an underpowered estimate must not fall through to R1 or R2",
    ),
    (
        "R3 does not fire at power exactly 0.8",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, power=0.8),
        "R1",
        "power_min is inclusive; the boundary decides between R3 and R1",
    ),
    (
        "R2 on an estimate at the margin",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, tv_bar=0.1),
        "R2",
        "the margin is exclusive for R1: exactly 0.10 is not below it",
    ),
    (
        "R2 on a rejected nil null below the margin",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, permutation_reject=True),
        "R2",
        "R2's disjunction must fire on rejection alone, with the estimate still small",
    ),
    (
        "R4 wins over R3 when both would fire",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, none_rate_max_observed=0.6, power=0.5),
        "R4",
        "the only genuine R4/R3 conflict: R4 fires on its none-rate disjunct while rho_hat "
        "stays above 0.5, so R3 fires too. The branches are not mutually exclusive as "
        "written and the sealed order is what removes the ambiguity. Reaching R4 through "
        "the rho_hat disjunct instead would NOT test the order, because R3 requires "
        "rho_hat >= 0.5 and so cannot fire at the same time -- an earlier version of this "
        "case made that mistake and passed under a deliberately reordered rule file",
    ),
    # -- malformed inputs are errors, not false predicates --------------------------------- #
    (
        "a missing quantity is an error",
        CONTROL_IN_BAND,
        _without(PRIMARY_R1, "rho_hat"),
        None,
        "a rule that silently evaluates False on a missing key is worse than no rule",
    ),
    (
        "a null quantity is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, power=None),
        None,
        "null must not be coerced",
    ),
    (
        "a stringified number is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, tv_bar="0.052"),
        None,
        "string comparison would have made this pass",
    ),
    (
        "a NaN is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, tv_bar=float("nan")),
        None,
        "every comparison with NaN is False, so NaN would quietly walk to the last branch",
    ),
    (
        "an int where a bool is expected is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, permutation_reject=0),
        None,
        "0 == False in Python; accepting it would let a malformed record satisfy R1",
    ),
    (
        "a bool where a number is expected is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, rho_hat=True),
        None,
        "True == 1 in Python, which would pass every lower bound",
    ),
    # -- the control against over-strictness ------------------------------------------------ #
    (
        "no-op: reordering the keys changes nothing",
        dict(reversed(list(CONTROL_IN_BAND.items()))),
        dict(reversed(list(PRIMARY_R1.items()))),
        "R1",
        "a checker that failed on everything would pass every case above; this one "
        "must still succeed, and reach the same branch",
    ),
)


def _run(tmp: Path, control: dict[str, Any], primary: dict[str, Any] | None) -> tuple[int, str]:
    control_path = tmp / "control.json"
    control_path.write_text(json.dumps(control), encoding="utf-8")
    argv = [
        sys.executable,
        str(EVALUATOR),
        "--rules",
        str(RULES),
        "--control",
        str(control_path),
    ]
    if primary is not None:
        primary_path = tmp / "primary.json"
        primary_path.write_text(json.dumps(primary), encoding="utf-8")
        argv += ["--primary", str(primary_path)]
    out_path = tmp / "report.json"
    argv += ["--out", str(out_path)]

    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return completed.returncode, ""
    report = json.loads(out_path.read_text(encoding="utf-8"))
    return 0, report["branch"]


def main() -> int:
    if not RULES.is_file():
        print(f"[rules-scope] FAIL: the sealed rules are missing: {RULES}", file=sys.stderr)
        return 1

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        for name, control, primary, expected, why in CASES:
            code, branch = _run(tmp, control, primary)
            if expected is None:
                if code == 0:
                    problems.append(
                        f"{name}: expected a non-zero exit (reason: {why}) but the "
                        f"evaluator succeeded and reported branch {branch!r}"
                    )
            elif code != 0:
                problems.append(
                    f"{name}: expected branch {expected!r} (reason: {why}) but the "
                    f"evaluator exited {code}"
                )
            elif branch != expected:
                problems.append(
                    f"{name}: expected branch {expected!r} (reason: {why}) but got {branch!r}"
                )

    if problems:
        print("[rules-scope] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[rules-scope] OK: {len(CASES)} cases, each an independently written literal "
        f"({sum(1 for c in CASES if c[3] is None)} of them required to be rejected). "
        "This measures the reach of the rules, not their correctness."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
