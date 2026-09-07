# 実行環境

`reproducibility-discipline` ルール2: **環境は lockfile で固定する**。

## lockfile

| ファイル | 置き場所 | 由来 | 状態 |
|---|---|---|---|
| `uv.lock` | `env/uv.lock` | ERRE-Sandbox 本体からコピー | **未配置** |
| `pyproject.toml` | `env/pyproject.toml` | 本論文の解析に必要な依存だけに削る | **未配置** |

> 本体の `pyproject.toml` をそのまま持ってこない。**この論文の解析に要る依存だけ**に削ること。
> 削った結果 `uv lock` を打ち直したら、その lock を置く。

## 実行環境の記録 (実走したら埋める)

| 項目 | 値 |
|---|---|
| OS | (未記録) |
| Python | (未記録) |
| uv | (未記録) |
| CPU / GPU | (未記録) |
| LLM backend / model | (未記録。該当する場合) |
| 実行日 | (未記録) |

## 決定性に関する注意

ERRE-Sandbox 本体由来のデータを扱う場合、**浮動小数は 6 桁量子化されている前提**
(`CANONICAL_FLOAT_DECIMALS = 6`)。生の float を再量子化せずに hash すると
Windows/Linux 間で 1 ULP の差が出る。詳細は論文 03 を参照。
