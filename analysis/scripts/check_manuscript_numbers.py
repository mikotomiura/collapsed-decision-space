#!/usr/bin/env python3
"""本文に載る数値が凍結入力の値そのものであることを照合する.

``manuscript/main.md`` は「本文の数値は抽出スクリプトの出力から取る、手写ししない」と
書いている。**書いただけでは検査していない。** 表を生成するスクリプトがあることと、
本文がその値と一致していることは別の事実であり、前者だけを根拠に後者を主張するのは
``feedback_checker_handed_target_is_not_checked`` と同型である。本スクリプトがその差を埋める。

やり方は単純である。凍結入力の JSON から**キーを指定して**値を読み、その literal が
本文に出現することを確かめる。値の側は ``d["key"]`` の直接添字で取るので、キーが実
ファイルに無ければ ``KeyError`` で落ちる (既定値で黙って通らない)。

この検査が示すこと / 示さないこと:

* 示す — 下表の量について、本文の literal が**凍結 JSON の値と文字単位で一致する**。
  1 桁でも違えば落ちる。
* 示さない — 本文に現れる**すべての**数値の正しさ。下表に無い数値は対象外である。
  対象は「凍結 JSON から機械的に取れる量」に限られる。

使い方:  python analysis/scripts/check_manuscript_numbers.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402

#: (表示名, 入力ファイル, キー経路, literal 化の仕方) の対応表。
#: キー経路は dict を辿る。list は使わない。
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

#: 本文に**出てはならない**取り違え (G10 の数値版)。
#: 位置推定 `d_loco` の値が positive control のラベルで書かれていないかを見る。
MISLABEL_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "zone_function_d_loco の値が d_loco の値として書かれている",
        "d_loco = 7.401486830834377e-17",
    ),
    (
        "d_loco の値が zone_function_d_loco の値として書かれている",
        "zone_function_d_loco = 0.04682681825722385",
    ),
)


def literal_of(value: Any, how: str) -> str:
    if how == "str":
        return str(value)
    if how == "int":
        return str(int(value))
    if how == "two_dp":
        # `0.1` ではなく `0.10` と書く量 (事前宣言された margin / floor)。
        return f"{float(value):.2f}"
    return repr(value)


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

    main_md = repo_root / "manuscript" / "main.md"
    if not main_md.is_file():
        print(f"[numbers] FAIL: 本文が無い: {main_md}", file=sys.stderr)
        return 1
    text = main_md.read_text(encoding="utf-8")

    sources: dict[str, dict[str, Any]] = {}
    problems: list[str] = []

    for label, filename, keys, how in REQUIRED:
        if filename not in sources:
            sources[filename] = load_json(repo_root / "data" / "raw" / filename)
        node: Any = sources[filename]
        for key in keys:
            node = node[key]  # KeyError で落ちるのが正しい (既定値で通さない)
        literal = literal_of(node, how)
        if literal in text:
            print(f"[numbers] OK {label:<28} = {literal}")
        else:
            problems.append(
                f"{label}: 凍結入力の値 {literal!r} ({filename}) が main.md に無い。"
                "本文を抽出スクリプトの出力に合わせること"
            )

    for label, forbidden in MISLABEL_CHECKS:
        if forbidden in text:
            problems.append(f"取り違え: {label} — {forbidden!r} が main.md にある")

    if problems:
        print("[numbers] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"[numbers] OK: {len(REQUIRED)} 件の量が凍結入力の値と文字単位で一致する "
        "(この表に無い数値は検査対象外)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
