#!/usr/bin/env python3
"""a-priori categorical-multinomial power の 4 ケース比較表を作る.

`erre_sandbox.integration.embodied.bank_power.categorical_multinomial_power`
(実行には ``PYTHONPATH=analysis/apparatus`` が要る) を、ERRE-Sandbox
``experiments/20260708-m13-b-bank/power_worksheet.md`` (由来 commit
``589e881558f713b05312643cb842d0d924d1ce87``) の 3 ケースと同じ入力で
呼び出し、power を計算する。

★ 用語の精度 (重要、docstring と出力ヘッダの両方に必ず書く):
    power を殺すのは **base 分布が collapse していること自体ではない**。
    3 行目 (degenerate base + collapse-scale delta) が power≈0.95 と高いままに
    なることが示す通り、power を殺すのは **達成可能な delta_tv が小さいこと**
    である。base 分布が近-uniform でも degenerate でも、delta_tv が十分あれば
    power は高い。「collapse した分布では power が落ちる」という言い方は誤り
    (実測はむしろ逆: degenerate base の方が同じ delta_tv に対して敏感に反応し
    power が高くなる)。

自己検証: 4 ケースの power が期待帯に入らなければ exit 1 で落ちる
(帯: >=0.99 / 0.10<=p<=0.30 / >=0.85 / >=0.99)。加えて、4 ケースとも
seed・n_replicates 固定で出力は完全決定的なので、実測値そのものを
±1e-4 で厳密 pin する (`EXPECTED_POWER_PINS`)。期待帯は科学的主張の
番人として残し、pin は「この commit で数値が動いていないこと」の
回帰検知として別に効かせる。乱数は seed 固定 (POWER_SEED_DEFAULT
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
    "# power を殺すのは base 分布の collapse ではなく、\n"
    "# 達成可能な delta_tv が小さいことである\n"
    "# (ケース3: degenerate base + delta_tv=0.01 (事前登録 0.10 の 1/10) の\n"
    "#  shift でも power は高いままになる実測を参照)\n"
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
    Case(
        label="degenerate base + 事前登録設計 delta",
        base_dist=(0.96, 0.01, 0.01, 0.01, 0.01),
        delta_tv=0.10,
        expected_low=0.99,
        expected_high=1.0,
    ),
)

# 実測値の厳密 pin (±PIN_TOLERANCE)。CASES は seed・n_replicates を固定しており
# 出力は完全決定的なので、実測できる値を推測せずに pin できる。期待帯
# (Case.expected_low/high) は「科学的主張が生きているか」の番人として別に残し、
# こちらは「この commit で数値そのものが動いていないか」の回帰検知に使う。
# 値は analysis/scripts/power_curve.py をこの pin ブロック追加時点で実行し、
# categorical_multinomial_power の戻り値をそのまま転記したもの (推測禁止)。
EXPECTED_POWER_PINS: tuple[float, ...] = (
    1.0,  # 事前登録設計 (near-uniform)
    0.18425,  # collapse-scale delta (proposal の 1/10)
    0.95325,  # degenerate base + collapse-scale delta
    1.0,  # degenerate base + 事前登録設計 delta
)
PIN_TOLERANCE = 1e-4

M_DRAWS = M_MIN  # 300
K_CONTEXTS = K_MIN  # 8
POOLING = True
SEED = POWER_SEED_DEFAULT  # 20260708
N_REPLICATES = N_REPLICATES_DEFAULT  # 4000 (下げない)


def render_table() -> tuple[str, list[float]]:
    lines: list[str] = []
    lines.append(HEADER_NOTE)
    lines.append(
        f"共通パラメータ: m_draws={M_DRAWS}, k_contexts={K_CONTEXTS}, "
        f"pooling={POOLING}, seed={SEED}, n_replicates={N_REPLICATES}"
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
            f"| {case.label} | `{base_str}` | {case.delta_tv} | "
            f"{result.power:.4f} | {band_str} |"
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

    ok = True
    for case, power in zip(CASES, powers, strict=True):
        if not (case.expected_low <= power <= case.expected_high):
            sys.stderr.write(
                f"[FAIL] {case.label}: power={power:.4f} は期待帯 "
                f"[{case.expected_low}, {case.expected_high}] の外\n"
            )
            ok = False

    for case, power, pin in zip(CASES, powers, EXPECTED_POWER_PINS, strict=True):
        if abs(power - pin) > PIN_TOLERANCE:
            sys.stderr.write(
                f"[FAIL] {case.label}: power={power!r} は pin {pin!r} から "
                f"±{PIN_TOLERANCE} を超えて乖離\n"
            )
            ok = False

    # 検査を通過した場合にのみ data/derived/ へ書き出す。検査より前に書くと、
    # FAIL 時にも古い (あるいは誤った) 表が data/derived/ に残ってしまう。
    if ok:
        repo_root = Path(__file__).resolve().parents[2]
        default_out = repo_root / "data" / "derived" / "power-curve.md"
        out_path = args.out if args.out is not None else default_out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" を明示する。既定の text mode は Windows で \n を \r\n へ
        # 変換するため、同じ内容でも OS 間で出力ファイルの byte が一致しなくなる
        # (2026-09-12 に Windows / WSL2 で実測。内容差は無く eol 差だけだった)。
        with out_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(table)
    else:
        sys.stderr.write(
            "[FAIL] 検査未通過のため data/derived/power-curve.md は書き換えない\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
