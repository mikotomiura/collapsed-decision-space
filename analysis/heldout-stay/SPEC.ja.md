# 事後仮説「None は channel-on で増える」の held-out 検査 — 仕様

この文書と `freeze.json`、`analysis/scripts/heldout_stay_check.py`、それを走らせる
`.github/workflows/heldout-stay.yml` を、1 つの commit (以下「凍結 commit」) で凍結する。
**判定に効く値はすべて `freeze.json` と封印済の `seal/arm-spec.json` にあり**、script はそこから読む。
この文書の解釈表・修飾子・禁止主張の文言は `freeze.json` と一字一句一致しなければならず、
`--self-test` の `SPEC-drift` がそれを検査する。

## 0. この検査は何で、何でないか

- **事後に立てた仮説を、それを生んだデータとは別のデータで 1 回だけ検査する**。仮説は完了済 run を
  見てから立てた。検査に使う前向き 2 アームは、仮説とは独立に採った draws である。
- **形式上の事前登録ではない**。前向き 2 アームのデータは 2026-09-15 から存在する。凍結 commit の
  サーバ時刻が示せるのは「仕様が結果より先に存在した」ことまでで、「凍結前に誰も条件別の件数を
  見ていない」ことは示せない。その部分は §4 の宣言で補い、宣言であると明記する。
- **実行順とは切り離せない**。3 run とも、context ごとに on 300 draws → off 300 draws の順で呼んでいる
  (`bank.py` の呼び出し順)。棄却しても、channel の効果か実行順 (時間・サーバ状態・drift) の効果かは区別できない。
- **p 値の水準そのものも、この順序に条件づけられる**。§6 の厳密検定が α を保証するのは、帰無の下で
  各 context の 600 draws が実行位置・時刻に関して交換可能であるときに限る。固定ブロック設計はこれを
  保証しない。drift や系列依存があれば、原因の帰属だけでなく p 値の校正も失われうる。
- 封印済の登録解析 (`seal/**`、本文 §8、分岐 R4) は一切変えない。この検査の結果は封印の外側にある。

## 1. 仮説の出自

完了済 run (`data/raw/bank_annotation.jsonl`、qwen3:8b、4,800 draws) で、`pre_bias_destination_zone`
が `None` の draw は channel-off 124/2400、channel-on 206/2400 あり、8 context のすべてで on > off だった。
6 カテゴリ (5 zone + None) の context 平均 TV は 0.058333。この観察は外部監査 (2026-09-17/18) が
**データを見てから**行ったもので、ここではそれを「仮説」とだけ扱い、証拠には数えない。

on と off の違いは sampling だけである: temperature 0.70 → 0.82、top_p 0.90 → 0.94。
system / user prompt は on と off で同一 (完了済 run の records で確認)。前向きアームでも同じであることは §8 の I3 が検査する。

## 2. 申告 — 凍結 commit の時点で既知だったこと、既知でなかったこと

既知 (baseline)。すべてここに列挙する:

1. 完了済 run の None 件数は off 124 / on 206、8/8 context で on > off。6 カテゴリの事後解析は
   観測 0.058333、p ≈ 0.001 (監査と、凍結前に本 script で再計算した値)。
2. **完了済 run の None 330 件は、全件が schema 検証の失敗である**。raw_response を装置の
   `parse_llm_plan` で再 parse すると、330 件すべてが `"destination_zone": "null"` (**文字列**の "null")
   で enum 検証に落ち、plan 全体が棄却されていた。JSON の null・key 欠落は 0 件。記録値と再 parse の
   不一致は 4,800 行中 0 件。原因は prompt template (`prompting.py` 48・71 行) が
   `"study|peripatos|chashitsu|agora|garden|null"` と null を引用符の内側に書いていることにある。
   annotation の `resolved_from = "pre_bias_direct_parse"` は全行に付く固定タグで、parse の成否を記録していない。
3. 前向き 2 アームの**アーム全体** (条件で分けていない) の None 件数: control 250/4800、primary 168/4800。
4. 各アームのセル (context × condition) ごとの None 率の最大値: control 0.086667、primary 0.066667。
   どのセルの値かは記録されていない。
5. 前向き 2 アームの pooled zone share と、セルごとの最頻 zone 占有率の min / max / mean
   (著者の作業記録 `run-descriptive-stats.md` にある、条件で分けていない量)。
6. 条件の並び: 両アームとも、context ごとに on 300 → off 300 のブロックで、ファイル順 = 実行順。
7. 前向きの run-manifest の設定値 (context_ids / k_contexts = 8 / m_draws = 300 / seed) と、全入力ファイルの
   sha256 とバイト数。
