#!/usr/bin/env python3
"""Simulate the sealed decision pipeline under known channel-off bases (B3, post hoc).

The pipeline is the one the sealed protocol runs, called as it is: the vendored scorer
``score_bank_annotation`` with its defaults, then the sealed rules of ``seal/decision-rules.json``
through the sealed evaluator's own ``_load_rules`` and ``_evaluate_group``. Nothing in the
apparatus, the seal or the evaluator is re-implemented or changed; they are imported and called.
What this file adds is the synthetic annotation they are called on, built from the grid declared in
``analysis/autopsy/grid.json`` before the first full run (see ``DECLARATION.md``).

What this establishes: how often the sealed pipeline reaches each branch when the channel-off
distribution of every context is known and the channel-on distribution is moved from it by a
declared total-variation distance in a declared direction.
What it does not: anything about the channel. The bases are taken from runs, but the shifts are
put there by this script. A rate here is a property of the design under an assumed truth.

Modes:
  --self-test            fidelity checks (no rate is computed)
  --smoke --out DIR      timing only, with a master seed that is not the declared one
  --run --out FILE       the declared grid (refuses unless the declaration binding holds)
  --check-rep0 FILE      recompute replicate 0 of every cell and compare with FILE byte for byte
  --merge FILE... --out  concatenate shard outputs into the canonical order
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import multiprocessing
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from _common import (
    CONDITIONS,
    REPO_ROOT,
    Base,
    apply_moves,
    build_bases,
    cdf_of,
    declaration_commit,
    draw,
    load_grid,
    moves_for,
    roles_of,
    total_variation,
)

import numpy as np  # noqa: E402  (after _common, which sets sys.path)
import apply_decision_rules as adr  # noqa: E402
from erre_sandbox.integration.embodied.bank_power import (  # noqa: E402
    _perturb_to_delta_tv,
)
from erre_sandbox.integration.embodied.bank_power import (  # noqa: E402
    N_REPLICATES_DEFAULT,
    POWER_SEED_DEFAULT,
)
from erre_sandbox.integration.embodied.bank_scorer import (  # noqa: E402
    _permutation_test,
    _tv_from_labels,
    score_bank_annotation,
    verdict_to_dict,
)

COLUMNS: tuple[str, ...] = (
    "cell",
    "rep",
    "branch",
    "verdict",
    "rho_hat",
    "effective_k",
    "power",
    "tv_bar",
    "permutation_reject",
    "permutation_p_value",
    "test_reject",
)
SEEDVAR_CELL = "C|null|0|seedvar"
SEEDVAR_SPAWN = 99


@dataclass(frozen=True)
class Cell:
    id: str
    base: str
    direction: str  # "null" at delta 0
    delta: str
    replicates: int
    status: str  # run / infeasible / alias
    alias_of: str | None
    support_change: bool
    on: dict[str, tuple[Fraction, ...]] | None


def enumerate_cells(grid: dict[str, Any], bases: list[Base]) -> list[Cell]:
    """Every declared cell, in the canonical order: base, then null, then direction, then delta."""
    ctxs = tuple(grid["context_ids"])
    reps = grid["replicates"]
    cells: list[Cell] = []
    for base in bases:
        cells.append(
            Cell(
                id=f"{base.id}|null|0",
                base=base.id,
                direction="null",
                delta="0",
                replicates=int(reps["null"][base.id]),
                status="run",
                alias_of=None,
                support_change=False,
                on=dict(base.off),
            )
        )
        roles = roles_of(base.pooled)
        seen: dict[tuple[str, tuple[tuple[Fraction, ...], ...]], str] = {}
        for direction in reps["alternative_directions"][base.id]:
            for delta_text in grid["deltas"][1:]:
                delta = Fraction(delta_text)
                cell_id = f"{base.id}|{direction}|{delta_text}"
                on: dict[str, tuple[Fraction, ...]] = {}
                feasible = True
                for position, ctx in enumerate(ctxs):
                    moved = apply_moves(
                        base.off[ctx], moves_for(direction, roles, position, delta)
                    )
                    if moved is None:
                        feasible = False
                        break
                    if total_variation(base.off[ctx], moved) != delta:
                        raise AssertionError(f"{cell_id} {ctx}: TV is not delta")
                    on[ctx] = moved
                if not feasible:
                    cells.append(
                        Cell(cell_id, base.id, direction, delta_text, 0, "infeasible",
                             None, False, None)
                    )
                    continue
                support_change = any(
                    on[ctx][i] > 0 and base.off[ctx][i] == 0
                    for ctx in ctxs
                    for i in range(len(grid["zones"]))
                )
                key = (delta_text, tuple(on[ctx] for ctx in ctxs))
                if key in seen:
                    cells.append(
                        Cell(cell_id, base.id, direction, delta_text, 0, "alias",
                             seen[key], support_change, None)
                    )
                    continue
                seen[key] = cell_id
                cells.append(
                    Cell(
                        cell_id, base.id, direction, delta_text,
                        int(reps["alternative"][base.id]), "run", None, support_change, on,
                    )
                )
    return cells


# --------------------------------------------------------------------------------------------- #
# One replicate of one base: build the annotation, score it, apply the sealed rules
# --------------------------------------------------------------------------------------------- #

_STATE: dict[str, Any] = {}


def _state() -> dict[str, Any]:
    if not _STATE:
        grid = load_grid()
        bases = build_bases(grid)
        _STATE["grid"] = grid
        _STATE["bases"] = {b.id: b for b in bases}
        _STATE["cells"] = enumerate_cells(grid, bases)
        _STATE["rules"] = adr._load_rules(REPO_ROOT / "seal" / "decision-rules.json")
        _STATE["manifest"] = {
            "run": {
                "m_draws": int(grid["m_draws"]),
                "k_contexts": int(grid["k_contexts"]),
                "context_ids": list(grid["context_ids"]),
            },
            "env_pins": {"think": False},
        }
    return _STATE


def evaluate_branch(verdict: dict[str, Any], rules: dict[str, Any]) -> str:
    """The sealed rules in the sealed order, R5 left out (it reads the control arm)."""
    by_id = {rule["id"]: rule for rule in rules["rules"]}
    for rule_id in rules["evaluation_order"]:
        if rule_id == "R5":
            continue
        rule = by_id[rule_id]
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                value, _rows = adr._evaluate_group(rule, verdict, "primary")
        except SystemExit:
            return "die"
        outcome = rule["on_pass"] if value else rule["on_fail"]
        if outcome["action"] == "stop":
            return rule_id
    return "none"


Labels = dict[str, tuple[np.ndarray, np.ndarray]]


def draw_labels(
    grid: dict[str, Any], base: Base, on: dict[str, tuple[Fraction, ...]], uniforms: np.ndarray
) -> Labels:
    """Parsed draws of every (context, condition), in mc_index order."""
    m_draws = int(grid["m_draws"])
    out: Labels = {}
    for c_index, ctx in enumerate(grid["context_ids"]):
        pair = []
        for k_index, cond in enumerate(CONDITIONS):
            dist = on[ctx] if cond == "on" else base.off[ctx]
            parsed = base.parsed(ctx, cond, m_draws)
            pair.append(draw(cdf_of(dist), uniforms[c_index, k_index, :parsed]).astype(np.int64))
        out[ctx] = (pair[0], pair[1])
    return out


def annotation_rows(grid: dict[str, Any], labels: Labels) -> list[dict[str, Any]]:
    """The shipped annotation's shape: None at the highest mc_index of each cell."""
    zones = grid["zones"]
    m_draws = int(grid["m_draws"])
    rows: list[dict[str, Any]] = []
    for ctx in grid["context_ids"]:
        for cond, drawn in zip(CONDITIONS, labels[ctx], strict=True):
            for mc in range(m_draws):
                zone = zones[int(drawn[mc])] if mc < drawn.shape[0] else None
                rows.append(
                    {
                        "frozen_ctx_id": ctx,
                        "condition": cond,
                        "mc_index": mc,
                        "pre_bias_destination_zone": zone,
                        "resolved_from": "autopsy_simulation",
                    }
                )
    return rows


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def score_rows(rows: list[dict[str, Any]], seed: int | None = None) -> dict[str, Any]:
    state = _state()
    kwargs: dict[str, Any] = {}
    if seed is not None:
        kwargs["seed"] = seed
    verdict = score_bank_annotation(
        annotation_rows=rows, manifest=state["manifest"], **kwargs
    )
    return verdict_to_dict(verdict)


