# 02 — Powered null: 身体化チャネルは配線するが伝播しない

> **タイトル (確定 2026-09-07)**: A powered null on a verified channel: separating
> effect-absent from low power in embodied LLM agents
> **repo (PUBLIC)**: <https://github.com/mikotomiura/powered-null>

> **status (2026-09-13)**: Stage 1 Registered Report protocol の**初稿が
> `manuscript/main.md` にある**。前向きの draw は 1 つも取得していない。
> データ収集は in-principle acceptance の後に始まる (`manuscript/main.md` §11)。
> 投稿先 = **PCI Registered Reports → Peer Community Journal**。

## 0. この論文の一文

> エージェントの空間移動履歴が decode サンプリングを駆動する因果チャネルは、ablation で
> bit-identical に消える形で実在する。しかし検出力を確保した M-sample 設計の下で、その
> チャネルは下流の離散ゾーン選択を偏らせない。かつ、near-uniform なカテゴリ分布は
> 低検出力を意味しない。

**主語は「チャネル」であって「歩行」でも「創造性」でもない。**

## 1. claim 境界

**正典は `manuscript/CLAIM-BOUNDARY.md`** (禁止句 G1-G13 + 検査パターン)。
`analysis/scripts/check_claim_boundary.py` がそれを読み、`manuscript/main.md` と
**この README** を検査する。検査は `repro.sh` から呼ばれる。

### 書いてよいこと

- チャネルが非退化に配線されていること (ES-1/ES-3、positive control が 0 を返せることを含む)
- そのチャネルの下流効果が、事前登録された margin の下で検出されなかったこと
- near-uniform 基質でも検出力が確保できること (直感の反証)
- effect-absent / low-power / apparatus-invalid の三分離

### 絶対に書かないこと (要約。全 13 件は `manuscript/CLAIM-BOUNDARY.md`)

- 「歩行は創造的発散を生まない」 — **測っていない**
- 「身体性は無意味である」 — bounded envelope (real qwen3:8b / think=False / 単一 apparatus) 限定
- 「事前宣言 margin を導入したのが新規」 — **[28] が既にやっている**。good practice の遵守として書く

## 2. 中核の数値 (全て取得済・追加実験不要)

**本文に載せる数値は `analysis/scripts/extract_verdict_table.py` の出力から取る。手写ししない。**

| 量 | 値 | 出典 |
|---|---|---|
| `d_loco` (**主推定**) | 0.04682681825722385 | `data/raw/es3-verdict-forensic.json` (→ `data/derived/verdict-table.md`) |
| `ci_lower` (90% bootstrap) | 0.04529199663455194 ≥ `amp_floor` 0.02 (2.3×) | 同上 |
| `zone_function_d_loco` — **positive control。上の主推定とは別のフィールド**であり、λ=h(z) を強制したときに estimand が 0 を取りうることの実証 | 7.401486830834377e-17 | 同上 |
| ablation (None vs gain=0) | bit-equal、`ablation_max_abs_diff = 0.0` | 同上 |
| ES-1 `median(D_obs)` | **未収録**。`data/raw/` に ES-1 SPDM の機械可読 verdict が無い (apparatus コード `analysis/apparatus/erre_sandbox/evidence/spdm/` は同梱済みだが出力 verdict は未取得)。抽出スクリプトが出せない数値は本文にも書かない — フォローアップ課題 | — |
| **verdict** | `NO_CHANNEL_CONFORMANCE` | `data/raw/cproper-verdict.json` (→ `data/derived/verdict-table.md`) |
| `rho_hat` | 1.0 (8/8 context PASS) | 同上 |
| `power` | 1.0 | 同上 |
| `tv_bar` | **0.038065** < `delta_tv_min` 0.10 | 同上 |
| `permutation_p_value` | 0.057986 (reject=False) | 同上 |
| 設計 | M=300 × K=8 (4800 draws)、real qwen3:8b | `data/raw/cproper-verdict.json` (`thresholds`) / `data/raw/cproper-manifest.json` (`run`, `env_pins.model`) |
| power worksheet | near-uniform `[0.2]×5` (delta_tv=0.10) で power=1.0 / **near-uniform base + delta_tv=0.01** で power≈0.18 / **degenerate base + delta_tv=0.01 で power=0.9533** | `analysis/scripts/power_curve.py` → `data/derived/power-curve.md` |

