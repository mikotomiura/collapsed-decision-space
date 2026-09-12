#!/usr/bin/env python3
"""Extract the quantities the manuscript quotes, mechanically, from the frozen records.

This exists so that numbers are never copied by hand. Extraction uses direct subscripting,
``d["key"]``, and never ``.get(..., default)``: a key absent from the file raises rather than
returning something plausible, which is what makes "this value was present in the record" a fact
rather than an assumption.

Inputs, relative to the repository root:
  - data/raw/cproper-verdict.json
  - data/raw/cproper-manifest.json
  - data/raw/es3-verdict-forensic.json

Output: a Markdown table on standard output, and to the path given by ``--out`` if supplied
(by default data/derived/verdict-table.md, which is not tracked).
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
    """Render data/raw/cproper-verdict.json as Markdown rows."""
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
    lines.append("| Quantity | Value |")
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
    lines.append("| Key | Value |")
    lines.append("|---|---|")
    lines.extend(f"| {key} | {value} |" for key, value in v_thresholds.items())
    lines.append("")
    return lines


def _render_manifest_section(manifest: dict[str, Any]) -> list[str]:
    """Render data/raw/cproper-manifest.json as Markdown rows."""
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
    lines.append("| Quantity | Value |")
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
    """State mechanically how each shuffle variant compares with the point estimate."""
    lines: list[str] = []
    for hist_label, hist_value in hist_fields:
        if hist_value > e_d_loco:
            relation_text = "larger than"
        elif hist_value < e_d_loco:
            relation_text = "smaller than"
        else:
            relation_text = "equal to"
        lines.append(
            f"> Note: {hist_label}={hist_value} is {relation_text} the point estimate "
            f"d_loco={e_d_loco}."
        )
    return lines


def _render_es3_ci_footnote(
    e_d_loco: float, e_ci_lower: float, e_ci_upper: float
) -> list[str]:
    """Note the differing aggregation units when the point estimate falls outside its CI."""
    if not (e_d_loco > e_ci_upper or e_d_loco < e_ci_lower):
        return []
    excess = e_d_loco - e_ci_upper if e_d_loco > e_ci_upper else e_d_loco - e_ci_lower
    note = (
        f"> Note: the point estimate d_loco={e_d_loco} lies outside its own interval "
        f"[{e_ci_lower}, {e_ci_upper}] (by {excess:.6e}). The interval is a 90 per cent "
        "percentile bootstrap over per-walk-seed aggregates, while the point estimate is a "
        "cell-equal-weighted median over headroom-valid cells. The two use different "
        "aggregation units (see the estimand definition in the caveats), and a median is not "
        "guaranteed to fall inside an interval built this way."
    )
    return [note, ""]


def _render_es3_section(es3: dict[str, Any]) -> list[str]:
    """Render data/raw/es3-verdict-forensic.json as Markdown rows."""
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
        "zone_function_d_loco (the positive control -- **a different field from the point "
        "estimate**: forcing the modulation to be a function of the zone shows the estimand "
        "is able to read zero)"
    )

    header = "# ES-3 locomotion verdict forensic (data/raw/es3-verdict-forensic.json)"
    lines: list[str] = []
    lines.append(header)
    lines.append("")
    lines.append("| Quantity | Value |")
    lines.append("|---|---|")
    lines.append(f"| verdict | `{e_verdict}` |")
    lines.append(f"| **d_loco (the point estimate)** | **{e_d_loco}** |")
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

    lines.append("## caveats (es3-verdict-forensic.json, verbatim)")
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
        help="repository root; data/raw/*.json is resolved beneath it",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output file (default: <repo-root>/data/derived/verdict-table.md)",
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
    # newline is set explicitly: the default text mode rewrites line endings on Windows, so
    # identical content would produce different bytes across platforms. Measured on Windows and
    # Linux -- the content agreed and only the line endings differed.
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(table)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
