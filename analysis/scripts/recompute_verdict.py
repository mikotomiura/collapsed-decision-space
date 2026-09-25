#!/usr/bin/env python3
"""Recompute the recorded verdicts from the shipped annotations, and require them to match.

This is the strongest check in the repository. The others establish that a record agrees with a
shipped file, or that shipped bytes are the bytes registered upstream -- but all of them **read** the
recorded verdict rather than deriving it. Here the scorer actually runs.

What runs, once per run in :data:`RUNS`:
    ``score_bank_annotation(annotation_rows=<annotation>, manifest=<manifest>)``
at the sealed Monte-Carlo settings, which are the defaults and are not lowered to make the check
faster. The result is compared against the landed verdict:

- the completed run: ``data/raw/bank_annotation.jsonl`` + ``data/raw/cproper-manifest.json``
  against ``data/raw/cproper-verdict.json``;
- the two prospective arms (since 2026-09-25): ``data/prospective/<arm>/run_annotation.jsonl``
  + ``run-manifest.json`` against ``data/raw/<arm>-verdict.json``, the files step 13 applies the
  sealed rules to. Until then step 13 read those two verdicts without anything deriving them.

All three are required. A missing input is a failure, not a skip: the files are shipped, and a
check that goes quiet when its input disappears is the failure this repository keeps finding.

**What this establishes**: each verdict and every gate read-out follow from the shipped data and
the shipped apparatus alone, and agree with the record. The scorer's Monte-Carlo step is
deterministic under its fixed seed. That the prospective annotations agree with the per-draw
records they were read from is a different check -- the held-out workflow's ``--verify`` -- and
is not repeated here.

**What it does not**: regeneration of the language-model draws. Draws do not recur when regenerated,
so the per-draw record is treated as a frozen input.

**The comparison is itself tested on every run.** After a run agrees, each compared field of a
copy of its record is altered in turn, and the comparison is required to report that field by
name; a comparison that could not see a difference would otherwise pass in the same words.
``--self-test`` perturbs the *inputs* instead (one annotation row moved, one dropped), rescoring
each time, and requires an unperturbed control to agree. It runs in
``.github/workflows/compendium.yml``.

Usage:  python analysis/scripts/recompute_verdict.py [--self-test]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402

#: Fields compared between the recomputation and the record, secondary descriptors included.
COMPARED_SCALARS: tuple[str, ...] = (
    "verdict",
    "n_contexts",
    "effective_k",
    "rho_hat",
    "none_rate_max_observed",
    "tv_bar",
    "tv_pool",
    "permutation_reject",
    "permutation_p_value",
    "power",
)

#: Fields holding dictionaries (the per-context read-outs).
COMPARED_MAPPINGS: tuple[str, ...] = (
    "per_context_h",
    "i_pass_mask",
    "tv_per_context",
    "thresholds",
)

#: Tolerance for float comparison; verdict.json holds values quantised to six decimals.
FLOAT_TOL = 5e-7


@dataclass(frozen=True)
class Run:
    """One verdict to re-derive: its record and its inputs, relative to the repository root."""

    name: str
    verdict: str
    manifest: str
    annotation: str


#: The three verdicts this repository ships. Written out rather than discovered, so that a missing
#: file is reported by name instead of silently shortening the loop.
RUNS: tuple[Run, ...] = (
    Run(
        "completed",
        "data/raw/cproper-verdict.json",
        "data/raw/cproper-manifest.json",
        "data/raw/bank_annotation.jsonl",
    ),
    Run(
        "control",
        "data/raw/control-verdict.json",
        "data/prospective/control/run-manifest.json",
        "data/prospective/control/run_annotation.jsonl",
    ),
    Run(
        "primary",
        "data/raw/primary-verdict.json",
        "data/prospective/primary/run-manifest.json",
        "data/prospective/primary/run_annotation.jsonl",
    ),
)


def _agree(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= FLOAT_TOL
    return bool(left == right)


def load_annotation_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def compare(result: dict[str, Any], recorded: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (problems, lines that agreed) for one recomputed verdict against its record."""
    problems: list[str] = []
    agreed: list[str] = []
    for field in COMPARED_SCALARS:
        if field not in recorded:
            problems.append(f"the record has no {field}")
            continue
        if not _agree(result[field], recorded[field]):
            problems.append(
                f"MISMATCH {field}: recomputed={result[field]!r} "
                f"recorded={recorded[field]!r}"
            )
        else:
            agreed.append(f"OK {field:<24} = {recorded[field]}")

    for field in COMPARED_MAPPINGS:
        recomputed_map = result[field]
        recorded_map = recorded.get(field)
        if recorded_map is None:
            problems.append(f"the record has no {field}")
            continue
        if set(recomputed_map) != set(recorded_map):
            problems.append(
                f"MISMATCH {field}: different key sets "
                f"(recomputed={sorted(recomputed_map)} recorded={sorted(recorded_map)})"
            )
            continue
        bad = [
            key
            for key in recorded_map
            if not _agree(recomputed_map[key], recorded_map[key])
        ]
        if bad:
            problems.append(f"MISMATCH {field}: keys whose values differ: {bad}")
        else:
            agreed.append(f"OK {field:<24} ({len(recorded_map)} keys)")
    return problems, agreed


