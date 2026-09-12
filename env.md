# 実行環境

`reproducibility-discipline` ルール2: **環境は lockfile で固定する**。

## lockfile

| ファイル | 置き場所 | 由来 | 状態 |
|---|---|---|---|
| `uv.lock` | `env/uv.lock` | ERRE-Sandbox 本体からコピー | **配置済** |
| `pyproject.toml` | `env/pyproject.toml` | ERRE-Sandbox 本体のプロジェクト定義 | **配置済 (削っていない。理由は下)** |

### なぜ `pyproject.toml` を削らなかったか

当初の方針は「この論文の解析に要る依存だけに削り、`uv lock` を打ち直す」だった。
**採らなかった。** `env/uv.lock` の SHA-256 は完了済み実走の manifest が pin している
`env_pins.uv_lock_sha256` (`9cc70f9dc5d6…`) と**一致している**。削って lock を打ち直すと
この一致が壊れ、「解析環境が実走環境と同じ lockfile に由来する」ことを言う手段を失う。
lockfile は証拠であって便宜物ではないので、byte 無改変で保存する側を採った。
`verify_data_hashes.py` がこの一致を毎回照合する (主張ではなく検査にしてある)。

代償は、依存が論文の解析に必要な範囲より広いこと。実害は `uv sync` の時間だけである
(既定の install に重い ML スタックは入らない。それらは extras の下にある)。

### 実行方法 (`--no-install-project` が要る)

```bash
uv sync --frozen --no-install-project --project env
```

`env/pyproject.toml` は `[tool.uv.build-backend] module-root = "src"` を宣言しているが、
本 repo に `src/erre_sandbox` は無い。`--no-install-project` を付けないと
**`Expected a Python module at: env\src\erre_sandbox\__init__.py` で落ちる** (2026-09-12 実測)。
解析スクリプトは `PYTHONPATH=analysis/apparatus` 経由で apparatus を読むので、
プロジェクト自体を install する必要がない。`repro.sh` はこの形で呼んでいる。

## 完了済み実走の環境 (`data/raw/cproper-manifest.json` の `env_pins`)

この論文の中核 verdict を産んだ実行環境。**機械可読な正本は manifest 側**であり、
下表はその読み下しである。

| 項目 | 値 |
|---|---|
| model | `qwen3:8b` |
| model digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |
| ollama | 0.31.1 |
| `think` | `false` |
| Python | 3.11.15 |
| httpx / pydantic | 0.28.1 / 2.13.2 |
| VRAM | 16.0 GB |
| `ERRE_ZONE_BIAS_P` | 0.2 |
| `uv.lock` SHA-256 | `9cc70f9dc5d61f6c74c08dee4dd73815993861022a80781a75ef5d873860c0f7` |
| 規模 | M=300 × K=8 = 4,800 draws |

## 前向き実走の環境 (Stage 1 で事前登録した条件)

実走は in-principle acceptance の後に行う。条件は `manuscript/main.md` §6 で凍結してある。

| 項目 | 値 |
|---|---|
| primary モデル | `llama3.1:8b`、digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` |
| control モデル | `qwen3:8b` (再走) |
| ollama | 0.32.12 |
| GPU | NVIDIA GeForce RTX 5060 Ti (16,311 MiB) |
| OS | Windows-10-10.0.26200-SP0 |
| 規模 | 2 アーム × 4,800 = 9,600 draws (≈ 5.09 h の見積り) |

> モデル / ollama version / 閾値 / seed / M / K / context bank の変更は
> **軽微な逸脱として扱わない** (`manuscript/main.md` §11)。

## 解析環境 (`repro.sh` を通した環境)

| 項目 | 値 |
|---|---|
| OS | Windows 11 (10.0.26200) |
| Python | 3.11.15 (lockfile 由来。`uv` が取得する) |
| uv | 0.11.7 |
| 実行日 | 2026-09-12 |

> `repro.sh` は解析の再現であって、LLM の draw の再現ではない。LLM の draw は
> 再生成すると一致しないので、`data/raw/` に凍結した出力を入力として扱う。

## 決定性に関する注意

ERRE-Sandbox 本体由来のデータを扱う場合、**浮動小数は 6 桁量子化されている前提**
(`CANONICAL_FLOAT_DECIMALS = 6`)。生の float を再量子化せずに hash すると
Windows/Linux 間で 1 ULP の差が出る。詳細は論文 03 を参照。
