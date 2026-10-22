#!/usr/bin/env python3
"""Simulate, on the primary arm's channel-off base, what the entropy floor's firing withheld (post hoc).

The declared simulation of the sealed pipeline (``analysis/autopsy/``) left the primary arm's base
out, because the entropy floor stops the sealed pipeline there. This file asks the question that
leaves open: on that base, would a pipeline whose measurability gate reads support -- a context is
admitted when its pooled zone distribution occupies at least two zones -- reach R2 at the
registered shift? It runs, on the same draws, the sealed pipeline, that counterfactual pipeline,
and the sealed permutation test with no gate in front of it.

Everything is called as the declared simulation calls it: the vendored scorer with its defaults,
the sealed rules through the sealed evaluator, the declared directions, deltas, roles and draws.
The one difference is the counterfactual gate, made by replacing the scorer's module constant
``H_MIN_BITS`` at run time for the counterfactual call only. No file of the apparatus, the seal or
the declared simulation is changed.

What this establishes: rates of the two pipelines and of the test on an assumed truth taken from
the primary arm's channel-off draws, at the declared directions, deltas and numbers of draws.
What it does not: anything about the channel. The primary arm's channel-on draws are not read, and
nothing here compares the two conditions of any run.

Modes:
  --self-test            fidelity checks (no rate of the declared cells is computed)
  --run --out FILE       the declared grid (refuses unless the declaration binding holds)
  --render FILE --out    the tables and the case of the reading rules, from a --run output
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import multiprocessing
import subprocess
import sys
from fractions import Fraction
from math import sqrt
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "autopsy"))

from _common import (  # noqa: E402  (sets the apparatus and scripts paths)
    CONDITIONS,
    Base,
    apply_moves,
    load_run,
    moves_for,
    roles_of,
    total_variation,
)

import numpy as np  # noqa: E402
import apply_decision_rules as adr  # noqa: E402
import simulate as b3  # noqa: E402
from erre_sandbox.integration.embodied import bank_scorer  # noqa: E402
from erre_sandbox.integration.embodied.bank_power import POWER_SEED_DEFAULT  # noqa: E402

GRID_PATH = HERE / "grid.json"
B3_GRID_PATH = REPO_ROOT / "analysis" / "autopsy" / "grid.json"
DECLARATION_TAG = "autopsy-primary-declared"
#: Files whose bytes at the declaration tag bind every output of --run and --render.
DECLARED_FILES: tuple[str, ...] = (
    "analysis/autopsy-primary/grid.json",
    "analysis/autopsy-primary/DECLARATION.md",
    "analysis/autopsy-primary/simulate_primary.py",
    "analysis/autopsy/grid.json",
    "analysis/autopsy/_common.py",
    "analysis/autopsy/simulate.py",
    "data/prospective/primary/run_annotation.jsonl",
    "seal/decision-rules.json",
    "analysis/scripts/apply_decision_rules.py",
    "analysis/apparatus/erre_sandbox/integration/embodied/bank_scorer.py",
    "analysis/apparatus/erre_sandbox/integration/embodied/bank_power.py",
    "env/uv.lock",
)
SUPPORT_FLOOR = 1e-9
COLUMNS: tuple[str, ...] = (
    "cell",
    "rep",
    "sealed_branch",
    "sealed_rho_hat",
    "support_branch",
    "support_rho_hat",
    "support_power",
    "support_tv_bar",
    "support_permutation_reject",
    "test_reject",
)


# --------------------------------------------------------------------------------------------- #
# The grid
# --------------------------------------------------------------------------------------------- #


def load() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        json.loads(GRID_PATH.read_text(encoding="utf-8")),
        json.loads(B3_GRID_PATH.read_text(encoding="utf-8")),
    )


def build_base(grid: dict[str, Any], b3_grid: dict[str, Any]) -> Base:
    """Base P, built exactly as the declared simulation builds its empirical bases."""
    zones = tuple(b3_grid["zones"])
    ctxs = tuple(b3_grid["context_ids"])
    m_draws = int(b3_grid["m_draws"])
    run = load_run(grid["base"]["none_counts_from"], zones)
    none_counts = {(c, k): run.none_counts[(c, k)] for c in ctxs for k in CONDITIONS}
    off: dict[str, tuple[Fraction, ...]] = {}
    for ctx in ctxs:
        counts = run.zone_counts[(ctx, "off")]
        total = sum(counts)
        off[ctx] = tuple(Fraction(c, total) for c in counts)
    weights = {ctx: m_draws - none_counts[(ctx, "off")] for ctx in ctxs}
    total_weight = sum(weights.values())
    pooled = tuple(
        sum(Fraction(weights[ctx]) * off[ctx][i] for ctx in ctxs) / total_weight
        for i in range(len(zones))
    )
    return Base(
        id=grid["base"]["id"],
        index=int(grid["base"]["index"]),
        off=off,
        none_counts=none_counts,
        pooled=pooled,
    )


def enumerate_cells(grid: dict[str, Any], b3_grid: dict[str, Any], base: Base) -> list[b3.Cell]:
    """The declared cells of base P, by the declared simulation's rules (feasibility, aliases)."""
    ctxs = tuple(b3_grid["context_ids"])
    reps = grid["replicates"]
    cells = [
        b3.Cell(f"{base.id}|null|0", base.id, "null", "0", int(reps["null"]), "run", None,
                False, dict(base.off))
    ]
    roles = roles_of(base.pooled)
    seen: dict[tuple[str, tuple[tuple[Fraction, ...], ...]], str] = {}
    for direction in grid["directions"]:
        for delta_text in grid["deltas"][1:]:
            delta = Fraction(delta_text)
            cell_id = f"{base.id}|{direction}|{delta_text}"
            on: dict[str, tuple[Fraction, ...]] = {}
            feasible = True
            for position, ctx in enumerate(ctxs):
                moved = apply_moves(base.off[ctx], moves_for(direction, roles, position, delta))
                if moved is None:
                    feasible = False
                    break
                if total_variation(base.off[ctx], moved) != delta:
                    raise AssertionError(f"{cell_id} {ctx}: TV is not delta")
                on[ctx] = moved
            if not feasible:
                cells.append(b3.Cell(cell_id, base.id, direction, delta_text, 0, "infeasible",
                                     None, False, None))
                continue
            support_change = any(
                on[ctx][i] > 0 and base.off[ctx][i] == 0
                for ctx in ctxs
                for i in range(len(b3_grid["zones"]))
            )
            key = (delta_text, tuple(on[ctx] for ctx in ctxs))
            if key in seen:
                cells.append(b3.Cell(cell_id, base.id, direction, delta_text, 0, "alias",
                                     seen[key], support_change, None))
                continue
            seen[key] = cell_id
            cells.append(b3.Cell(cell_id, base.id, direction, delta_text,
                                 int(reps["alternative"]), "run", None, support_change, on))
    return cells