def _perturbed(value: Any) -> Any:
    """A value the comparison must tell apart from ``value``."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if value is None:
        return 0.5
    if isinstance(value, str):
        return value + "-X"
    raise TypeError(f"no perturbation for {type(value).__name__}")


def comparison_catches(result: dict[str, Any], recorded: dict[str, Any]) -> list[str]:
    """Alter one compared field of a copy of the record at a time; each must be reported by name.

    A scalar is replaced by a different value; a mapping has one value altered, or, when empty
    (the primary arm's ``tv_per_context``), one key added.
    """
    missed: list[str] = []
    for field in (*COMPARED_SCALARS, *COMPARED_MAPPINGS):
        mutated = copy.deepcopy(recorded)
        if field in COMPARED_SCALARS:
            mutated[field] = _perturbed(mutated[field])
        elif mutated[field]:
            key = sorted(mutated[field])[0]
            mutated[field][key] = _perturbed(mutated[field][key])
        else:
            mutated[field]["fixture-key"] = 0.0
        found, _ = compare(result, mutated)
        if not any(problem.startswith(f"MISMATCH {field}:") for problem in found):
            missed.append(f"self-check: an altered {field} was not reported ({found!r})")
    return missed


def _load_scorer(repo_root: Path) -> tuple[Any, str]:
    apparatus = repo_root / "analysis" / "apparatus"
    if str(apparatus) not in sys.path:
        sys.path.insert(0, str(apparatus))

    from erre_sandbox.integration.embodied.bank_scorer import (  # noqa: PLC0415
        SCORER_SCHEMA_VERSION,
        score_bank_annotation,
    )

    return score_bank_annotation, SCORER_SCHEMA_VERSION


def recompute(
    run: Run, repo_root: Path, score: Any, schema: str
) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None]:
    """Score one run. Returns (problems, result, record) and prints what agreed."""
    paths = [repo_root / p for p in (run.verdict, run.manifest, run.annotation)]
    missing = [p.relative_to(repo_root).as_posix() for p in paths if not p.is_file()]
    if missing:
        return [f"{run.name}: input missing: {missing}"], None, None

    recorded = load_json(paths[0])
    manifest = load_json(paths[1])
    rows = load_annotation_rows(paths[2])

    declared = recorded.get("scorer_schema_version") or manifest.get(
        "scorer_schema_version"
    )
    if declared is not None and declared != schema:
        return (
            [f"{run.name}: scorer_schema_version differs (recorded={declared} shipped={schema})"],
            None,
            None,
        )

    print(
        f"[recompute] {run.name}: scoring {len(rows)} annotation rows from {run.annotation} "
        f"with {schema} (sealed defaults)…"
    )
    result = asdict(score(annotation_rows=rows, manifest=manifest))
    problems, agreed = compare(result, recorded)
    for line in agreed:
        print(f"[recompute] {run.name}: {line}")
    return [f"{run.name}: {p}" for p in problems], result, recorded


def self_test(repo_root: Path, score: Any) -> int:
    """Perturb the inputs and require the recomputation to disagree; the unperturbed case agrees.

    Uses the control arm, whose verdict populates every compared field (the primary arm's
    permutation read-outs are null). Every case is rescored from scratch.
    """
    run = next(r for r in RUNS if r.name == "control")
    recorded = load_json(repo_root / run.verdict)
    manifest = load_json(repo_root / run.manifest)
    rows = load_annotation_rows(repo_root / run.annotation)

    def rescore(rows_: list[dict[str, Any]]) -> list[str]:
        return compare(asdict(score(annotation_rows=rows_, manifest=manifest)), recorded)[0]

    failures: list[str] = []
    unperturbed = rescore(rows)
    if unperturbed:
        failures.append(f"the unperturbed control disagreed: {unperturbed}")

    # One draw's zone moved to another zone that occurs in the same run.
    zones = sorted(
        {r["pre_bias_destination_zone"] for r in rows if r["pre_bias_destination_zone"]}
    )
    moved = copy.deepcopy(rows)
    index = next(
        i for i, r in enumerate(moved) if r["pre_bias_destination_zone"] == zones[0]
    )
    moved[index]["pre_bias_destination_zone"] = zones[1]
    if not rescore(moved):
        failures.append("one annotation row's zone was moved, and the recomputation still agreed")

    # One draw dropped.
    if not rescore(rows[1:]):
        failures.append("one annotation row was dropped, and the recomputation still agreed")

    if failures:
        print("[recompute] FAIL --self-test", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(
        "[recompute] OK --self-test: the unperturbed control agrees; a moved zone and a "
        "dropped row are each reported as a mismatch"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="perturb the inputs and require the recomputation to disagree",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root
    score, schema = _load_scorer(repo_root)

    if args.self_test:
        return self_test(repo_root, score)

    problems: list[str] = []
    fields = len(COMPARED_SCALARS) + len(COMPARED_MAPPINGS)
    caught = 0
    for run in RUNS:
        found, result, recorded = recompute(run, repo_root, score, schema)
        problems.extend(found)
        if result is not None and recorded is not None and not found:
            missed = comparison_catches(result, recorded)
            problems.extend(f"{run.name}: {m}" for m in missed)
            caught += fields - len(missed)

    if problems:
        print("[recompute] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[recompute] OK self-check: {caught} single-field alterations of the records "
        f"({len(RUNS)} runs x {fields} fields), each reported by name"
    )
    print(
        f"[recompute] OK: all {len(RUNS)} recorded verdicts "
        f"({', '.join(r.name for r in RUNS)}) are re-derivable from the shipped data and "
        "the shipped apparatus"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