8. 封印済の検査結果: control は 5 カテゴリ推定量で非棄却 (p = 0.43989)、primary は推定量が測定不能 (分岐 R4)。

既知でない (realized):

- 前向き 2 アームの**条件別**の None 件数と、その向き
- 前向き 2 アームの None の内訳 (N_str / N_json / K / Z / S / F)

§8 の I6 は、3 と 4 の値がデータと一致することを機械検査する。申告したものが実物と違えば、検査は STOP で止まる。
ただし I6 が示すのは一致であって、その値を凍結前から知っていたという時刻ではない。

## 3. データと pin

入力は各アーム 3 ファイル (`run_annotation.jsonl` / `run_records.jsonl` / `run-manifest.json`)。
sha256 とバイト数は `freeze.json` の `inputs` に pin する。annotation と records の digest は、
実走 driver が 2026-09-15 に書いた `run-manifest.json` の `artifacts` 欄の値と一致する (I3 が検査する)。
実行後、これらのファイルを `data/prospective/{control,primary}/` に byte のまま置く (§13)。

## 4. 盲検の宣言

**この文書を含む凍結 commit の時点で、前向き 2 アームの条件別の None 件数と、その None の内訳は、
著者も、この仕様を書いたエージェントも、レビューに使った Codex も集計していなかった。**
凍結前に前向きデータについて知っていたのは §2 の 3〜8 に列挙したものである。
そのうち 3〜5 は、過去の作業記録にある条件で分けていない集計を読んだものである。
この仕様の作業中に前向きデータに対して行ったのは、sha256・行数・run-manifest のキー名と設定値の確認だけである。
仕様の検査は、完了済 run のデータと合成データで行った。Codex の実行記録には、前向きデータのパスへのアクセスは無い。
以上は**宣言**であって、検査で示したものではない。

## 5. outcome と分類器 (Q0)

- **主 outcome** Y = annotation の `pre_bias_destination_zone` が `None` であること。これは装置が記録した None であり、
  完了済 run の 124 / 206 と同じ操作的変数であり、封印推定量が落とした成分でもある。
- **分類器** (副次)。None の行の raw_response を、装置の parser 自身の手順 (`_extract_json_object` →
  `json.loads` → `destination_zone` の値) で読み、次の 6 類に分ける。
  - `N_str`: strip と casefold の後に "null" となる文字列
  - `N_json`: JSON の null
  - `K`: `destination_zone` の key が無い (parser の既定値は None なので、plan としては有効でありうる)
  - `Z`: zone 名 (表記ゆれで enum に落ちたもの、または zone は正しいが他の field で plan が棄却されたもの)
  - `S`: それ以外の値
  - `F`: JSON オブジェクトが無い・壊れている・オブジェクトでない・64KB を超える
- **明示的 null 表現** = `N_str` ∪ `N_json`。destination に null と書いた出力のことであり、意図 (「留まる」) を意味しない。
  `K` を含めないのは、何も書いていない出力は明示的な表現ではないからである。
- 主 outcome を明示的 null 表現にしない理由: 分類器は、完了済 run の内訳 (§2 の 2) を知った**後**に書いた新しい道具である。
  それを主に据えると、解析者が選べる余地が増える。

## 6. 検定 (Q1・Q2・Q10)

- アームごとに、H0 = 各 context の中で Y と条件ラベルが交換可能。H1 = on > off (片側)。**α = 0.025**。
  向きは完了済 run を見てから選んだので、片側 0.025 (両側 0.05 と同じ厳しさ) にする。
- 統計量 T = Σ_c (context c の on 側の Y の数)。帰無分布は、各 context の Y の総数 N_c を所与とした
  超幾何分布 Hypergeom(600, N_c, 300) を 8 個畳み込んだもので、**整数と有理数で厳密に**計算する。
  p = P0(T ≥ t_obs)。層別 permutation を厳密に評価したものに等しい。300/300 の均衡設計なので、
  T は pooled 率差・context 平均の率差・片側 CMH と順序が一致する。
- この厳密性は、帰無の下での交換可能性 (§0) を前提にした厳密性である。
- 判定は `Fraction(p) <= Fraction(1, 40)`。主検定と §7 の明示的 null 検定に乱数は使わない。
- scipy は使わない。封印済の環境 (`env/uv.lock`、凍結入力) では scipy が `eval` extra にしか無いので、
  `math.comb` と `fractions.Fraction` で書く。