# --------------------------------------------------------------------------------------------- #
# One replicate
# --------------------------------------------------------------------------------------------- #

_STATE: dict[str, Any] = {}


def _state() -> dict[str, Any]:
    if not _STATE:
        grid, b3_grid = load()
        base = build_base(grid, b3_grid)
        _STATE.update(
            grid=grid,
            b3_grid=b3_grid,
            base=base,
            cells=enumerate_cells(grid, b3_grid, base),
            rules=adr._load_rules(REPO_ROOT / "seal" / "decision-rules.json"),
            manifest={
                "run": {
                    "m_draws": int(b3_grid["m_draws"]),
                    "k_contexts": int(b3_grid["k_contexts"]),
                    "context_ids": list(b3_grid["context_ids"]),
                },
                "env_pins": {"think": False},
            },
        )
    return _STATE


def score(rows: list[dict[str, Any]], floor: float | None) -> dict[str, Any]:
    """The vendored scorer with its defaults; ``floor`` replaces H_MIN_BITS for this call only."""
    manifest = _state()["manifest"]
    if floor is None:
        verdict = bank_scorer.score_bank_annotation(annotation_rows=rows, manifest=manifest)
        return bank_scorer.verdict_to_dict(verdict)
    sealed = bank_scorer.H_MIN_BITS
    bank_scorer.H_MIN_BITS = floor
    try:
        verdict = bank_scorer.score_bank_annotation(annotation_rows=rows, manifest=manifest)
    finally:
        bank_scorer.H_MIN_BITS = sealed
    return bank_scorer.verdict_to_dict(verdict)


def one(cell: b3.Cell, rep: int, uniforms: np.ndarray) -> str:
    state = _state()
    b3_grid = state["b3_grid"]
    assert cell.on is not None
    labels = b3.draw_labels(b3_grid, state["base"], cell.on, uniforms)
    rows = b3.annotation_rows(b3_grid, labels)
    sealed = score(rows, None)
    support = score(rows, SUPPORT_FLOOR)
    with contextlib.redirect_stderr(io.StringIO()):
        sealed_branch = b3.evaluate_branch(sealed, state["rules"])
        support_branch = b3.evaluate_branch(support, state["rules"])
    alone = b3.test_alone_reject(labels, support, b3_grid, POWER_SEED_DEFAULT)
    values = (
        cell.id, rep, sealed_branch, sealed["rho_hat"], support_branch, support["rho_hat"],
        support["power"], support["tv_bar"], support["permutation_reject"], alone,
    )
    return "\t".join(b3._fmt(v) for v in values)


