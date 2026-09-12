#!/usr/bin/env python3
"""Compare the numbers the manuscript quotes with the frozen inputs they come from.

The manuscript states that its numbers are taken from the extraction script rather than copied by
hand. **Stating it is not checking it.** That an extraction script exists, and that the prose agrees
with what it produces, are two different facts; asserting the second on the strength of the first is
the error this script removes.

The method is plain. Each quantity is read from the frozen JSON **by key** -- direct subscripting,
never a default -- so a key absent from the file raises rather than returning something plausible.
The resulting literal must then appear in the manuscript.

What this establishes: for the quantities listed below, the literal in the manuscript matches the
frozen record character for character, and a single altered digit fails the run.

What it does not: the correctness of every number in the manuscript. Its scope is the quantities
obtainable mechanically from the frozen inputs; anything outside that list is not covered.

Usage:  python analysis/scripts/check_manuscript_numbers.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402

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

    sources: dict[str, dict[str, Any]] = {}
    problems: list[str] = []

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

    for label, forbidden in MISLABEL_CHECKS:
        if forbidden in text:
            problems.append(f"mix-up: {label} -- {forbidden!r} appears in main.md")

    if problems:
        print("[numbers] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[numbers] OK: {len(REQUIRED)} quantities match the frozen inputs character for "
        "character (numbers outside this list are not covered)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
