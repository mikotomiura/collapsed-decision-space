#!/usr/bin/env python3
"""verdict.json / manifest.json / es3-verdict-forensic.json から数値を機械抽出する。

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


def render_table(
    verdict: dict[str, Any],
    manifest: dict[str, Any],
    es3: dict[str, Any],
) -> str:
    lines: list[str] = []

    # --- C-proper verdict (data/raw/cproper-verdict.json) ---
    v_verdict = verdict["verdict"]
    v_rho_hat = verdict["rho_hat"]
    v_power = verdict["power"]
    v_tv_bar = verdict["tv_bar"]
    v_perm_p = verdict["permutation_p_value"]
    v_perm_reject = verdict["permutation_reject"]
    v_none_rate_max_observed = verdict["none_rate_max_observed"]
    v_effective_k = verdict["effective_k"]
    v_n_contexts = verdict["n_contexts"]
    v_thresholds = verdict["thresholds"]

    per_context_h = verdict["per_context_h"]
    per_context_h_values = [per_context_h[k] for k in per_context_h]
    per_context_h_min = min(per_context_h_values)
    per_context_h_max = max(per_context_h_values)

    tv_per_context = verdict["tv_per_context"]
    tv_per_context_values = [tv_per_context[k] for k in tv_per_context]
    tv_per_context_min = min(tv_per_context_values)
    tv_per_context_max = max(tv_per_context_values)

    lines.append("# C-proper verdict (data/raw/cproper-verdict.json)")
    lines.append("")
    lines.append("| 量 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| verdict | `{v_verdict}` |")
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
    for key in v_thresholds:
        lines.append(f"| {key} | {v_thresholds[key]} |")
    lines.append("")

    # --- run manifest (data/raw/cproper-manifest.json) ---
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

    cost_ceiling = manifest["cost_ceiling"]
    c_max_llm_calls = cost_ceiling["max_llm_calls"]

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

    # --- ES-3 locomotion verdict forensic (data/raw/es3-verdict-forensic.json) ---
    e_verdict = es3["verdict"]
    e_d_loco = es3["d_loco"]
    e_ci_lower = es3["ci_lower"]
    e_ci_upper = es3["ci_upper"]
    e_amp_floor = es3["amp_floor"]
    e_zone_function_d_loco = es3["zone_function_d_loco"]
    e_ablation_bit_equal = es3["ablation_bit_equal"]
    e_ablation_max_abs_diff = es3["ablation_max_abs_diff"]

    lines.append("# ES-3 locomotion verdict forensic (data/raw/es3-verdict-forensic.json)")
    lines.append("")
    lines.append("| 量 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| verdict | `{e_verdict}` |")
    lines.append(f"| d_loco (D_loco) | {e_d_loco} |")
    lines.append(f"| ci_lower | {e_ci_lower} |")
    lines.append(f"| ci_upper | {e_ci_upper} |")
    lines.append(f"| amp_floor | {e_amp_floor} |")
    lines.append(f"| zone_function_d_loco (zone-function positive control) | {e_zone_function_d_loco} |")
    lines.append(f"| ablation_bit_equal | {e_ablation_bit_equal} |")
    lines.append(f"| ablation_max_abs_diff | {e_ablation_max_abs_diff} |")
    lines.append("")

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

    out_path = args.out if args.out is not None else repo_root / "data" / "derived" / "verdict-table.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(table, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
