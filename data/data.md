# data provenance

`reproducibility-discipline` ルール: **データの version/hash を残す**。
凍結入力は `raw/` に置き、**一度置いたら書き換えない**。派生物は `derived/` に置き、必ず再生成できるようにする。

## raw/ (凍結入力 — 手で編集しない)

| ファイル | 由来 (元のパス) | SHA-256 | サイズ | 取得日 | ライセンス |
|---|---|---|---|---|---|
| `bank_annotation.jsonl` | `experiments/20260710-m13-c-proper/artifacts/bank_annotation.jsonl` | `378b5423d5b9d927f884e4381c80dd2116ef9342b6f05a92a07b12cd17bdc6fc` | 682,130 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ) |
| `cproper-manifest.json` | `experiments/20260710-m13-c-proper/artifacts/manifest.json` | `99c8d9fb3bd0ffa11f010980c29e2b0cc2d7fd70170f63e3ef07b43ad5529bed` | 1,240 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ) |
| `cproper-verdict.json` | `experiments/20260710-m13-c-proper/artifacts/verdict.json` | `a3412e4a6cd843d5846c7769a1f025c6350055ed8f79b6e94c92b30e8ecde2ea` | 1,207 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ) |
| `es3-verdict-forensic.json` | `experiments/20260629-m13-es3-locomotion/data/raw/verdict-forensic.json` | `24c6d3ba479b17897ac99d32e91e60679a9cff5dc0896d49d0ba501120c385a2` | 11,743 bytes | 2026-09-12 | 本 repo と同一 (著者自身が生成した研究データ)。原本は上流リポジトリの**追跡外の作業ディレクトリ**にあり、2026-09-11 に追跡下の `experiments/` へ byte 無改変で退避した。したがって上流の git 履歴はこの記録の**内容**を証言するが**産出時刻**は証言しない (`analysis/freeze-provenance.json` の `provenance_kind = "relocation"` / `manuscript/main.md` §12.5) |

> hash の取り方 (PowerShell): `Get-FileHash -Algorithm SHA256 data/raw/<file>`
> hash の取り方 (bash): `sha256sum data/raw/<file>`

### この表は SSOT であり、機械照合される

**hash の SSOT は本ファイルの上の表**である。機械可読な複製を別ファイルに置くと、
人が読む provenance と機械が読む pin のどちらが正かが曖昧になるので二重管理しない。

`analysis/scripts/verify_data_hashes.py` が**この表をパースして**照合する
(`repro.sh` の 3/8)。検査するのは 5 つ:

1. 表が想定どおりパースできること (**4 行ちょうど** / 64 桁 hex / サイズ整数)
2. `data/raw/` の各ファイルの SHA-256 とサイズが表と一致すること
3. `data/raw/` に**表に無いファイルが無い**こと (記録漏れの検出)
4. **実走 manifest が持つ独立 pin との交差照合** — 自分の記録同士の照合で閉じないために、
   `cproper-manifest.json` が持つ pin と突き合わせる:
   `bank_annotation.jsonl` ⇔ `artifacts[...].sha256` /
   `env/uv.lock` ⇔ `env_pins.uv_lock_sha256`
5. **上流 blob との content-addressed 照合** — 1〜3 は「本ファイルの記録と出荷物が一致する」
   ことしか言わない (repo 内で閉じた integrity check)。`analysis/freeze-provenance.json` の
   `frozen_inputs` が持つ**上流 commit の blob SHA-1** と突き合わせて初めて、
   同梱物が上流に登録された bytes そのものだと言える

> **2026-09-12 まで、本ファイルは hash を記録しただけで照合していなかった** (`B-P1A-4`)。
> 記録と照合は別の行為であり、記録だけを根拠に「検証した」と書くのは
> 「検査器に渡した ≠ 検査が走った」と同型の誤りである。上の 5 項目はその差を埋めるために置いた。

## derived/ (再生成可能 — repro.sh が作る)

`derived/` は `.gitignore` 配下であり、追跡しない。`repro.sh` が毎回作り直す。

| ファイル | 生成元 | 生成コマンド |
|---|---|---|
| `verdict-table.md` | `raw/cproper-verdict.json` / `raw/cproper-manifest.json` / `raw/es3-verdict-forensic.json` | `python analysis/scripts/extract_verdict_table.py --out data/derived/verdict-table.md` |
| `power-curve.md` | `analysis/apparatus/.../bank_power.py` (assumed-distribution only、入力ファイル無し) | `python analysis/scripts/power_curve.py --out data/derived/power-curve.md` |

## apparatus の由来 (analysis/apparatus/)

- 由来: ERRE-Sandbox `src/erre_sandbox/**` の推移閉包 69 ファイル (パッケージ相対 import を
  保つため `analysis/apparatus/erre_sandbox/<原本と同じ相対パス>` にそのまま配置している)。
  `bank_scorer.py` (`scorer_schema_version = "ecl-cproper-scorer-1"`) は 2026-09-12 に追加された
  (68 → 69 files)。`raw/cproper-verdict.json` がこの `scorer_schema_version` を宣言しているのに
  scorer が同梱されておらず、**中核 verdict を本 repo 単体で再導出できなかった**ため。
  原因は移送元の閉包計算の seed 登録漏れで、新たな推移依存は増えていない
