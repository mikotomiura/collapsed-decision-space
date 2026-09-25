#!/usr/bin/env python3
"""Summarise the post hoc simulation (B3) and apply the reading rules declared in ``grid.json``.

Reads ``data/posthoc/pipeline-replicates.tsv`` (one line per replicate) and
``data/posthoc/side-analyses.json`` and writes, under ``data/posthoc/``:

- ``pipeline-summary.json``: per cell, integer counts and the rates derived from them, with
  Wilson 95% intervals; the reading rules applied mechanically (Type-I labels, the smallest declared
  delta reaching 0.8, the sentence form at the registered delta)
- ``pipeline.md`` and ``side-analyses.md``: the same, as tables. Every declared cell appears,
  including the infeasible ones and the aliases
- ``manifest.json``: the digests that tie these outputs to the declared grid and the sealed files

Nothing here draws a random number. Floats are rounded to six decimals, the files are written with
``\\n`` line endings, and the outputs are compared byte for byte across two operating systems.

Usage:  python analysis/autopsy/render.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from _common import (
    DECLARATION_TAG,
    GRID_PATH,
    POSTHOC_DIR,
    REPO_ROOT,
    SEALED_INPUTS,
    declaration_commit,
    load_grid,
    sha256_file,
)

import numpy as np  # noqa: E402
from simulate import SEEDVAR_CELL, _state  # noqa: E402

Z = 1.959963984540054
DP = 6
BRANCHES: tuple[str, ...] = ("R4", "R3", "R1", "R2", "die", "none")
REGISTERED_DELTA = "0.10"
DETECTED = "CHANNEL_CONFORMANCE_DETECTED"


def _q(value: float) -> float:
    return round(float(value), DP)


def wilson_raw(k: int, n: int) -> tuple[float, float]:
    """Unrounded Wilson 95% interval. Classifications use this; only the display is rounded."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> dict[str, Any]:
    low, high = wilson_raw(k, n)
    return {
        "k": k, "n": n, "rate": _q(k / n) if n else None,
        "wilson_low": _q(low), "wilson_high": _q(high),
    }


