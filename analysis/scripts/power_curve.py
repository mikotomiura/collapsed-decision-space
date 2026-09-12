#!/usr/bin/env python3
"""a-priori categorical-multinomial power の 3 ケース比較表を作る。

`erre_sandbox.integration.embodied.bank_power.categorical_multinomial_power`
(実行には ``PYTHONPATH=analysis/apparatus`` が要る) を、
``C:\\ERRE-Sand_Box\\experiments\\20260708-m13-b-bank\\power_worksheet.md`` の
3 ケースと同じ入力で呼び出し、power を計算する。

★ 用語の精度 (重要、docstring と出力ヘッダの両方に必ず書く):
    power を殺すのは **base 分布が collapse していること自体ではない**。
    3 行目 (degenerate base + collapse-scale delta) が power≈0.95 と高いままに
    なることが示す通り、power を殺すのは **達成可能な delta_tv が小さいこと**
    である。base 分布が近-uniform でも degenerate でも、delta_tv が十分あれば
    power は高い。「collapse した分布では power が落ちる」という言い方は誤り
    (実測はむしろ逆: degenerate base の方が同じ delta_tv に対して敏感に反応し
    power が高くなる)。

自己検証: 3 ケースの power が期待帯に入らなければ exit 1 で落ちる
(帯: >=0.99 / 0.10<=p<=0.30 / >=0.85)。乱数は seed 固定 (POWER_SEED_DEFAULT
= 20260708)。n_replicates は勝手に下げない (既定 N_REPLICATES_DEFAULT=4000
のまま)。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from erre_sandbox.integration.embodied.bank_power import (
    K_MIN,
    M_MIN,
    N_REPLICATES_DEFAULT,
    POWER_SEED_DEFAULT,
    categorical_multinomial_power,
)

HEADER_NOTE = (
    "# power を殺すのは base 分布の collapse ではなく、達成可能な delta_tv が小さいことである\n"
    "# (ケース3: degenerate base + delta_tv=0.10 相当の shift でも power は高いままになる実測を参照)\n"
)


@dataclass(frozen=True)
class Case:
    label: str
    base_dist: tuple[float, ...]
    delta_tv: float
    expected_low: float
    expected_high: float


CASES: tuple[Case, ...] = (
    Case(
        label="事前登録設計 (near-uniform)",
        base_dist=(0.2, 0.2, 0.2, 0.2, 0.2),
        delta_tv=0.10,
        expected_low=0.99,
        expected_high=1.0,
    ),
    Case(
        label="collapse-scale delta (proposal の 1/10)",
        base_dist=(0.2, 0.2, 0.2, 0.2, 0.2),
        delta_tv=0.01,
        expected_low=0.10,
        expected_high=0.30,
    ),
    Case(
        label="degenerate base + collapse-scale delta",
        base_dist=(0.96, 0.01, 0.01, 0.01, 0.01),
        delta_tv=0.01,
        expected_low=0.85,
        expected_high=1.0,
    ),
)

M_DRAWS = M_MIN  # 300
K_CONTEXTS = K_MIN  # 8
POOLING = True
SEED = POWER_SEED_DEFAULT  # 20260708
N_REPLICATES = N_REPLICATES_DEFAULT  # 4000 (下げない)


def render_table() -> tuple[str, list[float]]:
    lines: list[str] = []
    lines.append(HEADER_NOTE)
    lines.append(
        f"共通パラメータ: m_draws={M_DRAWS}, k_contexts={K_CONTEXTS}, pooling={POOLING}, "
        f"seed={SEED}, n_replicates={N_REPLICATES}"
    )
    lines.append("")
    lines.append("| ケース | base_dist | delta_tv | power (実測) | 期待帯 |")
    lines.append("|---|---|---|---|---|")

    powers: list[float] = []
    for case in CASES:
        result = categorical_multinomial_power(
            base_dist=case.base_dist,
            delta_tv=case.delta_tv,
            m_draws=M_DRAWS,
            k_contexts=K_CONTEXTS,
            pooling=POOLING,
            n_replicates=N_REPLICATES,
            seed=SEED,
        )
        powers.append(result.power)
        base_str = "[" + ", ".join(f"{v:g}" for v in case.base_dist) + "]"
        band_str = f"[{case.expected_low}, {case.expected_high}]"
        lines.append(
            f"| {case.label} | `{base_str}` | {case.delta_tv} | {result.power:.4f} | {band_str} |"
        )

    lines.append("")
    return "\n".join(lines) + "\n", powers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="出力先ファイル (既定: <repo-root>/data/derived/power-curve.md)",
    )
    args = parser.parse_args(argv)

    table, powers = render_table()
    sys.stdout.write(table)

    repo_root = Path(__file__).resolve().parents[2]
    out_path = args.out if args.out is not None else repo_root / "data" / "derived" / "power-curve.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(table, encoding="utf-8")

    ok = True
    for case, power in zip(CASES, powers, strict=True):
        if not (case.expected_low <= power <= case.expected_high):
            sys.stderr.write(
                f"[FAIL] {case.label}: power={power:.4f} は期待帯 "
                f"[{case.expected_low}, {case.expected_high}] の外\n"
            )
            ok = False

    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
