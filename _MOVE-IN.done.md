# MOVE-IN — 02 powered null を独立リポジトリにするための移送リスト

> このファイルは**あなたが手で移す作業の指示書**。移し終わったらこのファイルは消してよい。
> 想定リポジトリ名: `erre-paper-02-powered-null` (公開)

## ★ 大原則

1. **`.steering/` `.claude/` `.codex/` `.idea/` `loop/` をそのまま持ち込まない。**
   ただし **その中にある機械可読な verdict JSON は「証拠」なので、単体で抽出して
   provenance を付けて `data/raw/` に置く** (markdown の議論部分は持ち込まない)。
2. `data/raw/` は一度置いたら書き換えない。
3. 置いたら `data/data.md` に **SHA-256・由来・取得日**を記入する。

## 1. データ (→ `data/raw/`)

### そのまま移せるもの

| 元のパス | 移送先 | サイズ | 備考 |
|---|---|---|---|
| `experiments/20260710-m13-c-proper/artifacts/verdict.json` | `data/raw/cproper-verdict.json` | 1.2 KB | **本稿の中核**。`NO_CHANNEL_CONFORMANCE` / `tv_bar=0.038065` / `power=1.0` / `rho_hat=1.0` |
| `experiments/20260710-m13-c-proper/artifacts/manifest.json` | `data/raw/cproper-manifest.json` | 1.2 KB | run の来歴 |
| `experiments/20260710-m13-c-proper/artifacts/bank_annotation.jsonl` | `data/raw/bank_annotation.jsonl` | 682 KB | 注釈付き bank |
| `.steering/20260629-m13-es3-impl/verdict-forensic.json` | `data/raw/es3-verdict-forensic.json` | 要確認 | **ES-3 の機械可読 verdict はここにしか無い** (`D_loco=0.0468` 等)。JSON 単体で抽出する |

### git に入れないもの (→ Zenodo)

| 元のパス | 扱い | 理由 |
|---|---|---|
| `experiments/20260710-m13-c-proper/artifacts/bank_records.jsonl` | **Zenodo にアップロードし、リポジトリからは DOI で参照** | **17.7 MB**。GitHub の制限内ではあるが、生の LLM 出力を git 履歴に載せる利点がない。`repro.sh` が DOI から取得する形にする |

## 2. ★ D_loco の再生成 — 経路は存在する (2026-09-07 確認)

`experiments/` 配下に ES-1 / ES-3 のディレクトリは**無い**が、**再生成の単一エントリポイントは存在する**。

```
scripts/es3_verdict_run.py
```

docstring より (要点):

- 凍結 `evidence.es3_locomotion.constants` の閾値と `verdict_report` の決定ロジックだけを使い、
  **何も再チューニングしない**。事前登録された seed bank を通すだけ
- estimand = headroom 正規化 within-cell amplitude `D_loco`、verdict 統計量 =
  per-walk-seed bootstrap CI (`CI_lower(D_loco) ≥ AMP_FLOOR` → GO)
- forensic trail に **zone-function control (0 に潰れること)**、**ablation bit-equality**、
  N_hist 感度、per-cell headroom / λ-spread を記録する
- **「verdict は決定的なので、2 回目の実行は byte-identical な確認にしかならない」**
- forking-paths guard: 事前登録 seed bank で **1 回だけ**走らせる。gain / floor を弄って
  verdict を反転させるのは禁止 (別 config は superseding ADR が要る)

**→ したがって本稿の数値は `.steering` の markdown からの手写しではなく、
このスクリプトの再実行で再生成できる。** 移送前に本体で 1 回走らせ、出力を
`experiments/20260907-paper02-figs/` に置いてから、その成果物を `data/raw/` へ集約するのが最も強い。

| 使う凍結 apparatus | 場所 | 備考 |
|---|---|---|
| ES-3 locomotion | `src/erre_sandbox/evidence/es3_locomotion/` | **改変禁止**。`gather.ps1` が `analysis/scripts/apparatus/` へコピー済み |
| ES-1 SPDM | `src/erre_sandbox/evidence/spdm/` | 同上 (コピー済み) |
| power worksheet | `src/erre_sandbox/integration/embodied/bank_power.py` | **evidence/ ではなく通常 src**。コピー済み |
| 再生成ドライバ | `scripts/es3_verdict_run.py` | **未コピー**。走らせてから成果物を移すか、スクリプトごと移すかを決める |

## 3. 解析コード (→ `analysis/`)