def run_rep(rep: int) -> list[tuple[str, int, str]]:
    state = _state()
    grid, b3_grid, base = state["grid"], state["b3_grid"], state["base"]
    uniforms = b3.uniforms_for(int(grid["master_seed"]), base, rep, b3_grid)
    return [
        (cell.id, rep, one(cell, rep, uniforms))
        for cell in state["cells"]
        if cell.status == "run" and rep < cell.replicates
    ]


# --------------------------------------------------------------------------------------------- #
# The declaration binding
# --------------------------------------------------------------------------------------------- #


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, check=False)


def binding_problems() -> list[str]:
    """The tag exists, is an ancestor of HEAD, and every declared file is as it was at the tag."""
    if _git("rev-parse", "--verify", "--quiet", f"refs/tags/{DECLARATION_TAG}").returncode:
        return [f"the declaration tag {DECLARATION_TAG} does not exist"]
    if _git("merge-base", "--is-ancestor", DECLARATION_TAG, "HEAD").returncode:
        return [f"{DECLARATION_TAG} is not an ancestor of HEAD"]
    problems = []
    for relative in DECLARED_FILES:
        declared = _git("show", f"{DECLARATION_TAG}:{relative}")
        current = (REPO_ROOT / relative).read_bytes() if (REPO_ROOT / relative).is_file() else None
        if declared.returncode or current != declared.stdout:
            problems.append(f"{relative} differs from its copy at {DECLARATION_TAG}")
    return problems


# --------------------------------------------------------------------------------------------- #
# Self-test, run, render
# --------------------------------------------------------------------------------------------- #


def self_test() -> int:
    """Fidelity of the wrapper and of the counterfactual gate. No declared cell is computed."""
    problems: list[str] = []
    state = _state()
    base = state["base"]
    # (a) base P is the primary arm's channel-off counts, as Table 6 of the manuscript describes.
    pooled_support = sum(1 for p in base.pooled if p > 0)
    print(f"[primary] (a) base P pooled support = {pooled_support} of 5 zones; "
          f"per-context support = {sorted({sum(1 for p in d if p > 0) for d in base.off.values()})}")
    if pooled_support != 3:
        problems.append(f"(a) the primary arm's channel-off base should occupy 3 zones, not {pooled_support}")
    # (b) the replacement of H_MIN_BITS is confined to the call: the sealed value is back after it.
    rows = b3.annotation_rows(
        state["b3_grid"],
        b3.draw_labels(state["b3_grid"], base, base.off,
                       b3.uniforms_for(1, base, 0, state["b3_grid"])),
    )
    score(rows, SUPPORT_FLOOR)
    if bank_scorer.H_MIN_BITS != 0.5:
        problems.append(f"(b) H_MIN_BITS is {bank_scorer.H_MIN_BITS} after the counterfactual call")
    # (c) on the completed run's shipped annotation, where every context clears both floors, the
    # two pipelines give the same verdict, field by field except the reported threshold.
    shipped = [
        json.loads(line)
        for line in (REPO_ROOT / "data" / "raw" / "bank_annotation.jsonl").read_text("utf-8").splitlines()
    ]
    a, b = score(shipped, None), score(shipped, SUPPORT_FLOOR)
    differ = sorted(k for k in a if a[k] != b[k] and k != "thresholds")
    if differ:
        problems.append(f"(c) sealed and support pipelines differ on the completed run: {differ}")
    print(f"[primary] (c) completed run: sealed and support verdicts agree outside thresholds: {not differ}")
    # (d) cells: feasibility and aliases, without drawing anything.
    status: dict[str, int] = {}
    for cell in state["cells"]:
        status[cell.status] = status.get(cell.status, 0) + 1
    print(f"[primary] (d) cells: {status}")
    if problems:
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("[primary] self-test OK (no declared cell was computed)")
    return 0


