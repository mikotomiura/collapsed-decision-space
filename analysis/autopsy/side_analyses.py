#!/usr/bin/env python3
"""Three side analyses of the post hoc simulation (B3), declared in ``grid.json`` with the grid.

1. **Concentration and the null expectation of ``tv_bar``.** Along declared paths of per-context
   bases, the expected ``tv_bar`` when both conditions are drawn from the same distribution, its
   95th percentile, and the conditional permutation-null mean (labels permuted within a context,
   which for fixed pooled counts is a multivariate hypergeometric draw).
2. **One-sided binomial upper bounds on the empty cells** (exact, 0 of n).
3. **Sensitivity of the R3 surrogate** to a pseudocount added to the base counts, and to the floor
   the chi-square statistic puts under an expected count of zero. The pseudocount is passed to the
   sealed function; the floor is not a parameter of it, so it is varied in a re-implementation
   that must agree with the sealed function bit for bit at the sealed floor of 1e-12.

Plus the surrogate's value at every base and delta of the main grid, shown next to the pipeline's
rates without comment.

What this establishes: properties of the statistic, the surrogate and the data counts under the
declared settings. What it does not: anything about the channel.

Usage:  python analysis/autopsy/side_analyses.py --out data/posthoc/side-analyses.json
        python analysis/autopsy/side_analyses.py --self-test
"""

from __future__ import annotations

import argparse
import decimal
import json
import math
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

from _common import (
    CONDITIONS,
    REPO_ROOT,
    RUN_FILES,
    build_bases,
    declaration_commit,
    load_grid,
    load_run,
)

import numpy as np  # noqa: E402
from erre_sandbox.integration.embodied.bank_power import (  # noqa: E402
    ALPHA_SIGNIFICANCE,
    _perturb_to_delta_tv,
    categorical_multinomial_power,
)

DP = 6


def _q(value: float) -> float:
    return round(float(value), DP)


def _entropy_bits(p: np.ndarray) -> float:
    nz = p[p > 0]
    return float(-np.sum(nz * np.log2(nz))) if nz.size else 0.0


# --------------------------------------------------------------------------------------------- #
# 1. Concentration and the null expectation of tv_bar
# --------------------------------------------------------------------------------------------- #


def _tv_bar(on: np.ndarray, off: np.ndarray, n_on: np.ndarray, n_off: np.ndarray) -> np.ndarray:
    """Mean over contexts of TV between count arrays shaped (..., K, Z)."""
    tv = 0.5 * np.abs(on / n_on[..., None] - off / n_off[..., None]).sum(axis=-1)
    return tv.mean(axis=-1)


def concentration(grid: dict[str, Any]) -> list[dict[str, Any]]:
    spec = grid["side_analyses"]["concentration_and_null_mean"]
    master = int(grid["master_seed"])
    ctxs = tuple(grid["context_ids"])
    zones = tuple(grid["zones"])
    base_c = next(b for b in build_bases(grid) if b.id == "C")
    m = int(grid["m_draws"])
    n_on = np.asarray([base_c.parsed(c, "on", m) for c in ctxs], dtype=np.int64)
    n_off = np.asarray([base_c.parsed(c, "off", m) for c in ctxs], dtype=np.int64)
    uniform = tuple(Fraction(1, len(zones)) for _ in zones)
    study, agora, chashitsu = zones.index("study"), zones.index("agora"), zones.index("chashitsu")

    points: list[tuple[str, str, dict[str, tuple[Fraction, ...]]]] = []
    for path in spec["paths"]:
        if path["id"] == "uniform_to_C":
            for t_text in path["t"]:
                t = Fraction(t_text)
                dists = {
                    c: tuple((1 - t) * u + t * p for u, p in zip(uniform, base_c.off[c], strict=True))
                    for c in ctxs
                }
                points.append((path["id"], f"t={t_text}", dists))
        else:
            for eps_text in path["eps"]:
                eps = Fraction(eps_text)
                dists = {}
                for c in ctxs:
                    moved = list(base_c.off[c])
                    moved[study] -= 2 * eps
                    moved[agora] += eps
                    moved[chashitsu] += eps
                    dists[c] = tuple(moved)
                points.append((path["id"], f"eps={eps_text}", dists))

    n_null = int(spec["null_datasets"])
    n_cond = int(spec["conditional"]["datasets"])
    n_perm = int(spec["conditional"]["permutations"])
    rows: list[dict[str, Any]] = []
    for index, (path_id, label, dists) in enumerate(points):
        p = np.asarray([[float(x) for x in dists[c]] for c in ctxs], dtype=np.float64)
        rng = np.random.default_rng(np.random.SeedSequence(master, spawn_key=(200 + index,)))
        on = np.stack([rng.multinomial(n_on[k], p[k], size=n_null) for k in range(len(ctxs))], axis=1)
        off = np.stack([rng.multinomial(n_off[k], p[k], size=n_null) for k in range(len(ctxs))], axis=1)
        null = _tv_bar(on.astype(np.float64), off.astype(np.float64), n_on.astype(np.float64), n_off.astype(np.float64))

        prng = np.random.default_rng(np.random.SeedSequence(master, spawn_key=(300 + index,)))
        cond_means = np.empty(n_cond, dtype=np.float64)
        for d in range(n_cond):
            pooled = on[d] + off[d]  # (K, Z)
            perm_on = np.stack(
                [prng.multivariate_hypergeometric(pooled[k], n_on[k], size=n_perm) for k in range(len(ctxs))],
                axis=1,
            )  # (n_perm, K, Z)
            perm_off = pooled[None, :, :] - perm_on
            cond_means[d] = _tv_bar(
                perm_on.astype(np.float64), perm_off.astype(np.float64),
                n_on.astype(np.float64), n_off.astype(np.float64),
            ).mean()

        approx = np.mean(
            [
                0.5 * sum(
                    math.sqrt(2.0 / math.pi) * math.sqrt(q * (1.0 - q) * (1.0 / n_on[k] + 1.0 / n_off[k]))
                    for q in p[k]
                )
                for k in range(len(ctxs))
            ]
        )
        rows.append(
            {
                "path": path_id,
                "point": label,
                "mean_entropy_bits": _q(np.mean([_entropy_bits(p[k]) for k in range(len(ctxs))])),
                "mean_sum_sqrt_pq": _q(np.mean([np.sqrt(p[k] * (1 - p[k])).sum() for k in range(len(ctxs))])),
                "support_size": int(max(int((p[k] > 0).sum()) for k in range(len(ctxs)))),
                "null_mean_tv_bar": _q(null.mean()),
                "null_p95_tv_bar": _q(np.percentile(null, 95)),
                "conditional_permutation_null_mean": _q(cond_means.mean()),
                "first_order_approximation": _q(approx),
            }
        )
    return rows


