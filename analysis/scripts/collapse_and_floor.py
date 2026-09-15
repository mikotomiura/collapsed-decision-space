#!/usr/bin/env python3
"""Recompute the two properties of the completed run that the reframed claim rests on.

Both are derived here rather than quoted, for the same reason the verdict is recomputed rather than
copied: a number that only a person has ever calculated is an assertion.

**The support of the decision space.** The estimand is described as a five-way choice. Over the
4,800 draws of the completed run two of the five zones are never produced in the channel-off
condition -- which is the condition that matters here, and the qualification is not decoration:
one of the two does appear a handful of times when the channel is on, and ``zero_support_zones``
below is computed over the channel-off pooled distribution alone. That is not a detail of
presentation either: the power calculation takes that same empirical channel-off distribution as
its base and builds its alternative by moving mass into the *smallest* cell, so a cell of
probability exactly zero determines what the gate can detect.

**The null floor of the estimand.** Total variation is a non-negative distance, so its expectation
under the null is not zero. Permuting the condition labels within each context, which is the same
null the scorer's own permutation test uses, gives the distribution the observed value should be
read against.

What this establishes: the two quantities follow from the shipped annotation.
What it does not: anything about the prospective arms' draws or verdicts.

Outputs are quantised to six decimal places before rendering, because the last bits of a float are
not stable across platforms and the derived artefacts are compared byte-for-byte across two.

Usage:  python analysis/scripts/collapse_and_floor.py --out data/derived/collapse-and-floor.md
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

import numpy as np

from erre_sandbox.integration.embodied.bank_power import categorical_multinomial_power

#: Effect sizes at which the power gate is evaluated against the empirical base, expressed as
#: fractions of the declared materiality margin of 0.10. The gate's threshold is 0.8.
POWER_SWEEP: tuple[float, ...] = (0.1, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002)

#: Replicates for the power Monte Carlo. Smaller than the permutation null because each
#: replicate is a multinomial draw of 2,400 rather than a full re-permutation.
POWER_REPLICATES: int = 1000

#: The five zones, in the order the apparatus uses.
ZONES: tuple[str, ...] = ("agora", "chashitsu", "garden", "peripatos", "study")

#: The measurement seed, as frozen in the protocol. Also used for the permutation null here.
SEED: int = 20260708

#: Replicates for the permutation null. Fixed so the derived artefact is reproducible.
N_REPLICATES: int = 2000

#: Rendered decimals. Six is the repository's convention for emitted floats.
DP: int = 6


def _q(value: float) -> float:
    return round(float(value), DP)


def load_cells(annotation: Path) -> dict[str, dict[str, list[int]]]:
    """Group the annotation into per-context, per-condition zone indices, dropping unparsed draws."""
    cells: dict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: {"on": [], "off": []}
    )
    with annotation.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            zone = row["pre_bias_destination_zone"]
            if zone is None:
                continue
            cells[row["frozen_ctx_id"]][row["condition"]].append(ZONES.index(zone))
    return dict(cells)


def pooled_distribution(cells: dict[str, dict[str, list[int]]], condition: str) -> tuple[np.ndarray, int]:
    counts = np.zeros(len(ZONES), dtype=np.int64)
    for conditions in cells.values():
        for index in conditions[condition]:
            counts[index] += 1
    total = int(counts.sum())
    return counts, total


def tv_bar(cells: dict[str, dict[str, list[int]]]) -> float:
    """Mean per-context total-variation distance between the two conditions."""
    per_context: list[float] = []
    for conditions in cells.values():
        on = np.bincount(np.asarray(conditions["on"]), minlength=len(ZONES)) / len(conditions["on"])
        off = np.bincount(np.asarray(conditions["off"]), minlength=len(ZONES)) / len(
            conditions["off"]
        )
        per_context.append(0.5 * float(np.abs(on - off).sum()))
    return float(np.mean(per_context))


def permutation_null(cells: dict[str, dict[str, list[int]]]) -> np.ndarray:
    """The distribution of tv_bar under within-context permutation of the condition labels."""
    pooled: list[np.ndarray] = []
    n_on: list[int] = []
    for conditions in cells.values():
        pooled.append(np.asarray(conditions["on"] + conditions["off"]))
        n_on.append(len(conditions["on"]))

    rng = np.random.default_rng(SEED)
    draws = np.empty(N_REPLICATES, dtype=np.float64)
    for replicate in range(N_REPLICATES):
        total = 0.0
        for arr, count in zip(pooled, n_on, strict=True):
            order = rng.permutation(len(arr))
            mask = np.zeros(len(arr), dtype=bool)
            mask[order[:count]] = True
            on = np.bincount(arr[mask], minlength=len(ZONES)) / count
            off = np.bincount(arr[~mask], minlength=len(ZONES)) / (len(arr) - count)
            total += 0.5 * float(np.abs(on - off).sum())
        draws[replicate] = total / len(pooled)
    return draws


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    root: Path = args.repo_root

    cells = load_cells(root / "data" / "raw" / "bank_annotation.jsonl")
    off_counts, off_total = pooled_distribution(cells, "off")
    on_counts, on_total = pooled_distribution(cells, "on")
    off_probabilities = off_counts / off_total

    zero_support = [ZONES[i] for i, p in enumerate(off_probabilities) if p == 0.0]
    support_sizes = {
        ctx: len({*conditions["on"], *conditions["off"]}) for ctx, conditions in cells.items()
    }

    observed = tv_bar(cells)
    null = permutation_null(cells)

    # The gate as it actually runs: the base is the empirical channel-off distribution, the same
    # one tabulated above, so the zero cells are the ones the alternative moves mass into.
    sweep: list[dict[str, Any]] = []
    for delta in POWER_SWEEP:
        result = categorical_multinomial_power(
            base_dist=[float(p) for p in off_probabilities],
            delta_tv=delta,
            m_draws=300,
            k_contexts=8,
            pooling=True,
            n_replicates=POWER_REPLICATES,
            seed=SEED,
        )
        sweep.append(
            {
                "delta_tv": delta,
                "fraction_of_margin": _q(delta / 0.10),
                "power": _q(result.power),
                "passes_gate": bool(result.power >= 0.8),
            }
        )
    smallest_passing = min(
        (row["delta_tv"] for row in sweep if row["passes_gate"]), default=None
    )

    summary: dict[str, Any] = {
        "schema": "cds-collapse-and-floor-1",
        "seed": SEED,
        "n_replicates": N_REPLICATES,
        "off_total_draws": off_total,
        "on_total_draws": on_total,
        "off_distribution": {z: _q(p) for z, p in zip(ZONES, off_probabilities, strict=True)},
        "off_counts": {z: int(c) for z, c in zip(ZONES, off_counts, strict=True)},
        "on_counts": {z: int(c) for z, c in zip(ZONES, on_counts, strict=True)},
        "zero_support_zones": zero_support,
        "zero_support_count": len(zero_support),
        "contexts_with_support_of_three": sum(1 for n in support_sizes.values() if n == 3),
        "context_support_sizes": {ctx: support_sizes[ctx] for ctx in sorted(support_sizes)},
        "observed_tv_bar": _q(observed),
        "null_mean_tv_bar": _q(float(null.mean())),
        "null_p95_tv_bar": _q(float(np.percentile(null, 95))),
        "observed_over_null_mean": _q(float(observed / null.mean())),
        "null_floor_share_of_observed_pct": _q(float(null.mean() / observed * 100.0)),
        "observed_below_null_p95": bool(observed < float(np.percentile(null, 95))),
        "power_replicates": POWER_REPLICATES,
        "power_gate_threshold": 0.8,
        "power_sweep": sweep,
        # Promoted to a top-level key because the abstract quotes it, and the number check
        # walks dictionaries only. A value the prose depends on should not sit inside a list
        # where nothing can reach it.
        "power_at_one_hundredth_of_margin": next(
            row["power"] for row in sweep if row["delta_tv"] == 0.001
        ),
        "smallest_delta_tv_passing_the_gate": smallest_passing,
        "smallest_passing_as_fraction_of_margin": (
            _q(smallest_passing / 0.10) if smallest_passing is not None else None
        ),
    }

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )

    lines = [
        "# The support of the decision space, and the null floor of the estimand",
        "",
        "Generated by `analysis/scripts/collapse_and_floor.py` from `data/raw/bank_annotation.jsonl`.",
        "Do not edit by hand.",
        "",
        f"Channel-off draws that parsed: {off_total}. Channel-on: {on_total}.",
        "",
        "| Zone | Channel-off count | Channel-off probability |",
        "|---|---|---|",
    ]
    for zone, count, probability in zip(ZONES, off_counts, off_probabilities, strict=True):
        lines.append(f"| `{zone}` | {int(count)} | {_q(probability)} |")
    lines += [
        "",
        f"Zones never produced under the channel-off condition: "
        f"{', '.join('`' + z + '`' for z in zero_support) or 'none'} "
        f"({summary['zero_support_count']} of {len(ZONES)}).",
        "",
        f"Contexts whose combined support is three zones: "
        f"{summary['contexts_with_support_of_three']} of {len(cells)}.",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| observed `tv_bar` | {summary['observed_tv_bar']} |",
        f"| null mean `tv_bar` ({N_REPLICATES} within-context permutations, seed {SEED}) "
        f"| {summary['null_mean_tv_bar']} |",
        f"| null 95th percentile | {summary['null_p95_tv_bar']} |",
        f"| observed / null mean | {summary['observed_over_null_mean']} |",
        f"| null mean as a share of the observed value | "
        f"{summary['null_floor_share_of_observed_pct']}% |",
        "",
        "The power gate evaluated against this same empirical base, at the sampling plan of the",
        f"completed run (*M* = 300, *K* = 8, pooled), {POWER_REPLICATES} replicates, seed {SEED}:",
        "",
        "| `delta_tv` | as a fraction of the 0.10 margin | power | passes the 0.8 gate |",
        "|---|---|---|---|",
    ]
    for row in sweep:
        lines.append(
            f"| {row['delta_tv']} | {row['fraction_of_margin']} | {row['power']} | "
            f"{'yes' if row['passes_gate'] else 'no'} |"
        )
    lines += [
        "",
        f"Smallest effect size in this sweep that still passes the gate: "
        f"{summary['smallest_delta_tv_passing_the_gate']}, which is "
        f"{summary['smallest_passing_as_fraction_of_margin']} of the declared margin.",
        "",
    ]
    text = "\n".join(lines)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"[collapse] wrote {args.out}")
    else:
        print(text)

    print(
        f"[collapse] zero-support zones = {zero_support}; "
        f"observed {summary['observed_tv_bar']} vs null mean "
        f"{summary['null_mean_tv_bar']} (p95 {summary['null_p95_tv_bar']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
