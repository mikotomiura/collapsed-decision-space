# Claim boundary — what the manuscript may say, and what it may not

> Kept in a separate file from the manuscript **on purpose**, so that whoever writes the manuscript
> cannot satisfy themselves by reading the manuscript alone.
>
> The manuscript is written in English, which is the submission language, so the search patterns
> below are English regular expressions. A few are literals in Japanese, so that the Japanese
> README is not checked by nothing but numerals.
>
> `analysis/scripts/check_claim_boundary.py` reads the table in §2 from this file and enforces it.
> This file is the single source of the patterns: the checker never takes them from the text it is
> checking, because a text that carries its own forbidden-phrase list would trivially agree with
> itself.

---

## 1. What the evidence supports

- The channel is wired non-degenerately (from the channel study and the determinism study),
  **including that the positive control is able to return zero**.
- **Each of the three gates that decide what a null report from this apparatus is worth ran as
  written, and each read a quantity other than the one the reading of its result depends on.** R3
  read the power of a pooled one-sample chi-square goodness-of-fit surrogate, not of the stratified
  permutation test the decision turns on. R4's entropy floor read the per-context entropy of the
  draws pooled over both conditions, not the support of the channel-off base the power calculation
  uses. R4's cap read the largest per-cell rate of the draws the estimand drops, not how that rate
  differs between the conditions. Shown on one apparatus, two model families and eight frozen
  contexts, and recomputed on every run; **not** surveyed for how often gates read proxies
  elsewhere.
- **At the registered `delta_tv` the surrogate returns `1.0000` for both bases checked**,
  near-uniform `[0.2 × 5]` and degenerate `[0.96, 0.01 × 4]`, so a pass of R3 does not distinguish
  a collapsed base from a spread one. Only those two bases were checked, and nothing is said about
  what the surrogate returns for bases in general. Against the completed run's channel-off base,
  with two empty cells, it clears `0.8` at one hundredth of the margin. **The power of the
  permutation test is evaluated nowhere.**
- **For this surrogate calculation, concentration of the base distribution is not itself what
  lowers the computed power** — what lowers it is a small attainable shift. Stated this way because
  the worksheet's own near-uniform row reaches `power = 0.1842` at `delta_tv = 0.01`, so "a
  near-uniform substrate does not imply low power", which earlier drafts wrote here, is contradicted
  by the table it was meant to summarise. It is a property of the surrogate; earlier drafts stated it
  as a property of the design, which overreached.
- The channel's downstream effect was not detected under a materiality margin declared in advance,
  in the two runs that produced an estimate. What that non-detection is worth is what the three
  gates above were meant to settle.
- Effect-absent, low-power and apparatus-invalid are kept apart as **three distinct outcomes**.
- **Clearing a per-context entropy floor in every context does not certify the support that the
  power calculation depends on**, and failing it in every context is compatible with every
  (context, condition) cell producing two or more zones. The completed run and the control arm both
  record `rho_hat` = 1.0 while the channel-off base is missing two of five zones; the primary arm
  records `rho_hat` = 0.0 while each of its cells produces two to four. The first half holds at any
  floor: a floor bounds the support from below, and only by two. What follows for the gate is
  **narrower and threshold-bound** — at the values fixed in §6.3, R4's two conditions are not met by
  the completed run or the control arm, but the same per-context entropies against a floor above
  0.68 would meet them. So what may be said is that this gate, at these thresholds, does not
  **flag** that case; what may **not** be said is that a gate of this shape cannot, or that one arm's
  decision space collapsed further than another's — support size and per-context entropy are
  different quantities, and the records do not order the arms on either.
- **Neither of the two runs that produced an estimate returned one its own permutation test
  rejected.** Both of those runs are `qwen3:8b`, so the *n* is two runs of one model family and not
  three independent measurements; §12.7 gives the reason agreement across runs of this apparatus
  would not establish what it appears to. This is a statement about what has been observed, not
  about the power of any test (§12.6), and not about whether the read-out could have detected a
  material shift.
