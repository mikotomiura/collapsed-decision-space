#!/usr/bin/env bash
# 1 コマンド再現 (reproducibility-discipline ルール3)。
# これが exit 0 で通らないうちは「再現できる」と書かない。
#
# 使い方:  bash repro.sh
#
# 前提:
#   - uv がインストール済み (https://docs.astral.sh/uv/)
#   - ネットワーク (初回の `uv sync` で依存を取得するため)
#
# 走らせるもの (順に、1 つでも落ちたら即座に非ゼロで終わる):
#   1. lockfile による環境固定
#   2. lint
#   3. 凍結入力の SHA-256 + 上流 blob 照合 analysis/scripts/verify_data_hashes.py
#   4. 閾値の凍結検査 (値 + bytes)        analysis/scripts/verify_threshold_freeze.py
#   5. verdict の再計算と記録との突合     analysis/scripts/recompute_verdict.py
#   6. 本文に載る数値の機械抽出           analysis/scripts/extract_verdict_table.py
#   7. power 表の再生成                   analysis/scripts/power_curve.py
#   8. 本文の数値と凍結入力の照合         analysis/scripts/check_manuscript_numbers.py
#   9. claim 境界の禁止句検査 + 陽性対照  analysis/scripts/check_claim_boundary.py
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# --- seed 固定 (reproducibility-discipline ルール2) ---
SEED_VALUE="$(cat SEED)"
export PYTHONHASHSEED="$SEED_VALUE"
export ERRE_SEED="$SEED_VALUE"
echo "[repro] SEED=$SEED_VALUE (repo 全体の seed)"
# 測定側の seed は 20260708 で、manuscript/main.md §6.3 に凍結してある。
# この SEED は repo 全体の慣習値であり、派生物の決定性は POWER_SEED_DEFAULT が担う。

# 日本語の診断メッセージが Windows コンソール (cp932) で落ちないようにする。
export PYTHONUTF8=1

# 同梱 apparatus を import させる。これが本 repo 内のパスへ解決することが
# self-contained であることの条件である (data/data.md の「apparatus の由来」参照)。
export PYTHONPATH="$REPO_ROOT/analysis/apparatus"

# --- 1. 環境を lockfile で固定 ---
# `--no-install-project` が要る: env/pyproject.toml は上流 ERRE-Sandbox の
# プロジェクト定義そのもの (env/uv.lock と対にして、実走時の lockfile を byte 無改変で
# 保存するために置いてある) であり、本 repo に src/erre_sandbox は無い。解析スクリプトは
# PYTHONPATH=analysis/apparatus 経由で apparatus を読むので、プロジェクト自体を
# install する必要がない。
echo "[repro] 1/9 uv sync"
uv sync --frozen --no-install-project --project env

RUN=(uv run --project env --no-sync)

# --- 2. lint ---
echo "[repro] 2/9 ruff check"
"${RUN[@]}" ruff check analysis/scripts

# --- 3. データの完全性検証 (data/data.md の hash と照合) ---
echo "[repro] 3/9 verify_data_hashes"
if [ -n "${ERRE_SANDBOX_REPO:-}" ]; then
  "${RUN[@]}" python analysis/scripts/verify_data_hashes.py \n    --upstream-repo "$ERRE_SANDBOX_REPO"
else
  "${RUN[@]}" python analysis/scripts/verify_data_hashes.py
fi

# --- 4. 閾値の凍結検査 ---
# 上流 ERRE-Sandbox の clone があれば ERRE_SANDBOX_REPO に渡すと、commit 日時と
# ancestor 関係まで機械検査される。無ければオフライン検査のみ (manuscript/main.md
# §10.2 に、それぞれが何を示して何を示さないかを書いてある)。
echo "[repro] 4/9 verify_threshold_freeze"
if [ -n "${ERRE_SANDBOX_REPO:-}" ]; then
  "${RUN[@]}" python analysis/scripts/verify_threshold_freeze.py \
    --upstream-repo "$ERRE_SANDBOX_REPO"
else
  "${RUN[@]}" python analysis/scripts/verify_threshold_freeze.py
fi

# --- 5. 記録された verdict を同梱データから再計算して突き合わせる ---
# 本 repo で最も強い再現検査。他のステップは「記録と出荷物が一致する」ことしか
# 言わないが、ここは中核 verdict が同梱データから導けることを実際に確かめる。
echo "[repro] 5/9 recompute_verdict"
"${RUN[@]}" python analysis/scripts/recompute_verdict.py

# --- 6. 本文に載る数値の機械抽出 ---
echo "[repro] 6/9 extract_verdict_table -> data/derived/verdict-table.md"
"${RUN[@]}" python analysis/scripts/extract_verdict_table.py \
  --out data/derived/verdict-table.md > /dev/null

# --- 7. power 表の再生成 ---
echo "[repro] 7/9 power_curve -> data/derived/power-curve.md"
"${RUN[@]}" python analysis/scripts/power_curve.py \
  --out data/derived/power-curve.md > /dev/null

# --- 8. 本文の数値が凍結入力の値そのものであることの照合 ---
# 「手写ししない」は方針であって検査ではない。ここで literal を突き合わせる。
echo "[repro] 8/9 check_manuscript_numbers"
"${RUN[@]}" python analysis/scripts/check_manuscript_numbers.py

# --- 9. claim 境界の検査 ---
echo "[repro] 9/9 check_claim_boundary"
"${RUN[@]}" python analysis/scripts/check_claim_boundary.py

echo "[repro] DONE: 9 ステップすべて通過した"