## 7. 多重性 (Q3) と明示的 null の語 (IUT)

- **固定順序**: H_C (control) を α = 0.025 で検定する。H_P (primary) は、H_C が棄却されたときに限り
  α = 0.025 で確認的に検定する。これで主検定の FWER は 0.025 以下になる。H_C が棄却されなければ、primary の p は
  記述として報告するだけにする。順序の理由は、同じ model での再現を先に置き、別の族への一般化を後に置くことにある。
  封印済規則で R5 が primary を gate する形とも同じである。
- **明示的 null の語**は IUT で許可する。条件は、その arm の主検定が確認的に棄却され、かつ明示的 null 表現の指標に同じ
  厳密検定をかけて p ≤ 0.025 であること。**水準はアーム単位**であり、2 アームの主張を合わせた FWER は保証しない。

## 8. gate (Q4)

アームごとに I1 から順に評価する。許容誤差は 0。

| gate | 発火条件 | 帰結 |
|---|---|---|
| I1 | 入力の sha256 またはバイト数が pin と違う | STOP |
| I2 | 行数・キー・条件・context の集合・(context, condition) ごとの mc_index = {0..299}・ファイル順 (context、on ブロック → off ブロック、mc_index 昇順)・zone 値の集合のどれかが崩れている | STOP |
| I3 | ファイルの意味が仕様と違う: run-manifest の arm・model・model digest・think・ollama 版・bank checksum・context_ids・k・m・seed が `seal/arm-spec.json` と一致しない、manifest が annotation / records の digest を記録していない、draw の sampling がその条件について宣言した値でない、context 内で prompt が draw や条件によって違う | STOP |
| I4 | annotation と records の zone が食い違う | STOP |
| I5 | 装置の `parse_llm_plan` を raw_response に再適用しても、記録値を全行では再現しない | STOP |
| I6 | §2 の 3・4 の申告値 (アーム全体の None 件数、セルごとの最大 None 率) がデータと違う | STOP |
| I7 | 全 Y を on 側に置いた最も極端な配置の p (= Π C(300, N_c) / C(600, N_c)) が 0.025 を超える | その arm は検査不能 |

- STOP は欠陥であって結果ではない。解釈せず、どの gate かを報告し、user 裁定に回す。
- I7 を件数の閾値にしなかった理由: 件数で閾値を置くと、どこに置いても恣意的になる。しかも既知の合計 (§2 の 3) を見れば、
  発火するかどうかが分かってしまう。I7 は検定そのものの性質なので、調整の余地が無い。
  **主検定では I7 が発火しないことは、既知の合計 (250 / 168) から分かっている。** 明示的 null 検定については、
  内訳が未知なので分からない (到達不能なら p > 0.025 になり、明示的 null の語は使えない)。
- 検出力は gate にしない (§14 で申告する)。

## 9. 解釈表 (Q5)

script が行 ID を機械的に出す。行の文言は `freeze.json` の `rows` と一致する。

| ID | いつ | 言えること | 言えないこと | 改稿への含意 |
|---|---|---|---|---|
| STOP | I1〜I6 のいずれかが発火した | どの gate が何を検出したか | どちらのアームについても、条件差に関する主張 | 結果は無い。欠陥として user 裁定に回す |
| A | control が確認的に棄却し、primary も確認的に棄却した | 前向き 2 run の両方で、channel-on ブロックの記録上の None が channel-off ブロックより多かった | 実行順から切り離した channel の効果、意図 (留まることを選んだ) の主張、2 model・8 context の外への一般化 | 事後の発見が独立 draws で再現し、2 つ目の族でも封印推定量が落とした成分が動いた。DA-P2-22 の理由 2 (§12.1 の confound) には部分的にしか答えない |
| B | control が確認的に棄却し、primary は確認的に棄却しなかった | 同じ model・別の backend 版の独立 draws で、channel-on ブロックの記録上の None が多かった | llama3.1:8b に効果が無い、あるいは同等である | 事後の発見は同じ model で再現した。2 つ目の族では確認されなかったので、改稿は単一 model の範囲で書く |
| B_prime | control が確認的に棄却し、primary が I7 で検査不能だった | 同じ model・別の backend 版の独立 draws で、channel-on ブロックの記録上の None が多かった。primary はこの検定では検査不能だった | llama3.1:8b についての主張すべて | B と同じく単一 model の範囲で書き、primary は検査不能と明記する |
| C | control が棄却しなかったが、primary の記述的な p は 0.025 以下だった | 確認的な主張は無い。primary の p は記述として報告する | llama3.1:8b に効果がある (固定順序のもとで primary は確認的に検定されていない) | 事後の発見は同じ model の独立 draws で再現しなかった。改稿は power と推定量の不一致に絞り、primary の値は記述に留める |
| D | control が棄却せず、primary の記述的な p も 0.025 を超えた | held-out では再現しなかった。完了済 run の発見は探索的な位置づけに下げる | 効果が無い、あるいは同等である | 事後の発見は脆い。改稿は power と推定量の不一致に絞る |
| E | control が I7 で検査不能だった | 確認的な主張は無い。どの gate で止まったかを報告する | どちらのアームについても、条件差の主張 | I6 が通っていれば起こらない行である (250 件の None で到達不能にはならない)。起きたら欠陥を疑い user 裁定に回す |

