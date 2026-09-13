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
    problems: list[str] = []
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

    unknown = README_QUANTITIES - {label for label, _, _, _ in REQUIRED}
    if unknown:
        problems.append(
            f"README_QUANTITIES names quantities that are not in REQUIRED: {sorted(unknown)}"
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
        f"[numbers] OK: {len(REQUIRED)} frozen and {len(DERIVED_REQUIRED)} derived quantities "
        f"occur in main.md as their sources "
        f"render them, {covered_in_readme} of them also in README.md. The test is "
        "occurrence, not uniqueness: a value that appears more than once is not protected "
        "against one of its occurrences being altered. Numbers outside this list are not "
        "covered at all."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