def run(out: Path, workers: int) -> int:
    problems = binding_problems()
    if problems:
        for problem in problems:
            print(f"[primary] refuse: {problem}", file=sys.stderr)
        return 1
    state = _state()
    top = max(c.replicates for c in state["cells"] if c.status == "run")
    records: list[tuple[str, int, str]] = []
    if workers <= 1:
        for rep in range(top):
            records.extend(run_rep(rep))
    else:
        with multiprocessing.get_context("spawn").Pool(workers) as pool:
            for part in pool.imap_unordered(run_rep, range(top), chunksize=4):
                records.extend(part)
    order = {cell.id: i for i, cell in enumerate(state["cells"])}
    records.sort(key=lambda r: (order[r[0]], r[1]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\t".join(COLUMNS) + "\n" + "".join(line + "\n" for _, _, line in records),
                   encoding="utf-8", newline="\n")
    print(f"[primary] wrote {out} ({len(records)} records)")
    return 0


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959963984540054
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = `{round(k / n, 6)}` [{round(lo, 6)}, {round(hi, 6)}]"


def render(source: Path, out: Path) -> int:
    problems = binding_problems()
    if problems:
        for problem in problems:
            print(f"[primary] refuse: {problem}", file=sys.stderr)
        return 1
    state = _state()
    lines = source.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    rows = [dict(zip(header, line.split("\t"), strict=True)) for line in lines[1:]]
    by_cell: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_cell.setdefault(row["cell"], []).append(row)
    branches = ("R4", "R3", "R1", "R2", "none", "die")

    def counts(cell_rows: list[dict[str, str]], key: str) -> str:
        return " / ".join(f"{b} {sum(1 for r in cell_rows if r[key] == b)}" for b in branches)

    out_lines = [
        "# What the entropy floor withheld on the primary arm's base (post hoc)",
        "",
        "Generated by `analysis/autopsy-primary/simulate_primary.py --render` from the --run output.",
        "Do not edit by hand. Grid, seeds, replicate counts and reading rules were declared in",
        "`analysis/autopsy-primary/grid.json` before the first full run (tag "
        f"`{DECLARATION_TAG}`). A property of the design under an assumed truth taken from the",
        "primary arm's channel-off draws; not an estimate of any effect of the channel.",
        "",
        "| Cell | n | P(R2), sealed | P(R4), sealed | P(R2), support gate | P(test_reject) | sealed branches | support branches |",
        "|---|---|---|---|---|---|---|---|",
    ]
    at_registered: list[tuple[str, tuple[float, float], tuple[float, float]]] = []
    for cell in state["cells"]:
        if cell.status != "run":
            note = "infeasible" if cell.status == "infeasible" else f"alias of `{cell.alias_of}`"
            out_lines.append(f"| `{cell.id}` | — | {note} | | | | | |")
            continue
        cell_rows = by_cell.get(cell.id, [])
        n = len(cell_rows)
        if n != cell.replicates:
            print(f"[primary] {cell.id}: {n} records, {cell.replicates} declared", file=sys.stderr)
            return 1
        r2s = sum(1 for r in cell_rows if r["sealed_branch"] == "R2")
        r4s = sum(1 for r in cell_rows if r["sealed_branch"] == "R4")
        r2u = sum(1 for r in cell_rows if r["support_branch"] == "R2")
        tr = sum(1 for r in cell_rows if r["test_reject"] == "1")
        out_lines.append(
            f"| `{cell.id}` | {n} | {rate(r2s, n)} | {rate(r4s, n)} | {rate(r2u, n)} | "
            f"{rate(tr, n)} | {counts(cell_rows, 'sealed_branch')} | "
            f"{counts(cell_rows, 'support_branch')} |"
        )
        if cell.delta == "0.10":
            at_registered.append((cell.id, wilson(r2u, n), wilson(r4s, n)))
    # The reading rule, applied mechanically (grid.json, reading_rules[3]): (A) the support
    # pipeline's Wilson lower limit of P(R2) and the sealed P(R4) are both at least 0.8 in every
    # feasible direction; (B) the support pipeline's upper limit is below 0.8 in every one; (C) else.
    sealed_fires = [
        sum(1 for r in by_cell[c] if r["sealed_branch"] == "R4") / len(by_cell[c]) >= 0.8
        for c, _, _ in at_registered
    ]
    if at_registered and all(lo >= 0.8 for _, (lo, _), _ in at_registered) and all(sealed_fires):
        case = "A"
    elif at_registered and all(hi < 0.8 for _, (_, hi), _ in at_registered):
        case = "B"
    else:
        case = "C"
    out_lines += [
        "",
        "Table: Base P, every declared cell. Rates are k/n with Wilson 95% intervals.",
        "",
        f"**Case of the declared reading rule at delta 0.10: {case}.** Feasible directions at 0.10: "
        + ", ".join(f"`{c}`" for c, _, _ in at_registered),
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8", newline="\n")
    print(f"[primary] wrote {out}; case {case}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--render", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--workers", type=int, default=max(1, (multiprocessing.cpu_count() or 2) - 1))
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.run:
        if args.out is None:
            parser.error("--run needs --out")
        return run(args.out, args.workers)
    if args.render:
        if args.out is None:
            parser.error("--render needs --out")
        return render(args.render, args.out)
    parser.error("choose --self-test, --run or --render")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
