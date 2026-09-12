#!/usr/bin/env python3
"""同梱 annotation と manifest から verdict を**再計算**し、記録と一致させる.

本 repo で最も強い再現検査である。他の検査は「記録と出荷物が一致する」「同梱 bytes が
上流の bytes である」を言うが、いずれも**記録された verdict を読んでいるだけ**で、
それが同梱データから導けることは確かめていない。ここで scorer を実際に走らせる。

走らせるもの:
    ``score_bank_annotation(annotation_rows=<data/raw/bank_annotation.jsonl>,
                            manifest=<data/raw/cproper-manifest.json>)``
封印実走と同じ ``N_REPLICATES_DEFAULT`` / ``POWER_SEED_DEFAULT`` を既定のまま使う
(検査を速くするために下げない)。結果を ``data/raw/cproper-verdict.json`` と突き合わせる。

**この検査が示すこと**: 中核 verdict とその全 gate readout が、同梱データと同梱 apparatus
だけから再導出でき、記録と一致する。scorer の Monte-Carlo は seed 固定で決定的である。

**示さないこと**: LLM の draw の再現。draw は再生成すると一致しないので、``data/raw/`` に
凍結した出力を入力として扱っている (``manuscript/main.md`` §13)。

使い方:  python analysis/scripts/recompute_verdict.py
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

#: 再計算と記録を突き合わせるフィールド。secondary descriptor も含めて全部見る。
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

#: dict 値のフィールド (per-context の読み出し)。
COMPARED_MAPPINGS: tuple[str, ...] = (
    "per_context_h",
    "i_pass_mask",
    "tv_per_context",
    "thresholds",
)

#: 浮動小数の比較許容。verdict.json は 6 桁量子化された値を持つ。
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
        help="repo root",
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
            f"[recompute] FAIL: scorer_schema_version が違う "
            f"(記録={declared} 同梱={SCORER_SCHEMA_VERSION})",
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
            problems.append(f"記録側に {field} が無い")
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
            problems.append(f"記録側に {field} が無い")
            continue
        if set(recomputed_map) != set(recorded_map):
            problems.append(
                f"MISMATCH {field}: キー集合が違う "
                f"(recomputed={sorted(recomputed_map)} recorded={sorted(recorded_map)})"
            )
            continue
        bad = [
            key
            for key in recorded_map
            if not _agree(recomputed_map[key], recorded_map[key])
        ]
        if bad:
            problems.append(f"MISMATCH {field}: 値が違うキー {bad}")
        else:
            print(f"[recompute] OK {field:<24} ({len(recorded_map)} keys)")

    if problems:
        print("[recompute] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        "[recompute] OK: 記録された verdict は同梱データと同梱 apparatus から再導出できる"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
