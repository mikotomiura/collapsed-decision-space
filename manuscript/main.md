# Three gates, three proxies: auditing the null-report checks of a pre-registered LLM-agent evaluation

<!-- TMLR:DROP -->

**A sealed, pre-registered evaluation, its outcome reported against the sealed rules, and an audit of the gates that decided what that outcome is worth. Every analysis outside the sealed rules is labelled by when it was fixed (§2.4).**
No prospective draw existed when the decision rules were sealed. They are sealed in machine-readable
form, so that the branch reported afterwards can be re-derived from the rules as they stood before
it (§J).

| | |
|---|---|
| Author | Mikoto Miura |
| ORCID | [0009-0000-4196-0508](https://orcid.org/0009-0000-4196-0508) |
| Affiliation | Independent Researcher |
| Correspondence | via the submission system of the venue this manuscript is submitted to |
| Code and data | <https://github.com/mikotomiura/collapsed-decision-space>. Development continues on the default branch; what pins the protocol against later change is the seal of §H and §J, not a branch name |
| Licence | Code: Apache-2.0 OR MIT. Manuscript and figures: CC BY 4.0 |
| Protocol status | The protocol was sealed before any prospective draw was collected. Each arm then produced one complete run, on 2026-09-14 (UTC); the control arm's first capture attempt was stopped from outside before it produced a verdict, and that arm was restarted from the beginning (§I.5). The two verdicts reach branch R4, reported in the results section. A held-out test of a post hoc observation was run afterwards, outside the seal (§2.4). §H states what the seal covers and what breaks it |

---
<!-- /TMLR:DROP -->

## Abstract

A pre-registered evaluation that may end in a null must fix in advance what a null is worth, through
gates on power, read-out variability and dropped outputs. We audit the three gates of one sealed
evaluation of a language-model agent. The agent receives one fixed prompt, set in a simulated world
with five named zones, and returns a plan naming its next zone. The evaluation asked whether a
change in sampling driven by the agent's recent movement shifts that choice by more than a
total-variation margin of 0.10. Its rules stopped at the measurability gate, with no estimate for
the second of two models. Each gate ran as written and read a quantity other than the one its
reading depends on. The power gate evaluates a chi-square surrogate, not the permutation test that
decides. A post hoc simulation of that test, fixed before it ran, shifts the first run's channel-off
distribution as the surrogate's alternative does: the test's rejection rate stands at the
surrogate's 1.0 from half the registered effect size upward, but at a tenth of the margin the
surrogate returns 1.0 where the test rejects in 122 of 1,000 simulated replicates. The entropy floor
passes two runs whose channel-off draws leave two of the five zones empty. The cap on draws with no
recorded zone reads the worst cell rather than the difference between conditions. A held-out test
found more such draws in both arms' channel-on blocks (156 against 94; 107 against 61), mostly the
string "null" in one arm and missing or malformed JSON in the other, confounded with execution
order. This case motivates three diagnostics for interpreting protocol gates. The claims concern
these gates on two models and one prompt, not the effect of the channel.

---

## 1. Introduction

Generative agents are language-model agents that act in a simulated world, keep an internal state,
and choose their next action from it [2]. Whether that state reaches the choices downstream of it
is a question about the validity of such simulations [38, 39]. The agent studied here acts in a
simulated world with five named zones. At each step it returns a plan, as a JSON object, that names
the zone it moves to next. A scalar computed from its recent movement enters the sampling settings
of that step. We call this path the channel.

A pre-registered evaluation that may end in a null must fix in advance what a null is worth
[35, 36, 44]. It does so through gates, each with a threshold fixed before the data exist. A power
gate asks whether the design could detect a shift of the declared size. An entropy floor asks whether
the read-out varies enough to register such a shift. A cap on draws with no recorded zone asks
whether the scored draws stand for what each condition produced. A rule rather than a later
judgement then settles whether a null may be reported.

We examine one sealed evaluation of this kind. It asked whether the channel shifts the agent's
choice of zone by more than a margin of 0.10 in total variation. Its rules were sealed after a
completed run on one model and before any prospective draw existed. Applied to a control arm on the
same model and a primary arm on a second model, the rules stopped at the measurability gate, and the
second model yields no estimate.

This paper asks what each gate of that evaluation read, and what the reading of its result depends
on.

Each gate ran as written: it passed, or it fired by its own rule. Each read a quantity other than
the one the reading of its result depends on (Table 1). The power gate reads a chi-square surrogate
rather than the permutation test that decides. The entropy floor reads how evenly each context's
draws spread rather than how many zones they reach. The cap on draws with no recorded zone reads the
worst cell rather than the difference between conditions. The prospective arms and a held-out test
did not settle this; they exposed it.

| Gate | What it reads | What the reading of its result depends on |
|---|---|---|
| Power gate | The power of a pooled chi-square goodness-of-fit surrogate, against an alternative built from the channel-off draws | The power of the stratified permutation test on which the decision turns |
| Entropy floor | The entropy of each context's zone distribution, pooled over both conditions | How many zones the draws occupy, in particular in the channel-off base that the power calculation uses |
| Cap on draws with no recorded zone | The largest rate, over the cells of one context and one condition, of the draws the estimand drops | How the share of dropped draws differs between the channel-on and the channel-off blocks |

Table: The three gates of the sealed evaluation, what each reads, and what the reading of its result depends on.

The case motivates three diagnostics for interpreting protocol gates. Simulate the power of the test
that decides, through the whole pipeline. Report how many zones each condition's draws occupy,
beside the entropy the floor reads. Compare the rate of dropped outputs between conditions, and read
what the dropped outputs contain.

The claims concern these gates on two models and one frozen prompt run in eight pairs of blocks.
They are not claims about the effect of the channel, and they do not use the value of the margin.
Most of the evidence is descriptive, post hoc or held-out, and §2.4 labels every analysis by when
it was fixed. The thresholds are not revised, and the sealed branch stands as the rules give it. The
contributions are three. The first is a documented case in which each gate of a sealed protocol ran
as written and read a proxy, shipped with rules, records and checks that redraw every figure and
compare most quoted quantities with the data. The
second is an account of what the estimand drops: in the completed run, the string "null" that the
prompt template itself offers. The third is the set of diagnostics of §7.1, each stated with what it
can and cannot show. The statistics they rest on are standard, and §7.2 relates them to prior work.

§2 sets out the agent, the manipulation, the estimand and the gates. §3 reports what the sealed
rules returned, and §4 to §6 take the three gates in turn. §7 states the diagnostics, and §8 the
limitations.

---

## 2. Setting and protocol

### 2.1 The agent, the world and the read-out

The apparatus descends from the generative-agent architecture [2]. Its world has five named zones:
`agora`, `chashitsu`, `garden`, `peripatos` and `study`. Every draw sends the model the same two
messages. The system prompt places the agent in that world, gives it a neutral persona with no
preferred zone, and states that it is in `agora`. The user prompt lists its recent observations and
memories: a cue in `study`, a cue in `garden`, and a move from `agora` towards each. It asks for a
single JSON object that says what the agent does next. One field of that object,
`destination_zone`, names the zone it moves to.

The read-out is that field as the parser records it, before any later bias is applied. A
draw is one model call and its recorded read-out. The parser accepts one of the five zone names, or
a JSON `null` as an empty destination, and otherwise rejects the whole plan. A draw with no recorded
zone is a draw whose read-out is recorded as `None`: its plan was rejected, or it named no
destination.

The channel is an exponential moving average over the agent's recent moves. It yields a scalar λ,
and the apparatus composes λ into the sampling settings of the next generation. With the channel on,
that path is active. With it off, the locomotion input is removed. A completed preliminary study
established that the path is causal, is separable from the static location channel, and vanishes
under ablation (§A). Wherever this paper speaks of an effect, its subject is the channel. It is not
walking, and it is not creativity.

### 2.2 The manipulation and the runs

The sealed protocol compares the zone distribution with the channel on against the same
distribution with the channel off. Its unit is the context: a frozen bank of eight contexts, each
run for 300 draws per condition, 4,800 model calls per run. Three runs of this measurement
exist. The completed run used `qwen3:8b` under ollama 0.31.1, with thinking disabled, and preceded
the seal. After the seal, the control arm re-ran `qwen3:8b` under ollama 0.32.12, so that a change of
backend is not read as a change of model family. The primary arm ran `llama3.1:8b`, a model of the
same parameter scale from another family. The backend returns samples, not token probabilities, so
each distribution is estimated from draws. §C gives the sealed design, and §I.2 the cost of sample
access.

**[Post hoc]** The per-draw records of the three runs show what each draw was made with. Read from
those records, all 14,400 draws of the three runs carry one system prompt and one user prompt. In
every run, channel-on draws are sampled at temperature 0.82 and top-p 0.94, channel-off draws at
temperature 0.70 and top-p 0.90, with a repetition penalty of 1.0 in both. Each run consists of
eight pairs of blocks, each pair 300 channel-on draws followed by 300 channel-off draws, one pair
per context. The channel-on block of every pair ran first, so the condition is also a position in
the run (§8.2).

On these records, then, a context is a pair of blocks of one prompt, distinguished by its identifier
and its position in the run. The sealed text keeps the words "contexts" and "per-context λ" (§C.3),
and this paper quotes them as sealed. Differences between blocks are differences between repetitions
of one input, not between input situations. The registered per-context computations and the
stratified test stand as sealed. Stratifying by block does not make the draws within a block
exchangeable over their positions, and the held-out test states that as an assumption (§6.2).

### 2.3 Estimand, test, margin and gates

For each context, the distance is the total variation between the five-zone distributions of its
channel-on and channel-off draws. Draws with no recorded zone are dropped first and the rest
renormalised. The primary estimand is the mean of that distance over the contexts the scorer admits.
A stratified permutation test, with the contexts as strata, tests
whether the conditions differ at α = 0.05. It is a nil-null test, and failing to reject is not
evidence of equivalence. The protocol runs no equivalence test [36, 41].

The margin of 0.10 is a rule for reading an estimate, fixed before the data: an estimate below it,
with no rejection, is read as below the materiality margin. It is not a prediction of where the
estimate falls. Its value was frozen upstream before the completed run (§G.2), and no rationale is
added after the fact. The claims of this paper do not use the value.

The sealed rules read six recorded quantities and are evaluated in the order R5 → R4 → R3 → R1 → R2,
stopping at the first rule whose action is to stop (§E). Three gates are the subject of this paper:

- the **power gate** (R3) stops the evaluation as underpowered if the recorded power is below 0.8;
- the **entropy floor** is the first condition of the measurability gate (R4): R4 fires if fewer
  than half the contexts reach an entropy of 0.5 bit;
- the **cap on draws with no recorded zone** is its second condition: R4 fires if any cell of one
  context and one condition drops more than half its draws.

R5 is a concordance check on the control arm. It requires that arm to reproduce the completed run
within a band declared in advance. R1 and R2 are the two outcome branches for the primary arm: an
estimate below the margin with no rejection (R1), or not (R2). R4 and R3 are written for the primary
arm, but the scorer computes the same gate quantities on every run.

### 2.4 Analysis map

The analyses of this paper were fixed at four different times, and what each may be read as depends
on when. From here on, a paragraph that reports an analysis outside the sealed rules opens with the
tag of its layer.

| Layer | Computes, on which data | Fixed when | Licenses | Where |
|---|---|---|---|---|
| **[Registered]** | The mean distance over five zones, with draws with no recorded zone dropped; the permutation test; rules R5 → R4 → R3 → R1 → R2. Scorer run on each prospective arm; rules applied to the two verdicts | Sealed before any prospective draw (§H, §J) | The reported branch, R4. Nothing about the channel's effect in the primary arm | §3; §C–§E |
| **[Prospective, descriptive]** | Quantities no rule reads, from the same two arms: per-context entropy, zones per cell, channel-off support | After the runs. No test | Descriptions of these two runs. No change to the branch | §3, §5 |
| **[Post hoc]** | On the completed run: channel-off support, the surrogate's sensitivity, what the dropped draws contain, the permutation-null mean. On the records of all three runs: the prompt and sampling of every draw. A seed-fixed simulation of the sealed pipeline and its permutation test, under channel-off bases taken from the runs and shifts put in by the simulation | After the completed run was seen: the re-analysis that `seal/protocol.md` §5 leaves unregistered. The simulation's grid, seeds and reading rules were pushed before its first full run | Descriptions of that run, of the records and of the gates; operating characteristics of the design under assumed distributions. It generated the held-out hypothesis and is not evidence for it; the simulation says nothing about the channel | §2.2, §4, §5, §6.1, §M.3 |
| **[Held-out]** | One-sided stratified test that recorded None is more frequent in channel-on blocks; per arm, control first, α = 1/40; class breakdown and qualifiers. On both arms' per-draw annotation and records | Frozen before the condition-wise counts were tabulated (declared); run once (declared) | Row A of its frozen table, always quoted with its qualifiers and class breakdown. Not separable from block order; no reading as intention; nothing beyond two models and one prompt | §6.2 |

Table: The four layers of analysis, when each was fixed, and what each licenses.

Only the [Registered] layer is bound by the seal. Nothing in the other three changes the reported
branch or the sealed text of §E. The [Post hoc] layer is the re-analysis of the completed run that
the sealed plan excludes (§F), carried out outside that plan and labelled as such. The [Held-out]
layer tests a hypothesis the [Post hoc] layer produced, on draws collected before its specification
existed, and is not given the standing of the sealed analysis.

---

## 3. What the sealed rules returned

<!-- REPORTED-BRANCH: R4 -->

<!-- TMLR:FIGURE pipeline -->
**Figure 1.** The sealed rules in their evaluation order, with each predicate as
`seal/decision-rules.json` states it; the figure is generated from that file. The note beside each
gate says what quantity it reads. R5 applies to the control arm and the others to the primary arm,
and evaluation stops at the first rule whose action is `stop` (§E).
<!-- /TMLR:FIGURE -->

**[Registered]** Both arms were run on 2026-09-14 (UTC) at the sealed sampling plan, 4,800 model calls per arm and 9,600 in total. Each arm produced one complete run.
The control arm's first capture attempt was stopped from outside before it had produced a verdict,
and was restarted from the beginning (§I.5). Each bundle was checked against the seal before its verdict was landed. The
branch below was derived by hand from the two landed verdicts and `seal/decision-rules.json`,
quantity by quantity, in `manuscript/REPORTED-BRANCH.md`.

**[Registered] Control arm (`qwen3:8b`).** The recorded quantities are `verdict` =
NO_CHANNEL_CONFORMANCE, `rho_hat` = 1.0, `power` = 1.0, the estimate `tv_bar` = 0.030575, and
`permutation_reject` = false at permutation *p* = 0.43989, with `none_rate_max_observed` = 0.086667
across the arm's cells. All eight contexts clear the entropy floor. R5 is satisfied on all six of its
predicates: the estimate sits 0.007490 from the centre of a tolerance of 0.03. A pass states band
membership and nothing further about the backend upgrade. Evaluation continues to the primary
arm.

**[Registered] Primary arm (`llama3.1:8b`).** `rho_hat` = 0.0, with `effective_k` = 0 of 8. No
context reaches the entropy floor of 0.5 bit: the per-context entropies run from 0.165654 to
0.274008. Draws are produced and parsed, and `none_rate_max_observed` = 0.066667 is of the same order
as in the control arm. Because no context is admitted, the scorer stops before forming the contrast
between the conditions. `tv_bar`, `power` and `permutation_reject` are therefore absent from the
verdict, not small in it.

**[Registered] The branch is R4, apparatus validity.** R4 is evaluated ahead of the estimate so that
a floor effect cannot be read as an absent effect, and `rho_hat` < 0.5 satisfies it. The reading the
sealed rule attaches (§E.2) is that in the primary family "the substrate does not license two or
more zones", that the estimand is therefore not measurable in that family, that this is not read as
NO_CHANNEL_CONFORMANCE, and that the claim narrows to single-model scope. R3, R1 and R2 were not
reached. The primary verdict still carries the string NO_CHANNEL_CONFORMANCE, because the scorer has
one exit for a read-out it cannot score; that label describes a comparison only in the two runs that
formed an estimate.

**[Prospective, descriptive] The sealed reading and the data.** The first part of that reading does
not match the data literally: every one of the primary arm's 16 (context, condition) cells produces
two or more zones, between two and four. The rule fired on `rho_hat`, which the entropy floor
defines, and not on the paraphrase. The generated rule text stands as sealed, and neither the firing
nor the branch is affected.

**[Registered, post hoc and held-out]** The table sets out, gate by gate, what the three runs show.
The recorded gate quantities are registered. The completed run's observations and the simulation are
post hoc, and the counts under the held-out test are held-out.

| Gate | What the runs show |
|---|---|
| Power gate (R3) | `power` = 1.0 in the completed run and the control arm; none is produced in the primary arm. At `delta_tv` = 0.10 the surrogate returns `1.0000` for both bases checked, near-uniform and degenerate, so a pass does not tell them apart; against the completed run's channel-off base it returns `0.921` at one hundredth of the margin (§4.1). Simulated post hoc on that base, the test's rejection rate equals the surrogate's 1.0 from `delta_tv` = 0.05 upward along the surrogate's direction and is below it at smaller shifts (§4.2) |
| Entropy floor (R4) | Completed run and control arm: `rho_hat` = 1.0 in both, while `agora` and `chashitsu` never appear in either channel-off base. Primary arm: the rule fired, `rho_hat` = 0.0, although each of its 16 (context, condition) cells produced between two and four zones (§5) |
| Cap on draws with no recorded zone (R4) | All three runs pass (`0.123333`, `0.086667`, `0.066667`). The channel-on blocks hold more such draws: 206 against 124 in the completed run, where the observation arose; under the held-out test (row A of the held-out test's frozen interpretation table; §6.2), 156 against 94 in the control arm and 107 against 61 in the primary arm |

Table: What the three runs show at each gate.

§M gives further results of the run, including the scorer's exit label record by record (§M.4).

---

## 4. Gate 1: power

### 4.1 What the power gate reads

The power gate (R3) reads `power`, the Monte-Carlo power of a pooled one-sample Pearson chi-square
goodness-of-fit test. Its base is the run's pooled channel-off distribution. Its alternative moves
probability mass from the largest cell of that base to the smallest, by the registered shift of 0.10
in total variation. The decision itself turns on the stratified permutation test of §2.3. The two
tests use different statistics, and the sealed design did not evaluate the power of the permutation
test. `power` is therefore the nominal sensitivity of a surrogate. A pass of R3 is not read here as
evidence about the power of the decision, and a power figure computed after the data cannot
interpret a non-significant result in any case [44].

**[Post hoc]** At the registered shift the surrogate returns `1.0000` for a near-uniform base as well
as for a degenerate one (§B.1), so a pass does not tell them apart. Against the completed run's
channel-off base the surrogate behaves differently. That
base has two empty cells (§5), and the alternative
moves mass into one of them. The statistic divides by the expected count, which the implementation
floors at a small constant only to avoid dividing by zero. A single draw in a cell of base
probability zero therefore produces an enormous statistic, the sensitivity to small cells that
chi-square-type statistics are known for [43]. The sweep below is recomputed on every reproduction
run:

| `delta_tv` | as a fraction of the 0.10 margin | power | passes the `0.8` gate |
|---|---|---|---|
| `0.1` | 1 | `1.0` | yes |
| `0.02` | 1/5 | `1.0` | yes |
| `0.01` | 1/10 | `1.0` | yes |
| `0.005` | 1/20 | `0.999` | yes |
| `0.002` | 1/50 | `0.993` | yes |
| `0.001` | 1/100 | `0.921` | yes |
| `0.0005` | 1/200 | `0.708` | no |
| `0.0002` | 1/500 | `0.39` | no |

Table: The surrogate's power against the completed run's channel-off base, from the margin down to one five-hundredth of it.

**[Post hoc]** The surrogate clears 0.8 at one hundredth of the margin that the study declared material. Its value
alone says almost nothing about whether the test that decides could detect a shift of the declared
size; §4.2 evaluates that test by simulation.

<!-- TMLR:FIGURE power -->
**Figure 2.** [Post hoc] Top: how often the sealed permutation test alone rejects (test) and how
often the sealed pipeline reaches R2 (pipeline), along the surrogate's direction D1 on the completed
run's channel-off base `C` and on the degenerate base `G`, beside the R3 surrogate at the same shift;
the plotted values are printed beneath. A marker's shape shows the quantity and its size the base, so
that curves which coincide, as the test and the pipeline on `C` nearly do, can both be seen. Bottom:
for every declared base and direction, the smallest declared shift at which each rate reaches 0.8
(n.r.: not reached in the declared grid; n/a: not in the grid). Simulated under assumed channel-off
distributions, not an estimate of any effect of the channel.
<!-- /TMLR:FIGURE -->

### 4.2 Simulated operating characteristics of the sealed pipeline

**[Post hoc]** The simulation measures what the gate was meant to stand for. It asks how often the
sealed pipeline, and the permutation test inside it, reject when every context's channel-off
distribution is known and the channel-on distribution is moved from it by a stated amount. Like any
simulation study of a method [49], it measures a property of the design under assumed distributions.
It estimates nothing the channel did, and no rate
below turns the completed run's non-rejection into evidence that an effect is absent. Every shift is
put in by the simulation, and its grid, seeds and reading rules were fixed before its first full run.

**[Post hoc]** In brief, there are five channel-off bases per context: the completed run's (`C`), the control arm's
(`K`), `C` with its two empty zones filled (`Cs`), and the near-uniform (`U`) and degenerate (`G`)
bases of §B.1. There are six directions of shift. D1 is the surrogate's own, from the largest cell to
the smallest, which on `C` is an empty zone; D5 moves mass into the empty zones. Every context is
moved by the same total variation, from 0 to 0.15. Two rates are reported. `P(R2)` is the share of replicates that
reach R2, by a rejection or an estimate at or above the margin; a stop at R4 or R3 does not count. `P(test_reject)` is how often the permutation test rejects when
applied to all eight contexts with no gate in front of it.

**[Post hoc]** At the registered shift on the completed run's base, the pipeline reaches R2 in 1,000 of 1,000
replicates in each of the four feasible directions (D1, D2, D3, D5), and the test alone rejects in
1,000 of 1,000; D4 and D6 are infeasible there, because one context holds less than 0.10 in `garden`.
These are not four independent confirmations: the replicates share their channel-off draws, and D1
and D5 give identical statistics there from `delta_tv` = 0.05 upward. At the registered margin, on
this base, a pass of the power gate and the test's simulated rejection rate agree. Along the
surrogate's own direction on the same base they agree from `delta_tv` = 0.05 upward and part below it
(Figure 2).

**[Post hoc]** The test and the pipeline come apart on the degenerate base: along D1, at `delta_tv` = 0.02 the test
alone rejects in 411 of 500 replicates (`0.822`) while the pipeline stops at R4 in 500 of 500, and
P(R2) first reaches 0.8 there at `delta_tv` = 0.10 (497 of 500). The simulation does not cover other
bases, other directions, shifts that differ in size between contexts, or numbers of draws other than
the completed run's. §B.3 gives the declaration, the design and every declared cell.

---

## 5. Gate 2: entropy floor

The entropy floor is the first condition of the measurability gate (R4). For each context it computes
the entropy of the zone distribution, pooled over both conditions with draws with no recorded zone
excluded, and admits the context if that entropy reaches 0.5 bit. `rho_hat` is the fraction of
contexts admitted, and R4 fires if it falls below 0.5. The floor reads how evenly a context's draws
spread. The reading of the gate depends on how many zones the draws reach, and in particular on the
support of the channel-off base that the power calculation uses. The sealed reading of R4 itself
speaks of "two or more zones".

**[Post hoc]** In the completed run, two of the five zones never appear in the channel-off condition.
Pooled over that condition (2,276 draws that parsed), the read-out distribution is:

| Zone | Count | Probability |
|---|---|---|
| `agora` | 0 | `0.0` |
| `chashitsu` | 0 | `0.0` |
| `garden` | 295 | `0.129613` |
| `peripatos` | 32 | `0.01406` |
| `study` | 1949 | `0.856327` |

Table: The completed run's channel-off read-out, pooled over the contexts.

**[Post hoc]** `chashitsu` is not produced once in the whole run, under either condition, and `agora` appears three
times, all in one context. Seven of the eight contexts have a combined support of three zones. Both
zeros are empirical: they are what these draws did, not a property the task imposes.

**[Post hoc and prospective, descriptive]** The entropy floor admits every context of the completed
run. The control arm records `rho_hat` = 1.0 as well, and its channel-off base also never produces
`agora` or `chashitsu`: of its 2,306 parsed channel-off draws, `garden` has 386, `study` 1,896 and
`peripatos` 24. The primary arm is the reverse case: no context clears the floor, although every
cell reaches two or more zones. The table sets the zones each run's parsed draws occupy beside what
the gate recorded. The completed run's row is post hoc, and the two arms' rows are prospective and
descriptive.

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
(§8.2). The completed run's panel belongs to the post hoc layer and the two arms' panels to the
prospective descriptive layer (§2.4).
<!-- /TMLR:FIGURE -->

**[Post hoc and prospective, descriptive]** Entropy measures how evenly a context's draws spread,
and support how many zones they reach. In these
runs the two come apart in both directions. Clearing a per-context entropy floor therefore does not
certify the support that the power calculation depends on. A floor of 0.5 bit requires at least two
zones in a context and says nothing more about the support. At the frozen thresholds R4 does not flag
the completed run or the control arm. That depends on the thresholds rather than on the shape of the
rule: a floor set above 0.68 would have fired on the completed run too.

---

## 6. Gate 3: cap on draws with no recorded zone

### 6.1 What the dropped draws are

The cap is the second condition of the measurability gate (R4). The estimand drops every draw with
no recorded zone and renormalises over the five zones. The sealed protocol chose that over a sixth
category, and made the rate of such draws the quantity R4 reads (`seal/protocol.md` §1). The cap
reads the largest rate over the 16 cells of one context and one condition, against 0.5. The reading
of the gate depends on how the share of dropped draws differs between the channel-on and the
channel-off blocks, which the cap does not read.

**[Post hoc]** In the completed run the dropped draws are 124 of the 2,400 channel-off draws and 206
of the 2,400 channel-on draws, with more in the channel-on condition in 8 of the 8 contexts. That
observation was made after the run. It is the hypothesis §6.2 tests, and it is not counted as
evidence here.

**[Post hoc]** All 330 are the same thing: a response that followed the prompt template literally. The template
shows the field as `"destination_zone": "study|peripatos|chashitsu|agora|garden|null"`, with `null`
inside the quotation marks (`analysis/apparatus/erre_sandbox/cognition/prompting.py`, lines 48 and
71). In `destination_zone` the parser accepts only the five zones or a JSON `null`, so the string
`"null"` fails validation, the whole plan is rejected, and the record carries `None`. Re-parsing the
completed run's raw responses with the apparatus parser reproduces every recorded value, and all 330
`None` records are this string-`"null"` failure, with no JSON `null` and no missing key among them.
The estimand's word for these draws, "unparseable", is exact for this run. Output that follows the
format of the prompt, or fails a required output format, is a known dependence of language-model
evaluation [45, 47], and this is an instance of it.

### 6.2 A held-out test of the post hoc observation

**[Held-out]** The observation of §6.1 was tested once, on the two prospective arms, whose draws had
been collected without reference to it. The specification, the test and the interpretation table
were frozen at commit `61dbd96` (`analysis/heldout-stay/SPEC.ja.md`, `freeze.json` and
`analysis/scripts/heldout_stay_check.py`, which the `heldout-stay` workflow runs on two operating
systems), and the test was run once from that commit. It is not a formal pre-registration: the
prospective draws existed before the specification did. That the condition-wise counts had not been
tabulated before the freeze is a declaration in the specification, not something any check
demonstrates. The outcome is whether a draw is recorded as `None`. The test is an exact one-sided
stratified test, with the eight contexts as strata and each context's `None` total held fixed, at
level 1/40. It was applied to the control arm first, and counted for the primary arm only if the
control arm's test rejected.

**[Held-out]** Both rejected. That is row A of the frozen interpretation table, whose wording is: in both
prospective runs, recorded `None` was more frequent in the channel-on blocks than in the channel-off
blocks.

| Arm | `None`, channel-on blocks | `None`, channel-off blocks | one-sided *p* |
|---|---|---|---|
| control (`qwen3:8b`) | 156 | 94 | 3.415046e-05 |
| primary (`llama3.1:8b`) | 107 | 61 | 1.894707e-04 |

Table: Draws recorded as `None` in each arm, by condition, with the held-out test. Specification frozen at commit `61dbd96`, before the condition-wise counts were tabulated (declared).

**[Held-out]** What was recorded as `None` differs between the arms, and the frozen specification
requires the
difference to be reported with the result. Each `None` draw's raw response was classified with the
parser's own steps:

| What `destination_zone` held | control, on | control, off | primary, on | primary, off |
|---|---|---|---|---|
| the string `"null"` | 154 | 94 | 5 | 2 |
| a JSON `null` | 1 | 0 | 0 | 0 |
| no `destination_zone` key | 0 | 0 | 1 | 0 |
| a valid zone name, with the plan rejected on another field | 0 | 0 | 0 | 0 |
| some other value | 0 | 0 | 3 | 2 |
| no usable JSON object | 1 | 0 | 98 | 57 |

Table: What `destination_zone` held in each draw recorded as `None`, by arm and condition.

**[Held-out]** In the control arm almost every `None` is an explicit `"null"`, as in the completed
run, where all 330
dropped draws are the string `"null"`. In the primary arm almost every one is a missing or malformed
JSON object, and 41 of the primary arm's 46-draw excess in the channel-on blocks is of that kind. The
word "unparseable" is exact for all but two of the draws dropped in the prospective arms; the other
two are a JSON `null` and an absent destination key, which the parser treats as an empty destination
rather than an error. The frozen qualifier for writing that outputs naming `null` as the destination
increased holds for the control arm, where the same test applied to the string and JSON `null` alone
gives *p* = 4.359535e-05, and not for the primary arm, where it gives *p* = 2.263667e-01. For the
primary arm, what increased is recorded `None` in general. **What replicated is an operational
outcome, the recorded `None`, and not the same behavioural meaning or the same parser-failure
mechanism across the two families.**

**[Held-out]** The difference cannot be separated from execution order. Every context ran its
channel-on block
before its channel-off block, so a difference between the conditions is also a difference between
earlier and later draws (§8.2). The *p*-values above are exact only if the draws within a context are
exchangeable over their positions in the run, which a fixed block order does not guarantee. What the
result does not license was fixed in the specification before it was known: an effect of the channel
separated from execution order; any attribution to λ, locomotion, embodiment, temperature or top_p;
reading `None` as an intention; reading the difference in effect size between the arms as a
difference between model families; and any statement beyond two models and eight frozen contexts,
which on the records are one prompt (§2.2). §M.5 reports the secondary six-category distance the
specification requires, without judging it against the margin.

---

## 7. Lessons and related work

### 7.1 Three diagnostics

Three diagnostics for interpreting protocol gates follow from this case. Their usefulness on other
protocols, and how often gates read proxies elsewhere, are not examined here.

**Simulate the power of the test that decides.** The input is the sealed pipeline, its decision test,
and channel-off bases taken from the runs or assumed. The diagnostic looks at how often the decision
test, and the whole pipeline, reject under shifts put in by the simulation, by direction and size. It
shows whether a pass of a power gate computed on another statistic agrees with the test that decides,
and at which shifts it does not (§4.2). It says nothing about bases or directions not simulated, or
about an effect in the data. Power computed after the data cannot interpret a non-significant result
[44], and NLP evaluations often lack the power their conclusions assume [35]. Which significance test
suits a comparison depends on its evaluation measure and setup [48], so the power that matters is the
power of the test actually chosen. A simulation study, in which the data-generating mechanism sets the
truth, is the standard way to measure such operating characteristics [49]. One in which every shift
is put in by design does not read a power figure after the data, and it measures the power the
decision actually has.

**Report support beside entropy, for each condition.** The input is the parsed draws of each
condition. The diagnostic looks at how many categories the draws occupy in each condition, and in the
base the power calculation uses, beside the per-context entropy the floor reads. It shows whether a
floor that is cleared still leaves categories empty, as in the completed run and the control arm, or
fails while every cell reaches several categories, as in the primary arm (§5). It does not show
whether an empty category belongs to the model or to the apparatus; that takes a varied read-out
(§8.3). Chi-square-type statistics are highly sensitive to small cells [43], which is why the
support matters to the power calculation.

**Compare the rate of dropped outputs between conditions, and read their content.** The input is
every draw the estimand drops, with its raw response. The diagnostic looks at the dropped count in
each condition, and at the content of each dropped output as the parser's own steps classify it. It
shows whether dropping and renormalising removes a difference between the conditions, and what the
dropped outputs are (§6). Dropping them is a complete-case analysis, which can be biased when the
dropped units differ from those kept [50]. The diagnostic does not show a cause. When the conditions
run in a fixed order, a difference between them is also a difference in position in the run. Randomising or counterbalancing
the order separates the two only under assumptions about drift and about dependence between
successive draws. Language-model output depends on the format of the prompt and on required output
formats [45, 47], which is what makes the content worth reading.

### 7.2 Related work

Fixing an equivalence bound before analysis is standard practice [36], and declaring a materiality
margin in advance has been applied to language-model evaluation [28]; this protocol follows that
practice. Tests of equivalence between two multinomial distributions exist [41], and estimating a
total-variation distance well from samples is a problem in its own right [29, 42]; the protocol runs
neither kind of procedure and makes no efficiency claim for its plug-in estimate. Preregistration has
been argued for experiments with AI agents [37]. Validating generative social simulations is an open
problem [38, 39], and it motivates asking whether a wired mechanism propagates. Separating instrument artefacts from real effects
in a pre-registered setting is adjacent work on a different object [27]. Language-model output moves
with the formatting of the prompt [45], with the positions and identifiers of listed options [46],
and with required output formats [47]. The apparatus fixes its template, the order in which the
template lists the zones, and its JSON schema, and varies none of them.

---

## 8. Limitations

### 8.1 Model family and think regime move together

The two arms differ in model family and, unavoidably, in think regime. Within the available memory
budget no model of another family at this scale has a native thinking regime. The design therefore attributes
nothing to either factor alone, and no result under §E licenses an attribution to one of them. This
confound was declared in advance and is carried as a limitation.

### 8.2 Condition is confounded with execution order

In all three runs the contexts were run in sorted order, and within each context the 300 channel-on
draws were requested before the 300 channel-off draws. The order is fixed by the upstream apparatus:
the loop at lines 276–284 of `src/erre_sandbox/integration/embodied/bank.py`, with the condition
order `("on", "off")` at line 118, at commit `4e45adb33d7472d2adf6da29a800bde9b8f58f9e` of the
upstream repository, the commit the prospective driver was run at. Its working tree was not clean
(§I.5); the file is unchanged there since before the completed run. Any difference between the conditions is therefore also a difference between
earlier and later draws of the same context: the sealed estimate, the descriptive quantities and the
held-out difference in recorded `None` alike. Elapsed time, server state or drift could produce it as
well as the channel could. The design does not separate them, and nothing in this paper assigns a
condition difference to the channel.

### 8.3 A shared collapse would not be a replication

Had the two arms agreed under R1, the agreement would not have been a replication of the channel
result. The collapse of the decision space is at least as plausibly a property of the harness -- the
prompt, the parser, the zone vocabulary, the frozen bank -- as of any model, and both arms run the
same harness on the same prompt. If the same two zones went unproduced in both, the agreement would
be evidence that the apparatus behaves consistently, not that the channel fails to propagate in two
model families.

Every claim here is bounded by one apparatus, one disabled-thinking regime, two models and one frozen
prompt run in eight pairs of blocks, with a five-way zone decision. §I gives further limitations.

---

## References

[2] Park, J. S. et al. *Generative Agents: Interactive Simulacra of Human Behavior.*
arXiv:2304.03442, 2023.

[27] Otterson, J. *Adversarial Test-Hardening for AI-Written Code: An Instrument Autopsy and a
Pre-Registered Causal Estimate of the Critic Loop.* arXiv:2607.23002, 2026.

[28] Singh, A. *Certifying Compressed Language Models: An Audit and a Statistical Toolkit.*
arXiv:2608.15046, 2026.

[29] Price, E., Tian, K., Xun, Z. and Zhu, Y. *Total Variation Distance Estimation in
Autoregressive Models.* arXiv:2607.19510, 2026.

[35] Card, D., Henderson, P., Khandelwal, U., Jia, R., Mahowald, K. and Jurafsky, D. *With Little
Power Comes Great Responsibility.* Proceedings of the 2020 Conference on Empirical Methods in
Natural Language Processing (EMNLP), pp. 9263–9274, 2020. doi:10.18653/v1/2020.emnlp-main.745

[36] Lakens, D. *Equivalence Tests: A Practical Primer for t Tests, Correlations, and
Meta-Analyses.* Social Psychological and Personality Science, 8(4), 355–362, 2017.
doi:10.1177/1948550617697177

[37] Vaccaro, M. *Preregistration for Experiments with AI Agents.* arXiv:2606.11217, 2026.

[38] Larooij, M. and Törnberg, P. *Validation is the central challenge for generative social
simulation: a critical review of LLMs in agent-based modeling.* Artificial Intelligence Review,
59(1), article 15, 2025. doi:10.1007/s10462-025-11412-6

[39] Tomašević, A., Cvetković, D., Major, S., Maletić, S., Anđelković, M., Vranić, A., Stupovski,
B., Vudragović, D., Bogojević, A. and Mitrović Dankulov, M. *Towards operational validation of
LLM-agent social simulations: a replicated study of a Reddit-like technology forum.* EPJ Data
Science, 15(1), article 72, 2026. doi:10.1140/epjds/s13688-026-00674-x

[41] Bastian, P., Dette, H. and Koletzko, L. *Testing equivalence of multinomial distributions — A
constrained bootstrap approach.* Statistics & Probability Letters, 206, article 109999, 2024.
doi:10.1016/j.spl.2023.109999

[42] Jiao, J., Han, Y. and Weissman, T. *Minimax Estimation of the L1 Distance.* IEEE Transactions
on Information Theory, 64(10), 6672–6706, 2018. doi:10.1109/TIT.2018.2846245

[43] Balakrishnan, S. and Wasserman, L. *Hypothesis testing for high-dimensional multinomials: A
selective review.* The Annals of Applied Statistics, 12(2), 727–749, 2018.
doi:10.1214/18-AOAS1155SF

[44] Hoenig, J. M. and Heisey, D. M. *The Abuse of Power: The Pervasive Fallacy of Power
Calculations for Data Analysis.* The American Statistician, 55(1), 19–24, 2001.
doi:10.1198/000313001300339897

[45] Sclar, M., Choi, Y., Tsvetkov, Y. and Suhr, A. *Quantifying Language Models' Sensitivity to
Spurious Features in Prompt Design or: How I learned to start worrying about prompt formatting.*
arXiv:2310.11324, 2023.

[46] Zheng, C., Zhou, H., Meng, F., Zhou, J. and Huang, M. *Large Language Models Are Not Robust
Multiple Choice Selectors.* arXiv:2309.03882, 2023.

[47] Tam, Z. R., Wu, C.-K., Tsai, Y.-L., Lin, C.-Y., Lee, H.-y. and Chen, Y.-N. *Let Me Speak
Freely? A Study On The Impact Of Format Restrictions On Large Language Model Performance.*
Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing: Industry
Track, pp. 1218–1236, 2024. doi:10.18653/v1/2024.emnlp-industry.91

[48] Dror, R., Baumer, G., Shlomov, S. and Reichart, R. *The Hitchhiker's Guide to Testing
Statistical Significance in Natural Language Processing.* Proceedings of the 56th Annual Meeting of
the Association for Computational Linguistics (Volume 1: Long Papers), pp. 1383–1392, 2018.
doi:10.18653/v1/P18-1128

[49] Morris, T. P., White, I. R. and Crowther, M. J. *Using simulation studies to evaluate
statistical methods.* Statistics in Medicine, 38(11), 2074–2102, 2019. doi:10.1002/sim.8086

[50] Little, R. and Rubin, D. *Statistical Analysis with Missing Data, Third Edition.* Wiley, 2019.
doi:10.1002/9781119482260

Reference numbers are permanent identifiers assigned in the author's central bibliography and are
not renumbered between manuscripts.

<!-- TMLR:APPENDIX -->

The appendices hold three kinds of material. §C to §H are the record of the sealed protocol: its
design, analysis plan, decision rules, eligibility audit, checks and seal. §A, §B and §M hold
further results: the channel study, the completed preliminary studies and pilot, and further
results of the prospective run. §I to §L hold further limitations, the reproduction path, the
AI-use disclosure and the section numbers that frozen files cite; §N discusses further related
work, and §O states ethics, funding and interests.

## A. The apparatus and the channel (completed preliminary study)

This section reports a completed preliminary study. It is not among the prospective analyses,
and no rule in §E reads it except for the one constant named in §B; §F audits that separation
quantity by quantity.

The agent moves on a discretised world. An exponential moving average over its recent moves yields
a scalar λ, and λ composes into the temperature used for the next generation. A forensic run
(`data/raw/es3-verdict-forensic.json`) established the properties of this channel. All values below
are extracted mechanically by `analysis/scripts/extract_verdict_table.py`; none are transcribed by
hand.

| Quantity | Value | What it says |
|---|---|---|
| `verdict` | `GO` | The channel is eligible to carry a downstream measurement |
| `d_loco` (the point estimate) | `0.04682681825722385` | Within-cell locomotion amplitude, normalised by headroom |
| `ci_lower` (90% percentile bootstrap) | `0.04529199663455194` | Above the pre-registered floor by a factor of 2.3 |
| `ci_upper` | `0.04681628791857268` | See the note on aggregation units below |
| `amp_floor` (pre-registered) | `0.02` | The floor `ci_lower` had to clear |
| `ablation_bit_equal` | `True` | The `loco_delta=None` path and the `gain=0` path agree exactly |
| `ablation_max_abs_diff` | `0.0` | The ablation removes the channel with no residue |
| `zone_function_d_loco` — the **zone-function positive control**, a different quantity from the point estimate above: λ is forced to be a function of the zone, and the estimator must collapse | `7.401486830834377e-17` | **The estimator can read zero.** A non-zero reading on the blind walk is therefore a measurement, not a construction |

Table: The forensic record of the channel study, as the extraction script reads it.

The point estimate and the zone-function positive control are two different fields of the same
forensic record and are reported side by side deliberately. The small value belongs to the
positive control; the point estimate is `0.0468`.

**Note on aggregation units.** The point estimate lies marginally outside its own bootstrap
interval (by `1.05e-05`). The interval is a 90% percentile bootstrap over per-walk-seed aggregates,
while the point estimate is a cell-equal-weighted median over headroom-valid cells. The two use
different aggregation units, and a median is not guaranteed to fall inside an interval constructed
this way. The extraction script emits this note automatically whenever the condition holds, so it
cannot be dropped silently.

**Two shuffle variants are reported and do not act as null controls.** The record also carries
`n_hist_history_shuffle_d_loco` = `0.047184763036048454` and `n_hist_lambda_shuffle_d_loco` =
`0.049235973743896363`. Both are *larger* than the point estimate. This is consistent with the
estimand being an amplitude rather than a statistic of temporal ordering: permuting the move
history or the λ sequence preserves the within-cell spread that the amplitude reads. These variants
therefore characterise the estimator's sensitivity; they are not controls that produce a null, and
we do not present them as such. The control that does produce a null is the zone-function positive
control above.

**A second completed preliminary study (ES-1, a structured-probe determinism measurement) measured
the upstream determinism property of the same apparatus.** Its machine-readable
verdict record was not retained as a shipped artefact and is therefore not included in this
repository. Because this manuscript quotes only numbers that the extraction script can produce from
shipped data, no ES-1 quantity is quoted here. This is recorded as a provenance limitation
(§I.4).

---

## B. Completed preliminary studies and pilot data

Everything in this section is completed work. It is reported here because the protocol of §C-§E
is unreadable without it: §2.2 is the measurement the prospective arms repeat, §B.1 is the power
worksheet the sampling plan rests on, and §B.2 is the feasibility evidence that the second arm can
be run at all. None of it is re-analysed as part of the prospective plan, and §F states, per
planned analysis, what that separation does and does not buy.

The record of the completed run of §2.2, as the scorer wrote it:

| Quantity | Value |
|---|---|
| `verdict` | `NO_CHANNEL_CONFORMANCE` |
| `rho_hat` | `1.0` (8 of 8 contexts) |
| `power` | `1.0` |
| `tv_bar` | `0.038065` |
| `permutation_p_value` | `0.057986` |
| `permutation_reject` | `False` |
| `none_rate_max_observed` | `0.123333` |
| `effective_k` / `n_contexts` | `8` / `8` |
| per-context entropy `H(zone \| c)` | `0.628287` – `0.754149` bit |
| per-context TV distance | `0.010227` – `0.054712` |
| model digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |

Table: The record of the completed run, as the scorer wrote it.

The completed run of §2.2 is the study that motivates the present protocol. It was executed under the thresholds listed
in §C.4, which had already been frozen upstream before it ran; §G.2 gives the provenance and the
scope of what that provenance establishes. The completed run is therefore not the origin of those
values.

It is reported in §2.2 and §4 to §6, and it is **not** re-analysed as part of the prospective plan. One
value of this record does enter §E, and we state it rather than leave it implicit: `tv_bar =
0.038065` is the pre-declared centre of the R5 tolerance band. It enters as a fixed constant
settled before any prospective draw exists, not as data to be re-analysed, and no other quantity
of this record is read by any rule in §E.

### B.1 Power worksheet: for the surrogate, concentration is not what lowers the computed power

An a-priori calculation with the same pooled chi-square surrogate that R3 uses, reproduced by
`analysis/scripts/power_curve.py` at the frozen seed, gives:

| Base distribution | `delta_tv` | Power |
|---|---|---|
| near-uniform `[0.2, 0.2, 0.2, 0.2, 0.2]` | `0.10` | `1.0000` |
| near-uniform `[0.2, 0.2, 0.2, 0.2, 0.2]` | `0.01` | `0.1842` |
| degenerate `[0.96, 0.01, 0.01, 0.01, 0.01]` | `0.01` | `0.9533` |
| degenerate `[0.96, 0.01, 0.01, 0.01, 0.01]` | `0.10` | `1.0000` |

Table: The surrogate's power for two reference bases, at the registered shift and at a tenth of it.

The third row is the one that matters for the surrogate. For this calculation the computed power is
governed by the size of the shift being looked for, not by how concentrated the base distribution
is: a degenerate base with a collapse-scale shift still attains `0.9533`. The `0.1842` figure
belongs specifically to a **near-uniform base with `delta_tv = 0.01`**, one tenth of the declared
margin, and is quoted only in that full form. The first and fourth rows are the ones §4.1
relies on: at the registered `delta_tv` the surrogate returns `1.0000` for both bases. All four rows
are properties of the surrogate; none of them is the power of the permutation test the decision
turns on (§4.1). That concentration is not what lowers the computed power follows from the form of
the statistic, which cells with small expected counts dominate [43].

### B.2 Feasibility pilot for the second model (no verdict computed)

Before writing this protocol we ran a feasibility pilot on the second model. **The pilot computes
no verdict.** By construction it does not apply the scorer, does not form the on/off contrast, and
does not compute `rho_hat`, `power`, the permutation test, or per-context entropy. These
prohibitions are enforced by tests in the source repository rather than by policy, and the pilot's
aggregation is restricted to pooled quantities.

| Item | Result |
|---|---|
| Model | `llama3.1:8b`, digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` |
| Backend | ollama 0.32.12 |
| Peak GPU memory | 7,492 MiB of 16,311 MiB available; `ollama ps` reports 100% GPU |
| `think` handling | A request carrying `think` disabled is accepted; a request omitting it is also accepted |
| Pilot size | 96 draws (*M* = 6 × *K* = 8 × two conditions) |
| Per-draw latency, primary model | 1.7533 s (4,800 draws → 2.34 h) |
| Per-draw latency, reference model | 2.0663 s (4,800 draws → 2.76 h) |
| Projected cost of the full two-arm design (9,600 draws) | ≈ 5.09 h (the sum of the two rows above) |
| Plan parse rate | band `≥ 0.8` |
| Zone-present rate | band `≥ 0.8` |
| Disk | model 4.92 GB; projected artefacts ≈ 37 MB |

Table: The feasibility pilot for the second model.

**Parse quantities are recorded as three-level bands, not as rates.** The bands are `< 0.2`,
`[0.2, 0.8)` and `≥ 0.8`, and the band edges are deliberately not placed at `0.5`. The reason is
that rule R4 (§E) turns on a none-rate crossing `0.5`; recording an exact rate would let a reader
— and the authors — anticipate that rule's outcome. The bands are reported at the resolution that
answers the feasibility question and no finer. This resolution is not reduced later: the exact
rates are not restored anywhere in this manuscript.

No parse or zone quantity was collected for the reference model in the pilot, because that model is
the control arm of the prospective design and observing its parse behaviour would be observing a
component of R5.

---

### B.3 Simulated operating characteristics: declaration, design and every declared cell

**[Post hoc]** This subsection holds the detail of §4.2.

**What was declared, and when.** The grid, the seeds, the replicate counts and the rules for
reading the results were committed and pushed before the first full run, at the commit the tag
`autopsy-b3-declared` points at (`analysis/autopsy/grid.json` and `analysis/autopsy/DECLARATION.md`).
Every output is bound to that commit: the scripts refuse to run unless the declared files are
unchanged or a departure is recorded in `analysis/autopsy/DEVIATIONS.md`. That file holds two entries:
a generated file listed by mistake among the bound ones, and a correction to how the check read
the ledger, which had let a file cited in its prose count as waived. Neither changes a number. Every declared
cell is reported in `data/posthoc/pipeline.md`, and the tables below are rendered from the same
source. That the declaration was pushed before the run is recorded by the repository host's
timeline, not by any check.

**Design.** Five channel-off bases, each a distribution per context: the completed run's, the
control arm's, the completed run's with its two empty zones given 0.005 each, and the near-uniform
and degenerate bases of §B.1. Six directions of shift: the surrogate's own, from the largest cell to
the smallest (on the completed run's base, into an empty zone); from the largest cell to the
smallest non-empty one; to the second-largest; from the second-largest back to the largest; into the
empty zones in equal parts; and a mixture that moves in opposite directions in two halves of the
contexts. Every context is moved by the same total variation `delta_tv`, one of 0, 0.01, 0.02,
0.03, 0.04, 0.05, 0.075, 0.10 and 0.15. A direction a context cannot supply at a given size is
reported as infeasible rather than clipped. The draws with no zone are held at the counts of the run
the base comes from, so R4's condition on them does not fire anywhere in the grid. Each replicate
builds an annotation of the shipped shape, passes it to the vendored scorer with its defaults, and
applies the sealed rules R4, R3, R1, R2 to the result through the sealed evaluator; R5, which reads
the control arm, is left out. The grid comes to 117,000 scorer calls.

**Rates.** `P(R2)` is reached through a permutation reject or through `tv_bar` ≥ 0.10, and R4 or R3
can stop evaluation before either is read. Each rate is a count out of the replicates, with a
Wilson 95% interval and the label declared for it. On the degenerate base `G`, D4 and D6 are
feasible only at 0.01, and the surrogate returns 1.0 from 0.02 upward (`data/posthoc/pipeline.md`).
Outside the degenerate base, replicates stopped at R4 only in `C|D4|0.04` (1 of 1,000), `C|D4|0.05`
(3 of 1,000), `C|D4|0.075` (54 of 1,000); none stopped at R3 or ended in an evaluator exit anywhere
in the grid.

**Under the null** (`delta_tv` = 0; *compatible* means the interval contains 0.05, *conservative*
that it lies below):

| Base | P(R2) | P(test_reject) |
|---|---|---|
| completed run, channel-off per context | 195/4000 = `0.04875` [0.042499, 0.055867], compatible | 192/4000 = `0.048` [0.041798, 0.055069], compatible |
| control arm, channel-off per context | 222/4000 = `0.0555` [0.048822, 0.063031], compatible | 222/4000 = `0.0555` [0.048822, 0.063031], compatible |
| completed run, its two empty zones filled | 216/4000 = `0.054` [0.047414, 0.061442], compatible | 216/4000 = `0.054` [0.047414, 0.061442], compatible |
| near-uniform | 203/4000 = `0.05075` [0.044369, 0.057993], compatible | 203/4000 = `0.05075` [0.044369, 0.057993], compatible |
| degenerate | 0/4000 = `0.0` [0.0, 0.000959], conservative | 207/4000 = `0.05175` [0.045305, 0.059055], compatible |
| completed run, scorer seed varied per replicate | 93/2000 = `0.0465` [0.038109, 0.05663], compatible | 92/2000 = `0.046` [0.037657, 0.056084], compatible |

Table: Rates under the null, per base, with Wilson 95% intervals and the declared labels.

The sealed scorer permutes with one fixed seed, so every replicate of the grid shares one sequence of
permutations; the last row repeats the completed run's base with the scorer's seed, which also
seeds the R3 calculation, varied per replicate. On the degenerate base the branch counts under the
null are R4 4,000, R3 0, R1 0, R2 0.

Along the surrogate's own direction on the completed run's base:

| `delta_tv` | surrogate (R3) | P(R2) | P(test_reject) |
|---|---|---|---|
| `0.01` | `1.0` | 123/1000 = `0.123` [0.104074, 0.144811] | 122/1000 = `0.122` [0.103149, 0.143744] |
| `0.02` | `1.0` | 390/1000 = `0.39` [0.360245, 0.420596] | 392/1000 = `0.392` [0.36221, 0.422616] |
| `0.03` | `1.0` | 803/1000 = `0.803` [0.777209, 0.826472] | 803/1000 = `0.803` [0.777209, 0.826472] |
| `0.04` | `1.0` | 983/1000 = `0.983` [0.972944, 0.989359] | 983/1000 = `0.983` [0.972944, 0.989359] |
| `0.05` | `1.0` | 1000/1000 = `1.0` [0.996173, 1.0] | 1000/1000 = `1.0` [0.996173, 1.0] |
| `0.075` | `1.0` | 1000/1000 = `1.0` [0.996173, 1.0] | 1000/1000 = `1.0` [0.996173, 1.0] |
| `0.10` | `1.0` | 1000/1000 = `1.0` [0.996173, 1.0] | 1000/1000 = `1.0` [0.996173, 1.0] |
| `0.15` | `1.0` | 1000/1000 = `1.0` [0.996173, 1.0] | 1000/1000 = `1.0` [0.996173, 1.0] |

Table: The surrogate beside the pipeline and the test, along the surrogate's direction on the completed run's base.

The smallest declared `delta_tv` at which each rate reaches 0.8, as a point estimate and as the lower
limit of its interval, for every base and direction (D1 the surrogate's direction, D2 to the smallest
non-empty cell, D3 to the second-largest, D4 back to the largest, D5 into the empty zones, D6 the
mixture; the bases in the order of the table above, `C`, `K`, `Cs`, `U`, `G`):

| Base | Direction | P(R2): estimate / lower limit | P(test_reject): estimate / lower limit |
|---|---|---|---|
| `C` | D1 | 0.03 / 0.04 | 0.03 / 0.04 |
| `C` | D2 | 0.04 / 0.04 | 0.04 / 0.04 |
| `C` | D3 | 0.05 / 0.05 | 0.05 / 0.05 |
| `C` | D4 | 0.04 / 0.04 | 0.04 / 0.04 |
| `C` | D5 | 0.04 / 0.04 | 0.04 / 0.04 |
| `C` | D6 | 0.05 / 0.05 | 0.04 / 0.05 |
| `K` | D1 | 0.04 / 0.04 | 0.04 / 0.04 |
| `K` | D3 | 0.05 / 0.05 | 0.05 / 0.05 |
| `Cs` | D1 | 0.04 / 0.04 | 0.04 / 0.04 |
| `Cs` | D2 | 0.04 / 0.04 | 0.04 / 0.04 |
| `Cs` | D3 | 0.05 / 0.05 | 0.05 / 0.05 |
| `Cs` | D4 | 0.04 / 0.04 | 0.04 / 0.04 |
| `Cs` | D5 | 0.04 / 0.04 | 0.04 / 0.04 |
| `Cs` | D6 | 0.04 / 0.05 | 0.04 / 0.05 |
| `U` | D1 | 0.05 / 0.075 | 0.05 / 0.075 |
| `U` | D2 | 0.05 / 0.075 | 0.05 / 0.075 |
| `U` | D3 | 0.05 / 0.075 | 0.05 / 0.075 |
| `U` | D4 | 0.05 / 0.075 | 0.05 / 0.075 |
| `U` | D5 | 0.075 / 0.075 | 0.075 / 0.075 |
| `U` | D6 | 0.05 / 0.05 | 0.05 / 0.05 |
| `G` | D1 | 0.10 / 0.10 | 0.02 / 0.03 |
| `G` | D2 | 0.10 / 0.10 | 0.02 / 0.03 |
| `G` | D3 | 0.10 / 0.10 | 0.02 / 0.03 |
| `G` | D4 | not reached in the declared grid (feasible only at 0.01) / not reached in the declared grid (feasible only at 0.01) | not reached in the declared grid (feasible only at 0.01) / not reached in the declared grid (feasible only at 0.01) |
| `G` | D5 | 0.075 / 0.075 | 0.03 / 0.03 |
| `G` | D6 | not reached in the declared grid (feasible only at 0.01) / not reached in the declared grid (feasible only at 0.01) | not reached in the declared grid (feasible only at 0.01) / not reached in the declared grid (feasible only at 0.01) |

Table: The smallest declared shift at which each rate reaches 0.8, per base and direction.

Some directions are the same shift on a base: on `Cs`, D2 is D1; on `U`, D2 and D3 are D1; on `G`,
D2 and D3 are D1. Each is computed once and listed under every name. **Three smaller checks.** The empty zones of the completed run have 0 of 2,276 channel-off draws, a
one-sided 95% upper bound of `0.00131536` for each of `agora` and `chashitsu`; `chashitsu`, absent
from all 4,470 parsed draws, has a bound of `0.000669962`. These bound what these draws allow, not
what the model does. The surrogate's sweep in §4.1 does not depend on the numerical floor under
an expected count of zero: it is identical for every floor from `1e-12` to `1e-3`. It does depend on
reading the zeros as exact. With a pseudocount added to every channel-off count, the smallest
`delta_tv` in the sweep at which the surrogate clears 0.8, written as the value at the pseudocount,
is `0.001` at 0; `0.001` at 0.01; `0.002` at 0.1; `0.002` at 0.5; `0.002` at 1; `0.005` at 2, still a
small fraction of the margin in every case. And the null expectation of `tv_bar`, simulated at the
completed run's parsed counts along a path of bases from near-uniform to the completed run's, falls
at every declared point, from `0.067924` for the near-uniform base to `0.026945` at the completed
run's base. It should: to a first approximation each zone contributes to that expectation in
proportion to the square root of p(1 − p), which is largest when the base is spread evenly.
§M.3 reports `0.027813` for the permutation null of the completed run's own draws. That is the mean over all eight contexts,
not the scorer's `tv_bar`, which averages only the contexts that clear the entropy floor.

### B.4 What the record of the dropped draws does not show

**[Post hoc]** Three things about the record are easy to misread. The annotation field `resolved_from` carries the
same tag on every row and records nothing about whether a parse succeeded; the annotation has no
column that tells a rejected plan from a JSON `null`. The parser documents `None` in this field as
`stay put`; that is a statement of the parser's design, quoted as such, and not a description of
what any recorded `None` is. And the re-parse needs the completed run's per-draw records, which are
shipped in `data/completed/bank_records.jsonl` and pinned by digest in
`data/raw/cproper-manifest.json`:
`analysis/scripts/heldout_stay_check.py --self-test --cproper-records data/completed/bank_records.jsonl`
performs it, `analysis/heldout-stay/freeze.json` pins the class counts it must reproduce, and the
`compendium` workflow runs it on two operating systems. The frozen held-out script, its
specification and its own workflow were written before the records were shipped, and still say
that they are not; those bytes are frozen and are left as they are, so the frozen workflow's run
of the same self-test still reports this one check as skipped. The continuous integration of this
repository re-parses the two prospective arms as well, whose records are shipped too (results
section).

## C. Prospective design

### C.1 What this protocol estimates

The sealed protocol is written as an estimation problem rather than a hypothesis test: it
estimates, in a second model family, the magnitude of the channel's downstream effect on a five-way
categorical decision, and compares that estimate against a materiality margin fixed before any of
the data existed. We state no directional expectation about where the estimate will fall, and the
decision rules in §E are written so that every outcome category is an acceptable result.

The second arm had a second purpose, given that the completed run's channel-off draws never produce
two of the five zones (§5), and it is worth naming because it changes what the arm is for. If
the same collapse appears in a different model family running the same harness, the collapse is
more plausibly a property of the apparatus -- the prompt, the parser, the zone vocabulary -- than of
any model. If it does not appear, the completed run's numbers are specific to that model in a way
§5 could not establish on its own. Either way the second arm is informative, which is not
something we could have said of a replication attempt whose only purpose was to see the null again.

Neither of those two cases is what occurred. The sealed rules stopped at R4 in the second family,
where the scorer admitted no context and produced no estimate, so the arm reached neither side of
the disambiguation set out here, and the question remains open. What the arm did show is the second
gate at work (§5): the entropy floor fired on an arm each of whose cells produced two or more
zones.

### C.2 Arms

| Arm | Model | Role | `think` regime |
|---|---|---|---|
| **control** | `qwen3:8b` (re-run) | Absorbs the backend upgrade from ollama 0.31.1 to 0.32.12, so that a change of model family is not read together with a change of platform version | disabled, as in §2.2 |
| **primary** | `llama3.1:8b` | Cross-family replication in a natively non-thinking model | none natively; the harness's disabled-`think` request is accepted (the pilot established acceptance, not behavioural inertness) |

Table: The two prospective arms.

`llama3.1:8b` was chosen because it is the same parameter scale as the reference model. A larger
model would move scale at the same time as family.

**The control arm is a comparison of statistics inside a declared band, not a bitwise comparison.**
Language-model draws do not reproduce exactly when regenerated. The bitwise agreement reported
elsewhere in this line of work is a property of replaying recorded outputs, not of regenerating
them, and it plays no part here.

### C.3 Sampling plan

Both arms use *M* = 300 draws per condition and the same frozen bank of *K* = 8 contexts
(`cproper-ctx-0` … `cproper-ctx-7`) with the same per-context λ, giving 4,800 model calls per arm
and 9,600 in total. The read-out is the pre-bias destination (`pre_bias_destination_zone`): the
environment pins `ERRE_ZONE_BIAS_P = 0.2`, but no bias has been applied at the point at which the
zone is read, so the estimand is unaffected by it. The random seed is `20260708`. The apparatus
that performs the run is used unmodified; the arm driver lives outside the sealed measurement
package.

### C.4 Thresholds — unchanged from the completed run

```
alpha            = 0.05
delta_tv_min     = 0.10
h_min_bits       = 0.5
k_contexts       = 8
k_min            = 8
m_draws          = 300
m_min            = 300
none_rate_max    = 0.5
power_min        = 0.8
rho_min          = 0.5
seed             = 20260708
```

None of these values is changed for this study, and none is added to. Their freeze provenance is
in §G.2 and is checked mechanically by `analysis/scripts/verify_threshold_freeze.py`.

---

## D. Analysis plan

The prospective analysis plan contains two kinds of analysis, and **both are part of the plan.**
The labels below are roles, not a partition of the plan into included and excluded parts.

### D.1 Role A — primary estimand

Estimate `tv_bar` in the primary arm as defined in §2.3, and evaluate the decision function of
§2.3 against §C.4 and the rules in §E.

### D.2 Role B — planned quality-control and positive-control analyses

Three checks are planned, evaluated on prospectively collected draws, and consequential: each one
can change what may be concluded. They are part of the analysis plan and are not set aside.

| Check | What it protects | Declared pass criterion (fixed in advance) | Known at seal time? | Reported after the run |
|---|---|---|---|---|
| **R5** — control-arm concordance | That a change in backend version between the completed run and this one is not read as a family effect | The control arm reproduces the five quantities of §B within the band given in §E | **No** | All five quantities, and which fell outside the band if any did |
| **R4** — apparatus validity | That the estimand is measurable at all in the primary family (absence of a floor) | `rho_hat ≥ 0.5` and the per-cell maximum `none_rate ≤ 0.5` (§2.3) | **No** | Both quantities, against the R4 condition |
| **R3** — attained power | That the estimate is not vacated by insufficient power | `power ≥ 0.8` | **No** | The attained `power`, against `power_min` |

Table: The planned quality-control checks, with the pass criterion each declared in advance.

The consequence of each failure is fixed here and is not renegotiable after the data exist:
R5 failing stops interpretation of the primary arm; R4 failing narrows the conclusion to a
single-model scope; R3 failing yields an inconclusive-underpowered result that changes no claim.

### D.3 Role C — completed preliminary studies

§A, §B and the completed run of §2.2 are completed work. They are reported, not re-analysed. The single point of contact with
§E is the one named in §B: the completed run's `tv_bar` fixes the centre of the R5 tolerance band
as a pre-declared constant. No rule in §E re-analyses any of this material.

---

## E. Decision rules

### E.1 The six quantities the rules read

| Quantity | Read by | Role |
|---|---|---|
| `tv_bar` | R1, R2, R5 | The primary estimand; compared against the materiality margin |
| `rho_hat` | R1–R5 | Fraction of contexts whose per-context entropy of the zone distribution, pooled over both conditions with unparseable draws excluded, reaches `h_min_bits` (apparatus validity). It reads entropy, not the number of zones produced; §5 shows the two coming apart in both directions |
| `power` | R1–R3, R5 | Monte-Carlo power of a pooled one-sample chi-square goodness-of-fit test against an alternative built by moving mass from the largest to the smallest cell of the empirical channel-off distribution: the nominal sensitivity of a surrogate diagnostic. **This is not the power of the permutation test that produces `permutation_reject`**, which is the test the decision actually turns on; the two use different statistics and are not interchangeable (§4.1), and §4.2 simulates the second post hoc. At the registered `delta_tv` it is 1.0 for both bases §B.1 checks, near-uniform and degenerate, so a pass does not distinguish them; §4.1 shows its sensitivity when a cell of the base is empty |
| `permutation_reject` | R1, R2, R5 | Outcome of the permutation test at the declared α |
| `none_rate_max_observed` | R4 | The apparatus computes the fraction of draws yielding no parseable zone **per (context, condition) cell** and records the maximum across cells. No pooled figure is produced anywhere in the run output, so the maximum is the quantity R4 is evaluated on. The sealed text's word "pooled" names a quantity the run output does not contain. The scorer independently returns `INCONCLUSIVE` if any single cell exceeds `none_rate_max`, so R4's second condition partly duplicates a gate upstream of it. It caps the rate in any one cell; it does not read how the rate differs between the conditions (§6) |
| `verdict` | R5 | The categorical verdict emitted by the scorer for the control arm |

Table: The six quantities the sealed rules read.

No threshold is added by listing these: `none_rate_max` is already among the values in §C.4, and
`verdict` is categorical.

Stating this explicitly matters: a protocol that named only `tv_bar` would understate what the
decision after the run actually depends on.

### E.2 The rules as sealed

The following are **not predictions.** They are decision rules, fixed in advance, that determine
which scope of claim an estimate may be mapped onto once it is obtained. **R1, R2, R3 and R4 are
all permissible outcomes, and the authors do not predict which will occur.** The branch names are
category labels, not expectations.

**The rules below are not written here.** They are generated from `seal/decision-rules.json`, the
sealed machine-readable statement of them, by `analysis/scripts/render_decision_rules.py`, and step
12 of `repro.sh` fails if the block in this manuscript is not what that file renders to. This is
the whole of the pre-registration's mechanical content, and it is worth saying why it is arranged
this way. A protocol whose rules exist only as prose can be re-read after the data arrive, and
nothing catches it unless a third party holds the rules. There is no such third party here, so the rules are held instead by three checks that do not require one: the sealed
bytes (step 12), the generated text below (step 12), and the evaluator that applies the rules to
the recorded quantities and reports the branch it reaches (§J). None of the three establishes
*when* the rules were fixed. What they establish is that the branch reported after the run follows
from the rules as they stand here.

Before the block is read, one of its words needs a pointer. The estimand drops "unparseable" draws,
meaning every draw whose recorded destination is `None`. §6.1 shows what those draws are: in the
completed run the word is exact for all 330 of them, and in the prospective arms for all but
two of the 418, the other two being a JSON `null` and an absent destination key, which the parser
treats as an empty destination rather than an error.

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

**What an R5 pass states.** A pass states that the five quantities fall inside the declared band.
That is the whole of its content. It is not a statement about whether the backend upgrade changed
anything, and §I.1 records this limit.

## F. Eligibility: what is known at seal time, and what is not

A protocol is pre-registered only for the outcomes its authors do not already know. That is a
statement about **realised outcomes**, not about data: a completed measurement may be reported in
full, at any length, without any realised outcome of a planned analysis being known. The audit
below is our answer to the question a reader is entitled to ask — *which of these did you already
have?*

Three things must be kept apart when reading the R5 row. The **baseline** — the completed run of
§2.2 — is known, and is reported here in full. The **declared pass criterion** — the band in §E —
is fixed in advance, which is what an outcome-neutral check requires. The **realised outcome** —
whether the control re-run under ollama 0.32.12 actually lands inside that band — is not known at
seal time, because R5 exists precisely to detect a version drift whose presence or absence has not
been observed. The same three-way distinction applies to R4 and R3.

The table is written in two tenses on purpose. The third column is a fact about the **sealed
state**, and it does not stop being true when the run completes. The fourth says what is reported
**after** the run, whichever way each analysis falls. A table with a single "not yet known" column
would contradict itself the moment the arms were executed; this one does not have to be rewritten
to stay honest.

| Planned analysis | Role | Realised outcome known at seal time? | Reported after the run |
|---|---|---|---|
| `tv_bar` in `llama3.1:8b` | A — primary estimand | **No.** At the moment of sealing, not one draw had been collected from this model under the measurement | The estimate, and the branch of §E it selects |
| Permutation test in `llama3.1:8b` | A — decision function | **No.** As above | `permutation_p_value` and `permutation_reject`, and their effect on the branch |
| Control-arm concordance on five quantities (R5) | B — planned QC | **No** — baseline known, band declared, **realised unknown**: whether version drift has occurred has not been observed | All five quantities, and which of them fell outside the band if any did |
| `rho_hat` and the per-cell maximum `none_rate` (R4) | B — planned QC | **No.** The Phase 0 pilot observed pooled parse and zone bands, which are adjacent information, not the R4 outcome (§B.2) | Both quantities, against the R4 condition |
| Attained-power check (R3) | B — planned QC | **No.** No value of `power` exists for the primary family | The attained `power`, against `power_min` |
| Re-analysis of the completed run | **Not performed** | (baseline known) | Nothing: it is excluded from the planned analyses and stays excluded |

Table: What was known at seal time, analysis by analysis.

The last row is a statement about the plan, and it stays true of the plan. Re-analyses of the
completed run are reported outside the plan, as the post hoc layer of §2.4 (§4.1, §5 and §6.1).

---

## G. Outcome-neutral checks and the provenance of the thresholds

### G.1 Outcome-neutral checks

An outcome-neutral check is one whose pass criterion is **settled in advance by construction**, so
that writing the criterion down cannot reveal anything about the result. That is why stating those
criteria in §D.2 does not compromise the eligibility position of §F: declaring what would count as
a pass is not the same as knowing what will be observed. A positive control is one way to obtain
such a check, and this design has one; it is not the only way, and not every outcome-neutral check
here is of that kind.

The outcome-neutral checks in this design are R5, R4 and R3, and, from the completed work, the
zone-function positive control of §A, which shows that the upstream estimator can return zero, and
the ablation identity, which shows that removing the channel removes it without residue.

### G.2 The thresholds were frozen before the completed run, and this is checkable

A reader is entitled to ask whether the materiality margin of `0.10` was chosen after seeing
`tv_bar = 0.038065`. The threshold constants live in two modules of the source repository, both of
which are shipped inside this repository under `analysis/apparatus/`, and both of which are public
and dated upstream.

| Shipped file | Upstream commit that froze it | Commit time (UTC) |
|---|---|---|
| `…/integration/embodied/bank_power.py` (eight constants, including `delta_tv_min`) | `2efe407cf7afd60e43f0a525a11a1739a8ca8d24` — the only commit ever to touch this file | 2026-07-07T17:08:49Z |
| `…/integration/embodied/bank_scorer.py` (`none_rate_max`) | `580b8aa8c884a35a761ed744b9f5a5f834a38137` | 2026-07-10T09:25:18Z |
| run artefact `verdict.json` of the completed study | `6cbffcb3191059d3c72bd4bd97670ea26d6cbaa1` — the only commit ever to add this file | 2026-07-10T12:25:06Z |

Table: The upstream commits that froze the thresholds and added the completed run's record.

Both freeze commits are ancestors of the run commit. The records are at
<https://github.com/mikotomiura/ERRE-Sandbox>. `analysis/freeze-provenance.json` carries the
commit identifiers, the blob identifiers and the times; the URLs for following them by hand are in
`analysis/upstream-links.json`, kept separate because the provenance file is sealed and a
repository URL names its owner — see §H and §J.

`analysis/scripts/verify_threshold_freeze.py` checks two things on every reproduction run:

1. of the eleven values recorded in the completed run's `verdict.json`, the **nine threshold
   constants** agree with the constants in the shipped modules (eight in `bank_power.py`, one in
   `bank_scorer.py`), and the remaining two — `k_contexts` and `m_draws`, which are run parameters
   rather than module constants — agree with the run manifest. A twelfth key appearing without a
   recorded mapping also fails the check, so a threshold cannot be added silently; and
2. the shipped modules — and the whole 69-module apparatus closure, and the four frozen inputs in
   `data/raw/` — are **byte-identical to the blobs at their upstream commits**, verified by
   recomputing the git blob identifier of each shipped file from its contents. This requires no
   network access and no git installation.

**The scope of that check, stated plainly.** What runs offline establishes that the constants
shipped here are the exact bytes of those commits. The commit *dates* are a property of the public
upstream repository and are confirmed by following the links above. The ordering claim — that the
thresholds were fixed before the run — is the conjunction of the two, and we state it as such
rather than implying that either half carries it alone. Passing `--upstream-repo` to the script
adds the second half as a machine check when a clone of the upstream repository is available.

### G.3 Claim-boundary enforcement

The claims this manuscript must not make are listed, with search patterns, in
`manuscript/CLAIM-BOUNDARY.md`. `analysis/scripts/check_claim_boundary.py` reads those patterns
from that file, requires that none of them matches this manuscript, and requires that every one of
them matches a fixture written to trip all of them. That fixture is
`manuscript/_claim_boundary_positive_control.md`; every sentence in it is deliberately false and it
exists only so that a silently broken pattern cannot report success. A pattern that stops matching
the fixture fails the run. A second fixture, `manuscript/_claim_boundary_negative_control.md`, holds
the opposite: sentences this manuscript and the seal must be able to say -- the sealed reading of R4,
the sealed note that the completed run attained power 1.0, the statements that the sealed design
did not evaluate the power of the permutation test and what its post hoc simulation reports, a
sentence that corrects an earlier reading -- and the run fails if
any pattern matches one of them. The block of §E generated from the seal is scanned with the rest of
this manuscript, so a pattern that matched a sealed sentence could never be satisfied.

---

## H. What the seal covers, and what breaks it

The two arms together require approximately 5.09 h of compute on the recorded hardware (§B.2), and
the run is executed once (§I.5 records the one restart, of a capture attempt that had produced no
verdict).

Before any prospective draw is collected, eleven files are sealed, in six groups:

| Group | Files | Why it has to be fixed |
|---|---|---|
| The rules | `seal/decision-rules.json` | The decision itself. Everything else exists to stop this changing quietly |
| The run | `seal/arm-spec.json` | Every value the list below calls a not-minor deviation |
| The protocol | `seal/protocol.md` | The part of this manuscript whose alteration would change how the result reads |
| The code that reads them | `apply_decision_rules.py`, `render_decision_rules.py`, `verify_seal.py`, `check_seal_scope.py`, `_provenance.py` | A checker that can be edited is not a check. The last of these supplies the hashing the others use, and the seal also fails if a sealed script imports a local module that is not itself sealed |
| The code that reaches outside | `collect_zenodo_witness.py` | The only script here that touches the network. It reads an archive's public record and writes down the checksums and server-assigned times it finds, which is the one input to these checks that does not come from the author. A collector editable after the deposit could be taught to write down whatever made the comparison agree |
| The record and the command | `analysis/freeze-provenance.json`, `repro.sh` | The provenance of the frozen thresholds, and the fourteen steps that check all of the above |

Table: The eleven sealed files, in six groups.

`seal/SEAL-MANIFEST.json` records the SHA-256 of each and a self-hash over itself under a stated
canonicalisation, and step 12 of `repro.sh` fails if any of them has moved since (§J). What that
buys is narrow and worth naming exactly: the branch reported after the run can be re-derived, by
anyone, from the rules as they stood before it. It does not establish that the seal is old, and no
check that lives inside this repository could. That would take a copy held by somebody else. One
now exists, at `10.5281/zenodo.22735436`; §J describes the step that compares these files against
it, together with the reason that comparison, even when it passes, bounds less than it appears to.

The following are **not** minor deviations:

- substituting a different model for `llama3.1:8b`;
- changing the backend version;
- changing any of the threshold values in §C.4;
- changing the seed `20260708`;
- changing *M* or *K*;
- substituting the frozen context bank.

Each of the six is recorded as a field in `seal/arm-spec.json` and compared against the run
manifest by `analysis/scripts/verify_seal.py`, so the list is checked rather than promised.

**If any of them occurs, the seal is broken, and we say so rather than repair the wording.** No third
party here rules on deviations, and we do not put an assurance in the place of that authority. The
rule is a forfeit: should any of the six become necessary, it is reported as a deviation with the
results, and **that run is not presented as pre-registered.** Making the
claim again would require a fresh seal and a fresh run. This is a condition under which the
pre-registration lapses — not a licence to change the rules and carry on.

---

## I. Further limitations

### I.1 What the control arm establishes

R5 compares five statistics against a declared band. A pass is a statement about band membership
and carries nothing further about the backend upgrade. If R5 fails, we report the control mismatch
and stop; the primary arm is not interpreted, and this manuscript does not speculate about what it
might have shown.

### I.2 Sample access rather than logit access

The backend used here does not expose token-level logits, so the five-way decision distribution is
estimated from sampled generations. For the total-variation distance between two autoregressive
models, logit access lowers the number of queries an estimate needs, compared with sampling [29];
how much it would lower the cost of this decision-level distance is not examined here. This is a
constraint of the deployment, and it sets the cost of the design.

### I.3 Bounded envelope

Every claim is bounded by a single apparatus, a single disabled-`think` regime, one frozen prompt
run in eight pairs of blocks (the frozen bank of eight contexts, §2.2), and a five-way zone decision. The subject is the channel described in §2.1. Nothing
here is a statement about human ambulation, about creative production, or about whether embodiment
matters in general.

### I.4 Provenance gaps we are carrying

The ES-1 verdict record is not shipped (§A). The per-draw record of the completed run is shipped byte for byte in
`data/completed/`, checked by step 3 against its size and digest in `data/data.md` and against the digest the run's own manifest
pinned, and re-parsed as §6.1 describes.

One further gap concerns the ES-3 forensic record of §A. Its bytes are verifiably identical to the
blob registered upstream, but the upstream commit that carries it is a **relocation** commit: the
record was produced in June 2026 in a directory that was outside version control, and entered the
repository in September 2026 when it was moved, byte for byte, into a tracked path. Version history
therefore witnesses the record's *content*, not its *age*. The three records of the completed run
in §2.2 do not have this gap — their upstream commit is the run itself. This asymmetry is recorded
in `analysis/freeze-provenance.json` and is printed by the verification script rather than left to
the reader to discover.

All three gaps are stated rather than worked around.

### I.5 What the checks reach on the prospective arms, and what they do not

The reproduction script evaluates the sealed rules against the two landed verdicts, and step 5 also
recomputes both verdicts from the arms' per-draw annotations and manifests
in `data/prospective/`, exactly as it does for the completed run, and requires them to agree with
the landed files field by field. Whether the landed verdicts follow from the annotations shipped
beside them is therefore checked, not recorded. That the annotations agree with the raw per-draw
records they were read from is the held-out workflow's check, which recomputes its own result from
both on two operating systems. Three further things about the prospective arms are recorded by us
rather than checked by this repository: the dates; that each bundle passed seal verification
before its verdict was landed; and that each arm produced one complete run. The last needs a
qualification. The control arm's first capture attempt was stopped from outside before it had
produced a verdict, and the arm was restarted from the beginning. The driver's append-only attempt
logs are shipped under `data/attempts/`: the control arm's log records two starts and one
completed capture, and the primary arm's log records one start and one completed capture. The
stopped attempt's partial record is shipped beside the control log, byte for byte as committed
upstream at `d8ee75348bf92c81b19a9134b645e7f6988d0fa8` (that this is how the driver left it is
recorded, not checked); it holds 41 complete per-call lines (call indices 1 to 41) followed by 594 NUL bytes and
no final newline. Step 9 counts the events in both logs and the lines of the partial record from
the shipped files, and requires each capture event to report the full 4,800 calls. Every start
event in both logs records the driver file's SHA-256, which equals that of
`scripts/paper02_run_arms.py` at upstream commit `4e45adb33d7472d2adf6da29a800bde9b8f58f9e`, and
also records that the upstream working tree was not clean (`git_dirty`); what else differed from
that commit is not recorded, and this repository does not check it. What the files cannot show is that no
other attempt was made and discarded, which is why the complete-run count stays on the recorded
side. Step 3 establishes only that each landed verdict is a document distinct from
every frozen input, and its own output says so rather than leaving the stronger reading available.

Two further limits are worth naming exactly, because both were found in review rather than by a
check that failed. Step 13 reads only the predicates of the rules it reaches — five quantities from
the control arm and two from the primary arm — so a quantity being quoted correctly and a quantity
participating in the reported branch are different facts. And step 9 tests occurrence rather than
uniqueness: six quantities quoted from the landed verdicts are compared against them, but `rho_hat`
and `effective_k` are not among the six, because their literals are `1.0`, `0.0` and `8` and a
check for those would pass against prose that never mentioned the quantity at all. Adding them
would have produced a line of output and no coverage.

Those two are held a different way, and it is worth saying exactly how far it goes. Step 9
re-derives each arm's `effective_k` and `rho_hat` from that arm's own per-context entropies against
that arm's own `h_min_bits`, so "every context clears that floor" and "`effective_k` = 0 of 8" fail
if the recorded summary stops following from the map it summarises. It evaluates R4's sealed
predicates — read from `seal/decision-rules.json`, not restated in the checker — against all three
records, so the reading above fails if any of them comes to stand differently. And it requires the
zones of probability zero to be *named* in this manuscript, because `agora` and `chashitsu` are
distinctive enough for an occurrence test while "two of five" is not. Twelve mutations and one
positive control are run against copies of the real records on every reproduction, three of them
against the sealed rule itself, so a checker that had quietly stopped reading the seal would be
reported rather than pass. The rows of the tables in §5 and §6.2 are held by the rendered
comparison described in §J.

One thing is still outside all of it: the prose in §B.2, the timings and digests of the pilot,
exists in no shipped record at all, as §4 of `manuscript/CLAIM-BOUNDARY.md` states.

### I.6 What the post hoc simulation adds to the reading of R3

Two consequences follow for what a pass of R3 can be read as. At the registered `delta_tv`, the
surrogate returns `1.0000` for both bases §B.1 checks, near-uniform and degenerate, so a pass does
not distinguish a collapsed base from a spread one; only those two bases were checked, and nothing
here says what the surrogate returns for bases in general. And against the completed run's
channel-off base, whose empty cells §5 describes, it clears its `0.8` threshold at effect sizes
two orders of magnitude below the declared margin. R3 is retained as a planned check, and its
failure would still be consequential, but a **pass** of R3 is not read here as evidence about the
power of the decision the design makes. We state that rather than let the word "power" carry a
weight the number cannot bear.

**[Post hoc]** What the simulation of §4.2 adds holds for the bases and directions it declared and
for no others. On the completed run's channel-off base the test's simulated rejection rate is 1.0 at
the registered `delta_tv` in every feasible direction, so there a pass of the gate and the test
agree; along the surrogate's direction they agree down to half the margin and not below it. At a
tenth of the margin the surrogate still returns 1.0 where the test rejects in the proportion §B.3
tabulates, and on the degenerate base the pipeline stops at R4 in replicates where the test alone
rejects. None of this changes how a pass of R3 is read here: a
figure that agrees with the test at one effect size and not at others does not measure it. And the
simulation is a property of the design under assumed distributions; it does not bear on the
completed run's estimate (§2.3, and [44] on why a power figure cannot interpret a non-significant
result).

### I.7 What would distinguish a shared collapse from a replication

The prospective design does not resolve this, and no rule in §E attributes the agreement either
way. We name it in advance so that an R1 outcome is not read as more than it is. Distinguishing the
two would need the read-out varied -- a different zone vocabulary, a different parser, a different
bank -- which is outside this protocol and is not a change we may make to it (§H).

## J. Data, code and reproducibility

**Everything this manuscript refers to is reachable from one place.** The repository is
<https://github.com/mikotomiura/collapsed-decision-space>. Work continues on its default branch, so
a path named below is in general a moving target — with one exception, and it is the exception that
carries the pre-registration. The files listed in §H are sealed by content: `seal/SEAL-MANIFEST.json`
records their SHA-256 and a self-hash over itself, and step 12 below fails if the checkout in front
of you does not hold exactly those bytes. **The pin is a hash, not a branch name and not a tag.**

The upstream source repository the apparatus and the provenance records come from is
<https://github.com/mikotomiura/ERRE-Sandbox>, and §G.2 gives the commit identifiers within it.
Apart from the archival deposit of the sealed files described in §J, there is no separate
supplementary archive: the data, the analysis scripts, the apparatus and the reproduction command
are all in the repository named here.

**The submission PDF is derived, not maintained.** The PDF is built from
this manuscript by `analysis/scripts/make_pdf_source.py` with pandoc 3.5 and the official TMLR style
(vendored in `manuscript/tmlr/` and pinned there by SHA-256); there is no second manuscript. Its
three figures are drawn by `analysis/scripts/make_figures.py` from the shipped data, and
`make_figures.py --check` requires every number a figure sets to match that data. The finished PDF
is then read back: `check_pdf_text.py` requires the headings, the quantities, the characters at risk
of silent loss, the page on which the references begin and each figure's numbers row by row,
`check_claim_boundary.py` runs on its text, and for the anonymous build `check_pdf_identity.py`
requires that nothing in the file identifies the author. The manual `submission-pdf` workflow
performs all of it. The anonymous build takes its manuscript from a copy of this repository
de-identified by `analysis/scripts/make_anonymous_bundle.py`, which reports what identifying strings
it cannot remove and why; that copy is an intermediate of the build and is not submitted.

This repository contains the frozen inputs of the completed studies (`data/raw/`, each pinned by
SHA-256 and size in `data/data.md`), the analysis scripts (`analysis/scripts/`), and the measurement
apparatus as an import closure of 69 modules (`analysis/apparatus/`) reproduced byte-for-byte from
the upstream source repository. That closure covers the scoring and power machinery, which is what
the analyses in this repository exercise; it does not include the live driver that produced the
draws, since regenerating draws is out of scope here (§C.3). That driver is in the
upstream repository as `scripts/paper02_run_arms.py` at commit
`4e45adb33d7472d2adf6da29a800bde9b8f58f9e`, the commit it was run at (with a working tree that
was not clean, §I.5), and the call order it inherits
from the apparatus is described in §8.2. Neither is checked by anything in this repository.

`bash repro.sh` performs fourteen steps, in order: environment installation from the lockfile; a
lint check; verification of the frozen inputs against both `data/data.md` and their upstream blobs;
verification of the threshold freeze and of the whole apparatus closure; **recomputation of the
completed run's verdict and of the two prospective verdicts from the shipped annotations and
manifests**; mechanical extraction of the
quantities quoted in §A and §B; regeneration of the power table of §B.1; derivation of the
support of the decision space and of the permutation-null mean reported in §M.3; a character-level
comparison of the numbers quoted in this manuscript against the frozen inputs they come from; the
claim-boundary check of §G.3; a mutation sweep that measures what the seal and the decision rules
actually catch; verification of the seal itself, which includes requiring that the rule text in §E
and in `seal/protocol.md` be **generated from** the sealed rules rather than restated alongside
them; the evaluator of §E applied to the recorded quantities; and, last, a comparison of the
sealed files against a recorded copy of the per-file checksums an archive publishes for them. It
exits non-zero if any step fails, and its closing line names any step that was skipped rather than
reporting a count of steps that passed.

The fourteen steps include no test suite and no `pytest` run: this repository has none, and its
checks run as the steps themselves and, for the held-out test, as the `heldout-stay` workflow. The
sealed `repro.sh` names step 8, and the script and output file it calls, with the word "floor"
(`collapse_and_floor`). Those names are sealed bytes and stay as they are. The quantity the step
computes is the permutation-null mean of §M.3, a reference value for the observed statistic rather
than a floor under it.

The post hoc simulation of §4.2 is outside the fourteen steps, because `repro.sh` is sealed and a
step cannot be added to it. Its code, grid and declaration are in `analysis/autopsy/` and its
outputs in `data/posthoc/`. The `autopsy` workflow runs on two operating systems on every change:
it checks that the declared files are those of the tagged declaration, runs the fidelity
self-tests, recomputes the side analyses and the summaries and requires them to equal the committed
files, recomputes the first replicate of every cell and requires it to equal the committed record
byte for byte, and compares the two systems' outputs. The `autopsy-full` workflow recomputes the
whole grid, split into sixteen shards on each system, and requires both results to equal the
committed record; it runs when the simulation or its inputs change. The numbers §4.2 and §B.3 quote are
read from that record by the character-level comparison of step 9, like the others.

The thirteenth step is the third of the three checks named in §E. Both prospective verdicts are
now in place, so it runs: it re-derives the branch from the sealed rules and compares it with the
branch this manuscript reports. Before they existed it reported that it was skipping, and why. It
was wired in from the start all the same, and the reason is the seal. `repro.sh` is itself a sealed file. Adding this step after the
arms had run would change its bytes, fail step 12, and force the seal to be rebuilt — leaving a
record of the seal being remade with the results already in hand, which is exactly the sequence the
seal exists to rule out. The step is guarded on the existence of its inputs rather than on a date,
so nothing in the sealed bytes asserts that the run has not happened; it simply starts working when
the files appear. When they do, it re-derives the branch from the sealed rules and fails if the
branch named in `manuscript/reported-branch.txt` is not the one they give.

The fourteenth step is the one that reaches outside this repository, and it was wired in before
there was anything for it to read, for the same reason and with the same guard. Steps 3 to 13
compare records inside this repository against one another; anyone with write access can change
both sides of any one of them in a single commit, which is why §H says what it says. An archive
publishes, for every file it holds, a checksum that anyone can read without an account.
`analysis/scripts/collect_zenodo_witness.py`, which is sealed, reads that listing and records it as
`seal/zenodo-witness.json`, pairing deposited files with sealed paths **by content** — each sealed
file is hashed locally and matched against the published checksums — so the correspondence between
the two sets is not something we assert. Step 14 then compares the recorded listing against the
sealed files, and is guarded on the existence of that file.

The deposit exists. The eleven sealed files, together with `seal/SEAL-MANIFEST.json`, were
deposited at `10.5281/zenodo.22735436` (concept) and `10.5281/zenodo.22735437` (this version) —
each file individually rather than inside an archive, because a checksum over an archive says
nothing about the files within it. `seal/zenodo-witness.json` records what that deposit publishes
about them: the per-file MD5 digests, the sizes, and the times the servers assigned. The latest of
those twenty-seven times is **`2026-09-13T23:44:39.000Z`**, and it is the DOI registration time;
step 14 recomputes that maximum rather than reading it, and fails if the recorded anchor is not the
one the witness's own deposit listing implies. The publication date the deposit carries is supplied
by the depositor, and the checker refuses to admit it to the anchor for that reason.

The deposit's title field carries a working title that differs from the title of this manuscript.
Its metadata is not edited, and no new version is created under the concept identifier: the deposit's last-modified
time is one of the server times the witness records, so an edit would move the anchor described above and the
collector would no longer reproduce the witness.

**What step 14 establishes is less than its name suggests.** The step is offline. It establishes two things: that the recorded witness agrees with
these bytes, and that the witness is closed against itself — its anchor is the maximum of the
server-assigned times it carries, and those times are exactly the ones its own deposit listing
implies, one created and one updated per deposited file, with no invented name and no duplicate.
It does *not* establish that the witness is what the archive returned. It cannot: a file in this
repository is a file in this repository, whatever it describes. The closure requirements above
reject a witness written from nothing -- digests computed locally in an algorithm no archive
publishes, timestamps from the year 2000, a per-file time naming a file that does not exist. They
cannot reject a witness that is closed against itself and still not what the archive returned;
that limit is what this paragraph states.

Turning a *recorded* external half into a *checked* one takes one online act, and it is the
reader's: the witness records the public URL it was read from, and re-running the collector against
that URL reproduces the file. That is deliberately not a step in `repro.sh`, which has to run with
no network and inside a de-identified copy where the identifier is removed. A reviewer who wants
the outside half performs it; a reviewer who does not still gets steps 1 to 13, which need neither
the archive nor an account nor any identifier, and which are where the binding of the reported
branch to the sealed rules actually lives.

Two further limits, stated here rather than left to be discovered. The checksums an archive
publishes per file are MD5, so agreement is agreement on that digest rather than a proof of
identical bytes. And a deposit record **remains editable by its owner for a period after
publication, with the identifier unchanged** — the archive's own documentation says so — which
means the time above bounds when that record was last touched, not when these files were written.
No timestamp of any kind can establish that no draw preceded it. The deposit is corroboration, and
it is offered as corroboration.

The eleventh step deserves a sentence, because a check that is never exercised may be vacuous. It
mutates the things the seal is supposed to protect — a threshold moved in the sealed rules, a hash
altered in the manifest with and without recomputing the manifest's self-hash, the band moved in §E
of this manuscript while every sealed byte stays put — and requires each case to fail **with a
diagnostic naming what was changed**, not merely to fail. Five control cases must not fail at all,
including an edit to this manuscript outside the generated block — a seal that forbade that would
be a seal nobody could keep — and a witness that honestly declares a missing registry timestamp
rather than supplying one. Requiring the diagnostic rather than the exit code is not fastidiousness.
While the sweep was being written every mutation was failing for one unrelated reason, and on exit
code alone the sweep reported success.

The recomputation step is the strongest of these. Every other step compares a record against a
shipped file; this one runs the scorer on each shipped per-draw annotation, at the sealed
Monte-Carlo settings, and requires the resulting verdict string, all nine gate read-outs and all
four per-context maps to agree with the recorded verdict: `data/raw/cproper-verdict.json` for the
completed run and `data/raw/control-verdict.json` and
`data/raw/primary-verdict.json` for the two arms. The completed run's record (§B), and the two verdicts step 13
reads, are therefore derivable from this repository rather than merely quoted from it. The step
also alters each compared field of a copy of each record in turn and requires the comparison to
name it, so that a comparison unable to see a difference cannot pass. It takes under two
seconds on the author's machine.

The ninth step is what turns "these numbers were not transcribed by hand" from an assurance into
a check: it reads each quantity from the frozen JSON by key and requires the resulting literal to
appear in this manuscript, and -- for the subset the repository README quotes -- in that README
too. Its scope is bounded twice over, and we state both bounds rather than let the check sound
stronger than it is. It covers only the quantities obtainable mechanically from the frozen
inputs; numbers outside that set are not covered at all. And within that set it tests
**occurrence, not uniqueness**: several of these values appear at more than one point in this
manuscript, so altering one occurrence while leaving another intact would not fail the run. A
single altered digit fails the run only for a quantity that occurs exactly once, and the check does
not determine which those are.

For quantities whose literals are too common for that -- small counts, zone counts, the rows of the
tables in §4.1, §5, §6.2 and §B.1, and the counts and class breakdown of the held-out
test -- the ninth step renders the expected row or phrase from its source (the per-draw
annotations, the verdict records, the derived artefacts, and `analysis/heldout-stay/result.json`
and `freeze.json`) and requires that exact text to occur exactly once, so that for these the test is
uniqueness and not only occurrence. On every run it also alters copies of those sources one at a time
and requires each such check to fail for the reason named, so that a rendering that had stopped
reading its source would be reported rather than pass.

What none of this reproduces is the generation of the draws themselves. Language-model draws do not
recur when regenerated, so the per-draw record is treated as a frozen input rather than as
something the script recreates.

Passing `ERRE_SANDBOX_REPO=/path/to/ERRE-Sandbox` additionally checks the upstream commit dates and
ancestry against a clone of the source repository.

The lockfile shipped at `env/uv.lock` is the lockfile recorded in the completed run's manifest: its
SHA-256 equals the `uv_lock_sha256` pinned in `data/raw/cproper-manifest.json`, and `repro.sh`
checks that equality rather than asserting it.

---

## K. AI usage disclosure

<!-- TMLR:FOOTNOTE -->
**Use of AI assistance.** This work was developed with substantial AI assistance: Claude (Anthropic) for
implementation, documentation and drafting, and OpenAI Codex for independent review. No AI system is an
author, and every AI-assisted output was reviewed and validated by the author. §K states the extent,
with commit counts a reader can recompute.
<!-- /TMLR:FOOTNOTE -->

This work was developed with substantial AI assistance, disclosed here in full.

Claude (Anthropic; the Opus 4.8, Opus 5 and Sonnet 5 models, via Claude Code) was used for
implementing the measurement apparatus and the analysis and verification scripts shipped here, for
documentation, and for drafting the text of this manuscript. OpenAI Codex (`gpt-5.5`) was used for
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
position of §F, the scope of every claim and of every limitation in §8, and the decision to seal
this protocol before collecting the prospective data. Validation is not self-reported: the numerical,
provenance and claim-boundary properties asserted in this manuscript are enforced by `repro.sh`
(§J) and re-run by public continuous integration on two operating systems, and the claim-boundary
guards are themselves checked against a fixture written to trip every one of them (§G.3), so a
guard that silently stopped working fails the run.

---

## L. Section numbers cited by files that cannot change

Some files cite a section of this manuscript by a number it no longer carries, and cannot be
edited, because the seal (§H), the freeze of the held-out test (§6.2) or the declaration
of the post hoc simulation (§4.2) binds their bytes. Each such citation is listed below with the
section it now means. `analysis/scripts/check_crossrefs.py` requires every row to match the file it
names, and fails if any other file in those groups cites a section of the manuscript.

| File | Line | Number cited | Now |
|---|---|---|---|
| `analysis/autopsy/DECLARATION.md` | 8 | 1.4 | §2.4 |
| `analysis/autopsy/grid.json` | 38 | 5.2 | §B.1 |
| `analysis/autopsy/grid.json` | 46 | 5.2 | §B.1 |
| `analysis/freeze-provenance.json` | 4 | 10.2 | §G.2 |
| `analysis/freeze-provenance.json` | 82 | 12.5 | §I.4 |
| `analysis/heldout-stay/SPEC.ja.md` | 21 | 8 | §E |
| `analysis/heldout-stay/SPEC.ja.md` | 147 | 12.1 | §8.1 |
| `analysis/heldout-stay/SPEC.ja.md` | 169 | 6.3 | §C.4 |
| `analysis/heldout-stay/freeze.json` | 133 | 12.1 | §8.1 |
| `analysis/heldout-stay/result.json` | 668 | 12.1 | §8.1 |
| `data/posthoc/pipeline.md` | 21 | 5.2 | §B.1 |
| `data/posthoc/pipeline.md` | 22 | 5.2 | §B.1 |
| `data/prospective/README.md` | 3 | 6 | §C |
| `repro.sh` | 52 | 6.3 | §C.4 |

Table: Section numbers cited by files that cannot change, with the section each now means.

## M. Further results of the prospective run

### M.1 What R4 does and does not flag at the frozen thresholds

The entropy-floor paragraph of §5 has a consequence for R4, the measurability gate of §E, which is written for the primary arm
and evaluated only there. Its two conditions are `rho_hat` < 0.5 and `none_rate_max_observed` >
0.5. Applied to the completed run and to the control arm, **neither condition is met** —
`rho_hat` is 1.0 in both, and `none_rate_max_observed` is 0.123333 and 0.086667 respectively. **At
the thresholds frozen in §C.4, a gate of this shape does not flag the regime of §5.** Two things
keep that from being true by construction. The gate is not inert: the same two conditions, at the
same thresholds, did fire on the primary arm, which is how this run reached R4 at all. And the
thresholds are what decide it rather than the shape of the rule — the completed run's per-context
entropies run from 0.628287 to 0.754149, so a floor set above 0.68 rather than at 0.5 would have put
`rho_hat` at 0.375 and fired R4 on the completed run too. What the entropy-floor paragraph of §5 says about
certification holds at any floor; what this paragraph says about flagging is a statement about these
thresholds, and §G.2 records that they were fixed before any of this was computed. Detecting the
regime of §5 took the support and permutation-null diagnostics of §5 and §M.3, which run on
every reproduction but are not gates in this protocol. The reading here is not left to the prose:
step 9 re-derives each arm's `effective_k` and `rho_hat` from its own per-context entropies,
evaluates R4's sealed predicates against all three records, and requires the zero-probability zones
to be named in this manuscript (§I.5).

### M.2 What the two arms' gate quantities do and do not compare

Two consequences of the table of zones in §5 are worth stating plainly. The question §C.1 puts — whether the narrow support of
the completed run belongs to the model or to the apparatus — is not answered in the primary family
by this run, because the quantity that would answer it was not estimable there. And the two arms
failed the gate quantities in different places: the completed `qwen3:8b` run admits all eight
contexts even though two of five zones are never produced in the channel-off condition, whereas the
primary arm has `effective_k` = 0 of 8 because none of its contexts clears `h_min_bits` = 0.5. These
are outcomes recorded of these runs under this apparatus, and they are not a comparison of how far
the decision spaces of two model families have collapsed: the two statements are about different
quantities, one the support of the read-out and the other a per-context entropy floor. What neither
licenses is reading an unmeasurable arm as agreement; §8.3 carries the reason a shared collapse
would not be a replication, and that reasoning applies with more force where there is no estimate
at all.

### M.3 The estimates the permutation test did not reject

**[Registered] Neither run that produced an estimate returned one its own permutation test
rejected.** The results of §3 should be set beside what the three runs of this measurement have
returned. In the completed run `tv_bar` = 0.038065 at a recorded `permutation_p_value` of 0.057986,
0.007986 above the α of 0.05. In the control
arm `tv_bar` = 0.030575 at a permutation *p* of 0.43989, and the test does not reject. In the
primary arm no estimate is produced at all. **Both runs that produced an estimate are `qwen3:8b`**,
so the *n* here is two runs of one model family; §8.3 gives the reason agreement across runs of
this apparatus would not establish what it appears to. It is a statement about what has been
observed, not about the power of any test — the sealed design did not evaluate the power of the
permutation test, and the post hoc simulation of §4.2 describes the design under assumed
distributions, not this run's estimate — and it changes no threshold and no decision rule. Whether the
read-out itself, the zone vocabulary, the parser and the frozen bank, is what holds the estimate
there is the question §8.3 raises, and this protocol cannot answer it: varying the read-out is a
change the seal does not permit (§H).

**[Post hoc] The permutation-null mean of the completed run's estimate.** Total variation is a
non-negative distance, so its expected value under the null is not zero. Permuting the condition
labels within each context -- the null the scorer's own permutation test uses -- 2,000 times at
seed `20260708` gives a permutation-null mean of 0.027813 and a null 95th percentile of 0.038839.
The observed 0.038065 falls 0.000774 below that percentile, which is the fact the recorded
`permutation_p_value` reports from the other side; neither margin is a comfortable distance. The
mean is a reference value against which the observed statistic is read, not a part of the
estimate that could be subtracted from it.

### M.4 The scorer's exit label, record by record

**[Registered] The scorer's exit label, read across the three records.** The scorer writes
`NO_CHANNEL_CONFORMANCE` into all three records. The label is the scorer's output and a predicate of
R5, so it cannot be renamed; what can be done is to say, record by record, what produced it:

| Record | `verdict` | What the scorer recorded when it wrote the label | On/off comparison made |
|---|---|---|---|
| completed run | `NO_CHANNEL_CONFORMANCE` | `rho_hat` = 1.0, `power` = 1.0, `tv_bar` = 0.038065, `permutation_reject` = false | yes |
| control arm | `NO_CHANNEL_CONFORMANCE` | `rho_hat` = 1.0, `power` = 1.0, `tv_bar` = 0.030575, `permutation_reject` = false | yes |
| primary arm | `NO_CHANNEL_CONFORMANCE` | `rho_hat` = 0.0 (`effective_k` = 0 of 8); no estimate formed | no |

Table: The scorer's exit label in each record, and what the scorer recorded when it wrote it.

Only the first two rows are what the label's name describes.

### M.5 The secondary six-category distance of the held-out test

**[Held-out]** A secondary six-category distance, with `None` as a sixth
category, is 0.047917 (permutation *p* = 0.061197) in the control arm and 0.030833 (*p* = 0.015049) in the
primary arm; it is reported without being judged against the margin of 0.10.

## N. Further related work and notes

### N.1 Further related work

**Standard results this paper rests on.** The power that bears on a decision is the power of the
test the decision uses; a figure computed for another statistic does not carry over, and using a
power figure computed after the data to interpret a non-significant result is a documented misuse
[44]. Card and colleagues [35] document how often conclusions in NLP rest on designs without the
power to support them. The sealed rules come close to the form that Hoenig and Heisey [44] warn
against: `power` is
computed after the draws, on the run's own channel-off distribution, though at the registered
`delta_tv` rather than at an observed effect, and clearing the power gate (`power` ≥ 0.8) is required
before R1 can be reached (§E). A Pearson goodness-of-fit statistic is highly sensitive to cells with
small expected counts, and the classical chi-square test can have poor power when many cells are
small relative to the sample size [43]. The truncated statistic discussed there bounds each cell's
denominator from below so that small cells cannot dominate it. The surrogate behind R3 is a five-cell
statistic, not a high-dimensional one, but its base has empirically empty cells, and its
implementation floors the denominators only at a small constant that avoids dividing by zero, which
leaves that sensitivity in place (§4.1). Entropy and support are different summaries of a
distribution: a distribution can clear an entropy floor while occupying few categories, or fall below
it while occupying several. Dropping a category and renormalising over the rest removes from the
comparison any difference between conditions in how often that category occurs.

**Total-variation estimation and equivalence.** Price, Tian, Xun and Zhu [29] give sample-complexity
results for estimating total-variation distance in autoregressive models. Their estimand is
sequence-level, and their access models (samples of the next token after any prefix, or its logits)
are richer than independent whole generations; ours is a decision-level five-way
categorical distance, and the gap between the two is the main efficiency cost of this design (§I.2).
Jiao, Han and Weissman [42] give minimax rates for estimating the L1 distance, twice the
total-variation distance, between two discrete distributions from samples, and show that in a
large-alphabet, non-asymptotic setting the plug-in estimate needs more samples than a rate-optimal
one. Our alphabet has five categories; `tv_bar` averages plug-in distances, and we make no claim about
its efficiency. Bastian, Dette and Koletzko [41] construct a bootstrap test of whether two
multinomial distributions are equivalent, in the sense that a norm of the difference between their
class probabilities, the L1 norm included, lies below a threshold. It is a direct test of the
question that a margin on a total-variation distance points toward, and this protocol runs neither it
nor any other equivalence test (§N.2).

**Surface sensitivity of language-model evaluation.** Sclar and colleagues [45] show that
meaning-preserving changes to prompt formatting can move a model's measured performance by large
amounts, and that performance across formats correlates only weakly between models. Zheng and
colleagues [46] show that models prefer particular option positions and identifiers when choosing
among listed options. Tam and colleagues [47] find that requiring output in a structured format such
as JSON lowers models' performance on reasoning tasks, more so the stricter the format. What the fixed
template, zone order and output schema of this apparatus contribute to the read-out is not measured
in this work.

**Preregistration, validation and adjacent audits.** Vaccaro [37] discusses preregistration for
experiments with AI agents. Larooij and Törnberg [38] argue that validation is the central challenge
for generative social simulation, and Tomašević and colleagues [39]
report a replicated operational validation of an LLM-agent social simulation. Both motivate measuring
whether a wired mechanism propagates rather than assuming that it does. Park and colleagues [2]
provide the generative-agent architecture this apparatus descends from. Singh [28] audits compressed
language models with a statistical toolkit built around equivalence testing at a declared margin:
the practice of fixing a bound in advance [36], applied to language-model evaluation, which this
protocol follows. Otterson [27] separates instrument artefacts from real
effects in a pre-registered causal setting; the separation logic is adjacent to ours, applied to a
different object.

### N.2 The margin, and why no equivalence test is run

**Where the value came from, and what is not added to it.** `delta_tv_min = 0.10` was fixed upstream,
with the other thresholds, before the completed run was executed; §G.2 gives the commits and what
checking them establishes. Fixing such a bound before analysis is established practice [36], and has
been applied to language-model evaluation [28]. No substantive justification for the value is
supplied after the fact: one written with every result in hand would be a rationalisation of a sealed
value rather than a reason for it. Each gate is read at whatever margin is registered, and no claim of
this paper uses the value.

**Relation to equivalence testing.** Where a study aims at evidence of absence, the standard
recommendation is a frequentist equivalence test [36]. **This protocol does not perform formal TOST
or Bayesian equivalence testing.** What it performs is estimation, comparison against a materiality
margin declared in advance, and a power guard. We do not call this formal evidence of equivalence, and
we do not claim that the procedure is the recommended framework under another name. The permutation
test is a nil-null test; failing to reject is not evidence of equivalence, and nothing in §E treats it
as such. No additional statistic and no additional threshold is introduced anywhere in this protocol
beyond the eleven values listed in §C.4.

## O. Ethics, funding and competing interests

This study involves no human or animal subjects. It measures the output distribution of
locally-run language models on a frozen bank of synthetic contexts, so no ethics approval is
required and none was sought.

This work received no financial support. The compute is a single desktop machine belonging to the
author, and the models are run locally; the projected cost of the full two-arm design is the 5.09 h
of that machine's time recorded in §B.2.

The author declares no competing interests.

---

The abstract at the head of this document and the `abstract` field of `CITATION.cff` are required
to be the same text; `analysis/scripts/check_claim_boundary.py` compares them on every
reproduction run, so the manuscript and the repository metadata cannot drift apart silently.