> **2026-09-12 訂正 (DA-P0-13)**: 以下の表は import 閉包の問題が判明する**前**の記述。
> `analysis/scripts/apparatus/<mod>/` へ平坦化コピーすると、コピーしたモジュールが
> `from erre_sandbox.evidence...` / `from erre_sandbox.schemas import ...` のように
> パッケージ相対で import しているため、移送先でパッケージパスが崩れて import が
> 解決できない (2026-09-07 実測、`C:\ERRE-Sand_Box\paper\gather.ps1` 177-186 行のコメント
> 参照)。正しい移送先は `analysis/apparatus/erre_sandbox/<原本と同じ相対パス>` であり、
> `PYTHONPATH=analysis/apparatus` を通すことで self-contained に import できる。
> 実際に採用したのはこちらの閉包 (68 ファイル、由来 commit `589e881558f713b05312643cb842d0d924d1ce87`、
> `pwsh paper/gather.ps1 -Verify` で MATCH 確認済) であり、旧 `analysis/scripts/apparatus/`
> (11 ファイル、平坦化・import 不能) は破棄した。

| 元のパス | 移送先 | 備考 |
|---|---|---|
| `src/erre_sandbox/evidence/es3_locomotion/` | `analysis/apparatus/erre_sandbox/evidence/es3_locomotion/` | 凍結 apparatus。閉包の一部として commit hash 込みで `data/data.md` に記録済 |
| `src/erre_sandbox/evidence/spdm/` | `analysis/apparatus/erre_sandbox/evidence/spdm/` | 同上 |
| `src/erre_sandbox/integration/embodied/bank_power.py` | `analysis/scripts/bank_power.py` | 検出力計算。**これは閉包コピーでなく別枠のまま存在**(現状維持、移動しない) |
| C-proper scorer (`scorer_schema_version = "ecl-cproper-scorer-1"`) | — | **確認済: 閉包に含まれない (未解決)**。`grep -rn "ecl-cproper-scorer-1" analysis/apparatus/` はヒット 0 件、`grep -rl "scorer" analysis/apparatus/` も scorer 実体ファイルなし (`world_model.py` 等の無関係な部分一致のみ)。所在は本タスクでは特定できなかった |

### 新規に書くもの

- `analysis/notebooks/02-powered-null.ipynb` — verdict + power worksheet から本文の表を生成
- `analysis/scripts/extract_verdict_table.py` — **`verdict.json` から機械抽出** (手写ししない)
- `analysis/scripts/power_curve.py` — near-uniform `[0.2]×5` で power=1.0 / collapse demo で power≈0.18 の図

## 4. 原稿 (→ `manuscript/`)

| 元 | 移送先 | 備考 |
|---|---|---|
| 既にある | `manuscript/refs.md` | 引用マニフェスト (移送済み) |
| `paper/02-powered-null/README.md` | `manuscript/CLAIM-BOUNDARY.md` に改名して残す | **§1 の「絶対に書かないこと」を本文と別に保持する** |
| (新規) | `manuscript/main.md` | 本文 |
| (生成) | `manuscript/refs.bib` | `docs/references.md` から機械生成 |

## 5. 環境・ライセンス

01 と同じ (`env/uv.lock` + 削った `pyproject.toml`、`LICENSE` / `LICENSE-MIT`、`CITATION.cff` の TODO 埋め)。

## 6. 移送後のチェック

- [ ] `git init -b main` して初回コミット (本体の履歴を持ち込まない)
- [ ] `.gitignore` が効き `.steering/` 等が 1 つも入っていない
- [ ] `data/data.md` に全 raw の SHA-256 と由来
- [ ] `bank_records.jsonl` が git に**入っていない**こと、DOI 参照になっていること
- [ ] `bash repro.sh` が exit 0
- [ ] **`D_loco` が .steering の markdown からの手写しでなく apparatus 由来**であること
- [ ] 本文に「歩行は発散を生まない」系の文が無いこと (README §1 の禁止事項を全文検索)

---

## 移送先 remote (2026-09-07 確定・作成済)

- **repo**: https://github.com/mikotomiura/powered-null (PUBLIC・空・license 未設定)
- **確定タイトル**: A powered null on a verified channel: separating effect-absent from low power in embodied LLM agents
- `CITATION.cff` の `repository-code` は記入済。残 TODO = title 以外の
  `abstract` / `authors` / `license` / ORCID。

```bash
# 本ディレクトリを repo root として移送したあと
git init -b main
git add -A
git commit -m "chore: initial import from ERRE-Sandbox paper track"
git remote add origin https://github.com/mikotomiura/powered-null.git
git push -u origin main
```

> **注意**: `paper/` は ERRE-Sandbox 側で `.gitignore` 済 = **版管理外**。
> 移送するまでドラフトは git のバックアップ・履歴の外にある (`design.md` DA-1 の代償)。
