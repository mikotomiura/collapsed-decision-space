# 引用マニフェスト — 02 powered null

書誌の SSOT は `docs/references.md`。**ここには `[n]` と役割だけを書く。著者名・DOI を再掲しない。**

## 登録済み ([n] 確定)

| [n] | 本稿での役割 | 置く節 |
|---|---|---|
| [28] | **必引用・二重の役割**。(a) 「LLM 評価に declared margin での equivalence testing を持ち込む」枠組みが既出であることを自ら示し、本稿の新規性主張をそこから外す。(b) 本稿の `delta_tv_min=0.10` 事前宣言を「既存 good practice の遵守」として正当化する | §2 Related work、§4 手続き |
| [29] | TV 距離推定のサンプル複雑性の formal な参照点。**ただし estimand は別物** (系列レベル TV vs 本稿の決定レベル categorical TV) — その差を明記する。あわせて logit access の安さを Limitations の弁明先に使う | §3 定式化、§8 Limitations |
| [27] | 参考。instrument artifact と real effect の分離という論法の隣接事例 | §2 (簡潔に) |

## 未登録 (執筆前に `literature-card` → `docs/references.md` 登録 → [n] 採番)

| 文献 | 本稿での役割 | 状態 |
|---|---|---|
| Vaccaro — *Preregistration for Experiments with AI Agents* (arXiv:2606.11217) | 事前登録の枠組み。01 と共有 | 未登録 |
| Card et al. — *With Little Power Comes Great Responsibility* (EMNLP 2020) | **検出力の議論の下敷き。本稿は「低検出力ではない」ことを主張するので必須** | 未登録 |
| Lakens — equivalence testing / TOST の標準的手続き (要特定) | 手続きの標準的出典。**まだ具体的な文献を特定していない** | 要調査 |
| Larooij & Törnberg (10.1007/s10462-025-11412-6) / Tomašević et al. (10.1140/epjds/s13688-026-00674-x) | 生成社会シミュレーションの検証論。positioning | 未登録 |
| [2] Park et al. Generative Agents | 装置の位置づけ。**既に references.md に [2] として登録済** | 登録済 |

## 注意

- `docs/references.md` 規則6 により、[27]-[31] は **abstract のみ実測確認済**。
  著者順・所属・版は正式引用前に原典で再確認する。特に **[30] は日付不整合あり** (本稿では未使用)
- 本稿は `.idea/paper-candidates-survey.md` の P02。**同 §5.2 に「新規性を狭める根拠」が記録されている**