> power を殺すのは base 分布の collapse ではなく、**達成可能な `delta_tv` が小さいこと**である
> (3 行目を参照)。`power≈0.18` を引くときは必ず「near-uniform base + `delta_tv=0.01`」まで書く。

## 3. 生き残っている新規性 (先行研究つぶし後、2026-09-07)

1. **estimand が「エージェント内部変調 → 下流カテゴリ選択」であること**。[28] の estimand は
   圧縮モデル同士の同等性であって、内部 knob の因果効果ではない
2. **near-uniform 基質での検出力直感の反証**

この 2 点**以外**を新規性として書かない。特に「LLM 評価に equivalence testing を持ち込む」は [28] で既出。

## 4. 先回りすべき査読リスク

- **[29] 由来**: 「logit access なら O(n/ε²) で済むのに、なぜ sample access で 4800 draws を引いたのか」
  → Ollama 経由で logit を取得していない制約を **Limitations に自分から書く** (`main.md` §12.3)
- **外的妥当性**: 単一モデル。**qwen3:8b 以外で同じ null が出るか**が最大の穴。
  → 2 個目のモデル (`llama3.1:8b`) の実走を Stage 1 として事前登録する (`main.md` §6)

## 5. ゲート

- [x] Stage 1 protocol 本文 (`manuscript/main.md`)
- [x] `verdict.json` から数値を機械抽出するスクリプト (手写ししない)
- [x] `repro.sh` (seed 固定・exit 0)
- [x] 凍結入力の SHA-256 照合 (`analysis/scripts/verify_data_hashes.py`)
- [x] 閾値の凍結が実走より前であることの検査 (`analysis/scripts/verify_threshold_freeze.py`)
- [x] 「書かないこと」に抵触する文が無いことの機械検査 + 陽性対照
      (`analysis/scripts/check_claim_boundary.py`)
- [x] 中核 verdict を同梱データから**再計算**して記録と突き合わせる
      (`analysis/scripts/recompute_verdict.py`、全 14 項目一致)
- [x] 本文の数値が凍結入力の値と文字単位で一致することの機械照合
      (`analysis/scripts/check_manuscript_numbers.py`)
- [x] 独立レビュー 2 者 (Opus code review + Codex gpt-5.5/xhigh)、HIGH 全反映
- [ ] **2 個目のモデルでの実走** — in-principle acceptance の後 (`main.md` §11)

## 6. 再現

```bash
bash repro.sh
```

9 ステップ (環境固定 / lint / 入力 hash + 上流 blob / 閾値凍結 + apparatus 閉包 /
**verdict の再計算** / 数値抽出 / power 表 / **本文数値の照合** / claim 境界) を順に走らせ、
1 つでも落ちれば非ゼロで終わる。両 OS の公開 CI (`.github/workflows/repro.yml`) が同じものを強制し、
派生物が両 OS で byte 一致することも突き合わせている。

上流 ERRE-Sandbox の clone があれば
`ERRE_SANDBOX_REPO=/path/to/ERRE-Sandbox bash repro.sh` で、commit 日時と ancestor 関係まで
機械検査される。

## 7. ライセンス

- コード (`analysis/`) = **Apache-2.0 OR MIT** (`LICENSE` / `LICENSE-MIT`)
- 本文と図 (`manuscript/`) = **CC BY 4.0** (`LICENSE-CC-BY-4.0.txt`)
- `data/raw/` = 著者自身が生成した研究データ。由来と hash は `data/data.md`