「別の backend 版」「model」は I3 が run-manifest と `seal/arm-spec.json` の照合で確かめる。

アームごとの修飾子 (表の行を変えない):

- explicit_null: その arm の主検定が確認的に棄却され、かつ明示的 null 表現 (N_str ∪ N_json) に同じ検定をかけた p も 0.025 以下のときに限り、「destination_zone に null と書いた出力が増えた」と書いてよい。水準はアーム単位であり、2 アームの主張を合わせた FWER は保証しない。成立しなければ「増えたのは記録上の None 全般である」とだけ書く
- reverse: 下側の p が 0.025 以下なら、逆向き (off > on) の差が記述的に出たと書く。確認的な主張にはしない

**表に無い結果が出たら、解釈を足さずに止めて報告する。**

## 10. 副次解析 (Q6) と記述統計

判定には使わず、表のどの行も変えない。多重性の family にも入れない。

- **6 カテゴリの平均 TV**: 5 zone + None の 6 カテゴリで、context ごとに TV(on, off) を取り、8 context で平均する。
  entropy gate はかけない。帰無分布は `bank_scorer.py` と同じ形の層別 permutation で作る:
  B = 20,000、arm ごとに新しく `numpy.random.default_rng(20260708)` を作る (20260708 は本文 §6.3 で凍結済みの測定 seed)。
  context はソート順、pool は on → off の順に連結、TV は小数 9 桁に丸めてから ≥ で比較し、p = (ge + 1)/(B + 1)。
  観測値と一緒に、帰無の平均と p95 を並べて報告する (帰無の下でも 0 にならない量である)。
- **記述統計** (事前に列挙する。これ以外は出さない):
  - 16 セル (context × condition) の None 件数、pooled の率と率差
  - Mantel–Haenszel の共通オッズ比と、Robins–Breslow–Greenland の 95% 区間
  - on > off / 同数 / on < off となる context の数
  - None の分類 (§5) × 条件、および context 別の内訳
  - 各ブロックの前半 (mc_index < 150) と後半の None 率 (条件別、pooled)。実行順による drift の診断であり、効果を実行順から切り離す力は無い
  - 下側の p (§9 の reverse 修飾子)
  - 明示的 null 検定の T・p・到達可能な最小の p

## 11. どの結果でも言ってはいけない主張 (Q7)

- エージェントが「留まることを選んだ」という意図の主張 (None の実体は schema 検証失敗である)
- 実行順 (context ごとに on ブロック → off ブロック)・時間・サーバ状態から切り離した channel の効果
- 固定ブロック設計のまま、実行位置に対する交換可能性や時間的安定性を仮定せずに、厳密 p 値の水準が保証されたとする主張
- λ・locomotion・身体性への帰属、および temperature と top_p のどちらか一方への帰属
- 形式上の事前登録、または PCI RR の意味での confirmatory
- 非棄却を「効果が無い」「同等である」と読むこと
- arm 間の効果量の差を model family の差として読むこと
- 完了済 run の p ≈ 0.001 を証拠として数えること (仮説を生んだデータである)
- 封印済 verdict や分岐 R4 / R5 を変える主張
- 6 カテゴリの平均 TV を margin 0.10 に照らして materiality を判定すること
- 凍結前に誰も条件別の件数を見ていないことを、検査で示したと書くこと (宣言にすぎない)
- 2 model・8 固定 context の外への一般化

正しい言い方は「事後仮説を held-out データで検査した。仕様は条件別の集計より前に凍結した」である。

## 12. 凍結と実行 (Q8)