- 由来 commit hash: `589e881558f713b05312643cb842d0d924d1ce87`
- 検証方法: `pwsh paper/gather.ps1 -Verify` (ERRE-Sandbox root で実行)。
  2026-09-12 実行結果 = **176 件中 MATCH 176 / DRIFT 0 / MISSING 0**

> **一度 DRIFT 1 を出したので、原因と対処を残す (2026-09-12)。**
> 対象は `data/raw/es3-verdict-forensic.json`。global の `core.autocrlf = input` により、
> **初回 import の `git add` 時点で CR が剥がされ、commit 済みの内容が原本と
> byte 一致しなくなっていた** (11,743 → 11,401 bytes)。
> 作業ツリーにはコピー直後の CRLF が残っていたため、**checkout が走るまで表面化しなかった**。
>
> これは「改行コードだけの無害な差」ではない。本ファイルの表 (上) は
> **原本の SHA-256 `24c6d3ba...` と 11,743 bytes を pin している**ので、
> 正規化された状態で公開すると **記録した hash と出荷物が食い違う** —
> `data/data.md` が防ぐはずのものそのものになる。
>
> 対処 = (1) 原本から byte 無改変で復元し、(2) `.gitattributes` に
> `data/raw/** -text` / `env/uv.lock -text` を置いて **git に二度と正規化させない**。
> 復元後の実測 = 11,743 bytes / `sha256 = 24c6d3ba...` で**上の表と一致**。
> **同梱 apparatus の docstring には、上流リポジトリの追跡外ディレクトリ (`.steering/…`) を
> 指す参照が残っている。** これらは本 repo に同梱していないので読者からは辿れない。
> 削れない理由は、apparatus を**上流の bytes そのもの**として出荷しているからである
> (1 文字でも変えると `verify_threshold_freeze.py` の blob 照合が落ちる)。
> 読み替えの必要な設計判断は `manuscript/main.md` に書いてある。

- 使い方: `PYTHONPATH=analysis/apparatus`
- 再現コマンド (self-contained 確認、出力が repo 内のパスであること。`repro.sh` の
  1/8 ステップと手順を揃えてある。素の `python` を直接呼ぶとクリーン checkout では
  `pydantic` 等が無く `ModuleNotFoundError` になる):
  ```bash
  uv sync --frozen --no-install-project --project env
  PYTHONPATH=analysis/apparatus uv run --project env --no-sync python -c "import erre_sandbox, erre_sandbox.evidence.es3_locomotion.verdict_report as v; print(v.__file__)"
  ```

  > **`--no-install-project` が要る** (2026-09-12 に実測)。`env/pyproject.toml` は上流
  > ERRE-Sandbox のプロジェクト定義そのもの (`env/uv.lock` と対にして、実走時の lockfile を
  > byte 無改変で保存するために置いてある) で、`[tool.uv.build-backend] module-root = "src"`
  > を宣言している。本 repo に `src/erre_sandbox` は無いので、これを付けずに実行すると
  > **`Expected a Python module at: env\src\erre_sandbox\__init__.py` で落ちる**。
  > 解析スクリプトは `PYTHONPATH=analysis/apparatus` 経由で apparatus を読むため、
  > プロジェクト自体を install する必要がない。
  >
  > 本ファイルは 2026-09-12 まで `uv sync --frozen --project env` と書いていたが、
  > **そのコマンドは一度も通っていなかった**。書いてあるコマンドが動くことは、
  > `repro.sh` が実際に走らせることでしか担保できない。

- **`env/uv.lock` は実走時の lockfile そのもの**である: その SHA-256 は
  `raw/cproper-manifest.json` の `env_pins.uv_lock_sha256`
  (`9cc70f9dc5d61f6c74c08dee4dd73815993861022a80781a75ef5d873860c0f7`) と一致する。
  `verify_data_hashes.py` がこの一致を毎回照合する (主張ではなく検査にしてある)。
- **凍結定数の由来と日付**は `analysis/freeze-provenance.json` にあり、
  `verify_threshold_freeze.py` が同梱 apparatus の git blob 識別子を再計算して
  上流 commit の blob と byte 一致することを確かめる。射程は `manuscript/main.md` §10.2。

## 外部データ (第三者由来)

外部データを使う場合、**ライセンスと再配布可否をここに明記する**。
再配布不可のものは `raw/` に置かず、`repro.sh` が取得する形にする。

| データセット | URL | ライセンス | 再配布可否 | 取得方法 |
|---|---|---|---|---|
| `bank_records.jsonl` (17.7 MB、SHA-256 `eec4b80db401c69b11e95c515385e72c0577ea9d9081e1e07148bca8d12352fb`、`data/raw/cproper-manifest.json` の `artifacts.bank_records.jsonl.sha256` に既に pin 済) | (Zenodo 未登録、取得元は ERRE-Sandbox `experiments/20260710-m13-c-proper/artifacts/bank_records.jsonl`) | 本 repo と同一 (著者自身が生成した研究データ) | サイズを理由に本 repo には同梱しない | ERRE-Sandbox 側の該当パスから取得し、上記 SHA-256 で照合する |