- **In a held-out test of one post hoc observation, recorded `None` was more frequent in the
  channel-on blocks than in the channel-off blocks in both prospective runs** — row A of the
  interpretation table frozen at commit `61dbd96`. It is stated only together with four things: the
  qualifier that licenses "explicit null" holds for the control arm and not for the primary arm; what
  was recorded as `None` differs between the arms (mostly an explicit `"null"` in one, mostly missing
  or malformed JSON in the other), so it is not a cross-family replication of the same behavioural
  meaning or parser-failure mechanism; the difference is not separable from the on-then-off block
  order; and the test is not a formal pre-registration, its blinding being declared rather than
  demonstrated.
- The envelope is bounded and stated: one apparatus, one sampling regime, two model families, eight
  frozen contexts.

---

## 2. What must not be written (G1–G28)

The **search pattern** in each row is what the checker applies to the manuscript, this repository's
README and the citation metadata. If a pattern matches, **the prose is fixed; the pattern is not
relaxed.** The checker scans the whole manuscript, including the block generated from the sealed
rules, so no pattern may match a sentence the seal fixes; §3 says how that is enforced.

| # | Claim that must not appear | Why it is out of reach | Search pattern (case-insensitive) |
|---|---|---|---|
| G1 | Walking, or movement itself, does not produce creative divergence | **Not measured.** The subject is the channel, not walking and not creativity | `locomotion (does not\|doesn't) (produce\|generate\|cause)`, `walking (does not\|doesn't)`, `no creative divergence` |
| G2 | Embodiment is meaningless | Extends a result obtained inside a bounded envelope into a general proposition | `embodiment is (meaningless\|useless\|irrelevant)`, `embodiment does not matter` |
| G3 | Introducing a pre-declared margin is novel | **Already established** in prior work; this study follows the practice rather than originating it | `(we\|this paper) (introduce\|propose)[a-z ]*(declared\|pre-declared\|pre-registered) margin`, `novel(ty)? (of\|is)[a-z ]*equivalence` |
| G4 | The design separates a model-family effect from a think-regime effect | A gate the design **cannot close**: the two factors move together and the protocol says so | `(separat\|disentangl\|decoupl)[a-z]* (the )?(family\|model family)[a-z ]*(from )?[a-z ]*think`, `isolates? the (family\|think)[a-z ]*effect` |
| G5 | The disabled think regime was shown — or ruled out — as the cause | Same gate as G4, reached from the other side | `think=false (is\|was) the cause`, `(shows?\|demonstrates?\|proves?) that think=false` |
| G6 | The control arm was a bitwise comparison | The control compares **statistics inside a declared band**. Bitwise agreement is a property of replaying recorded output, not of regenerating it | `byte-(identical\|exact)[a-z ]*control`, `control[a-z ]*byte-(identical\|exact)` |
| G7 | A collapsed distribution reduces detection power | **For the surrogate calculation, the measurement says otherwise**: a degenerate base with a collapse-scale shift still reaches `power = 0.9533`. What lowers the surrogate's power is a **small attainable `delta_tv`**, not concentration. This is a property of the pooled chi-square surrogate, not of the permutation test the decision turns on, whose power is evaluated nowhere | `collapsed? (base )?distribution[a-z ]*(low\|reduced\|kills?) power`, `degenerate[a-z ]*(low\|reduced) power` |
| G8 | The completed run's result is a prediction for the second model | Would make a realised outcome of a planned analysis known in advance; the completed run is not the focus of the planned analyses | `we (expect\|predict\|anticipate)[a-z ]*llama`, `llama[a-z0-9.: ]*will (also )?(show\|reproduce\|replicate)` |
| G9 | Level 6 is guaranteed | **Retained after the level declaration was removed.** The manuscript no longer declares a level, so this guard now has nothing to fire on there; it is kept because the level scheme belongs to a venue the submission plan keeps as a fallback, and because a level declaration is a defensible reading of two clauses read together rather than a guarantee stated by anyone. A guard that is inert costs a line; a guard removed and needed again costs the claim | `level 6 is (guaranteed\|assured\|preserved)`, `guarantees? level 6` |
| G10 | The point estimate is `7.40e-17` | **A field mix-up.** `7.401486830834377e-17` belongs to `zone_function_d_loco`, the zone-function positive control. The point estimate is `d_loco = 0.04682681825722385`. **The lookbehind carries the distinction**: `zone_function_d_loco = 7.401486830834377e-17` is *true* and must remain sayable, so the guard must not fire on an identifier that merely ends in `d_loco` | `(?<![a-z_])D_loco *= *7\.4`, `(?<![a-z_])D_loco[^\n]{0,40}e-17` |
| G11 | A control-arm pass proves that no version drift occurred | A pass states only that the quantities fall **inside the declared band** | `(proves?\|demonstrates?\|establishes?)[a-z ]*no (version )?drift`, `rules? out[a-z ]*version drift` |
| G12 | Speculation about the primary arm after a control-arm failure | Defeats the purpose of a stopping rule | `(had\|if)[a-z ]*r5[a-z ]*(failed\|fails)[^.]*primary[^.]*would` |
| G13 | Replication across two families therefore separated family from regime | A paraphrase that returns to G4 through the replication branch | `(two\|both) (model )?famil(y\|ies)[a-z ,]*(therefore\|thus\|hence)[a-z ]*(separat\|disentangl\|isolat)` |
| G14 | Measurement-validity gates, as a class, cannot detect a collapsed decision space | **Threshold-bound, not structural.** The completed run's per-context entropies are `0.628287`–`0.754149`, so the same rule at a floor above `0.68` would put `rho_hat` at `0.375` and fire. What the evidence supports is that clearing the floor **fixed in §6.3** does not certify the support the power calculation needs | `(validity\|measurability) gates?[a-z ,]*cannot (detect\|catch\|reach)`, `no (validity\|measurability) gate[a-z ]*(can\|could)`, `(entropy floors?\|validity gates?)[a-z ]*(are\|is) (useless\|blind)` |
| G15 | The three runs are three independent measurements of the null | Two of the three produced an estimate and **both are `qwen3:8b`**; the third produced none. §12.7 gives the reason agreement across runs of one apparatus is not replication | `three (independent\|separate) (runs\|measurements\|replications)`, `replicated (across\|in) three runs`, `three runs[a-z ,]*(independent\|confirm)` |
| G16 | The margin check and the power gate fail together, in the same direction, when the decision space collapses; a collapsed decision space defeats margin-and-power null reporting | **Withdrawn.** The permutation-null mean of a plug-in distance does not rise with concentration, and at the registered `delta_tv` the surrogate returns `1.0000` for a near-uniform base as well, so the empty cells are not shown to be why R3 passed. The earlier working title carried this claim, which is why it is not quoted verbatim anywhere | `both (guards\|gates\|checks)[a-z ,]{0,40}(stop\|fail\|cease\|break)`, `(stop\|fail\|break)[a-z ,]{0,60}same direction`, `collapsed decision spaces? (defeats?\|breaks?\|disables?\|undermines?)`, `(defeats?\|breaks?\|disables?) (the )?margin[- ]and[- ]power`, `margin[- ]and[- ]power (pairing \|pair )?(fails\|breaks\|collapses)`, `joint failure`, `what produces .?power = 1\.0`, `二重の破綻\|同時に、?同じ向き` |
| G17 | A fixed share of the estimate — roughly three-quarters — is a floor; the estimate has a null floor that rises with collapse | **Withdrawn.** The permutation-null mean is a reference value for the observed statistic, not an additive component that can be subtracted from it | `null floor`, `three[- ]quarters`, `floor (rises\|eats\|consumes)`, `(estimate\|observed value)[a-z ,]{0,30}(is\|are) (mostly \|largely \|mainly )?(the )?floor`, `帰無床` |
| G18 | The zones that were never produced are structurally impossible | **Empirical zeros.** They are what these draws did, not a property the task imposes | `structural(ly)? zeros?`, `(structurally\|logically) (impossible\|excluded)`, `(zones?\|cells?\|categor(y\|ies))[a-z ,]{0,40}(impossible\|unreachable\|cannot occur)` |
| G19 | Low per-context entropy proves that the estimand cannot be measured | The entropy floor is a **threshold on a proxy** (G14); the primary arm's cells each produce two or more zones. The sealed reading that the estimand "is not measurable in that family" is the rule's stated consequence, and stays sayable | `(low\|lower) (per-context )?entropy[a-z ,]{0,40}(proves?\|demonstrates?\|establishes?)`, `(proves?\|demonstrates?\|establishes?) that the estimand (is\|was) (not measurable\|unmeasurable)` |
| G20 | The Pearson surrogate is the power of the design or of its decision test; the design was adequately powered | `power` is the **nominal sensitivity of a surrogate**. The power of the permutation test is evaluated nowhere, and that sentence must stay sayable | `(design\|study\|protocol\|experiment) (was\|is) (adequately \|well \|sufficiently \|fully \|highly )?powered`, `power of the (stratified )?(label-)?permutation test (is\|was) (1\|0\.\d\|high\|full\|adequate\|sufficient\|above)`, `(design\|study) (had\|has\|achieved) (full \|adequate \|sufficient \|enough )?power` |
| G21 | The findings hold for LLM agents in general | **Two models, eight frozen contexts, one apparatus.** The earlier working title generalised to "LLM agents" | `(in\|across) (all \|other \|most )?(llm\|language[- ]model) agents\b`, `(llm\|language[- ]model) agents (reach\|show\|exhibit\|generally\|in general)`, `(all\|any\|every) (llm\|language[- ]model) agents?` |
| G22 | A `None` read-out is the agent choosing to stay | **Not an intention.** In the completed run every `None` is a rejected plan; in the prospective arms almost all are. The parser's design note (`None` = stay put) may be quoted as a description of the parser, never as a reading of a record | `(chose\|choose\|chooses\|choosing\|decided\|decides\|decision\|intends?\|intended\|intention\|wants?\|wanted) to stay`, `留まることを選` |
| G23 | The difference in `None` is caused by the channel, λ, locomotion, temperature or top_p | **Confounded with execution order**: every context ran its channel-on block first (§12.9) | `(channel\|λ\|lambda\|locomotion\|temperature\|top_p)[a-z ,]{0,20}(causes?\|caused\|drives?\|drove\|increases?\|increased\|raises?\|raised\|produces?\|produced) (more )?(none\|null\|unparse\|malformed\|format)`, `(none\|null\|unparse\w*\|malformed)[a-z ,]{0,40}(caused\|driven\|produced) by (the )?(channel\|λ\|lambda\|locomotion\|temperature\|top_p\|higher temperature)`, `(due\|attributable\|owing) to (the )?(channel\|λ\|lambda\|locomotion\|temperature\|top_p\|higher temperature)` |
| G24 | The held-out test is formally pre-registered, or confirmatory in the registered-report sense | Its data existed before its specification; the freeze shows the specification preceded the result, not that nobody had looked | `held-out[a-z ,]{0,60}(is\|was\|as) (a )?(formal(ly)? )?(pre-?registered\|preregistered\|confirmatory)`, `(confirmatory\|pre-?registered) held-out` |
| G25 | Not rejecting shows there is no effect, or that the conditions are equivalent | A nil-null test that fails to reject is not evidence of equivalence (§4.4) | `(not\|failure to\|failing to\|fails? to) reject[a-z ,]{0,40}(shows?\|means?\|establishes?\|demonstrates?\|implies?)[a-z ,]{0,20}(no effect\|equivalen\|absence of)`, `(channel\|it) has no effect`, `(conditions\|arms) (are\|were) equivalent` |
| G26 | A difference in effect size between the arms is a difference between model families | The arms differ in family, think regime and in what their `None` records are; nothing isolates the family | `more (sensitive\|susceptible\|responsive) to the (channel\|sampling\|temperature)`, `(odds ratio\|effect size)[a-z0-9., ]{0,60}(reflects?\|shows?\|indicates?) (a )?(model[- ])?famil` |
| G27 | The six-category distance is material, or immaterial, against the 0.10 margin | The margin was declared for the five-zone estimand; the six-category distance is a secondary description | `six-category[a-z ,]{0,60}(below\|under\|exceeds?\|above\|within) (the )?(materiality )?margin`, `(six\|6)[- ]categor\w*[^.]{0,80}\b(im)?material\b` |
| G28 | A check shows that nobody saw the condition-wise counts before the freeze | **A declaration**, not a demonstration; no check in this repository can show it | `blind(ing\|ed)? (was\|is\|has been) (verified\|demonstrated\|established\|proven\|shown\|guaranteed)`, `(shows?\|showed\|demonstrates?\|establishes?\|proves?\|verifies?) that no(body\| one\|one)[a-z ,]{0,30}(saw\|had seen\|looked at\|tallied\|counted)` |