1. **凍結の範囲** (`FROZEN_PATHS`): この文書、`freeze.json`、script、`.github/workflows/heldout-stay.yml`、
   vendored の apparatus 全体 (parser とそれが import するもの)、`env/pyproject.toml`、`env/uv.lock`、
   `seal/arm-spec.json`、`data/raw/bank_annotation.jsonl`。
   **凍結 commit とは、この範囲に最後に触れた commit のことである。** 実行と `--verify` の両方が、
   記録された凍結 commit がいまもそれであることを要求する。凍結後にこの範囲を 1 バイトでも変えれば、
   以後の `--verify` は落ち続ける。
2. 凍結 commit を push し、PR を開く。PR 本文の冒頭に凍結 commit の sha を書く。
3. 両 OS の CI (`heldout-stay` workflow の `--self-test` / `--mutations` / `--verify`) が緑になってから実行する。
   実行前に修正が要る場合は、新しい凍結 commit として作り直し、その経緯を記録する。
4. `--run --freeze-commit <sha>` を実行する。script は次のどれかが満たされなければ実行を拒否する:
   - 凍結 commit が存在し、HEAD がその子孫であり、凍結範囲に最後に触れた commit である
   - 凍結範囲のパスがすべて git で追跡されている
   - 追跡ファイルに変更が無い
   - 凍結 commit が remote にある
   - `result.json` と `run.log` がまだ無い
   - 入力が pin と一致する (I1)
5. script は結果を**黙って**計算し、`result.json` と `run.log` を排他的に作成してから、はじめて結果を表示する。
   計算が途中で止まれば、何も表示されず、何も作られない。`run.log` は `result.json` から決まる文字列なので、
   `--verify` は両者を互いに照合できる。
6. **「1 回だけ」が何で担保され、何で担保されないか。** 担保するのは次の 4 つである:
   - 同じ checkout での上書きの禁止 (排他的作成)
   - 凍結範囲が変わっていないこと (凍結 commit の条件)
   - 出力が凍結したコードと pin したデータだけで決まる関数であること (再実行しても同じものしか出ず、結果を選ぶ余地が無い)
   - 両 OS の CI による byte 単位の再計算

   担保しないのは次の 3 つである: ファイルを消してからの再実行、別の clone での実行、最初に見た結果と公開した結果が同一であること。
   これらは、公開された git 履歴と CI 履歴、そしてこの文書の宣言に委ねる。技術的な証明ではない。
7. script が出力の前にエラーで止まった場合に限り、修正を許す (修正内容と理由を記録する)。
   **結果が 1 行でも表示された後は、コードも仕様も変えない。** 変えたくなったら「逸脱」として記録し、user 裁定に回す。
8. サーバ時刻の証跡 (PR の作成時刻、凍結 commit に対する CI run) は、結果 commit のときに GitHub API から取得し、
   `WITNESS.md` に書く。

## 13. 出荷 (Q9)

- 結果 commit で、前向き 2 アームの `run_annotation.jsonl`・`run_records.jsonl`・`run-manifest.json` を
  `data/prospective/{control,primary}/` に byte のまま置く (計 約 36MB)。
  これで raw generations が公開され、I3〜I5 と分類を CI で再計算でき、封印済 verdict の再計算経路も開く。
- `.gitattributes` に `data/prospective/** -text` を加え、Windows の checkout で改行が変わらないようにする。
  匿名 bundle (`make_anonymous_bundle.py`) は `data/prospective/` を byte のまま複製する。
- `data/raw/`・`seal/**`・`data/data.md`・`verify_data_hashes.py`・`repro.sh` は触らない。
- 完了済 run の `bank_records.jsonl` (17.7MB、pin は `cproper-manifest.json` にある) はこの検査では出荷しない。
  それを使う `PC-records` は著者の手元でだけ走り、CI では SKIPPED と表示される。SKIPPED は検査をしていないという意味であって、
  通ったという意味ではない。

## 14. 検出力の申告

既知のアーム全体の None 件数を 8 context に均等に割った仮定のもとで、片側 α = 1/40 の厳密検定の検出力は次のとおり
(`freeze.json` の `declared_power`。`--self-test` の `DECL-power` が同じ値を再計算する)。

| arm | ψ = 1.72 (完了済 run の MH オッズ比 1.723700 を丸めた値) | ψ = 1.3 |
|---|---|---|
| control (None 250) | 0.983439 | 0.500634 |
| primary (None 168) | 0.927883 | 0.382802 |