def test_alone(labels: Labels, grid: dict[str, Any], seed: int) -> tuple[bool, float]:
    """The sealed stratified permutation test on all eight contexts, with no gate in front of it.

    The statistic, the test, the replicate count and alpha are the sealed ones; only the
    context set differs from the scorer's, which keeps the contexts that clear the entropy floor.
    """
    pairs = [labels[ctx] for ctx in sorted(grid["context_ids"])]
    tv_bar = float(np.mean([_tv_from_labels(on, off) for on, off in pairs]))
    return _permutation_test(pairs, tv_bar, n_replicates=N_REPLICATES_DEFAULT, seed=seed)


def test_alone_reject(
    labels: Labels, verdict: dict[str, Any], grid: dict[str, Any], seed: int
) -> bool:
    """Reuses the scorer's own test when it ran on all eight contexts (the same call)."""
    if verdict["effective_k"] == int(grid["k_contexts"]) and verdict["permutation_reject"] is not None:
        return bool(verdict["permutation_reject"])
    return test_alone(labels, grid, seed)[0]


def record_line(
    cell_id: str, rep: int, verdict: dict[str, Any], branch: str, test_reject: bool
) -> str:
    values = (
        cell_id,
        rep,
        branch,
        verdict["verdict"],
        verdict["rho_hat"],
        verdict["effective_k"],
        verdict["power"],
        verdict["tv_bar"],
        verdict["permutation_reject"],
        verdict["permutation_p_value"],
        test_reject,
    )
    return "\t".join(_fmt(v) for v in values)