# --------------------------------------------------------------------------------------------- #
# 2. Empty-cell bounds
# --------------------------------------------------------------------------------------------- #


def _upper(n: int) -> str:
    with decimal.localcontext() as ctx:
        ctx.prec = 40
        value = 1 - decimal.Decimal("0.05") ** (decimal.Decimal(1) / decimal.Decimal(n))
        return format(value, ".6g")


def empty_cell_bounds(grid: dict[str, Any]) -> list[dict[str, Any]]:
    spec = grid["side_analyses"]["empty_cell_bounds"]
    zones = tuple(grid["zones"])
    ctxs = tuple(grid["context_ids"])
    rows: list[dict[str, Any]] = []
    for run_name in spec["runs"]:
        run = load_run(RUN_FILES[run_name], zones)
        for zone in spec["zones"]:
            z = zones.index(zone)
            scopes: list[tuple[str, int, int]] = []
            off_count = sum(run.zone_counts[(c, "off")][z] for c in ctxs)
            off_n = sum(sum(run.zone_counts[(c, "off")]) for c in ctxs)
            scopes.append(("pooled channel-off", off_count, off_n))
            for c in ctxs:
                scopes.append((f"channel-off {c}", run.zone_counts[(c, "off")][z], sum(run.zone_counts[(c, "off")])))
            both = sum(run.zone_counts[(c, k)][z] for c in ctxs for k in CONDITIONS)
            both_n = sum(sum(run.zone_counts[(c, k)]) for c in ctxs for k in CONDITIONS)
            scopes.append(("both conditions pooled", both, both_n))
            for scope, count, n in scopes:
                rows.append(
                    {
                        "run": run_name,
                        "zone": zone,
                        "scope": scope,
                        "count": count,
                        "n": n,
                        "upper_95_one_sided": _upper(n) if count == 0 else None,
                    }
                )
    return rows


# --------------------------------------------------------------------------------------------- #
# 3. Surrogate sensitivity
# --------------------------------------------------------------------------------------------- #


def _surrogate_with_floor(
    base: np.ndarray, delta: float, n_total: int, n_replicates: int, seed: int, floor: float
) -> float:
    """The sealed algorithm of categorical_multinomial_power, with the expected-count floor as a
    parameter. Same RNG calls in the same order, so at floor 1e-12 it must equal the sealed value."""
    base = base / float(base.sum())
    rng = np.random.default_rng(seed)
    alt, _ = _perturb_to_delta_tv(base, delta)
    expected = n_total * base
    safe = np.where(expected > 0.0, expected, floor)
    stats = np.empty(n_replicates, dtype=np.float64)
    for i in range(n_replicates):
        counts = rng.multinomial(n_total, base)
        stats[i] = float(np.sum((counts - expected) ** 2 / safe))
    critical = float(np.quantile(stats, 1.0 - ALPHA_SIGNIFICANCE))
    rejections = 0
    for _ in range(n_replicates):
        counts = rng.multinomial(n_total, alt)
        if float(np.sum((counts - expected) ** 2 / safe)) > critical:
            rejections += 1
    return rejections / n_replicates