### 2.1 Declared, but not enforced by a pattern

Three claims the held-out specification forbids (`analysis/heldout-stay/SPEC.ja.md` §11) have no
row above, each for a stated reason. They are forbidden all the same.

- **That the exact *p*-values hold at their nominal level without assuming the draws of a context
  are exchangeable over their positions in the run.** A pattern stable enough to catch this would
  also catch the sentence that states the condition, which the manuscript must carry.
- **That the completed run's own *p* of about 0.001 counts as evidence.** That run generated the
  hypothesis. A pattern on the number, or on "evidence" near "completed run", would catch the
  sentences that say it is not counted.
- **That the sealed verdicts, or branch R4 or R5, read differently from how the sealed rules give
  them.** This is held mechanically rather than by a phrase: step 13 re-derives the branch from the
  sealed rules and compares it with `manuscript/reported-branch.txt`, and step 12 requires the rule
  text in the manuscript to be the one generated from the seal.

---

## 3. How the check is built so that it cannot pass vacuously

A check of the form "none of these patterns appears" passes trivially if the patterns are broken,
misparsed, or empty. **Being green and having been checked are different facts.** Five properties
are therefore required, and each was confirmed by breaking it deliberately and observing the
failure.

1. **The patterns are not taken from the text being checked.** Their single source is §2 of this
   file. A manuscript that listed its own forbidden phrases and confirmed it did not match itself
   would be checking nothing.

