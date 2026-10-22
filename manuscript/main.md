# Three gates, three proxies: auditing the null-report checks of a pre-registered LLM-agent evaluation

<!-- TMLR:DROP -->

**A sealed, pre-registered evaluation, its outcome reported against the sealed rules, and an audit of the gates that decided what that outcome is worth. Every analysis outside the sealed rules is labeled by when it was fixed (§2.5).**
No prospective draw existed when the decision rules were sealed. They are sealed in machine-readable
form, so that the branch reported afterwards can be re-derived from the rules as they stood before
it (§J).

| | |
|---|---|
| Author | Mikoto Miura |
| ORCID | [0009-0000-4196-0508](https://orcid.org/0009-0000-4196-0508) |
| Affiliation | Independent Researcher |
| Correspondence | mmiura.network@gmail.com |
| Code and data | <https://github.com/mikotomiura/collapsed-decision-space>. Development continues on the default branch; what pins the protocol against later change is the seal of §H and §J, not a branch name. |
| License | Code: Apache-2.0 OR MIT. Manuscript, figures, data and the sealed protocol: CC BY 4.0 |
| Protocol status | Sealed, by our record, before any prospective draw was collected (§H). By the same record, each arm then produced one complete run on 2026-09-14 (UTC) (§I.5), and the sealed rules applied to the two verdicts reach the apparatus-validity branch, R4 (§2.4). |

---
<!-- /TMLR:DROP -->

## Abstract

We audit the three gates, checks with thresholds fixed in advance, by which one of our own
pre-registered evaluations fixed what a null result would be worth. A language-model agent names
which of five zones it moves to next; the evaluation asked whether a channel from its recent
movement to its sampling settings, in practice two fixed sampling settings, shifts that choice by
more than a total-variation margin of 0.10. Each gate ran as written and read a quantity other than
the one its reading depends on. The entropy floor decided the reported branch: it stopped the rules
on the second of two models although each context and condition produced two to four zones. A post
hoc simulation on an assumed truth taken from that model's draws, at its declared shifts only,
finds the permutation test that decides detecting a shift of the margin's size in all 500
replicates of each of the four feasible directions, and the floor stopping 353, 452, 500 and 49 of
them. The other two gates did not change the branch. The power gate reads the power of a chi-square
surrogate, not of that test: simulated on the completed run's draws, the surrogate returns 1.0 at a
tenth of the margin, where the test rejects in about one replicate in eight. The cap on draws with
no recorded zone reads the worst context and condition, not the difference between conditions, so
the estimate describes only the draws that produced a zone. The case motivates three diagnostics:
simulate the power of the test that decides, report support beside entropy, and compare dropped
outputs between conditions. The claims concern these gates on one apparatus, two models and one
prompt, not the effect of the channel.

---

## 1. Introduction

A pre-registered evaluation that may end in a null has to settle in advance what a null will be
worth [35, 36, 44]. Registered Reports make that settlement part of the format: peer review and the
decision to publish take place before the results are known [55], a design is meant to make a null
result credible [54], and a protocol is expected to state outcome-neutral conditions, such as
positive controls or the absence of floor and ceiling effects, that show its methods can test its
hypotheses [56].

This paper takes up three such conditions, checked in a protocol by gates: that the design could detect an effect of the size that
matters, that the read-out could register one, and that the units scored stand for all that were
collected. Each has a known way of going wrong. A power analysis is meant for the test that will be
run [54], yet in one sample of preregistrations 5 of the 13 power analyses reported fully enough to
check addressed a test other than the main test of the hypothesis [59]. A check for floor effects
[56] leaves open which property of the read-out it establishes. And participants who drop out of
conditions for different reasons can confound the comparison between them [63], although unequal
dropout rates alone do not establish bias [64].

Meta-research has asked whether preregistered studies keep to their plans [57] and whether peer
review checks the plans [58]. This paper asks a different question of one protocol that was applied
as written: whether each of its gates read the quantity that the reading of its result depends on.

We designed and sealed one such evaluation ourselves, and examine it here. Generative agents act
in a simulated world, keep an internal state, and choose their next action from it [2]; whether
that state reaches the choices downstream of it bears on the validity of such simulations
[38, 39]. Our agent chooses which of five named zones to move to next, and a scalar computed from its
recent movement enters the sampling settings of that choice: the channel. The evaluation asked
whether the channel shifts the choice by more than a margin of 0.10 in total variation, and three
gates with thresholds fixed in advance settled what a null would be worth: a power gate, an
entropy floor, and a cap on draws with no recorded zone. Sealed after a completed run on one model,
the rules were applied to a control arm on that model and a primary arm on a second model, and
stopped when the entropy floor fired on the second.

Each gate ran as written and read a quantity other than the one the reading of its result depends
on. The entropy floor's firing decided the reported branch; the passes of the power gate and the cap
do not certify what they were written to secure. Table 1 sets out the three gates in the four
respects §3 to §5 take up in turn.

| Gate | Meant to secure | What it read | What we found | Effect on the evaluation |
|---|---|---|---|---|
| Power gate | That the design could detect a shift of the declared size | The power of a pooled chi-square goodness-of-fit surrogate, against an alternative built from the channel-off draws | Power 1.0 in both runs that formed an estimate. The surrogate agrees with the simulated test at the margin, and also passes shifts a hundred times smaller (§3, §B.1) | Latent: the branch is unchanged |
| Entropy floor | That the read-out varies enough to register such a shift | The entropy of each context's zone distribution, pooled over both conditions | Two runs passed while two zones never appeared in their channel-off draws; the primary arm fired although each of its 16 (context, condition) cells produced between two and four zones. §4 gives what it withheld in simulation, direction by direction | Actual: it decided the reported branch, R4 |
| Cap on draws with no recorded zone | That the scored draws stand for what each condition produced | The largest rate, over cells of one context and one condition, of the draws the estimand drops | All three runs passed, while the channel-on blocks dropped more draws in each (§5) | Latent for the branch; it changes which draws the estimate describes |

Table: The three gates of the sealed evaluation: what each was meant to secure, what it read, what we found and what it did to the evaluation. The last two columns are our reading, set after the results were seen.

The claims concern these gates on two models and one frozen prompt, not the effect of the
channel. Most of the evidence is descriptive, post hoc or held-out (§2.5); the thresholds and the
sealed branch stand as the rules give them. The contributions are a documented case of gates that ran as written and read proxies, with the rules, records and checks that recompute it (§J), and the diagnostics of §6.2, which rest on standard statistics (§6.3). Sections lettered A to O are appendices: §E and §K
follow the references, and the others are in the Supplementary Material.

---

## 2. The evaluation and what it returned

### 2.1 The agent, the world and the read-out

The apparatus descends from the generative-agent architecture [2]. Its world has five named zones:
`agora`, `chashitsu`, `garden`, `peripatos` and `study`. Every draw sends the model the same two
prompts, which place a neutral agent in `agora`, list cues in `study` and `garden`, and ask for a
JSON object whose field `destination_zone` names the zone the agent moves to next.

The read-out is that field as the parser records it, before any later bias is applied. A draw is one
model call and its recorded read-out. The parser accepts one of the five zone names, or a JSON
`null` as an empty destination, and otherwise rejects the whole plan. A draw with no recorded zone
is a draw whose read-out is recorded as `None`.

The channel is an exponential moving average over the agent's recent moves, yielding a scalar λ
that the apparatus composes into the sampling settings of the next generation; with the channel
off, the locomotion input is removed. A completed preliminary study showed that λ moves with the agent's recent movement and enters the sampling settings, and that ablation removes the path exactly (§A). Wherever this paper speaks of an effect, its subject is
the channel, not walking and not creativity.

### 2.2 The runs

The unit of the sealed protocol is the context: eight frozen contexts, each run for 300 draws per
condition, 4,800 model calls per run. The completed run used `qwen3:8b` under ollama 0.31.1, with
thinking disabled, and preceded the seal. After the seal, the control arm re-ran `qwen3:8b` under
ollama 0.32.12, and the primary arm ran `llama3.1:8b`, of the same scale from another family.

Read post hoc from the per-draw records, all 14,400 draws of the three runs carry one system prompt
and one user prompt. In every run, channel-on draws are sampled at temperature 0.82 and top-p 0.94,
channel-off draws at temperature 0.70 and top-p 0.90, with a repetition penalty of 1.0 in both.
Each run consists of eight pairs of blocks, each pair 300 channel-on draws followed by 300
channel-off draws, one pair per context. A context is therefore a pair of blocks of one prompt. Because every channel-on draw was sampled at one setting and every channel-off draw at another, the comparison between the conditions is, operationally, a comparison between those two sampling settings, made in a fixed order (§7.2).

### 2.3 Estimand, test, margin and gates

For each context, the distance is the total variation between the five-zone distributions of its
channel-on and channel-off draws, after draws with no recorded zone are dropped and the rest
renormalized. The primary estimand is the mean of that distance over the contexts the scorer
admits. A stratified permutation test, with the contexts as strata, tests whether the conditions
differ at α = 0.05. It is a nil-null test, and failing to reject is not evidence of equivalence;
the protocol runs no equivalence test [36, 41].

Total variation is half the sum of the absolute differences between zone probabilities, so a
distance of 0.10 means that ten percentage points of probability move. The margin of 0.10
(`delta_tv_min`) is a rule for reading an estimate, fixed before the data: an estimate below it,
with no rejection, is read as below the materiality margin. Its value was frozen upstream before
the completed run (§G.2), and no rationale is added after the fact. The claims of this paper do not
depend on whether the value is well chosen; whether a pass of the power gate agrees with the test
that decides does depend on it (§3).

The sealed rules read six recorded quantities: the scorer's verdict, the fraction of contexts the
entropy floor admits (`rho_hat`), the recorded power, the estimate (`tv_bar`), whether the
permutation test rejects, and the largest rate of draws with no recorded zone in any cell. They are
evaluated in the order R5 → R4 → R3 → R1 → R2, stopping at the first rule whose action is to stop
(Figure 1; §E). R5 requires the control arm to
reproduce the completed run within a declared band; R1 and R2 are the primary arm's outcome
branches, an estimate below the margin with no rejection (R1) or not (R2). Three gates are the
subject of this paper:

- the **power gate** (R3) stops the evaluation as underpowered if the recorded power is below 0.8;
- the **entropy floor**, the first condition of R4, fires if fewer than half the contexts reach an
  entropy of 0.5 bit;
- the **cap on draws with no recorded zone**, the second condition of R4, fires if any cell of one
  context and one condition drops more than half its draws.

<!-- TMLR:FIGURE pipeline -->
**Figure 1.** The sealed rules in their evaluation order, with each predicate as the sealed rule
file states it; the figure is generated from that file. The note beside each gate says what quantity
it reads. R5 applies to the control arm and the others to the primary arm, and evaluation stops at
the first rule whose action is to stop (§E).
<!-- /TMLR:FIGURE -->

### 2.4 What the sealed rules returned

<!-- REPORTED-BRANCH: R4 -->

Both arms were run on 2026-09-14 (UTC) and, by our record, each was checked against the seal before its verdict was landed (§I.5). In the control arm (`qwen3:8b`), all
eight contexts clear the entropy floor, the recorded power is 1.0, and the largest rate of draws
with no recorded zone in any cell is 0.086667. The estimate is 0.030575, and the permutation test
does not reject it (*p* = 0.43989). The sealed scorer reports no interval for it, and none is added (§M.3). R5 is satisfied, which says nothing about the backend upgrade (§D.4).

In the primary arm (`llama3.1:8b`), no context reaches the entropy floor: the per-context entropies
run from 0.165654 to 0.274008. The largest rate of draws with no recorded zone in any cell is 0.066667. Because no context is admitted,
the registered scoring stops before forming the contrast between the conditions: the power, the
estimate and the test are absent from the verdict, not small in it. The branch is R4, apparatus
validity; R3, R1 and R2 were not reached, and the sealed rule narrows the claim to single-model scope (§E).

### 2.5 What each analysis may be read as

The analyses of this paper were fixed at four different times, and what each may be read as depends
on when (Table 2). **Registered** analyses apply the estimand, the test and the rules to the two
prospective arms; **prospective, descriptive** ones describe those arms by quantities no rule
reads; **post hoc** ones describe the runs, simulate the design and generated the hypothesis that the
**held-out** test then tested once, on draws collected without reference to it.

| Layer | Fixed when | Licenses |
|---|---|---|
| Registered | Sealed before any prospective draw, by our record (§H) | The reported branch, R4. Nothing about the channel's effect in the primary arm |
| Prospective, descriptive | After the runs. No test | Descriptions of the two arms. No change to the branch |
| Post hoc | After the completed run was seen (§F); both simulations after both arms, and that of §4 also after an internal review of this manuscript (§B.5). Each simulation's grid, seeds and reading rules were pushed before its first full run | Descriptions of the runs, the records and the gates; operating characteristics of the design under assumed distributions. Nothing about the channel |
| Held-out | Specification frozen before the condition-wise counts were tabulated (declared); run once, control first, α = 1/40 | Row A of its frozen table, quoted with its class breakdown. Not separable from block order (§7.2) |

Table: The four layers of analysis, when each was fixed, and what each licenses.

§3 to §5 give each finding's layer in a table, and qualifiers that apply to whole layers are stated once, in §7.

---

## 3. Gate 1: power

**What it was meant to secure.** That the design could detect a shift of the declared size, so that
an estimate below the margin with no rejection could not be an artifact of a design too small to
see the effect.

**What it read.** The power gate reads the Monte Carlo power of a pooled one-sample Pearson
chi-square goodness-of-fit test. Its base is the run's pooled channel-off distribution, and its
alternative moves probability mass from the largest cell of that base to the smallest, by the
registered shift of 0.10 in total variation. The decision itself turns on the stratified
permutation test of §2.3. The two tests use different statistics, and the sealed design did not
evaluate the power of the permutation test, so the recorded power is the nominal sensitivity of a
surrogate. A pass of R3, a recorded power ≥ 0.8, is not read here as evidence about the power of the decision. It is computed at the registered margin rather than at an observed effect, so it is not the post hoc power that Hoenig and Heisey [44] show cannot interpret a non-significant result; what is wrong with it here is that it is the power of another statistic.

**What we found.**

| Finding | Layer |
|---|---|
| Recorded power 1.0 in the completed run and the control arm; none in the primary arm | Registered (arms); the completed run's own record |
| At the margin the surrogate returns `1.0000` for a near-uniform and a degenerate base alike (§B.1), and on the completed run's base it clears 0.8 down to a hundredth of the margin | Post hoc |
| The simulated test agrees with the surrogate at the margin and parts from it below half the margin; on the degenerate base the test and the pipeline part | Post hoc (simulation) |

Table: What was found at the power gate, and the layer of each finding.

The completed run's channel-off base has two empty cells (§4), and the surrogate's alternative
moves mass into one of them. The statistic divides by the expected count, which the implementation
floors at a small constant only to avoid dividing by zero, so a single draw in a cell of base
probability zero produces an enormous statistic: the sensitivity to small cells that chi-square-type
statistics are known for [43]. Against this base the surrogate returns `0.921` at one hundredth of
the margin that the study declared material, and clears the gate (§B.1 gives the whole sweep). Its
value alone therefore says almost nothing about whether the test that decides could detect a shift
of the declared size.

<!-- TMLR:FIGURE power -->
**Figure 2.** Simulated operating characteristics of the sealed pipeline (post hoc). Top: how often
the permutation test alone rejects (test) and how often the sealed pipeline reaches R2 (pipeline)
along the surrogate's direction D1, on the completed run's channel-off base `C` and on the
degenerate base `G`, beside the R3 surrogate at the same shift; the plotted values are printed
beneath, and a marker's shape shows the quantity and its size the base. Bottom: for every declared
base and direction, the smallest declared shift at which each rate reaches 0.8 (n.r.: not reached
in the declared grid; n/a: not in the grid). The rates are Monte Carlo estimates under assumed
distributions; §B.3 gives their Wilson 95% intervals.
<!-- /TMLR:FIGURE -->

To measure what the gate was meant to stand for, we simulated the sealed pipeline and its permutation test, moving each context's known channel-off distribution by a stated amount; like any simulation study of a method [49], this measures a property of the design under assumed distributions, with grid, seeds and reading rules
fixed before its first full run. It uses five channel-off bases, among them the completed run's
`C` and the degenerate base `G` of §B.1, and six directions of shift, of which D1 is the
surrogate's own (§B.3).

At the registered shift, on the completed run's base, the pipeline reaches R2 and the test alone
rejects in every replicate of every feasible direction, so at the margin a pass of the power gate
and the test's simulated rejection rate agree on this base. Along the surrogate's own direction
they agree from `delta_tv` = 0.05 upward and part below it (Figure 2). The test and the pipeline come apart on the degenerate base: along D1,
at `delta_tv` = 0.02 the test alone rejects in 411 of 500 replicates (`0.822`) while the pipeline
stops at R4 in 500 of 500, and P(R2) first reaches 0.8 there at `delta_tv` = 0.10 (497 of 500). Each rate rests on 4,000 replicates under the null and on 1,000 (base `C`) or 500 (other bases) per shifted cell. The counts were declared with the grid, not derived from a target Monte Carlo error (§B.3). The simulation does not cover other bases, other directions, shifts that differ in size between contexts, numbers of draws other than the completed run's, a difference between the conditions in how many draws are dropped, or drift with position in the run.

**Why it matters.** The flaw is latent. The gate passed in both runs that formed an estimate, and on
the bases simulated its pass coincides at the margin with what the test that decides can detect, so
it did not change the evaluation. But the pass carries no information about shifts smaller than the
margin, and the agreement is a property of a margin of this size: on the completed run's base the same gate, with the same surrogate, would pass a design whose test could not detect a margin a tenth as large (§6.1); the
power that matters can be simulated through the whole pipeline (§6.2).

---

## 4. Gate 2: entropy floor

**What it was meant to secure.** That the read-out varies enough to register a shift of the
declared size, so that a floor effect could not be read as an absent effect. The sealed reading of
R4 states this in terms of support: when the rule fires, "the substrate does not license two or
more zones, so this estimand is not measurable in that family" (§E).

**What it read.** For each context, the entropy of the zone distribution, pooled over both
conditions with draws with no recorded zone excluded. A context is admitted if that entropy is
≥ 0.5 bit, and R4 fires if `rho_hat`, the fraction admitted, falls below 0.5. The
floor reads how evenly a context's draws spread. The reading of the gate depends on how many zones
the draws reach, and in particular on the support of the channel-off base that the power
calculation uses.

**What we found.**

| Finding | Layer |
|---|---|
| The completed run and the control arm admit every context, while `agora` and `chashitsu` never appear in either run's channel-off base | Post hoc (completed run); prospective, descriptive (control arm) |
| The primary arm admits no context and fires R4, although every cell produces two or more zones | Registered (firing); prospective, descriptive (zones) |
| On the primary arm's channel-off base, at the registered shift, the test alone rejects in every replicate of each feasible direction; the sealed floor stops 353, 452, 500 and 49 of 500 along D1, D2, D3 and D5 | Post hoc (simulation) |

Table: What was found at the entropy floor, and the layer of each finding.

In the completed run, two of the five zones never appear in the channel-off condition. Pooled over
that condition (2,276 draws that parsed), the read-out distribution is:

| Zone | Count | Probability |
|---|---|---|
| `agora` | 0 | `0.0` |
| `chashitsu` | 0 | `0.0` |
| `garden` | 295 | `0.129613` |
| `peripatos` | 32 | `0.01406` |
| `study` | 1949 | `0.856327` |

Table: The completed run's channel-off read-out, pooled over the contexts.

`chashitsu` is not produced once in the whole run, under either condition, and `agora` appears three
times, all in one context. Both zeros are empirical: they are what these draws did, not a property
the task imposes. The control arm repeats the pattern: of its 2,306 parsed channel-off draws,
`garden` has 386, `study` 1,896 and `peripatos` 24. The primary arm is the reverse case: of its
2,339 parsed channel-off draws, `study` has 2,272, `garden` 59 and `agora` 8, and in every one of
its 16 cells the second most frequent zone has between 5 and 15 of some 300 draws. The table
below sets the zones each run's parsed draws occupy beside what the gate recorded.

| Run | Zones in the channel-off base | Zones under the channel on | Zones per (context, condition) cell | `rho_hat` |
|---|---|---|---|---|
| completed run (`qwen3:8b`) | 3 of 5 | 4 of 5 | 3–4 | `1.0` |
| control arm (`qwen3:8b`) | 3 of 5 | 4 of 5 | 3–4 | `1.0` |
| primary arm (`llama3.1:8b`) | 3 of 5 | 5 of 5 | 2–4 | `0.0` |

Table: The zones each run's parsed draws occupy, beside the fraction of contexts the entropy floor admitted.

<!-- TMLR:FIGURE distribution -->
**Figure 3.** The zone of every draw, per context and condition, for the three runs, with the draws
recorded as `None` shown (hatched) rather than dropped as the estimand drops them. The number at the
right of each bar is that bar's count of `None` draws. Each context ran its channel-on block first
(§7.2). The completed run's panel belongs to the post hoc layer and the two arms' panels to the
prospective descriptive layer (§2.5).
<!-- /TMLR:FIGURE -->

The sealed reading of the firing therefore does not match the data literally: every one of the
primary arm's 16 (context, condition) cells produces two or more zones, between two and four. The rule fired on the share of admitted contexts, which the entropy floor defines, and not on the paraphrase; the rule text stands as sealed, and neither the firing nor the branch is affected.

To see what the firing withheld, we simulated two pipelines on the primary arm's channel-off base
with the directions and shifts of §3, under a declaration pushed after both arms were seen and
before the simulation's first full run (§B.5): the sealed pipeline, and the same pipeline without
the floor, which admits any context whose pooled draws occupy two or more zones and so, on this
base at the registered shift, all eight. The channel-on draws were not used, and the comparison holds only at the declared
directions, deltas and numbers of draws. Under no shift the sealed pipeline stops at R4 in 4,000 of 4,000
replicates, and the pipeline without the floor reaches R2 in 187 (0.047), as often as the test
alone rejects. At the registered shift the test alone rejects, and the pipeline without the floor
reaches R2, in 500 of 500 replicates in each of the four feasible directions. The sealed floor
stops 353 of 500 along D1, 452 along D2, 500 along D3 and 49 along D5; D5 alone moves mass into the
empty zones, which raises the entropy the floor reads. The simulated shifts are written into the
read-out itself, so no replicate holds a floor effect, a read-out unable to register a shift: the
simulation counts what the floor stopped, not what it protects against. The reading rule declared with the simulation reports these directions one by one and
allows no statement that summarizes them.

**Why it matters.** This flaw is actual in the sense the record shows: the floor decided the reported branch. The entropy it reads is pooled over both conditions and so moves with the shift. Entropy measures how
evenly a context's draws spread, and support how many zones they reach, and in these runs the two
come apart in both directions. A floor of 0.5 bit requires at least two zones in a context and says
nothing more about the support, so clearing it does not certify the support the power calculation
depends on, and failing it does not show that the read-out is confined to one zone. That R4 does not flag the completed run or the control arm depends on the threshold rather than on the shape of the rule: the completed run's per-context entropies run from `0.628287` to `0.754149` bit, and only three of the eight exceed 0.679609, so any floor above that would have admitted fewer than half its contexts. A
measurability gate on a categorical read-out should report the support of each condition beside the
entropy it reads (§6.2).

---

## 5. Gate 3: cap on draws with no recorded zone

**What it was meant to secure.** That the draws the estimand scores stand for what each condition
produced.

**What it read.** The estimand drops every draw with no recorded zone and renormalizes over the five
zones; the sealed protocol chose that over a sixth category, and made the rate of such draws the
quantity R4 reads (§E). The cap reads the largest rate over the 16 cells of one context and one
condition, against 0.5. The reading of the gate depends on how the share of dropped draws differs
between the channel-on and the channel-off blocks, which the cap does not read.

**What we found.**

| Finding | Layer |
|---|---|
| The cap passes in all three runs (`0.123333`, `0.086667`, `0.066667`) | Registered (arms); the completed run's own record |
| In the completed run the channel-on blocks drop more draws, and every dropped draw is the string "null" the prompt template offers | Post hoc |
| In both prospective arms the channel-on blocks record `None` more often | Held-out |
| What is recorded as `None` differs between the arms | Held-out |

Table: What was found at the cap on draws with no recorded zone, and the layer of each finding.

In the completed run the dropped draws are 124 of the 2,400 channel-off draws and 206 of the 2,400
channel-on draws, with more in the channel-on condition in 8 of the 8 contexts. This excess, 206
against 124 in the completed run, was seen after the run and is tested below. All 330 are the same thing:
a response that followed the prompt template literally. The template shows the field as
`"destination_zone": "study|peripatos|chashitsu|agora|garden|null"`, with `null` inside the
quotation marks (§B.4). The parser accepts only the five zones or a JSON `null`, so the string
`"null"` fails validation, the whole plan is rejected, and the record carries `None`. Re-parsing the
completed run's raw responses with the apparatus parser reproduces every recorded value, and all 330
`None` records are this string-`"null"` failure. Output that follows the format of the prompt, or
fails a required output format, is a known dependence of language-model evaluation [45, 47], and
this is an instance of it.

The observation was tested once, on the two prospective arms, whose draws had been collected
without reference to it. The specification, the test and the interpretation table were frozen at
commit `61dbd96`; the prospective draws existed before the specification did, so this is not a
formal pre-registration (§7.2). The test, of whether a draw is recorded as `None`, is an exact one-sided stratified test, with the eight contexts as strata and each context's `None` total
held fixed, so that its null distribution is the convolution of eight hypergeometric distributions. It is run at level 1/40, one-sided because the direction was chosen after the completed run was seen, and was applied to the control arm first and counted for the primary arm only if
the control arm's test rejected, which holds the familywise error at 1/40. Both rejected, which is row A of the frozen interpretation table:
in both prospective runs, recorded `None` was more frequent in the channel-on blocks, 156 against 94
in the control arm and 107 against 61 in the primary arm. As rates, the channel-on blocks recorded
`None` more often by 2.6 percentage points in the control arm and 1.9 in the primary arm.

| Arm | `None`, channel-on blocks | `None`, channel-off blocks | one-sided *p* |
|---|---|---|---|
| control (`qwen3:8b`) | 156 | 94 | 3.415046e-05 |
| primary (`llama3.1:8b`) | 107 | 61 | 1.894707e-04 |

Table: Draws recorded as `None` in each arm, by condition, with the held-out test. Specification frozen at commit `61dbd96`, before the condition-wise counts were tabulated (declared). The *p*-values assume the draws within a context are exchangeable over their positions in the run (§7.2).

The frozen specification requires the content of the `None` draws to be reported with the result.
Each one's raw response was classified with the parser's own steps:

| What `destination_zone` held | control, on | control, off | primary, on | primary, off |
|---|---|---|---|---|
| the string `"null"` | 154 | 94 | 5 | 2 |
| a JSON `null` | 1 | 0 | 0 | 0 |
| no `destination_zone` key | 0 | 0 | 1 | 0 |
| a valid zone name, with the plan rejected on another field | 0 | 0 | 0 | 0 |
| some other value | 0 | 0 | 3 | 2 |
| no usable JSON object | 1 | 0 | 98 | 57 |

Table: What `destination_zone` held in each draw recorded as `None`, by arm and condition.

In the control arm almost every `None` is an explicit `"null"`, as in the completed run, where all
330 dropped draws are the string `"null"`. In the primary arm almost every one is a missing or
malformed JSON object, and 41 of the primary arm's 46-draw excess in the channel-on blocks is of
that kind. The word "unparseable" in the estimand is exact for all but two of the draws dropped in
the prospective arms; the other two are a JSON `null` and an absent destination key, which the
parser treats as an empty destination. The frozen qualifier for writing that outputs naming `null` as the destination increased holds for the control arm and not for the primary arm (§M.2). **What replicated is an operational outcome, the recorded `None`, and not the
same behavioral meaning or the same parser-failure mechanism across the two families.** The
specification also requires a six-category distance, with `None` as a sixth category: it is
0.047917 (permutation *p* = 0.061197) in the control arm and 0.030833 (*p* = 0.015049) in the
primary arm. It describes every draw rather than only those with a recorded zone, and it is not
judged against the margin. It treats `None` as an outcome rather than as missing, so it does not
model why a draw is dropped, and it carries the order confound of §7.2.

**Why it matters.** For the branch the flaw is latent: the cap passed with a wide clearance in every
run, and the reported branch was decided elsewhere. It bears instead on what the estimate describes. The estimand is a distance between the distributions of the draws that produced a zone, so a difference between the conditions in how often a draw produces none lies outside it by construction, and the cap cannot see that difference however large it is, so long as no single cell drops half its draws. The estimate remains a correct description of the draws it is defined on; read as a statement about every draw, it can mislead when the dropped shares differ (§6.1). A cap on dropped outputs should be read beside a comparison of their rate and content between conditions (§6.2).

---

## 6. Discussion

### 6.1 Flaws that changed the evaluation, and flaws that did not

An audit of whether a preregistered study kept to its plan [57] asks a different question. Here
every gate ran as written and the reported branch is the one the sealed rules reach; the
differences between plan and record that this report states (§E, §I.5) are left to the reader to
judge. The flaws lie between what a gate computes and what its result is taken to show.

One flaw changed the evaluation, in the sense the record shows: the entropy floor decided the
reported branch. What that withheld can be asked only of an assumed truth, and §4 reports it
direction by direction. The branch remains a correct application of the rule, and it rests on a
threshold (§4).

Two flaws did not, and each would surface under other conditions: the power gate's under a
smaller margin (§3), and the cap's when what is dropped differs between conditions, since dropping
such draws is a complete-case analysis that can be biased as a statement about every draw [50].

The distinction is between consequence and presence. All three flaws are present in the protocol as sealed; one had a consequence in this evaluation. The actual flaw qualifies this report, and the latent ones are what a protocol reusing these gates would inherit.

### 6.2 Three diagnostics

These diagnostics follow from the case. Their usefulness on other protocols, and how often gates
read proxies elsewhere, are not examined here.

**Simulate the power of the test that decides.** Given the sealed pipeline, its decision test and
channel-off bases taken from the runs or assumed, measure how often the test and the whole pipeline
reject under shifts put in by design, by direction and size. This shows whether a power gate
computed on another statistic agrees with the test that decides, and where it does not (§3); it
says nothing about bases not simulated, or about an effect in the data. If the test cannot reach the target rate at the margin, enlarge the design before collecting; after collecting, report the estimate with its uncertainty and make no claim that an effect lies below the margin. NLP evaluations often lack the power their conclusions assume [35], the suitable test depends on the measure and setup [48], and a simulation whose shifts are set by design does not read a power figure after the data [44, 49].

**Report support beside entropy, for each condition.** Count the categories each condition's draws
occupy, with the number of draws in each, and those of the base the power calculation uses, beside the entropy the floor reads. This
shows whether a cleared floor still leaves categories empty, or a failed one hides several (§4); it
does not show whether an empty category belongs to the model or to the apparatus (§7.3). Where a category is empty, say whether the zero is what the draws did or what the task imposes, and how the power calculation treats it. Support matters to the power calculation because chi-square-type statistics are sensitive to small cells [43].

**Compare the rate of dropped outputs between conditions, and read their content.** Count the
dropped outputs in each condition and classify each by the parser's own steps. This shows whether
dropping and renormalizing removes a difference between the conditions, and what is dropped (§5).
It does not show a cause: under a fixed order a difference between conditions is also one of
position, and randomizing or counterbalancing separates the two only under assumptions about drift
and dependence between draws. Before collecting, check that every output format the prompt shows is one the parser accepts: in the completed run every dropped draw was the template's own "null". After collecting, say whether the estimate is meant for the draws that produced a category or for every draw.

### 6.3 Relation to prior work

This case adds a further thing to audit in a preregistered evaluation: the correspondence between a gate and the reading of its result. In a Registered Report, outcome-neutral checks are to be specified before the results are known and to be independent of the primary outcome measures [56]. This protocol uses the term for pass
criteria fixed in advance (§G.1), which does not establish that independence: its gates are computed
from the same draws as the estimate, and it was not reviewed as a Registered Report. Meta-research on
preregistration has examined adherence and the disclosure of deviations [57], the reporting of power
analyses [59] and whether reviewers check preregistrations [58], and preregistration has been argued for experiments with AI agents [37]. Decisions that raise doubts about the validity of measures are questionable measurement practices [68]; these gates were stated openly, which that account holds necessary but not sufficient, and lacked evidence that each read the quantity its reading depends on. Shared data do not by themselves make reported values reproducible [69, 70]; the checks of §J are the author's own consistency checks, not an independent reproduction.

Fixing an equivalence bound before analysis is standard practice [36, 61], and declaring a materiality margin in advance has been applied to language-model evaluation [28]; this protocol follows that practice but runs no equivalence test [41, 61], and does not read a failure to reject as evidence that an effect is absent [62]. Its power gate is computed at the registered margin rather than at an observed effect [60], but on each run's own base and for a surrogate statistic (§N.1).

Recommendations for evaluating language models already ask for parts of what the diagnostics do. A power analysis to decide whether an evaluation can test a hypothesis of interest is recommended [65]; the first diagnostic applies it to the test that decides rather than to a surrogate. Agentic benchmarks are asked to establish that a check truly indicates success, and counting an empty response as a success is one way they fail [66]; reports of generative evaluations are asked to describe how answers are extracted [67]. The third diagnostic applies these to a gate, by asking whether what the parser drops differs between the conditions compared. None of them asks whether a protocol's gate reads the quantity that the reading of its result depends on.

Estimating a total-variation distance well from samples is a problem in its own right [29, 42]. Separating instrument artifacts from real effects in a pre-registered setting is adjacent work on a different object [27], and language-model output moves with prompt formatting [45], listed options [46] and required output formats [47], all of which this apparatus holds fixed.

---

## 7. Limitations

### 7.1 Model family and think regime move together

The two arms differ in model family and, unavoidably, in whether the model has a native thinking regime: `qwen3:8b` has one, which every run disabled, and within the available memory budget no model of another family at this scale has one. The design therefore
attributes nothing to either factor alone. This confound was declared in advance.

### 7.2 Condition is confounded with execution order

In all three runs the contexts were run in sorted order, and within each context the 300 channel-on
draws were requested before the 300 channel-off draws; the upstream apparatus fixes that order
(§I.5). Any difference between the conditions is therefore also a difference between earlier and
later draws of the same context: the sealed estimate, the descriptive quantities and the held-out
difference in recorded `None` alike. Elapsed time, server state, drift or the higher temperature and top-p of the channel-on draws could produce it as well as the channel could; a higher temperature makes malformed output more likely, and the prompt asks for Japanese text inside the JSON object (§B.4). The held-out *p*-values are exact only if the draws within a context
are exchangeable over their positions in the run, which a fixed block order does not guarantee, and that the condition-wise counts were not tabulated before the freeze is a declaration in the specification, not something any check demonstrates; the two verdicts, which record the largest rate of such draws in any one cell, had been seen. Nothing here assigns a condition difference to the channel, reads `None` as an intention, or reads a difference between the arms as one between model families.

### 7.3 A shared collapse would not be a replication

Had the two arms agreed under R1, the agreement would not have been a replication of the channel
result. The collapse of the decision space is at least as plausibly a property of the harness -- the
prompt, the parser, the zone vocabulary, the frozen bank -- as of any model, and both arms run the
same harness on the same prompt. If the same two zones went unproduced in both, the agreement would
be evidence that the apparatus behaves consistently, not that the channel fails to propagate in two
model families.

### 7.4 Scope

Every claim here is bounded by one apparatus, thinking disabled or absent in every run, two models and one frozen
prompt run in eight pairs of blocks, with a five-way zone decision. The simulations of §3 and §4 cover only their declared bases, directions and draw counts. §I gives further limitations.

---

## References

<!-- BEGIN RENDERED FROM manuscript/refs.json -- DO NOT EDIT BY HAND -->

[2] Park, J. S. et al. *Generative agents: Interactive simulacra of human behavior.*
arXiv:2304.03442, 2023.

[27] Otterson, J. *Adversarial test-hardening for AI-written code: An instrument autopsy and a
pre-registered causal estimate of the critic loop.* arXiv:2607.23002, 2026.

[28] Singh, A. *Certifying compressed language models: An audit and a statistical toolkit.*
arXiv:2608.15046, 2026.

[29] Price, E., Tian, K., Xun, Z. and Zhu, Y. *Total variation distance estimation in autoregressive
models.* arXiv:2607.19510, 2026.

[35] Card, D., Henderson, P., Khandelwal, U., Jia, R., Mahowald, K. and Jurafsky, D. *With little
power comes great responsibility.* Proceedings of the 2020 Conference on Empirical Methods in
Natural Language Processing (EMNLP), pp. 9263–9274, 2020. doi:10.18653/v1/2020.emnlp-main.745

[36] Lakens, D. *Equivalence tests: A practical primer for t tests, correlations, and
meta-analyses.* Social Psychological and Personality Science, 8(4), 355–362, 2017.
doi:10.1177/1948550617697177

[37] Vaccaro, M. *Preregistration for experiments with AI agents.* arXiv:2606.11217, 2026.

[38] Larooij, M. and Törnberg, P. *Validation is the central challenge for generative social
simulation: A critical review of LLMs in agent-based modeling.* Artificial Intelligence Review,
59(1), article 15, 2025. doi:10.1007/s10462-025-11412-6

[39] Tomašević, A., Cvetković, D., Major, S., Maletić, S., Anđelković, M., Vranić, A., Stupovski,
B., Vudragović, D., Bogojević, A. and Mitrović Dankulov, M. *Towards operational validation of
LLM-agent social simulations: A replicated study of a Reddit-like technology forum.* EPJ Data
Science, 15(1), article 72, 2026. doi:10.1140/epjds/s13688-026-00674-x

[41] Bastian, P., Dette, H. and Koletzko, L. *Testing equivalence of multinomial distributions — A
constrained bootstrap approach.* Statistics & Probability Letters, 206, article 109999, 2024.
doi:10.1016/j.spl.2023.109999

[42] Jiao, J., Han, Y. and Weissman, T. *Minimax estimation of the L1 distance.* IEEE Transactions
on Information Theory, 64(10), 6672–6706, 2018. doi:10.1109/TIT.2018.2846245

[43] Balakrishnan, S. and Wasserman, L. *Hypothesis testing for high-dimensional multinomials: A
selective review.* The Annals of Applied Statistics, 12(2), 727–749, 2018. doi:10.1214/18-AOAS1155SF

[44] Hoenig, J. M. and Heisey, D. M. *The abuse of power: The pervasive fallacy of power
calculations for data analysis.* The American Statistician, 55(1), 19–24, 2001.
doi:10.1198/000313001300339897

[45] Sclar, M., Choi, Y., Tsvetkov, Y. and Suhr, A. *Quantifying language models' sensitivity to
spurious features in prompt design or: How I learned to start worrying about prompt formatting.*
arXiv:2310.11324, 2023.

[46] Zheng, C., Zhou, H., Meng, F., Zhou, J. and Huang, M. *Large language models are not robust
multiple choice selectors.* arXiv:2309.03882, 2023.

[47] Tam, Z. R., Wu, C.-K., Tsai, Y.-L., Lin, C.-Y., Lee, H.-y. and Chen, Y.-N. *Let me speak
freely? A study on the impact of format restrictions on large language model performance.*
Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing: Industry
Track, pp. 1218–1236, 2024. doi:10.18653/v1/2024.emnlp-industry.91

[48] Dror, R., Baumer, G., Shlomov, S. and Reichart, R. *The hitchhiker's guide to testing
statistical significance in natural language processing.* Proceedings of the 56th Annual Meeting of
the Association for Computational Linguistics (Volume 1: Long Papers), pp. 1383–1392, 2018.
doi:10.18653/v1/P18-1128

[49] Morris, T. P., White, I. R. and Crowther, M. J. *Using simulation studies to evaluate
statistical methods.* Statistics in Medicine, 38(11), 2074–2102, 2019. doi:10.1002/sim.8086

[50] Little, R. and Rubin, D. *Statistical analysis with missing data.* Wiley, 3rd edition, 2019.
doi:10.1002/9781119482260

[54] Kiyonaga, A. and Scimeca, J. M. *Practical considerations for navigating Registered Reports.*
Trends in Neurosciences, 42(9), 568–572, 2019. doi:10.1016/j.tins.2019.07.003

[55] Scheel, A. M., Schijen, M. R. M. J. and Lakens, D. *An excess of positive results: Comparing
the standard psychology literature with Registered Reports.* Advances in Methods and Practices in
Psychological Science, 4(2), article 25152459211007467, 2021. doi:10.1177/25152459211007467

[56] Center for Open Science. *Registered Reports.* Web page, n.d.
https://www.cos.io/initiatives/registered-reports (retrieved 2026-10-03)

[57] Claesen, A., Gomes, S., Tuerlinckx, F. and Vanpaemel, W. *Comparing dream to reality: An
assessment of adherence of the first generation of preregistered studies.* Royal Society Open
Science, 8(10), article 211037, 2021. doi:10.1098/rsos.211037

[58] Syed, M. *Some data indicating that editors and reviewers do not check preregistrations during
the review process.* Journal of Trial and Error, 6(1), 8–19, 2026. doi:10.36850/e5ce-4cc5

[59] Bakker, M., Veldkamp, C. L. S., van den Akker, O. R., van Assen, M. A. L. M., Crompvoets, E.,
Ong, H. H. and Wicherts, J. M. *Recommendations in pre-registrations and internal review board
proposals promote formal power analyses but do not increase sample size.* PLOS ONE, 15(7), article
e0236079, 2020. doi:10.1371/journal.pone.0236079

[60] Lakens, D. *Sample size justification.* Collabra: Psychology, 8(1), article 33267, 2022.
doi:10.1525/collabra.33267

[61] Lakens, D., Scheel, A. M. and Isager, P. M. *Equivalence testing for psychological research: A
tutorial.* Advances in Methods and Practices in Psychological Science, 1(2), 259–269, 2018.
doi:10.1177/2515245918770963

[62] Harms, C. and Lakens, D. *Making ‘null effects’ informative: Statistical techniques and
inferential frameworks.* Journal of Clinical and Translational Research, 3(2), 382, 2018.
doi:10.18053/jctres.03.2017s2.007

[63] Zhou, H. and Fishbach, A. *The pitfall of experimenting on the web: How unattended selective
attrition leads to surprising (yet false) research conclusions.* Journal of Personality and Social
Psychology, 111(4), 493–504, 2016. doi:10.1037/pspa0000056

[64] Bell, M. L., Kenward, M. G., Fairclough, D. L. and Horton, N. J. *Differential dropout and bias
in randomised controlled trials: When it matters and when it may not.* BMJ, 346, article
e8668, 2013. doi:10.1136/bmj.e8668

[65] Miller, E. *Adding error bars to evals: A statistical approach to language model evaluations.*
arXiv:2411.00640, 2024.

[66] Zhu, Y., Jin, T., Pruksachatkun, Y., Zhang, A., Liu, S., Cui, S., Kapoor, S., Longpre, S.,
Meng, K., Weiss, R., Barez, F., Gupta, R., Dhamala, J., Merizian, J., Giulianelli, M., Coppock, H.,
Ududec, C., Sekhon, J., Steinhardt, J., Kellermann, A., Schwettmann, S., Zaharia, M., Stoica, I.,
Liang, P. and Kang, D. *Establishing best practices for building rigorous agentic benchmarks.*
arXiv:2507.02825, 2025.

[67] Biderman, S., Schoelkopf, H., Sutawika, L., Abbasi, B., Forde, J. Z., Gao, L., Tow, J., Aji, A.
F., Ammanamanchi, P. S., Black, S., Clive, J., DiPofi, A., Etxaniz, J., Fattori, B., Foster, C.,
Hsu, J., Jaiswal, M., Lee, W. Y., Li, H., Lovering, C., Muennighoff, N., Pavlick, E., Phang, J.,
Skowron, A., Tan, S., Tang, X., Wang, K. A., Winata, G. I., Yvon, F. and Zou, A. *Lessons from the
trenches on reproducible evaluation of language models.* arXiv:2405.14782, 2024.

[68] Flake, J. K. and Fried, E. I. *Measurement schmeasurement: Questionable measurement practices
and how to avoid them.* Advances in Methods and Practices in Psychological Science, 3(4),
456–465, 2020. doi:10.1177/2515245920952393

[69] Hardwicke, T. E., Mathur, M. B., MacDonald, K., Nilsonne, G., Banks, G. C., Kidwell, M. C.,
Hofelich Mohr, A., Clayton, E., Yoon, E. J., Henry Tessler, M., Lenne, R. L., Altman, S., Long, B.
and Frank, M. C. *Data availability, reusability, and analytic reproducibility: Evaluating the
impact of a mandatory open data policy at the journal Cognition.* Royal Society Open Science, 5(8),
article 180448, 2018. doi:10.1098/rsos.180448

[70] Hardwicke, T. E., Bohn, M., MacDonald, K., Hembacher, E., Nuijten, M. B., Peloquin, B. N.,
deMayo, B. E., Long, B., Yoon, E. J. and Frank, M. C. *Analytic reproducibility in articles
receiving open data badges at the journal Psychological Science: An observational study.* Royal
Society Open Science, 8(1), article 201494, 2021. doi:10.1098/rsos.201494

<!-- END RENDERED FROM manuscript/refs.json -->

Reference numbers are permanent identifiers assigned in the author's central bibliography and are
not renumbered between manuscripts.

<!-- TMLR:APPENDIX -->

Two appendices follow, §E and §K; §E states the decision rules as sealed. The other lettered
sections, §A to §D, §F to §J and §L to §O, are in the
Supplementary Material.

## E. Decision rules

The rules below are not written here. They are generated from `seal/decision-rules.json`, the
sealed machine-readable statement of them, by `analysis/scripts/render_decision_rules.py`, and
step 12 of `repro.sh` fails if the block is not what that file renders to. The block reproduces the
sealed text exactly, spelling included; in it, "unparseable" draws are those recorded as `None`
(§5). §D.4 says what each quantity the rules read is, and why the rules are held this way.

<!-- BEGIN GENERATED FROM seal/decision-rules.json -- DO NOT EDIT BY HAND -->

**Estimand.** `tv_bar` — Mean across the K frozen contexts of the total-variation distance between the channel-on and channel-off distributions over the five zones, computed after dropping unparseable draws and renormalising over the five zones. Materiality margin: 0.1.

**Arms.** `control` = `qwen3:8b` — Absorbs the backend version change; evaluated first and gates the primary arm. · `primary` = `llama3.1:8b` — Cross-family replication in a natively non-thinking model.

**Evaluation order: R5 → R4 → R3 → R1 → R2.** Evaluation is strictly ordered and stops at the first rule whose action is `stop`.

R4 is evaluated before R1-R3. The conditions are stated exactly as pre-registered and are not mutually exclusive as written; fixing the evaluation order removes the ambiguity without altering any condition.

**R5 — control-arm concordance** · arm `control` · role `outcome_neutral_gate`

- **Satisfied when**: `verdict` == "NO_CHANNEL_CONFORMANCE" ∧ `rho_hat` ≥ 0.75 ∧ `power` ≥ 0.8 ∧ `tv_bar` < 0.1 ∧ |`tv_bar` − 0.038065| ≤ 0.03 ∧ `permutation_reject` == false
- **Why these values**: The rho_hat bound of 0.75 is tighter than the rho_min of 0.5 used inside the verdict logic, and tolerates variation in at most two of the eight contexts. The tv_bar tolerance of 0.03 is set against the distance of 0.062 between the completed run's value and the materiality floor: a movement larger than 0.03 consumes more than 48% of the margin's interpretive room and is treated as a sign of version drift.
- **Satisfied → continue.** The five quantities fall inside the declared band. That is the whole of its content: it is not a statement about whether the backend upgrade changed anything.
- **Not satisfied → stop.** The control arm did not reproduce the declared band. Report which of the five quantities fell outside it. The primary arm is not interpreted. Only a differing verdict licenses the stronger statement that the version change moved the verdict.

**R4 — apparatus validity** · arm `primary` · role `outcome_neutral_gate`

- **Satisfied when**: `rho_hat` < 0.5 ∨ `none_rate_max_observed` > 0.5
- **Why these values**: rho_min = 0.5 and none_rate_max = 0.5 are among the constants frozen before the completed run and checked mechanically. Evaluated ahead of the estimate so that a floor effect cannot be read as an absent effect.
- **Satisfied → stop.** In the primary family the substrate does not license two or more zones, so this estimand is not measurable in that family. This is NOT read as NO_CHANNEL_CONFORMANCE. The claim narrows to single-model scope.
- **Not satisfied → continue.**

**R3 — attained power** · arm `primary` · role `outcome_neutral_gate`

- **Satisfied when**: `rho_hat` ≥ 0.5 ∧ `power` < 0.8
- **Why these values**: power_min = 0.8 is frozen with the other constants. The completed run attained power 1.0 at these same values of M and K, which is why the prospective design is run at those values rather than smaller ones. See the limitation recorded in the manuscript: this quantity is the power of a chi-square goodness-of-fit test, not of the permutation test the branch turns on.
- **Satisfied → stop.** INCONCLUSIVE_UNDERPOWERED. No claim changes, the result budget is not consumed, and a re-run at larger M/K is sought separately.
- **Not satisfied → continue.**

**R1 — replication** · arm `primary` · role `outcome_branch`

- **Satisfied when**: `rho_hat` ≥ 0.5 ∧ `power` ≥ 0.8 ∧ `tv_bar` < 0.1 ∧ `permutation_reject` == false
- **Why these values**: The materiality margin of 0.10 is exclusive here: an estimate of exactly 0.10 is not below it and falls to R2.
- **Satisfied → stop.** The estimate falls below the materiality margin in a non-Qwen natively non-thinking regime as well. The claim moves from single-model to two tested model families. The confound that stays open, and the possibility that a shared apparatus-level collapse rather than a channel property produces the agreement, are both carried as limitations.
- **Not satisfied → continue.**

**R2 — non-replication** · arm `primary` · role `outcome_branch`

- **Satisfied when**: `rho_hat` ≥ 0.5 ∧ `power` ≥ 0.8 ∧ (`tv_bar` ≥ 0.1 ∨ `permutation_reject` == true)
- **Why these values**: R1 and R2 partition the space that remains after R4 and R3, so the on_fail state of R2 is unreachable by construction and is recorded as a defect condition rather than as an outcome.
- **Satisfied → stop.** The result is specific to qwen3:8b under the disabled-think regime. The central claim narrows to that apparatus and model. This is a finding, not a failure.
- **Not satisfied → stop.** UNREACHABLE. R1 and R2 partition the space remaining after R4 and R3, so reaching this state indicates a defect in the rules or in the inputs, and must be reported as such rather than interpreted.

**Quantities that are easy to misread.**

- `none_rate_max_observed` — The apparatus computes the none-rate per (context, condition) cell and records the maximum across cells. No pooled none-rate is produced anywhere in the run output, so the maximum is the only quantity this predicate can be evaluated on. Recorded here explicitly because the protocol prose said 'pooled'.
- `permutation_reject` — From the stratified label-permutation test on tv_bar performed inside the scorer, at alpha = 0.05.
- `power` — Monte-Carlo power of a chi-square goodness-of-fit test against an alternative built by moving mass from the largest to the smallest cell of the empirical channel-off distribution. It is NOT the power of the permutation test that produces permutation_reject.

<!-- END GENERATED FROM seal/decision-rules.json -->

## K. AI usage disclosure

<!-- TMLR:FOOTNOTE -->
**Use of AI assistance.** This work was developed with substantial AI assistance: Claude (Anthropic) for
implementation, documentation and drafting, and OpenAI Codex for independent review. No AI system is an
author, and every AI-assisted output was reviewed and validated by the author. §K states the extent,
with commit counts a reader can recompute.
<!-- /TMLR:FOOTNOTE -->

This work was developed with substantial AI assistance, disclosed here in full.

Claude (Anthropic; the Opus 4.8, Opus 5, Opus 5.5 and Sonnet 5 models, via Claude Code) was used for
implementing the measurement apparatus and the analysis and verification scripts shipped here, for
documentation, and for drafting the text of this manuscript. OpenAI Codex (`gpt-5.5` and `gpt-6-astra`) was used for
independent design and code review. **No AI system is an author**, and **no figure in this
submission was generated by an image-generation model**: the three figures are drawn
deterministically from the shipped data by `analysis/scripts/make_figures.py`, which, like the rest of
the code, was written with AI assistance. The submission build checks every number a figure sets
against the data it is drawn from and against the page it lands on (§J).

The extent of that assistance is visible in the public record rather than asserted here, and the
counting method is stated so that a reader can reproduce the figures:

| Repository | Commits | Commits carrying at least one `Co-Authored-By` trailer naming the model |
|---|---|---|
| Upstream source, <https://github.com/mikotomiura/ERRE-Sandbox>, at commit `a2a19f9` | 305 | **205** |
| This repository, at commit `a32bcf3` | 20 | **18** |

Table: Commits carrying an AI co-author trailer, each count taken at the commit it names.

Trailers are counted **case-insensitively, as commits rather than as trailer lines**, over the
history reachable from the commit named in each row. Both halves of that sentence are load-bearing.
A single commit may carry more than one trailer, so the upstream history holds 286 such lines
across those 205 commits, and a count of lines reported as a count of commits would overstate the
figure by two fifths. And a count with no commit pinned beside it cannot be reproduced at all,
because the next commit changes it. Each row is therefore true of the commit it names and of no
other, which is the most a count of this kind can be: the commit that records a figure cannot be
included in it, so the row for this repository names the last commit before the one that wrote the
row. It also has to name a commit a reader can still reach, which is why the row names a commit on
`main`. Anyone can recompute both with `git log --format=%H%x01%B%x02` over the named commit and count
the entries whose body matches `co-authored-by:.*claude`, case-insensitively.

All AI-assisted output was reviewed, edited and validated by the human author, who made the
decisions that determine what this protocol claims: the choice of estimand and of the materiality
margin, the decision rules R1–R5 and the order in which they are evaluated, the eligibility
position of §F, the scope of every claim and of every limitation in §7, and the decision to seal
this protocol before collecting the prospective data. Validation is not self-reported: the numerical,
provenance and claim-boundary properties asserted in this manuscript are enforced by `repro.sh`
(§J) and re-run by public continuous integration on two operating systems, and the claim-boundary
guards are themselves checked against a fixture written to trip every one of them (§G.3), so a
guard that silently stopped working fails the run.

---