def _pooled_off_counts(run_name: str, grid: dict[str, Any]) -> list[int]:
    zones = tuple(grid["zones"])
    run = load_run(RUN_FILES[run_name], zones)
    return [sum(run.zone_counts[(c, "off")][z] for c in grid["context_ids"]) for z in range(len(zones))]


def surrogate_sensitivity(grid: dict[str, Any]) -> dict[str, Any]:
    spec = grid["side_analyses"]["surrogate_sensitivity"]
    m, k, reps, seed = int(spec["m_draws"]), int(spec["k_contexts"]), int(spec["n_replicates"]), int(spec["seed"])
    pseudo_rows: list[dict[str, Any]] = []
    for run_name in ("completed", "control"):
        counts = _pooled_off_counts(run_name, grid)
        for a_text in spec["pseudocounts"]:
            a = Fraction(a_text)
            total = sum(counts) + a * len(counts)
            dist = [float((c + a) / total) for c in counts]
            for delta_text in spec["deltas"]:
                power = categorical_multinomial_power(
                    base_dist=dist, delta_tv=float(delta_text), m_draws=m, k_contexts=k,
                    pooling=True, n_replicates=reps, seed=seed,
                ).power
                pseudo_rows.append(
                    {"run": run_name, "pseudocount": a_text, "delta_tv": delta_text,
                     "power": _q(power), "passes_gate": bool(power >= 0.8)}
                )
    floor_rows: list[dict[str, Any]] = []
    counts = np.asarray(_pooled_off_counts("completed", grid), dtype=np.float64)
    for floor_text in spec["floors"]:
        for delta_text in spec["deltas"]:
            power = _surrogate_with_floor(counts, float(delta_text), m * k, reps, seed, float(floor_text))
            floor_rows.append(
                {"run": "completed", "floor": floor_text, "delta_tv": delta_text,
                 "power": _q(power), "passes_gate": bool(power >= 0.8)}
            )
    return {"pseudocount": pseudo_rows, "floor": floor_rows}


def surrogate_alongside(grid: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for base in build_bases(grid):
        dist = [float(p) for p in base.pooled]
        for delta_text in grid["deltas"][1:]:
            power = categorical_multinomial_power(
                base_dist=dist, delta_tv=float(delta_text), m_draws=int(grid["m_draws"]),
                k_contexts=int(grid["k_contexts"]), pooling=True,
            ).power
            rows.append({"base": base.id, "delta_tv": delta_text, "surrogate_power": _q(power)})
    return rows


# --------------------------------------------------------------------------------------------- #


def self_test(grid: dict[str, Any]) -> int:
    problems: list[str] = []
    spec = grid["side_analyses"]["surrogate_sensitivity"]
    counts = np.asarray(_pooled_off_counts("completed", grid), dtype=np.float64)
    for delta_text in spec["deltas"]:
        sealed = categorical_multinomial_power(
            base_dist=list(counts / counts.sum()), delta_tv=float(delta_text), m_draws=300,
            k_contexts=8, pooling=True, n_replicates=int(spec["n_replicates"]), seed=int(spec["seed"]),
        ).power
        mine = _surrogate_with_floor(counts, float(delta_text), 2400, int(spec["n_replicates"]), int(spec["seed"]), 1e-12)
        if sealed != mine:
            problems.append(f"floor re-implementation differs at delta {delta_text}: {mine} != {sealed}")
    derived = json.loads((REPO_ROOT / "data" / "derived" / "collapse-and-floor.json").read_text("utf-8"))
    shipped = {repr(float(r["delta_tv"])): r["power"] for r in derived["power_sweep"]}
    for delta_text in spec["deltas"]:
        power = categorical_multinomial_power(
            base_dist=[float(Fraction(int(c), int(counts.sum()))) for c in counts],
            delta_tv=float(delta_text), m_draws=300, k_contexts=8, pooling=True,
            n_replicates=int(spec["n_replicates"]), seed=int(spec["seed"]),
        ).power
        if _q(power) != shipped[repr(float(delta_text))]:
            problems.append(f"a=0 row differs from collapse-and-floor.json at {delta_text}")
    if _upper(2276) != "0.00131536":  # -expm1(log(0.05)/2276) = 0.0013153609871
        problems.append(f"upper bound for 0/2276 is {_upper(2276)}")
    if problems:
        for p in problems:
            print(f"[side] FAIL {p}", file=sys.stderr)
        return 1
    print("[side] self-test OK: floor re-implementation bit-identical at 1e-12; a=0 equals "
          "collapse-and-floor.json; 0/2276 bound = 0.00131536")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    grid = load_grid()
    if args.self_test:
        return self_test(grid)
    if args.out is None:
        sys.exit("[side] --out is required")
    commit = declaration_commit()
    print(f"[side] declaration {commit}")
    result = {
        "schema": "cds-autopsy-side-1",
        "concentration_and_null_mean": concentration(grid),
        "empty_cell_bounds": empty_cell_bounds(grid),
        "surrogate_sensitivity": surrogate_sensitivity(grid),
        "surrogate_alongside": surrogate_alongside(grid),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"[side] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
