#!/usr/bin/env python3
"""verdict.json / manifest.json / es3-verdict-forensic.json から数値を機械抽出する.

手写しを禁止するための装置: 本文に載せる数値は必ずこのスクリプトの出力から
取ること。抽出は `d["key"]` の直接添字のみを使う (`.get(..., default)` は
使わない) — キーが実ファイルに無ければ黙って既定値を返さず KeyError で
落ちることで、「値が JSON に実在したこと」を保証する (恒真性を殺す)。

入力 (repo root からの相対、既定):
  - data/raw/cproper-verdict.json
  - data/raw/cproper-manifest.json
  - data/raw/es3-verdict-forensic.json

出力: 標準出力に Markdown テーブル。--out が与えられればそのファイルにも書く
(既定 data/derived/verdict-table.md。data/derived/* は .gitignore 済)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _render_cproper_section(verdict: dict[str, Any]) -> list[str]:
    """data/raw/cproper-verdict.json を Markdown 行列へ抽出する."""
    v_verdict = verdict["verdict"]
    v_reason = verdict["reason"]
    v_reason_text = "; ".join(str(item) for item in v_reason)
    v_rho_hat = verdict["rho_hat"]
    v_power = verdict["power"]
    v_tv_bar = verdict["tv_bar"]
    v_perm_p = verdict["permutation_p_value"]
    v_perm_reject = verdict["permutation_reject"]
    v_none_rate_max_observed = verdict["none_rate_max_observed"]
    v_effective_k = verdict["effective_k"]
    v_n_contexts = verdict["n_contexts"]
    v_thresholds = verdict["thresholds"]

    per_context_h_values = list(verdict["per_context_h"].values())
    per_context_h_min = min(per_context_h_values)
    per_context_h_max = max(per_context_h_values)

    tv_per_context_values = list(verdict["tv_per_context"].values())
    tv_per_context_min = min(tv_per_context_values)
    tv_per_context_max = max(tv_per_context_values)

    lines: list[str] = []
    lines.append("# C-proper verdict (data/raw/cproper-verdict.json)")
    lines.append("")
    lines.append("| 量 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| verdict | `{v_verdict}` |")
    lines.append(f"| reason | {v_reason_text} |")
    lines.append(f"| rho_hat | {v_rho_hat} |")
    lines.append(f"| power | {v_power} |")
    lines.append(f"| tv_bar | {v_tv_bar} |")
    lines.append(f"| permutation_p_value | {v_perm_p} |")
    lines.append(f"| permutation_reject | {v_perm_reject} |")
    lines.append(f"| none_rate_max_observed | {v_none_rate_max_observed} |")
    lines.append(f"| effective_k | {v_effective_k} |")
    lines.append(f"| n_contexts | {v_n_contexts} |")
    lines.append(f"| per_context_h (min) | {per_context_h_min} |")
    lines.append(f"| per_context_h (max) | {per_context_h_max} |")
    lines.append(f"| tv_per_context (min) | {tv_per_context_min} |")
    lines.append(f"| tv_per_context (max) | {tv_per_context_max} |")
    lines.append("")
    lines.append("## thresholds (cproper-verdict.json)")
    lines.append("")
    lines.append("| キー | 値 |")
    lines.append("|---|---|")
    lines.extend(f"| {key} | {value} |" for key, value in v_thresholds.items())
    lines.append("")
    return lines


def _render_manifest_section(manifest: dict[str, Any]) -> list[str]:
    """data/raw/cproper-manifest.json を Markdown 行列へ抽出する."""
    env_pins = manifest["env_pins"]
    m_model = env_pins["model"]
    m_ollama_version = env_pins["ollama_version"]
    m_qwen3_model_digest = env_pins["qwen3_model_digest"]
    m_think = env_pins["think"]
    m_python = env_pins["python"]

    run = manifest["run"]
    r_seed = run["seed"]
    r_k_contexts = run["k_contexts"]
    r_m_draws = run["m_draws"]

    c_max_llm_calls = manifest["cost_ceiling"]["max_llm_calls"]

    lines: list[str] = []
    lines.append("# run manifest (data/raw/cproper-manifest.json)")
    lines.append("")
    lines.append("| 量 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| env_pins.model | `{m_model}` |")
    lines.append(f"| env_pins.ollama_version | `{m_ollama_version}` |")
    lines.append(f"| env_pins.qwen3_model_digest | `{m_qwen3_model_digest}` |")
    lines.append(f"| env_pins.think | {m_think} |")
    lines.append(f"| env_pins.python | `{m_python}` |")
    lines.append(f"| run.seed | {r_seed} |")
    lines.append(f"| run.k_contexts | {r_k_contexts} |")
    lines.append(f"| run.m_draws | {r_m_draws} |")
    lines.append(f"| cost_ceiling.max_llm_calls | {c_max_llm_calls} |")
    lines.append("")
    return lines


def _render_es3_hist_notes(
    e_d_loco: float, hist_fields: tuple[tuple[str, float], ...]
) -> list[str]:
    """n_hist_*_shuffle_d_loco が主推定 d_loco とどちらが大きいかを機械判定する."""
    lines: list[str] = []
    for hist_label, hist_value in hist_fields:
        if hist_value > e_d_loco:
            relation_text = "より大きい (>)"
        elif hist_value < e_d_loco:
            relation_text = "より小さい (<)"
        else:
            relation_text = "と等しい (==)"
        lines.append(
            f"> 注: {hist_label}={hist_value} は主推定 "
            f"d_loco={e_d_loco} {relation_text}。"
        )
    return lines


def _render_es3_ci_footnote(
    e_d_loco: float, e_ci_lower: float, e_ci_upper: float
) -> list[str]:
    """点推定が自身の bootstrap CI の外にある場合、集計単位の違いを機械的に注記する."""
    if not (e_d_loco > e_ci_upper or e_d_loco < e_ci_lower):
        return []
    excess = e_d_loco - e_ci_upper if e_d_loco > e_ci_upper else e_d_loco - e_ci_lower
    note = (
        f"> 注: 点推定 d_loco={e_d_loco} は自身の CI [{e_ci_lower}, {e_ci_upper}] "
        f"の外にある (差分 {excess:.6e})。CI は CI_ALPHA=0.10 (90% percentile "
        "bootstrap) を per-walk-seed 集計に対して取ったものである一方、点推定 "
        "d_loco は headroom-valid cell に対する cell-equal-weighted median で"
        "あり、両者は集計単位が異なる (caveats の estimand 定義を参照)。点推定は "
        "cell 中央値のため、自身の区間内に入る保証はない。"
    )
    return [note, ""]


def _render_es3_section(es3: dict[str, Any]) -> list[str]:
    """data/raw/es3-verdict-forensic.json を Markdown 行列へ抽出する."""
    e_verdict = es3["verdict"]
    e_d_loco = es3["d_loco"]
    e_ci_lower = es3["ci_lower"]
    e_ci_upper = es3["ci_upper"]
    e_amp_floor = es3["amp_floor"]
    e_zone_function_d_loco = es3["zone_function_d_loco"]
    e_ablation_bit_equal = es3["ablation_bit_equal"]
    e_ablation_max_abs_diff = es3["ablation_max_abs_diff"]
    e_n_hist_history_shuffle = es3["n_hist_history_shuffle_d_loco"]
    e_n_hist_lambda_shuffle = es3["n_hist_lambda_shuffle_d_loco"]
    e_caveats = es3["caveats"]

    zone_label = (
        "zone_function_d_loco (positive control。**d_loco とは別物の参照値**: "
        "λ=h(z) を強制し estimand が 0 を取りうることの実証)"
    )

    header = "# ES-3 locomotion verdict forensic (data/raw/es3-verdict-forensic.json)"
    lines: list[str] = []
    lines.append(header)
    lines.append("")
    lines.append("| 量 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| verdict | `{e_verdict}` |")
    lines.append(f"| **d_loco (D_loco, 主推定)** | **{e_d_loco}** |")
    lines.append(f"| ci_lower | {e_ci_lower} |")
    lines.append(f"| ci_upper | {e_ci_upper} |")
    lines.append(f"| amp_floor | {e_amp_floor} |")
    lines.append(f"| {zone_label} | {e_zone_function_d_loco} |")
    lines.append(f"| ablation_bit_equal | {e_ablation_bit_equal} |")
    lines.append(f"| ablation_max_abs_diff | {e_ablation_max_abs_diff} |")
    lines.append(f"| n_hist_history_shuffle_d_loco | {e_n_hist_history_shuffle} |")
    lines.append(f"| n_hist_lambda_shuffle_d_loco | {e_n_hist_lambda_shuffle} |")
    lines.append("")

    hist_fields = (
        ("n_hist_history_shuffle_d_loco", e_n_hist_history_shuffle),
        ("n_hist_lambda_shuffle_d_loco", e_n_hist_lambda_shuffle),
    )
    lines.extend(_render_es3_hist_notes(e_d_loco, hist_fields))
    lines.append("")

    lines.extend(_render_es3_ci_footnote(e_d_loco, e_ci_lower, e_ci_upper))

    lines.append("## caveats (es3-verdict-forensic.json、全文)")
    lines.append("")
    lines.extend(f"{i}. {caveat}" for i, caveat in enumerate(e_caveats, start=1))
    lines.append("")
    return lines


def render_table(
    verdict: dict[str, Any],
    manifest: dict[str, Any],
    es3: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.extend(_render_cproper_section(verdict))
    lines.extend(_render_manifest_section(manifest))
    lines.extend(_render_es3_section(es3))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root (data/raw/*.json をこの下から解決する)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="出力先ファイル (既定: <repo-root>/data/derived/verdict-table.md)",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root
    verdict_path = repo_root / "data" / "raw" / "cproper-verdict.json"
    manifest_path = repo_root / "data" / "raw" / "cproper-manifest.json"
    es3_path = repo_root / "data" / "raw" / "es3-verdict-forensic.json"

    verdict = load_json(verdict_path)
    manifest = load_json(manifest_path)
    es3 = load_json(es3_path)

    table = render_table(verdict, manifest, es3)

    sys.stdout.write(table)

    default_out = repo_root / "data" / "derived" / "verdict-table.md"
    out_path = args.out if args.out is not None else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(table, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
