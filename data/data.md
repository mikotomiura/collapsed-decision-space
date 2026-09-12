# data provenance

`reproducibility-discipline` ルール: **データの version/hash を残す**。
凍結入力は `raw/` に置き、**一度置いたら書き換えない**。派生物は `derived/` に置き、必ず再生成できるようにする。

## raw/ (凍結入力 — 手で編集しない)

| ファイル | 由来 (元のパス) | SHA-256 | サイズ | 取得日 | ライセンス |
|---|---|---|---|---|---|
| `bank_annotation.jsonl` | `experiments/20260710-m13-c-proper/artifacts/bank_annotation.jsonl` | `378b5423d5b9d927f884e4381c80dd2116ef9342b6f05a92a07b12cd17bdc6fc` | 682,130 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ) |
| `cproper-manifest.json` | `experiments/20260710-m13-c-proper/artifacts/manifest.json` | `99c8d9fb3bd0ffa11f010980c29e2b0cc2d7fd70170f63e3ef07b43ad5529bed` | 1,240 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ) |
| `cproper-verdict.json` | `experiments/20260710-m13-c-proper/artifacts/verdict.json` | `a3412e4a6cd843d5846c7769a1f025c6350055ed8f79b6e94c92b30e8ecde2ea` | 1,207 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ) |
| `es3-verdict-forensic.json` | `experiments/20260629-m13-es3-locomotion/data/raw/verdict-forensic.json` | `24c6d3ba479b17897ac99d32e91e60679a9cff5dc0896d49d0ba501120c385a2` | 11,743 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ)。原本は `.steering/` 配下 (追跡外) にあり、2026-09-11 に `experiments/` へ byte 無改変で退避した (B-P03-5 / DA-CIS-4) |

> hash の取り方 (PowerShell): `Get-FileHash -Algorithm SHA256 data/raw/<file>`
> hash の取り方 (bash): `sha256sum data/raw/<file>`

## derived/ (再生成可能 — repro.sh が作る)

| ファイル | 生成元 | 生成コマンド |
|---|---|---|
| (未配置) | | |

## apparatus の由来 (analysis/apparatus/)

- 由来: ERRE-Sandbox `src/erre_sandbox/**` の推移閉包 68 ファイル (パッケージ相対 import を
  保つため `analysis/apparatus/erre_sandbox/<原本と同じ相対パス>` にそのまま配置している)
- 由来 commit hash: `589e881558f713b05312643cb842d0d924d1ce87`
- 検証方法: `pwsh paper/gather.ps1 -Verify` (ERRE-Sandbox root で実行)。
  2026-09-12 実行結果 = 175 件中 MATCH 175 / DRIFT 0 / MISSING 0 (うち paper 02 分 68 files)
- 使い方: `PYTHONPATH=analysis/apparatus`
- 再現コマンド (self-contained 確認、出力が repo 内のパスであること):
  ```bash
  PYTHONPATH=analysis/apparatus python -c "import erre_sandbox, erre_sandbox.evidence.es3_locomotion.verdict_report as v; print(v.__file__)"
  ```

## 外部データ (第三者由来)

外部データを使う場合、**ライセンスと再配布可否をここに明記する**。
再配布不可のものは `raw/` に置かず、`repro.sh` が取得する形にする。

| データセット | URL | ライセンス | 再配布可否 | 取得方法 |
|---|---|---|---|---|
| `bank_records.jsonl` (17.7 MB、SHA-256 `eec4b80db401c69b11e95c515385e72c0577ea9d9081e1e07148bca8d12352fb`、`data/raw/cproper-manifest.json` の `artifacts.bank_records.jsonl.sha256` に既に pin 済) | (Zenodo 未登録、取得元は ERRE-Sandbox `experiments/20260710-m13-c-proper/artifacts/bank_records.jsonl`) | 本 repo と同一 (著者自身が生成した研究データ) | サイズを理由に本 repo には同梱しない | ERRE-Sandbox 側の該当パスから取得し、上記 SHA-256 で照合する |
