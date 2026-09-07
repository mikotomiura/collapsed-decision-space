# 02 — Powered null: 身体化チャネルは配線するが伝播しない

> **確定タイトル (2026-09-07、user 裁定)**: A powered null on a verified channel: separating effect-absent from low power in embodied LLM agents
> **repo (作成済・PUBLIC・空)**: https://github.com/mikotomiura/powered-null.git


> status: ディレクトリ確保のみ。本文未着手。
> 投稿戦略の SSOT = `docs/publication-plan.md` / 科学的命題の SSOT = `docs/research-positioning.md`

## 0. この論文の一文

> エージェントの空間移動履歴が decode サンプリングを駆動する因果チャネルは、ablation で
> bit-identical に消える形で実在する。しかし検出力を確保した M-sample 設計の下で、その
> チャネルは下流の離散ゾーン選択を偏らせない。かつ、near-uniform なカテゴリ分布は
> 低検出力を意味しない。

**主語は「チャネル」であって「歩行」でも「創造性」でもない。**

## 1. claim 境界

### 書いてよいこと

- チャネルが非退化に配線されていること (ES-1/ES-3、positive control が 0 を返せることを含む)
- そのチャネルの下流効果が、事前登録された margin の下で検出されなかったこと
- near-uniform 基質でも検出力が確保できること (直感の反証)
- effect-absent / low-power / apparatus-invalid の三分離

### 絶対に書かないこと

- 「歩行は創造的発散を生まない」 — **測っていない**
- 「身体性は無意味である」 — bounded envelope (real qwen3:8b / think=False / 単一 apparatus) 限定
- 「事前宣言 margin を導入したのが新規」 — **[28] が既にやっている**。good practice の遵守として書く

## 2. 中核の数値 (全て取得済・追加実験不要)

| 量 | 値 | 出典 |
|---|---|---|
| `D_loco` | 0.0468 | `.steering/20260629-m13-es3-impl/verdict-result.md` |
| `CI_lower(D_loco)` (90% bootstrap) | 0.0453 ≥ AMP_FLOOR 0.02 (2.3×) | 同上 |
| zone-function positive control | `D_loco = 7.40e-17` (**estimand が 0 を取りうることの実証**) | 同上 |
| ablation (None vs gain=0) | bit-equal、`max|Δ| = 0.0` | 同上 |
| ES-1 `median(D_obs)` | 0.6667 (bootstrap 90%CI lower 0.6189) | `.steering/20260624-m13-es1-spdm/verdict-result.md` |
| **verdict** | `NO_CHANNEL_CONFORMANCE` | `experiments/20260710-m13-c-proper/artifacts/verdict.json` |
| `rho_hat` | 1.0 (8/8 context PASS) | 同上 |
| `power` | 1.0 | 同上 |
| `tv_bar` | **0.038065** < `delta_tv_min` 0.10 | 同上 |
| `permutation_p_value` | 0.057986 (reject=False) | 同上 |
| 設計 | M=300 × K=8 (4800 draws)、real qwen3:8b | 同上 (`thresholds`) |
| power worksheet | near-uniform `[0.2]×5` で power=1.0 / collapse demo で power≈0.18 | `.steering/20260708-m13-c-design-bank/design-final.md` (`bank_power.py`) |

## 3. 生き残っている新規性 (先行研究つぶし後、2026-09-07)

1. **estimand が「エージェント内部変調 → 下流カテゴリ選択」であること**。[28] の estimand は
   圧縮モデル同士の同等性であって、内部 knob の因果効果ではない
2. **near-uniform 基質での検出力直感の反証**

この 2 点**以外**を新規性として書かない。特に「LLM 評価に equivalence testing を持ち込む」は [28] で既出。

## 4. 先回りすべき査読リスク

- **[29] 由来**: 「logit access なら O(n/ε²) で済むのに、なぜ sample access で 4800 draws を引いたのか」
  → Ollama 経由で logit を取得していない制約を **Limitations に自分から書く**
- **外的妥当性**: 単一モデル。**qwen3:8b 以外で同じ null が出るか**が最大の穴。
  公開データより「2 個目のモデル」が要る (`.idea/paper-candidates-survey.md` §5.5)

## 5. ゲート

- [ ] 2 個目のモデルでの再現 (または「単一モデル限定」への正直な縮退)
- [ ] `verdict.json` から数値を機械抽出するスクリプト (手写ししない)
- [ ] 図の `repro.sh` (seed 固定)
- [ ] Codex (gpt-5.5 / xhigh) independent review、HIGH 全反映
- [ ] 「書かないこと」(§1) に抵触する文が本文に無いことを全文検索で確認