2. **Exactly twenty-eight guards, in order, must parse.** A parser that silently yields zero guards
   reports "no hits" against any text whatsoever, so the count and the identifiers are pinned.

3. **A positive control accompanies the "zero hits is correct" check.** The checker must be able to
   say both of the following:
   - no pattern matches `main.md`, this README or the citation metadata;
   - **every individual pattern** matches `_claim_boundary_positive_control.md`, a fixture whose
     every sentence is deliberately false and written in ordinary prose.

   Requiring it per *guard* is not enough: a guard with two patterns would still pass with one of
   them broken. That case was observed in testing, which is why the requirement is per *pattern*.

4. **Matching ignores line breaks.** The prose is hard-wrapped, so a forbidden phrase can straddle a
   line ending. Scanning line by line misses those; the checker normalises whitespace first. This
   too was found by a phrase that split across a wrap and went undetected.

5. **A negative control holds the patterns away from sentences the manuscript must be able to
   say.** `_claim_boundary_negative_control.md` lists, as literal text, sentences the seal fixes
   and sentences a correct account of this study needs — the sealed reading of R4, the sealed
   estimand, the sealed note that the completed run "attained power 1.0", "the power of the
   permutation test is evaluated nowhere", the parser's design note that `None` means stay put, the
   mention of the earlier working title, the withdrawal of the earlier reading — and **no pattern
   may match any of them**. The number of listed sentences is pinned, so a sentence cannot drop out
   silently. The list is written by hand and never generated from the manuscript: negatives taken
   from the text under check would make the check agree with itself. The first version of the
   patterns written for G20 matched the sealed "attained power 1.0" sentence, which is why this
   property exists.