def uniforms_for(master_seed: int, base: Base, rep: int, grid: dict[str, Any]) -> np.ndarray:
    rng = np.random.default_rng(np.random.SeedSequence(master_seed, spawn_key=(base.index, rep)))
    return rng.random((len(grid["context_ids"]), len(CONDITIONS), int(grid["m_draws"])))


def seedvar_seed(master_seed: int, rep: int) -> int:
    state = np.random.SeedSequence(master_seed, spawn_key=(SEEDVAR_SPAWN, rep)).generate_state(
        1, dtype=np.uint32
    )
    return int(state[0])


def _one(cell_id: str, rep: int, labels: Labels, seed: int | None) -> tuple[str, int, str]:
    state = _state()
    verdict = score_rows(annotation_rows(state["grid"], labels), seed=seed)
    branch = evaluate_branch(verdict, state["rules"])
    alone = test_alone_reject(labels, verdict, state["grid"], POWER_SEED_DEFAULT if seed is None else seed)
    return (cell_id, rep, record_line(cell_id, rep, verdict, branch, alone))


def run_unit(unit: tuple[str, int, int, tuple[str, ...] | None]) -> list[tuple[str, int, str]]:
    """All cells of one (base, replicate). Returns (cell id, rep, line)."""
    base_id, rep, master_seed, only = unit
    state = _state()
    grid = state["grid"]
    base = state["bases"][base_id]
    uniforms = uniforms_for(master_seed, base, rep, grid)
    out: list[tuple[str, int, str]] = []
    for cell in state["cells"]:
        if cell.base != base_id or cell.status != "run" or rep >= cell.replicates:
            continue
        if only is not None and cell.id not in only:
            continue
        assert cell.on is not None
        out.append(_one(cell.id, rep, draw_labels(grid, base, cell.on, uniforms), None))
    side = grid["permutation_seed_side"]
    if (
        base_id == side["base"]
        and rep < int(side["replicates"])
        and (only is None or SEEDVAR_CELL in only)
    ):
        null = next(c for c in state["cells"] if c.id == f"{base_id}|null|0")
        assert null.on is not None
        labels = draw_labels(grid, base, null.on, uniforms)
        out.append(_one(SEEDVAR_CELL, rep, labels, seedvar_seed(master_seed, rep)))
    return out


def all_units(master_seed: int, max_rep: int | None = None) -> list[tuple[str, int, int, None]]:
    state = _state()
    grid = state["grid"]
    units: list[tuple[str, int, int, None]] = []
    for spec in grid["bases"]:
        base_id = spec["id"]
        top = max(
            [c.replicates for c in state["cells"] if c.base == base_id and c.status == "run"]
            + ([int(grid["permutation_seed_side"]["replicates"])]
               if base_id == grid["permutation_seed_side"]["base"] else [])
        )
        if max_rep is not None:
            top = min(top, max_rep)
        units.extend((base_id, rep, master_seed, None) for rep in range(top))
    return units