def summarise(lines: list[str]) -> dict[str, dict[str, Any]]:
    header = lines[0].split("\t")
    by_cell: dict[str, list[dict[str, str]]] = {}
    for line in lines[1:]:
        row = dict(zip(header, line.split("\t"), strict=True))
        by_cell.setdefault(row["cell"], []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for cell, rows in by_cell.items():
        n = len(rows)
        if sorted(int(r["rep"]) for r in rows) != list(range(n)):
            raise ValueError(f"{cell}: replicates are not 0..{n - 1}")
        branches = Counter(r["branch"] for r in rows)
        r2 = [r for r in rows if r["branch"] == "R2"]
        tv_hit = lambda r: r["tv_bar"] != "NA" and float(r["tv_bar"]) >= 0.1  # noqa: E731
        rej = lambda r: r["permutation_reject"] == "1"  # noqa: E731
        tested = [r for r in rows if r["permutation_reject"] != "NA"]
        tvs = [float(r["tv_bar"]) for r in rows if r["tv_bar"] != "NA"]
        out[cell] = {
            "replicates": n,
            "branch_counts": {b: branches.get(b, 0) for b in BRANCHES},
            "r2": rate(len(r2), n),
            "r2_split": {
                "reject_only": sum(1 for r in r2 if rej(r) and not tv_hit(r)),
                "tv_bar_only": sum(1 for r in r2 if tv_hit(r) and not rej(r)),
                "both": sum(1 for r in r2 if rej(r) and tv_hit(r)),
            },
            "reject_unconditional": rate(sum(1 for r in rows if rej(r)), n),
            "reject_given_tested": rate(sum(1 for r in tested if rej(r)), len(tested)),
            "detected": rate(sum(1 for r in rows if r["verdict"] == DETECTED), n),
            "test_reject": rate(sum(1 for r in rows if r["test_reject"] == "1"), n),
            "effective_k": dict(sorted(Counter(r["effective_k"] for r in rows).items())),
            "mean_tv_bar": _q(math.fsum(tvs) / len(tvs)) if tvs else None,
        }
    return out


def type_i_label(r: dict[str, Any]) -> str:
    low, high = wilson_raw(r["k"], r["n"])
    if high < 0.05:
        return "conservative"
    if low > 0.05:
        return "liberal"
    return "compatible"


QUANTITIES: tuple[str, ...] = ("r2", "test_reject")


def apply_reading_rules(
    cells: list[Any], summary: dict[str, dict[str, Any]], grid: dict[str, Any]
) -> dict[str, Any]:
    source = {c.id: (c.alias_of or c.id) for c in cells}
    type_i = {
        q: {
            b["id"]: {
                **summary[f"{b['id']}|null|0"][q],
                "label": type_i_label(summary[f"{b['id']}|null|0"][q]),
            }
            for b in grid["bases"]
        }
        for q in QUANTITIES
    }
    seedvar = summary.get(SEEDVAR_CELL)
    surface: list[dict[str, Any]] = []
    registered: list[dict[str, Any]] = []
    for b in grid["bases"]:
        for direction in grid["replicates"]["alternative_directions"][b["id"]]:
            entry: dict[str, Any] = {"base": b["id"], "direction": direction}
            for q in QUANTITIES:
                smallest_point = smallest_lower = None
                for delta in grid["deltas"][1:]:
                    cell = next(c for c in cells if c.id == f"{b['id']}|{direction}|{delta}")
                    if cell.status == "infeasible":
                        continue
                    r = summary[source[cell.id]][q]
                    if smallest_point is None and r["k"] / r["n"] >= 0.8:
                        smallest_point = delta
                    if smallest_lower is None and wilson_raw(r["k"], r["n"])[0] >= 0.8:
                        smallest_lower = delta
                entry[q] = {
                    "smallest_delta_point_estimate_at_least_0_8": smallest_point,
                    "smallest_delta_wilson_low_at_least_0_8": smallest_lower,
                }
            surface.append(entry)
            if b["id"] == "C":
                cell = next(c for c in cells if c.id == f"C|{direction}|{REGISTERED_DELTA}")
                if cell.status == "infeasible":
                    registered.append({"direction": direction, "status": "infeasible"})
                    continue
                s = summary[source[cell.id]]
                registered.append(
                    {"direction": direction, "status": "run", "r2": s["r2"],
                     "test_reject": s["test_reject"], "branch_counts": s["branch_counts"]}
                )
    return {
        "type_i": type_i,
        "type_i_with_per_replicate_scorer_seed": (
            {q: {**seedvar[q], "label": type_i_label(seedvar[q])} for q in QUANTITIES}
            if seedvar else None
        ),
        "rate_surface": surface,
        "registered_delta_on_C": registered,
    }


def _fmt_rate(r: dict[str, Any]) -> str:
    return f"{r['k']}/{r['n']} = `{r['rate']!r}` [{r['wilson_low']!r}, {r['wilson_high']!r}]"


def render_pipeline_md(cells: list[Any], summary: dict[str, Any], rules: dict[str, Any],
                       side: dict[str, Any], grid: dict[str, Any]) -> str:
    surrogate = {(r["base"], r["delta_tv"]): r["surrogate_power"] for r in side["surrogate_alongside"]}
    labels = {b["id"]: b["label"] for b in grid["bases"]}
    out = [
        "# Simulated operating characteristics of the sealed pipeline (post hoc)",
        "",
        "Generated by `analysis/autopsy/render.py` from `data/posthoc/pipeline-replicates.tsv`.",
        "Do not edit by hand. Grid, seeds, replicate counts and reading rules were declared in",
        "`analysis/autopsy/grid.json` before the first full run (`analysis/autopsy/DECLARATION.md`).",
        "A property of the design under assumed channel-off bases, not an estimate of any effect of the channel.",
        "",
        "`P(R2)` is the rate at which the sealed rules, applied in the sealed order without R5, reach R2:",
        "an operating characteristic of the pipeline. `P(test_reject)` is the rejection rate of the sealed",
        "stratified permutation test applied to all eight contexts with no gate in front of it.",
        "Rates are k/n with a Wilson 95% interval. `surrogate` is the R3 surrogate at the same delta",
        "against the base pooled over the eight contexts.",
        "",
        "## Type-I (delta = 0)",
        "",
        "| Base | P(R2) | label | P(test_reject) | label |",
        "|---|---|---|---|---|",
    ]
    for b in grid["bases"]:
        t = rules["type_i"]["r2"][b["id"]]
        u = rules["type_i"]["test_reject"][b["id"]]
        out.append(
            f"| `{b['id']}` {labels[b['id']]} | {_fmt_rate(t)} | {t['label']} | "
            f"{_fmt_rate(u)} | {u['label']} |"
        )
    sv = rules["type_i_with_per_replicate_scorer_seed"]
    if sv:
        out.append(
            f"| `C`, scorer seed varied per replicate | {_fmt_rate(sv['r2'])} | "
            f"{sv['r2']['label']} | {_fmt_rate(sv['test_reject'])} | {sv['test_reject']['label']} |"
        )
    out += ["", "## Registered delta 0.10 on base C", "",
            "| Direction | P(R2) | P(test_reject) | R4 / R3 / R1 / R2 / die |", "|---|---|---|---|"]
    for r in rules["registered_delta_on_C"]:
        if r["status"] == "infeasible":
            out.append(f"| {r['direction']} | infeasible | infeasible | - |")
        else:
            bc = r["branch_counts"]
            out.append(
                f"| {r['direction']} | {_fmt_rate(r['r2'])} | {_fmt_rate(r['test_reject'])} | "
                f"{bc['R4']} / {bc['R3']} / {bc['R1']} / {bc['R2']} / {bc['die']} |"
            )
    out += ["", "## Smallest declared delta at which the rate reaches 0.8", "",
            "| Base | Direction | P(R2): estimate / Wilson lower | "
            "P(test_reject): estimate / Wilson lower |",
            "|---|---|---|---|"]
    none_text = "not reached in the declared grid"
    for r in rules["rate_surface"]:
        cols = []
        for q in QUANTITIES:
            e = r[q]
            cols.append(
                f"{e['smallest_delta_point_estimate_at_least_0_8'] or none_text} / "
                f"{e['smallest_delta_wilson_low_at_least_0_8'] or none_text}"
            )
        out.append(f"| `{r['base']}` | {r['direction']} | {cols[0]} | {cols[1]} |")
    out += ["", "## Every declared cell", "",
            "| Cell | support | n | P(R2) | R2: reject only / tv only / both | P(test_reject) | "
            "reject (all) | reject (tested) | DETECTED | R4 / R3 / R1 / R2 / die | mean tv_bar | "
            "surrogate |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cell in cells:
        if cell.status == "infeasible":
            out.append(f"| `{cell.id}` | - | - | infeasible: a source cell holds less than delta in some context | | | | | | | | |")
            continue
        src = cell.alias_of or cell.id
        s = summary[src]
        sp = s["r2_split"]
        bc = s["branch_counts"]
        name = f"`{cell.id}`" + (f" (= `{cell.alias_of}`)" if cell.alias_of else "")
        sur = surrogate.get((cell.base, cell.delta), "-") if cell.delta != "0" else "-"
        out.append(
            f"| {name} | {'changes' if cell.support_change else 'kept'} | {s['replicates']} | "
            f"{_fmt_rate(s['r2'])} | {sp['reject_only']} / {sp['tv_bar_only']} / {sp['both']} | "
            f"{_fmt_rate(s['test_reject'])} | `{s['reject_unconditional']['rate']!r}` | `{s['reject_given_tested']['rate']!r}` | "
            f"`{s['detected']['rate']!r}` | {bc['R4']} / {bc['R3']} / {bc['R1']} / {bc['R2']} / {bc['die']} | "
            f"`{s['mean_tv_bar']!r}` | `{sur!r}` |"
        )
    if SEEDVAR_CELL in summary:
        s = summary[SEEDVAR_CELL]
        out.append(f"| `{SEEDVAR_CELL}` | kept | {s['replicates']} | {_fmt_rate(s['r2'])} | "
                   f"{s['r2_split']['reject_only']} / {s['r2_split']['tv_bar_only']} / {s['r2_split']['both']} | "
                   f"{_fmt_rate(s['test_reject'])} | `{s['reject_unconditional']['rate']!r}` | `{s['reject_given_tested']['rate']!r}` | "
                   f"`{s['detected']['rate']!r}` | - | `{s['mean_tv_bar']!r}` | - |")
    return "\n".join(out) + "\n"


def render_side_md(side: dict[str, Any]) -> str:
    out = [
        "# Side analyses of the post hoc simulation",
        "",
        "Generated by `analysis/autopsy/render.py` from `data/posthoc/side-analyses.json`. Do not edit by hand.",
        "",
        "## Concentration and the null expectation of tv_bar (parsed counts of the completed run)",
        "",
        "| Path | Point | mean H (bits) | mean sum sqrt(p(1-p)) | support | E[tv_bar] null | "
        "null p95 | conditional permutation-null mean | first-order approximation |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in side["concentration_and_null_mean"]:
        out.append(
            f"| {r['path']} | {r['point']} | `{r['mean_entropy_bits']!r}` | `{r['mean_sum_sqrt_pq']!r}` | "
            f"{r['support_size']} | `{r['null_mean_tv_bar']!r}` | `{r['null_p95_tv_bar']!r}` | "
            f"`{r['conditional_permutation_null_mean']!r}` | `{r['first_order_approximation']!r}` |"
        )
    out += ["", "## One-sided 95% upper bounds on empty cells (0 of n)", "",
            "| Run | Zone | Scope | count / n | upper bound |", "|---|---|---|---|---|"]
    for r in side["empty_cell_bounds"]:
        bound = f"`{r['upper_95_one_sided']}`" if r["upper_95_one_sided"] else "not empty"
        out.append(f"| {r['run']} | `{r['zone']}` | {r['scope']} | {r['count']} / {r['n']} | {bound} |")
    out += ["", "## R3 surrogate: pseudocount on the base counts", "",
            "| Run | pseudocount | delta_tv | power | passes 0.8 |", "|---|---|---|---|---|"]
    for r in side["surrogate_sensitivity"]["pseudocount"]:
        out.append(f"| {r['run']} | {r['pseudocount']} | {r['delta_tv']} | `{r['power']!r}` | "
                   f"{'yes' if r['passes_gate'] else 'no'} |")
    out += ["", "## R3 surrogate: floor under an expected count of zero (completed run, pseudocount 0)", "",
            "| floor | delta_tv | power | passes 0.8 |", "|---|---|---|---|"]
    for r in side["surrogate_sensitivity"]["floor"]:
        out.append(f"| {r['floor']} | {r['delta_tv']} | `{r['power']!r}` | {'yes' if r['passes_gate'] else 'no'} |")
    return "\n".join(out) + "\n"


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=POSTHOC_DIR)
    args = parser.parse_args(argv)
    # The committed outputs are bound to the declaration. A scratch directory (used to exercise the
    # tables on a hand-built record) is not, and its manifest says so with a null commit.
    bound = args.dir.resolve() == POSTHOC_DIR.resolve()
    commit = declaration_commit() if bound else None
    grid = load_grid()
    cells = _state()["cells"]
    tsv = args.dir / "pipeline-replicates.tsv"
    side_path = args.dir / "side-analyses.json"
    lines = tsv.read_text(encoding="utf-8").splitlines()
    summary = summarise(lines)
    expected = {c.id for c in cells if c.status == "run"} | {SEEDVAR_CELL}
    if set(summary) != expected:
        sys.exit(f"[render] FAIL: cells in the record {sorted(set(summary) ^ expected)} differ from the grid")
    for c in cells:
        if c.status == "run" and summary[c.id]["replicates"] != c.replicates:
            sys.exit(f"[render] FAIL: {c.id} has {summary[c.id]['replicates']} replicates, declared {c.replicates}")
    side = json.loads(side_path.read_text(encoding="utf-8"))
    rules = apply_reading_rules(cells, summary, grid)
    payload = {
        "schema": "cds-autopsy-summary-1",
        "cells": [
            {"id": c.id, "base": c.base, "direction": c.direction, "delta": c.delta, "status": c.status,
             "alias_of": c.alias_of, "support_change": c.support_change,
             "summary": summary.get(c.alias_of or c.id) if c.status != "infeasible" else None}
            for c in cells
        ] + [{"id": SEEDVAR_CELL, "summary": summary[SEEDVAR_CELL]}],
        "reading_rules": rules,
    }
    _write(args.dir / "pipeline-summary.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _write(args.dir / "pipeline.md", render_pipeline_md(cells, summary, rules, side, grid))
    _write(args.dir / "side-analyses.md", render_side_md(side))

    manifest = {
        "schema": "cds-autopsy-manifest-1",
        "declaration_tag": DECLARATION_TAG,
        "declaration_commit": commit,
        "grid_sha256": sha256_file(GRID_PATH),
        "sealed_sha256": {p: sha256_file(REPO_ROOT / p) for p in SEALED_INPUTS},
        "numpy": np.__version__,
        "outputs_sha256": {
            name: sha256_file(args.dir / name)
            for name in ("pipeline-replicates.tsv", "side-analyses.json", "pipeline-summary.json")
        },
    }
    _write(args.dir / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"[render] wrote pipeline-summary.json, pipeline.md, side-analyses.md, manifest.json in {args.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
