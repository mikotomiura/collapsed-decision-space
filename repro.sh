#!/usr/bin/env bash
# 1 コマンド再現 (reproducibility-discipline ルール3)。
# これが通らないうちは「実験は未完了」とみなす。
#
# 使い方:  bash repro.sh
#
# 前提:
#   - uv がインストール済み
#   - env.md に記載の lockfile が env/ に配置済み
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# --- seed 固定 (reproducibility-discipline ルール2) ---
SEED_VALUE="$(cat SEED)"
export PYTHONHASHSEED="$SEED_VALUE"
export ERRE_SEED="$SEED_VALUE"
echo "[repro] SEED=$SEED_VALUE"

# --- 環境を lockfile で固定 ---
# TODO: env/ に uv.lock + pyproject.toml を置いたら以下を有効化する
# uv sync --frozen --project env

# --- データの完全性検証 (data/data.md の hash と照合) ---
# TODO: data/raw/ に凍結入力を置いたら有効化する
# python analysis/scripts/verify_data_hashes.py

# --- 解析の再実行 ---
# TODO: 図表の生成をここに書く。notebook は papermill か nbconvert で非対話実行する
# uv run --project env jupyter nbconvert --to notebook --execute \
#   analysis/notebooks/01-audit.ipynb --output-dir analysis/notebooks/_executed

# --- 図の再生成 ---
# TODO: manuscript/figs/ の全図を再生成する
# uv run --project env python analysis/scripts/make_figs.py --out manuscript/figs

echo "[repro] TODO: 上の各ステップを有効化するまで、このスクリプトは何も再現していない"
exit 1
