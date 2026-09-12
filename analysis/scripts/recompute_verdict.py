#!/usr/bin/env python3
"""Recompute the recorded verdict from the shipped annotation, and require it to match.

This is the strongest check in the repository. The others establish that a record agrees with a
shipped file, or that shipped bytes are the bytes registered upstream -- but all of them **read** the
recorded verdict rather than deriving it. Here the scorer actually runs.

What runs:
    ``score_bank_annotation(annotation_rows=<data/raw/bank_annotation.jsonl>,
                            manifest=<data/raw/cproper-manifest.json>)``
at the sealed Monte-Carlo settings, which are the defaults and are not lowered to make the check
faster. The result is compared against ``data/raw/cproper-verdict.json``.

**What this establishes**: the central verdict and every gate read-out follow from the shipped data
and the shipped apparatus alone, and agree with the record. The scorer's Monte-Carlo step is
deterministic under its fixed seed.

**What it does not**: regeneration of the language-model draws. Draws do not recur when regenerated,
so the per-draw record is treated as a frozen input.

Usage:  python analysis/scripts/recompute_verdict.py
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
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

    apparatus = repo_root / "analysis" / "apparatus"
    if str(apparatus) not in sys.path:
        sys.path.insert(0, str(apparatus))

    from erre_sandbox.integration.embodied.bank_scorer import (  # noqa: PLC0415
        SCORER_SCHEMA_VERSION,
        score_bank_annotation,
    )

    raw = repo_root / "data" / "raw"
    recorded = load_json(raw / "cproper-verdict.json")
    manifest = load_json(raw / "cproper-manifest.json")
    rows = load_annotation_rows(raw / "bank_annotation.jsonl")

    declared = recorded.get("scorer_schema_version") or manifest.get(
        "scorer_schema_version"
    )
    if declared is not None and declared != SCORER_SCHEMA_VERSION:
        print(
            f"[recompute] FAIL: scorer_schema_version differs "
            f"(recorded={declared} shipped={SCORER_SCHEMA_VERSION})",
            file=sys.stderr,
        )
        return 1

    print(
        f"[recompute] scoring {len(rows)} annotation rows with "
        f"{SCORER_SCHEMA_VERSION} (sealed defaults)…"
    )
    result = asdict(score_bank_annotation(annotation_rows=rows, manifest=manifest))

    problems: list[str] = []
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
            print(f"[recompute] OK {field:<24} = {recorded[field]}")

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
            print(f"[recompute] OK {field:<24} ({len(recorded_map)} keys)")

    if problems:
        print("[recompute] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        "[recompute] OK: the recorded verdict is re-derivable from the shipped data "
        "and the shipped apparatus"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
