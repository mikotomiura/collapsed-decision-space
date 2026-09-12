# CLAIM BOUNDARY — 本文に書いてよいこと / 絶対に書かないこと

> **本文 (`main.md`) とは別ファイルで保持する。** 本文を書く人が本文だけ読んで済ませられないようにするため。
> SSOT = `.steering/20260912-paper02-phase1a/design-final.md` §9 (ERRE-Sandbox 側、非公開)。
> 由来 = 本 repo の `README.md` §1 + 正典 ADR §4.1 + Codex independent review (2026-09-12)。
>
> **本文は英語で書く** (PCI RR は書式自由だが投稿言語は英語)。
> したがって下の検査パターンは**英語の正規表現**である。

---

## 1. 書いてよいこと

- チャネルが非退化に配線されていること (ES-1 / ES-3。**positive control が 0 を返せることを含む**)
- そのチャネルの下流効果が、事前登録された margin の下で検出されなかったこと
- near-uniform 基質でも検出力が確保できること (直感の反証)
- effect-absent / low-power / apparatus-invalid の**三分離**
- 単一 apparatus・単一 regime (`think=False`) という **bounded envelope** の明示

---

## 2. 絶対に書かないこと (G1-G13)

各行の **検査パターン** は `main.md` に対する機械検査で使う。
ヒットしたら **本文を直す。検査を緩めない。**

| # | 書かない主張 | 理由 | 検査パターン (case-insensitive) |
|---|---|---|---|
| G1 | 歩行 / 移動それ自体が創造的発散を生まない | **測っていない**。主語はチャネルであって歩行でも創造性でもない | `locomotion (does not\|doesn't) (produce\|generate\|cause)`, `walking (does not\|doesn't)`, `no creative divergence` |
| G2 | 身体性は無意味である | bounded envelope 限定の結果を一般命題に拡大している | `embodiment is (meaningless\|useless\|irrelevant)`, `embodiment does not matter` |
| G3 | 事前宣言 margin の導入が新規である | **[28] が既出**。good practice の遵守として書く | `(we\|this paper) (introduce\|propose)[a-z ]*(declared\|pre-declared\|pre-registered) margin`, `novel(ty)? (of\|is)[a-z ]*equivalence` |
| G4 | family effect と think-regime effect を分離した | 正典 ADR §4.1 の**閉じない gate** | `(separat\|disentangl\|decoupl)[a-z]* (the )?(family\|model family)[a-z ]*(from )?[a-z ]*think`, `isolates? the (family\|think)[a-z ]*effect` |
| G5 | `think=False` が死点の原因だと示した / 否定した | 同上 | `think=false (is\|was) the cause`, `(shows?\|demonstrates?\|proves?) that think=false` |
| G6 | byte 一致で control した | control は**統計量の許容帯比較**。byte 一致は replay-verify の性質 (DA-P02R-6) | `byte-(identical\|exact)[a-z ]*control`, `control[a-z ]*byte-(identical\|exact)` |
| G7 | collapse した分布では検出力が落ちる | **実測は逆**。degenerate base + collapse-scale delta では `power = 0.9533`。検出力を殺すのは **達成可能な `delta_tv` が小さいこと** | `collapsed? (base )?distribution[a-z ]*(low\|reduced\|kills?) power`, `degenerate[a-z ]*(low\|reduced) power` |
| G8 | C-proper の結果を `llama3.1` の予測として書く | §2.6 (eligibility) に当たる。C は planned analysis の焦点でない | `we (expect\|predict\|anticipate)[a-z ]*llama`, `llama[a-z0-9.: ]*will (also )?(show\|reproduce\|replicate)` |
| G9 | Level 6 が保証されている | **defensible な読み**であって PCI RR の明文の保証ではない | `level 6 is (guaranteed\|assured\|preserved)`, `guarantees? level 6` |
| G10 | `D_loco = 7.40e-17` と書く | **キーの取り違え**。`7.401486830834377e-17` は **`zone_function_d_loco`** (zone-function positive control)。**主推定は `d_loco = 0.04682681825722385`** | `D_loco *= *7\.4`, `D_loco[^\n]{0,20}e-17` |
| G11 | R5 PASS は版ドリフトが無かったことの証明である | PASS は**帯の中にあること**しか言わない | `(proves?\|demonstrates?\|establishes?)[a-z ]*no (version )?drift`, `rules? out[a-z ]*version drift` |
| G12 | R5 FAIL 時に primary の潜在結果を論じる | 停止条件の趣旨を壊す | `(had\|if)[a-z ]*r5[a-z ]*(failed\|fails)[^.]*primary[^.]*would` |
| G13 | 2 族で再現したので family / think-regime が分離できた | R1 経由で G4 に戻る**言い換え穴** | `(two\|both) (model )?famil(y\|ies)[a-z ,]*(therefore\|thus\|hence)[a-z ]*(separat\|disentangl\|isolat)` |

---

## 3. 検査の作り方 (Phase 1b で実装する。**恒真にしない**)

`.steering/.../design-final.md` §10 と `feedback_negative_fixture_must_not_be_self_referential`
の要求により、次の 2 条件を**両方**満たすこと。

1. **禁止句リストを、検査対象の本文から取らない。**
   パターンの SSOT は**このファイル**であり、検査器は `main.md` を検査する。
   `main.md` 自身にパターンを書いて「自分と一致しないこと」を確かめる形にしない
   (自己言及で恒真になる)

2. **「ヒット 0 が正解」の検査には陽性対照を添える。**
   検査器は次の 2 つを**両方**言えなければならない:
   - `manuscript/main.md` に禁止句が**無い**
   - `manuscript/_claim_boundary_positive_control.md` (故意に G1-G13 を全部書いた fixture) に
     禁止句が**ある** (G1-G13 の**すべて**を検出する)

   陽性対照が全件ヒットしなければ、検査器が壊れているか
   パターンが本文の言い回しを捕まえられていない。**その場合は exit != 0 で落とす。**

> **なぜここまでやるか**: 2026-09-07 に「negative fixture だけの検査が恒真だった」件、
> 2026-09-12 に「空の宛先を渡して比較経路が消えていた」件を実際に踏んでいる。
> **緑であることは、検査が走ったことを意味しない。**

---

## 4. 出典を書くときの注意

- 本文の数値は **`analysis/scripts/extract_verdict_table.py` の出力から取る。手写ししない**
- **`.steering/` を出典に書かない** — `.gitignore` で公開 repo に入らないため、
  読者から辿れない出典になる
- `power ≈ 0.18` を引くときは **必ず「near-uniform base + `delta_tv = 0.01`」まで書く** (G7)
- `d_loco` (主推定) と `zone_function_d_loco` (positive control) を**並べて書く** (G10)
