#!/usr/bin/env python3
"""Build the four-case comparison of a-priori categorical-multinomial power.

Calls ``categorical_multinomial_power`` from the vendored apparatus (which needs
``PYTHONPATH=analysis/apparatus``) with the same inputs as the upstream power worksheet.

**A point of wording that matters, and is repeated in the output header.** Everything below is the
power of the pooled one-sample chi-square goodness-of-fit **surrogate** that the attained-power gate
(R3) computes, not the power of the stratified permutation test the decision turns on; the latter is
evaluated nowhere. For this surrogate, what lowers the computed power is **not a concentrated base
distribution**. The third case below -- a degenerate base with a collapse-scale shift -- still
reaches a power of roughly 0.95. What lowers it is a **small attainable delta_tv**. Whether the base
is near-uniform or degenerate, ample delta_tv gives high surrogate power, and at the registered
delta_tv of 0.10 both bases checked here give 1.0, so a pass of the gate does not tell them apart.

Self-verification: the run fails if any of the four powers falls outside its expected band
(>=0.99 / 0.10-0.30 / >=0.85 / >=0.99). Because all four are deterministic under a fixed seed and a
fixed replicate count, the measured values are additionally pinned to within 1e-4
(``EXPECTED_POWER_PINS``). The bands guard the scientific statement; the pins are a separate
regression check that the numbers have not moved. The replicate count is not lowered to make the
run faster.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from erre_sandbox.integration.embodied.bank_power import (
    K_MIN,
    M_MIN,
    N_REPLICATES_DEFAULT,
    POWER_SEED_DEFAULT,
    categorical_multinomial_power,
)

HEADER_NOTE = (
    "# Power of the pooled chi-square surrogate the R3 gate computes, not of the\n"
    "# permutation test the decision turns on. For this surrogate, what lowers\n"
    "# the computed power is a small attainable delta_tv, not a concentrated base\n"
    "# (case 3: a degenerate base with delta_tv=0.01, one tenth of the\n"
    "#  pre-registered 0.10, still reaches high power)\n"
)


@dataclass(frozen=True)
class Case:
    label: str
    base_dist: tuple[float, ...]
    delta_tv: float
    expected_low: float
    expected_high: float


CASES: tuple[Case, ...] = (
    Case(
        label="pre-registered design (near-uniform)",
        base_dist=(0.2, 0.2, 0.2, 0.2, 0.2),
        delta_tv=0.10,
        expected_low=0.99,
        expected_high=1.0,
    ),
    Case(
        label="collapse-scale delta (one tenth of the proposal)",
        base_dist=(0.2, 0.2, 0.2, 0.2, 0.2),
        delta_tv=0.01,
        expected_low=0.10,
        expected_high=0.30,
    ),
    Case(
        label="degenerate base + collapse-scale delta",
        base_dist=(0.96, 0.01, 0.01, 0.01, 0.01),
        delta_tv=0.01,
        expected_low=0.85,
        expected_high=1.0,
    ),
    Case(
        label="degenerate base + pre-registered delta",
        base_dist=(0.96, 0.01, 0.01, 0.01, 0.01),
        delta_tv=0.10,
        expected_low=0.99,
        expected_high=1.0,
    ),
)

# Exact pins on the measured values (within PIN_TOLERANCE). The cases fix both the seed and
# the replicate count, so the output is fully deterministic and the measured values can be pinned
# without guessing any of them. The expected bands above guard the scientific statement; these
# pins are a separate regression check that the numbers have not moved in this commit. Each value
# was transcribed from an actual run of this script at the time the pins were added.
EXPECTED_POWER_PINS: tuple[float, ...] = (
    1.0,  # pre-registered design (near-uniform)
    0.18425,  # collapse-scale delta (one tenth of the proposal)
    0.95325,  # degenerate base + collapse-scale delta
    1.0,  # degenerate base + pre-registered delta
)
PIN_TOLERANCE = 1e-4

M_DRAWS = M_MIN  # 300
K_CONTEXTS = K_MIN  # 8
POOLING = True
SEED = POWER_SEED_DEFAULT  # 20260708
N_REPLICATES = N_REPLICATES_DEFAULT  # 4000; not lowered to make the run faster


def render_table() -> tuple[str, list[float]]:
    lines: list[str] = []
    lines.append(HEADER_NOTE)
    lines.append(
        f"Common parameters: m_draws={M_DRAWS}, k_contexts={K_CONTEXTS}, "
        f"pooling={POOLING}, seed={SEED}, n_replicates={N_REPLICATES}"
    )
    lines.append("")
    lines.append("| Case | base_dist | delta_tv | power (measured) | expected band |")
    lines.append("|---|---|---|---|---|")

    powers: list[float] = []
    for case in CASES:
        result = categorical_multinomial_power(
            base_dist=case.base_dist,
            delta_tv=case.delta_tv,
            m_draws=M_DRAWS,
            k_contexts=K_CONTEXTS,
            pooling=POOLING,
            n_replicates=N_REPLICATES,
            seed=SEED,
        )
        powers.append(result.power)
        base_str = "[" + ", ".join(f"{v:g}" for v in case.base_dist) + "]"
        band_str = f"[{case.expected_low}, {case.expected_high}]"
        lines.append(
            f"| {case.label} | `{base_str}` | {case.delta_tv} | "
            f"{result.power:.4f} | {band_str} |"
        )

    lines.append("")
    return "\n".join(lines) + "\n", powers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output file (default: <repo-root>/data/derived/power-curve.md)",
    )
    args = parser.parse_args(argv)

    table, powers = render_table()
    sys.stdout.write(table)

    ok = True
    for case, power in zip(CASES, powers, strict=True):
        if not (case.expected_low <= power <= case.expected_high):
            sys.stderr.write(
                f"[FAIL] {case.label}: power={power:.4f} is outside the expected band "
                f"[{case.expected_low}, {case.expected_high}]\n"
            )
            ok = False

    for case, power, pin in zip(CASES, powers, EXPECTED_POWER_PINS, strict=True):
        if abs(power - pin) > PIN_TOLERANCE:
            sys.stderr.write(
                f"[FAIL] {case.label}: power={power!r} departs from the pin {pin!r} by "
                f"more than {PIN_TOLERANCE}\n"
            )
            ok = False

    # Write only after the checks pass; writing first would leave a stale or wrong table
    # behind on failure.
    if ok:
        repo_root = Path(__file__).resolve().parents[2]
        default_out = repo_root / "data" / "derived" / "power-curve.md"
        out_path = args.out if args.out is not None else default_out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # newline is set explicitly: the default text mode rewrites line endings on Windows,
        # so identical content would produce different bytes across platforms. Measured on
        # Windows and Linux -- the content agreed and only the line endings differed.
        with out_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(table)
    else:
        sys.stderr.write(
            "[FAIL] checks did not pass; data/derived/power-curve.md is left unchanged\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