---

## 4. Conventions for sourcing

- Numbers the manuscript draws from the frozen inputs, and from the derived artefacts regenerated
  on every run, are checked by `analysis/scripts/check_manuscript_numbers.py` against those sources.
  Two limits on that, both of which earlier drafts of this file omitted. **The check tests
  occurrence, not uniqueness**: a value appearing in several places is not protected against one of
  them being altered. And **its scope is the listed quantities only** — in particular the pilot
  figures in §5.3 (timings, digests, peak memory, the projected run length) exist in no frozen input
  and are covered by nothing. They are transcribed by hand, and saying otherwise here would be the
  same error this file exists to prevent.
- Quantities whose literals are too common for an occurrence test — small counts, zone counts, the
  rows of the tables in §5.1.1, §5.2 and the results section, the held-out counts and class
  breakdown — are checked as **rendered rows and phrases**: the checker renders the expected text
  from `analysis/heldout-stay/result.json`, `analysis/heldout-stay/freeze.json`, the per-draw
  annotations, the verdict records and the derived artefacts, and requires that exact text to occur
  **exactly once** — for these, uniqueness rather than occurrence.
- Sources cited in published files must be reachable by a reader of this repository. Working
  directories that are not shipped here are not citable sources. Upstream records are cited by
  path and commit.
- When `power ≈ 0.18` is quoted, the base distribution and the `delta_tv` it belongs to are quoted
  with it (G7).
- The point estimate and the zone-function positive control are presented together, so that neither
  can be read as the other (G10).