def cell_order() -> dict[str, int]:
    order = {cell.id: i for i, cell in enumerate(_state()["cells"])}
    order[SEEDVAR_CELL] = len(order)
    return order


def canonical(records: list[tuple[str, int, str]]) -> str:
    order = cell_order()
    records = sorted(records, key=lambda r: (order[r[0]], r[1]))
    return "\t".join(COLUMNS) + "\n" + "".join(line + "\n" for _, _, line in records)


def compute(units: list[Any], workers: int) -> list[tuple[str, int, str]]:
    records: list[tuple[str, int, str]] = []
    if workers <= 1:
        for unit in units:
            records.extend(run_unit(unit))
        return records
    with multiprocessing.get_context("spawn").Pool(workers) as pool:
        for part in pool.imap_unordered(run_unit, units, chunksize=2):
            records.extend(part)
    return records


# --------------------------------------------------------------------------------------------- #
# Self-test (fidelity), smoke (timing), check of replicate 0
# --------------------------------------------------------------------------------------------- #


def self_test() -> int:
    state = _state()
    grid = state["grid"]
    problems: list[str] = []

    # (a) the completed run through the same wrapper reproduces the shipped verdict and reaches R1
    rows = [
        json.loads(line)
        for line in (REPO_ROOT / "data" / "raw" / "bank_annotation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    recomputed = score_rows(rows)
    shipped = json.loads((REPO_ROOT / "data" / "raw" / "cproper-verdict.json").read_text("utf-8"))
    if recomputed != shipped:
        diff = sorted(k for k in set(recomputed) | set(shipped) if recomputed.get(k) != shipped.get(k))
        problems.append(f"(a) the wrapper does not reproduce cproper-verdict.json: {diff}")
    branch = evaluate_branch(recomputed, state["rules"])
    if branch != "R1":
        problems.append(f"(a) the completed run as primary should reach R1, reached {branch}")
    print(f"[autopsy] (a) completed run reproduces cproper-verdict.json; branch as primary = {branch}")

    # (a2) the test with no gate, on the completed run's own labels (row order, None dropped),
    # reproduces the recorded test: all eight contexts clear the floor there, so it is the same call
    zones = grid["zones"]
    shipped_labels: Labels = {}
    for ctx in grid["context_ids"]:
        pair = []
        for cond in CONDITIONS:
            pair.append(np.asarray(
                [zones.index(r["pre_bias_destination_zone"]) for r in rows
                 if r["frozen_ctx_id"] == ctx and r["condition"] == cond
                 and r["pre_bias_destination_zone"] is not None],
                dtype=np.int64,
            ))
        shipped_labels[ctx] = (pair[0], pair[1])
    reject, p_value = test_alone(shipped_labels, grid, POWER_SEED_DEFAULT)
    if reject != shipped["permutation_reject"] or round(p_value, 6) != shipped["permutation_p_value"]:
        problems.append(f"(a2) the ungated test gives reject={reject} p={p_value}")
    print(f"[autopsy] (a2) ungated test on the completed run: reject={reject}, p={round(p_value, 6)}")

    # (b) every run cell is at exact total variation delta in every context (checked while the
    # cells are enumerated; an AssertionError there would have stopped _state()).
    n_run = sum(1 for c in state["cells"] if c.status == "run")
    print(f"[autopsy] (b) {n_run} cells built at exact TV = delta in every context")

    # (c) hi and lo are the indices the sealed perturbation moves, at every declared delta
    for base in state["bases"].values():
        roles = roles_of(base.pooled)
        pooled = np.asarray([float(p) for p in base.pooled])
        for delta_text in grid["deltas"][1:]:
            alt, shift = _perturb_to_delta_tv(pooled, float(delta_text))
            moved = np.flatnonzero(alt != pooled)
            if shift > 0 and sorted(moved.tolist()) != sorted({roles.hi, roles.lo}):
                problems.append(f"(c) base {base.id} delta {delta_text}: sealed moved {moved}")
        print(f"[autopsy] (c) base {base.id}: hi={grid['zones'][roles.hi]} lo={grid['zones'][roles.lo]} "
              f"second={grid['zones'][roles.second]} "
              f"smallest_nonzero={grid['zones'][roles.smallest_nonzero]} "
              f"empty={[grid['zones'][i] for i in roles.empty]}")

    # (d) a synthetic annotation has the shipped shape: 4800 rows, the None counts of its run
    base = state["bases"]["C"]
    uniforms = uniforms_for(1, base, 0, grid)
    labels = draw_labels(grid, base, base.off, uniforms)
    rows = annotation_rows(grid, labels)
    nones = sum(1 for r in rows if r["pre_bias_destination_zone"] is None)
    if len(rows) != 4800 or nones != sum(base.none_counts.values()):
        problems.append(f"(d) synthetic shape: {len(rows)} rows, {nones} None")
    # (d2) when the scorer tested all eight contexts, reusing its result equals computing it anew
    verdict = score_rows(rows)
    if verdict["effective_k"] == 8 and verdict["permutation_reject"] is not None:
        again = test_alone(labels, grid, POWER_SEED_DEFAULT)
        if again != (verdict["permutation_reject"], again[1]) or round(again[1], 6) != verdict["permutation_p_value"]:
            problems.append("(d2) the ungated test differs from the scorer's on eight contexts")
    else:
        problems.append("(d2) the check case did not reach the test on eight contexts")
    # (e) determinism: the same unit twice gives the same lines
    unit = ("G", 0, 1, None)
    if run_unit(unit) != run_unit(unit):
        problems.append("(e) run_unit is not deterministic")
    print("[autopsy] (d)(e) synthetic shape and determinism checked")

    if problems:
        for p in problems:
            print(f"[autopsy] FAIL {p}", file=sys.stderr)
        return 1
    print("[autopsy] self-test OK")
    return 0


def smoke(workers: int) -> int:
    """Timing only. Master seed 1 (not the declared one); three cells, three replicates."""
    only = ("C|null|0", "C|D1|0.10", "U|D3|0.05")
    units = [(cell.split("|")[0], rep, 1, only) for cell in ("C", "U") for rep in range(3)]
    start = time.perf_counter()
    records = compute(units, workers)
    elapsed = time.perf_counter() - start
    print(f"[autopsy] smoke: {len(records)} pipeline calls in {elapsed:.1f} s "
          f"({elapsed / max(len(records), 1):.3f} s per call, workers={workers}); "
          "no rate is computed or shown")
    return 0


def check_rep0(committed: Path, workers: int, master_seed: int) -> int:
    lines = committed.read_text(encoding="utf-8").splitlines()
    wanted = {tuple(line.split("\t")[:2]): line for line in lines[1:] if line.split("\t")[1] == "0"}
    units = [u for u in all_units(master_seed, max_rep=1)]
    got = compute(units, workers)
    problems = 0
    for cell_id, rep, line in got:
        if wanted.get((cell_id, str(rep))) != line:
            problems += 1
            print(f"[autopsy] rep0 mismatch {cell_id}: got {line!r}", file=sys.stderr)
    if len(got) != len(wanted):
        problems += 1
        print(f"[autopsy] rep0: {len(got)} recomputed, {len(wanted)} committed", file=sys.stderr)
    if problems:
        return 1
    print(f"[autopsy] rep0: {len(got)} cells recomputed, byte-identical to {committed.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--check-rep0", type=Path)
    mode.add_argument("--merge", type=Path, nargs="+")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--n-shards", type=int, default=1)
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.smoke:
        return smoke(args.workers)

    grid = load_grid()
    master_seed = int(grid["master_seed"])
    if args.check_rep0 is not None:
        declaration_commit()
        return check_rep0(args.check_rep0, args.workers, master_seed)
    if args.merge is not None:
        records: list[tuple[str, int, str]] = []
        for path in args.merge:
            for line in path.read_text(encoding="utf-8").splitlines()[1:]:
                fields = line.split("\t")
                records.append((fields[0], int(fields[1]), line))
        text = canonical(records)
    else:
        commit = declaration_commit()
        units = [u for i, u in enumerate(all_units(master_seed)) if i % args.n_shards == args.shard]
        start = time.perf_counter()
        text = canonical(compute(units, args.workers))
        print(f"[autopsy] declaration {commit}; shard {args.shard}/{args.n_shards}: "
              f"{len(units)} units in {time.perf_counter() - start:.0f} s")
    if args.out is None:
        sys.exit("[autopsy] --out is required")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"[autopsy] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
