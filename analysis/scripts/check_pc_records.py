#!/usr/bin/env python3
"""Run the frozen held-out self-test with the shipped completed-run records, and compare.

``analysis/scripts/heldout_stay_check.py`` is frozen (``FROZEN_PATHS``), and so is the workflow
that runs it, ``.github/workflows/heldout-stay.yml``. That workflow calls ``--self-test`` without
``--cproper-records``, because the completed run's per-draw records were not shipped when it was
frozen, so its positive control ``PC-records`` reports SKIPPED -- a check not made, not a check
passed. The records have been shipped in ``data/completed/`` since 2026-09-25. This script, which
is not frozen, runs the frozen script as it stands, twice:

1. ``--self-test`` -- as the frozen workflow runs it;
2. ``--self-test --cproper-records data/completed/bank_records.jsonl``.

and requires:

- both exit 0 and report no failed check;
- the first skips exactly ``PC-records`` and nothing else;
- the second skips nothing, and ``PC-records`` passes with nothing unreproduced;
- **every other check reports the same line in both runs**, in the same order. Supplying the
  records is meant to turn one skip into one pass and change nothing else; this is what makes
  "the other self-test items keep their meaning" a comparison rather than an assurance.

The second run's output is written to ``--out`` so that the ``compendium`` workflow can require it
to be byte-identical on both operating systems. The comparison logic is itself tested on every
run, against fabricated outputs, before the real ones are judged.

Usage:  python analysis/scripts/check_pc_records.py [--out build/compendium/pc-records.txt]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_SCRIPT = "analysis/scripts/heldout_stay_check.py"
RECORDS = "data/completed/bank_records.jsonl"
TARGET = "PC-records"

#: How many checks other than PC-records the frozen self-test reports. Pinned so that two equally
#: truncated outputs cannot agree with each other over an empty or shortened set.
EXPECTED_OTHER_CHECKS = 48

#: One per-check line of the frozen script: ``[heldout] OK    <code>: <detail>``.
CHECK_LINE_RE = re.compile(
    r"^\[heldout\] (?P<status>OK|FAIL|SKIPPED)\s+(?P<code>[^:\s]+):"
)


def checks(output: str) -> list[tuple[str, str, str]]:
    """Return ``(status, code, line)`` for every per-check line, in order."""
    found: list[tuple[str, str, str]] = []
    for line in output.splitlines():
        match = CHECK_LINE_RE.match(line)
        if match is not None:
            found.append((match.group("status"), match.group("code"), line))
    return found


def judge(
    without: str, with_records: str, expected_others: int = EXPECTED_OTHER_CHECKS
) -> list[str]:
    """Compare the two self-test outputs; return the problems."""
    problems: list[str] = []
    base, full = checks(without), checks(with_records)
    if not base or not full:
        return ["a self-test run printed no per-check lines"]

    for label, rows in (("without records", base), ("with records", full)):
        failed = [code for status, code, _ in rows if status == "FAIL"]
        if failed:
            problems.append(f"{label}: failed checks {failed}")

    base_skips = [code for status, code, _ in base if status == "SKIPPED"]
    if base_skips != [TARGET]:
        problems.append(
            f"without records: expected to skip exactly [{TARGET}], skipped {base_skips}"
        )

    full_skips = [code for status, code, _ in full if status == "SKIPPED"]
    if full_skips:
        problems.append(f"with records: skipped {full_skips}")
    target = [line for status, code, line in full if code == TARGET]
    if (
        len(target) != 1
        or not target[0].startswith("[heldout] OK")
        or "unreproduced 0;" not in target[0]
    ):
        problems.append(
            f"with records: {TARGET} did not pass with nothing unreproduced: {target}"
        )

    others_base = [line for _, code, line in base if code != TARGET]
    others_full = [line for _, code, line in full if code != TARGET]
    if len(others_base) != expected_others:
        problems.append(
            f"without records: {len(others_base)} checks other than {TARGET}, "
            f"expected {expected_others}"
        )
    if others_base != others_full:
        changed = [
            (b, f) for b, f in zip(others_base, others_full, strict=False) if b != f
        ] or [(len(others_base), len(others_full))]
        problems.append(
            f"supplying the records changed checks other than {TARGET}: {changed[:3]}"
        )
    return problems


#: Fabricated outputs for the self-check, written as literals.
_BASE = (
    "[heldout] OK    A-one: detail 1\n"
    "[heldout] OK    B-two: detail 2\n"
    "[heldout] SKIPPED PC-records: not given\n"
    "[heldout] self-test: 2 passed, 0 failed, 1 skipped (PC-records)\n"
)
_FULL = (
    "[heldout] OK    A-one: detail 1\n"
    "[heldout] OK    B-two: detail 2\n"
    "[heldout] OK    PC-records: unreproduced 0; classes {'N_str': 330}\n"
    "[heldout] self-test: 3 passed, 0 failed, 0 skipped\n"
)


def judge_fires() -> list[str]:
    """Measure what :func:`judge` catches, on fabricated outputs. Each case names its diagnostic."""
    cases: tuple[tuple[str, str, str, str | None], ...] = (
        ("C1 the expected pair", _BASE, _FULL, None),
        ("M1 the records run still skips", _BASE, _BASE, "with records: skipped"),
        (
            "M2 another check changes when the records are supplied",
            _BASE,
            _FULL.replace("detail 2", "detail 3"),
            "changed checks other than",
        ),
        (
            "M3 the positive control fails",
            _BASE,
            _FULL.replace("[heldout] OK    PC-records: unreproduced 0", "[heldout] FAIL  PC-records: unreproduced 1"),
            "failed checks ['PC-records']",
        ),
        (
            "M4 a draw is unreproduced but the line says OK",
            _BASE,
            _FULL.replace("unreproduced 0", "unreproduced 2"),
            "did not pass with nothing unreproduced",
        ),
        (
            "M5 the base run skips something else too",
            _BASE.replace("[heldout] OK    A-one", "[heldout] SKIPPED A-one"),
            _FULL,
            "expected to skip exactly",
        ),
        ("M6 a check disappears", _BASE, _FULL.replace("[heldout] OK    B-two: detail 2\n", ""), "changed checks other than"),
        (
            "M7 the same check disappears from both runs",
            _BASE.replace("[heldout] OK    B-two: detail 2\n", ""),
            _FULL.replace("[heldout] OK    B-two: detail 2\n", ""),
            "expected 2",
        ),
    )  # fmt: skip
    problems: list[str] = []
    for label, without, with_records, expect in cases:
        found = judge(without, with_records, expected_others=2)
        joined = " | ".join(found)
        if expect is None and found:
            problems.append(f"self-check {label}: expected nothing, got {found!r}")
        elif expect is not None and expect not in joined:
            problems.append(f"self-check {label}: wanted {expect!r}, got {found!r}")
    if not problems:
        mutations = sum(1 for case in cases if case[3] is not None)
        print(
            f"[pc-records] OK self-check: {mutations} mutations caught, "
            f"{len(cases) - mutations} control clean"
        )
    return problems


def run_self_test(*extra: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(  # noqa: S603
        [sys.executable, FROZEN_SCRIPT, "--self-test", *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode, proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=None, help="where to write the records run's output"
    )
    args = parser.parse_args(argv)

    problems = judge_fires()
    if not (REPO_ROOT / RECORDS).is_file():
        problems.append(f"{RECORDS} is missing")
    if problems:
        print("[pc-records] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    code_base, without = run_self_test()
    code_full, with_records = run_self_test("--cproper-records", RECORDS)
    if code_base != 0:
        problems.append(f"--self-test exited {code_base}")
    if code_full != 0:
        problems.append(f"--self-test --cproper-records exited {code_full}")
    problems += judge(without, with_records)

    if args.out is not None:
        out = REPO_ROOT / args.out if not args.out.is_absolute() else args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(with_records, encoding="utf-8", newline="\n")

    if problems:
        print("[pc-records] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    target = next(line for _, code, line in checks(with_records) if code == TARGET)
    others = len(checks(with_records)) - 1
    print(f"[pc-records] {target.removeprefix('[heldout] ')}")
    print(
        f"[pc-records] OK: with the shipped records, {TARGET} passes instead of skipping, and the "
        f"other {others} checks report the same line as without them"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