これらは arm ごとの周辺の検出力で、固定順序による primary の条件付けを含まない。完了済 run の効果量は、
仮説を選んだ当のデータから取った値なので、過大である可能性が高い (winner's curse)。ψ = 1.3 の行は、その割り引きを示すためにある。
明示的 null 検定の検出力は、内訳が未知なので申告できない。

## 15. 対照と変異検査 (`--self-test` / `--mutations`)

- **陽性対照**: 完了済 run で off 124 / on 206 / 8/8 を再現する。厳密 p = 1.728042e-06、MH オッズ比 = 1.723700、
  6 カテゴリ TV = 0.058333 (監査の 0.05833 と一致)、その permutation p ≤ 0.005。
  p・MH オッズ比・TV は、この script とは独立に書かれた実装 (凍結前の Codex review が、完了済 run の annotation だけから
  計算したもの) でも同じ値になった (p 1.7280424e-06、size 0.0228657、MH 1.7236997、TV 0.0583333)。
  golden 値はこの script 自身の出力を pin した回帰検査なので、独立な正しさの根拠はこの一致と、下の手計算 fixture である。
  完了済 run の records が手元にあれば、4,800 行の再 parse 一致と `N_str` = 330 も確かめる。
- **手計算 oracle**: 手で解ける 2×2 表 2 枚で MH オッズ比 = 5、手で解ける分布の組で TV = 0.5。
  厳密な帰無分布の平均と分散が超幾何の公式に一致すること。小さな場合で、厳密分布が全列挙と一致すること。
- **陰性対照**: 完了済 run の条件ラベルを context 内で shuffle すると帰無が成り立つ。これを 2,000 回
  (`SeedSequence([20260708, k])`) 行い、棄却率が [0.005, 0.0355] に入ること、棄却率が厳密な size から 4 SE 以内であることを確かめる。
  帯の上限 0.0355 は α + 3 SE (SE ≈ 0.0035)、下限 0.005 は、ほとんど棄却しない壊れた検定を落とすための値である
  (厳密検定は離散で保守的なので、下側を広く取る)。厳密な size ≤ α の確認は、臨界値の選び方からほぼ自明に成り立つ健全性確認であり、
  独立な校正ではない。独立な校正は shuffle のほうである。
- **fixture**: 手で書いた 14 個の raw 文字列で、分類と再 parse を確かめる。合成アームで、I1〜I6 がそれぞれ自分の gate として発火すること
  (I3 は model・sampling・prompt の 3 通り、I6 は件数とセル最大値の 2 通り)、I7 が到達可能性だけで決まることを確かめる。
  解釈表は、`evaluate_row` と独立に書いた真理値表 8 通りと照合する。
- **end-to-end**: 手で結果を書いた合成 2 アームの 3 シナリオを、`--run` と同じ `describe_arm` → `assemble` に通し、
  行 (A / C / D) と修飾子が期待どおりであることを確かめる。同じ結果で、`--verify` の照合が改ざんした `result.json`・改ざんした
  `run.log`・欠けた `run.log` をそれぞれ拒むことを確かめる。
- **実行ガード**: 使い捨ての git repository と使い捨ての remote を作り、未 push・push 済・凍結範囲外の後続 commit・
  凍結範囲の未 commit の変更・凍結範囲の commit 済の変更・既存の result の 6 通りで、ガードが期待どおりに拒否または許可することを確かめる。
- **変異検査**: script を一時ディレクトリに複製し、1 か所ずつ壊して `--self-test` が**期待した診断で**落ちることを要求する。
  対象は、判定行の否定 / 向きの反転 / on-off の入れ替え / 層別の除去 / None の反転 / I1〜I7 の各検査の無効化 /
  固定順序の迂回 / IUT の第 2 条件の削除 / assemble での arm の入れ替え / 明示的 null 修飾子への主検定 p の混入 /
  `--verify` の byte 比較の無効化 / 凍結範囲の後続変更の見逃し / `freeze.json` の α の緩和 / この文書だけの文言変更。
  コメントだけの変更 (no-op 対照) は落ちてはならない。置換元の文字列がちょうど 1 回出現することも検査する (no-op 変異の排除)。
  別の理由で落ちたものは「捕まった」に数えない。

## 16. この検査が示せないこと

1. 実行順と channel の分離、および交換可能性が成り立たない場合の p 値の校正 (§0)。
2. 形式上の事前登録であること、凍結前に誰も見ていないこと (§4 は宣言)、「1 回だけ」の技術的な証明 (§12 の 6)。
3. 部分的に既知の情報があったこと。§2 に列挙したとおり、アーム全体の件数とセルの最大値は既知だった。
