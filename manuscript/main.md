# Three gates, three proxies: an instrument autopsy of a sealed LLM-agent evaluation

**A sealed, pre-registered evaluation, its outcome reported against the sealed rules, and an autopsy of the gates that decided what that outcome is worth. Every analysis outside the sealed rules is labelled by when it was fixed (§1.4).**
No prospective draw existed when the decision rules were sealed. They are sealed in machine-readable
form, so that the branch reported afterwards can be re-derived from the rules as they stood before
it (§13).

| | |
|---|---|
| Author | Mikoto Miura |
| ORCID | [0009-0000-4196-0508](https://orcid.org/0009-0000-4196-0508) |
| Affiliation | Independent Researcher |
| Correspondence | via the submission system of the venue this manuscript is submitted to |
| Code and data | <https://github.com/mikotomiura/collapsed-decision-space>. Development continues on the default branch; what pins the protocol against later change is the seal of §11 and §13, not a branch name |
| Licence | Code: Apache-2.0 OR MIT. Manuscript and figures: CC BY 4.0 |
| Protocol status | The protocol was sealed before any prospective draw was collected. Each arm then produced one complete run, on 2026-09-14 and 2026-09-15; the control arm's first capture attempt was stopped from outside before it produced a verdict, and that arm was restarted from the beginning (§12.8). The two verdicts reach branch R4, reported in the results section. A held-out test of a post hoc observation was run afterwards, outside the seal (§1.4). §11 states what the seal covers and what breaks it |

---

## Abstract

A pre-registered evaluation that may end in a null has to fix in advance what a null would be
worth. We report an instrument autopsy of one that did: a sealed evaluation of whether an
agent-internal channel, a scalar from a language-model agent's recent movement composed into its
sampling temperature, shifts a five-way zone decision beyond a declared margin. Sealed after a
completed run on one model and applied to two prospective arms, its rules stop at R4, apparatus
validity. The three gates that decide what a null report is worth each ran as written, passing or
firing by its own rule, and each read a quantity other than the one its reading depends on. The
power gate reads a pooled chi-square surrogate, not the stratified permutation test the decision
turns on, whose power is evaluated nowhere: at the registered effect size the surrogate returns 1.0
for a near-uniform and a degenerate base alike, and 0.921 at one hundredth of the margin against an
empirical base with two empty zones. The entropy floor reads per-context entropy, not support: two
runs of one model clear it everywhere while their channel-off draws never produce two of the five
zones, and the second model fails it although each of its cells produced two or more zones. The cap
on draws with no zone, which the estimand drops, reads the largest per-cell rate, not the difference
between conditions: all three runs pass it, but a held-out test of a post hoc observation, specified
before the condition-wise counts were tabulated, found more such draws in the channel-on blocks of
both arms (156 against 94; 107 against 61). Those draws were mostly the string "null" in one
model's arm and missing or malformed JSON in the other's, and each context ran its channel-on block
first, so the difference is confounded with execution order. The prospective arms and the held-out
test did not resolve this; they exposed it. The claim concerns the instrument, not the channel, does
not depend on the margin's value, and is confined to two models and eight frozen contexts.

---

## 1. Introduction

A null report needs more than an estimate below a margin fixed in advance. The design must have
been able to detect a shift of that size had one been there, the read-out must vary enough to
register such a shift, and the draws that are scored must stand for what was produced in each
condition. A sealed protocol writes each of these down as a gate with a threshold before the data
exist, so that whether a null may be reported is settled by rule rather than after the fact. The
evaluation reported here was built that way, and this manuscript is about what its gates actually
read.

The evaluation asks whether an agent-internal channel moves a language-model agent's choice among
five zones (§1.1, §4). Its estimand, thresholds and decision rules were sealed after a completed
run of the same measurement on `qwen3:8b` (§5.1) and before any prospective draw existed (§8,
§11). Applied to a control arm on the same model and a primary arm on `llama3.1:8b`, the sealed
rules stop at R4, apparatus validity; the primary arm yields no estimate.

**Our central claim is about the instrument, not the channel.** Three gates decide what a null
report from this apparatus is worth: R3, attained power; R4's per-context entropy floor, read
through `rho_hat`; and R4's cap on the per-cell rate of draws that yield no zone, which the
estimand drops as unparseable. Each ran as written -- it passed, or it fired by its own rule --
and each read a quantity other than the one the reading of its result depends on. The prospective
arms and a held-out test did not resolve this; they exposed it.

| Gate | What it reads | What the reading of its result depends on | What the runs show |
|---|---|---|---|
| **R3**, attained power | Monte-Carlo power of a pooled one-sample Pearson chi-square goodness-of-fit test, against an alternative that moves mass from the largest to the smallest cell of the pooled channel-off base, at `delta_tv` = 0.10 | The power of the stratified permutation test that produces `permutation_reject`, the test the decision turns on | `power` = 1.0 in the completed run and the control arm; none is produced in the primary arm. At `delta_tv` = 0.10 the surrogate returns `1.0000` for both bases checked, near-uniform and degenerate (§5.2), so a pass does not tell them apart; against the completed run's channel-off base it returns `0.921` at one hundredth of the margin (§5.1.1). The power of the permutation test is evaluated nowhere (§12.6) |
| **R4**, entropy floor (`rho_hat`) | Per-context entropy of the five-zone distribution pooled over both conditions, draws with no zone excluded, against `h_min_bits` = 0.5; `rho_hat` is the fraction of contexts that clear it | How many zones the draws occupy, and in particular the support of the channel-off base the power calculation uses (R4's sealed reading speaks of "two or more zones") | Completed run and control arm: `rho_hat` = 1.0 in both, while `agora` and `chashitsu` never appear in either channel-off base. Primary arm: the rule fired, `rho_hat` = 0.0 with per-context entropies from 0.165654 to 0.274008, although each of its 16 (context, condition) cells produced between two and four zones |
| **R4**, cap on draws with no zone (`none_rate_max_observed`) | The largest rate, over the 16 (context, condition) cells, of draws that yield no zone, against `none_rate_max` = 0.5 | How the share of draws the estimand drops differs between the channel-on and channel-off execution blocks | All three runs pass (`0.123333`, `0.086667`, `0.066667`). The channel-on blocks hold more such draws: 206 against 124 in the completed run, where the observation arose; under the held-out test, 156 against 94 in the control arm and 107 against 61 in the primary arm |

The last column needs two notes of scope. R3 and R4 are written for the primary arm, and
evaluation stopped at R4 there, so R3 was not reached on that arm. The scorer computes the same
quantities against the same thresholds on every run, and step 9 of `repro.sh` evaluates R4's
sealed predicates against all three records (§12.8); that is what the column reports, and none of
it is a further branch. And R4's sealed reading, that in the primary family "the substrate does not
license two or more zones", does not match that arm's data literally: the rule fired on
`rho_hat`, which the entropy floor defines, while every cell of the arm produced two or more zones.
The generated block of §8 is left as sealed, the results section notes the discrepancy beside it,
and neither the firing nor the branch is affected.

**How the runs exposed the three rows.** The second arm was meant to settle whether the narrow
support of the completed run belonged to the model or to the apparatus (§1.2). It stopped before
that question, at the entropy floor, and the stop is itself an instance of the second row. The
control arm, on the model of the completed run, cleared the same floor in every context with the
same two zones absent from its channel-off base. The third row came from examining what the
estimand drops. In the completed run all 330 dropped draws are the string `"null"`: the prompt
template writes `null` inside the quotation marks of the destination field, so a response that
follows the template names no zone the plan schema accepts, and the whole plan is rejected
(§5.1.2). The estimand's word "unparseable" is therefore exact for those draws, and for all but
two of the draws dropped in the prospective arms; the other two are a JSON `null` and an absent
destination key, which the parser treats as an empty destination rather than an error. The sealed
protocol considered treating these draws as a sixth category, rejected it, and made their rate the
quantity R4 reads (`seal/protocol.md` §1). What the cap does not read is whether that rate differs
between conditions. In the completed run it did, and we tested that post hoc observation on the two
prospective arms: it recurred in both (row A of the held-out test's frozen interpretation table;
results section).

**What recurred, and what it does not show.** What recurred is an operational outcome, a recorded
None. In the control arm it is mostly an explicit `"null"`; in the primary arm it is mostly
missing or malformed JSON, and the frozen qualifier that would let us say that more outputs wrote
null as the destination holds for the control arm and not for the primary arm. This is not a
cross-family replication of the same behavioural meaning or of the same parser-failure mechanism.
Nor is the difference separated from the order of execution: in all three runs every context was
run as 300 channel-on draws followed by 300 channel-off draws (§12.9), so condition is confounded
with execution position -- elapsed time, server state, drift -- and this design gives no way to
assign the difference a cause. The held-out test also sits outside the seal. Its data existed
before its specification was written; the specification was frozen before the condition-wise counts
were tabulated, and the absence of any earlier tabulation is a declaration, not something a check
can show (§1.4).

**What the claim does not rest on.** The claim does not depend on the value of the 0.10 margin. No
row of the table uses it; the first row speaks of the registered effect size and neither defends
nor disputes it. The value was fixed upstream before the completed run (§10.2), and we add no
rationale for it after the fact (§4.3). Nor does the claim say anything about the channel's effect:
it concerns what three gates read, and it would stand whatever the channel does. The one condition
difference it reports is a difference between execution blocks, as above. Its scope is one
apparatus, two models and eight frozen contexts.

We did not set out to make this claim, and most of the evidence for it is not registered: it is
descriptive, post hoc or held-out, and §1.4 labels every analysis by when it was fixed. The
thresholds were fixed before any of it was computed and are not revised here, and the sealed branch
stands as the rules give it. What changes is what a pass or a firing of these gates can be taken to
show.

**An earlier reading, withdrawn.** An earlier version of this manuscript, under a different title
(§13), read the completed run as a statement about how the margin and the power gate behave when
some zones are never produced. That reading is withdrawn, with the first item of the earlier list in
§1.3. §5.1.1 gives the reasons. In brief, at the registered effect size the surrogate returns full
power on a near-uniform base as well, so the empty zones are not shown to be why the power gate
passed; and the permutation-null mean of the distance is a finite-sample reference value, not a
part of the estimate that can be subtracted from it.

### 1.1 The apparatus, and what the claims are about

The apparatus modulates decode-time sampling from an agent's recent movement history: an
exponential moving average over the agent's moves produces a scalar, and that scalar composes into
the temperature used for the next generation. The wiring question -- *is this a real causal
channel, or an artefact?* -- was answered in a completed preliminary study (§3): the channel is
causal, it is separable from the static location channel, and it vanishes bit-for-bit under
ablation, while a positive control shows that the same estimator can return zero. The propagation
question -- *does that channel move the agent's downstream discrete choices?* -- is the one the
sealed evaluation was written to measure; §1.2 records what became of it.

Wherever this manuscript speaks of an effect, its subject is **the channel**. It is not walking,
and it is not creativity. The estimand is defined over a frozen bank of contexts and a five-way
zone decision; nothing in the design licenses a statement about human ambulation or about creative
production. The central claim of §1 is not about an effect at all. It is about what three gates of
one sealed apparatus read, documented on two models and eight frozen contexts; we do not claim to
have surveyed how often gates of this kind read proxies elsewhere.

### 1.2 What this protocol estimates

The sealed protocol is written as an estimation problem rather than a hypothesis test: it
estimates, in a second model family, the magnitude of the channel's downstream effect on a five-way
categorical decision, and compares that estimate against a materiality margin fixed before any of
the data existed. We state no directional expectation about where the estimate will fall, and the
decision rules in §8 are written so that every outcome category is an acceptable result.

The second arm had a second purpose, given that the completed run's channel-off draws never produce
two of the five zones (§5.1.1), and it is worth naming because it changes what the arm is for. If
the same collapse appears in a different model family running the same harness, the collapse is
more plausibly a property of the apparatus -- the prompt, the parser, the zone vocabulary -- than of
any model. If it does not appear, the completed run's numbers are specific to that model in a way
§5.1.1 could not establish on its own. Either way the second arm is informative, which is not
something we could have said of a replication attempt whose only purpose was to see the null again.

Neither of those two cases is what occurred. The sealed rules stopped at R4 in the second family,
where the scorer admitted no context and produced no estimate, so the arm reached neither side of
the disambiguation set out here, and the question remains open. What the arm did show is the second
row of the table in §1: the entropy floor fired on an arm each of whose cells produced two or more
zones.

### 1.3 What is new here, and what is not

Most of what the table in §1 rests on is standard statistics, and we separate it out first.

**Standard, and not claimed here.** The power that bears on a decision is the power of the test
the decision uses; a figure computed for another statistic does not carry over. A Pearson
goodness-of-fit statistic is dominated by cells with small expected counts, so an alternative that
moves mass into an empty or nearly empty cell is detected almost at once. Entropy and support are
different summaries of a distribution: a distribution can clear an entropy floor while occupying
few categories, or fall below it while occupying several. Dropping a category and renormalising
over the rest removes from the comparison any difference between conditions in how often that
category occurs. A non-negative distance between two estimated distributions has a positive
expected value under the null. And declaring a materiality margin in advance for an
equivalence-style reading of language-model evaluation is established [28]; this protocol follows
that practice rather than originating it.

**Specific to this work**, to our knowledge:

1. a documented case in which each of the three gates of a sealed, pre-registered protocol ran as
   written and read a proxy, with rules, records and checks shipped together so that every row of
   the table in §1 can be recomputed rather than taken on trust. It includes a prospective arm on
   which the measurability gate, placed ahead of the estimate, fired, reported beside the sealed
   reading of that firing and the data that reading does not literally match;
2. the estimand itself -- *an agent-internal modulation acting on a downstream categorical choice*,
   rather than agreement between two models' output distributions;
3. an account of what the estimand drops: in the completed run every dropped draw is the string
   `"null"` that the prompt template itself offers, and the post hoc observation that such draws
   are more frequent in the channel-on blocks recurred in both prospective arms under a held-out
   test, with contents that differ between the arms (§5.1.2 and the results section); and
4. one observation kept from an earlier version of this list and restricted to the pooled
   chi-square surrogate calculation of §5.2: in that calculation, concentration of the base
   distribution is not itself what lowers the computed power; the size of the attainable shift is,
   and a degenerate base with a shift of one tenth of the margin still reaches `0.9533`. It follows
   from the form of the statistic noted above and is a property of that calculation, not of the
   design or of the permutation test the decision turns on. We list it because it runs against a
   common intuition, not because it is new statistics.

The earlier list opened with an item about how the margin and the power gate behave together when
some zones are never produced. That item is withdrawn with the reading it stated (§1, §5.1.1); its
last item, on placing a measurement-validity gate ahead of the estimate, is folded into item 1.

Everything else is the deliberate application of existing practice. The phrase *instrument autopsy*
also appears in the title of Otterson [27], whose separation of instrument artefacts from real
effects is adjacent to what this manuscript does, on a different object.

### 1.4 Analysis map

The analyses in this manuscript were fixed at four different times, and what each may be read as
depends on when. The table places every one of them. From here on, a paragraph that reports an
analysis outside §8 begins with the tag of its layer.

| Layer | Computes, on which data | Fixed when | Licenses | Where |
|---|---|---|---|---|
| **[Registered]** | `tv_bar` over five zones, draws with no zone dropped; the permutation test; rules R5 → R4 → R3 → R1 → R2. Scorer run on each prospective arm; rules applied to the two verdicts | Sealed before any prospective draw (§11, §13) | The reported branch, R4. Nothing about the channel's effect in the primary arm | §4, §6–§8; results |
| **[Prospective, descriptive]** | Quantities no rule reads, from the same two arms: per-context entropy, zones per cell, channel-off support, per-cell None rates | After the runs. No test | Descriptions of these two runs. No change to the branch | Results, after R4 |
| **[Post hoc]** | On the completed run: channel-off support, permutation-null mean, surrogate sensitivity sweep, what the dropped draws contain | After that run was seen: the re-analysis that `seal/protocol.md` §5 leaves unregistered | Descriptions of that run and of the gates. It generated the held-out hypothesis and is not evidence for it | §5.1.1, §5.1.2 |
| **[Held-out]** | One-sided stratified test that recorded None is more frequent in channel-on blocks; per arm, control first, α = 1/40; class breakdown and qualifiers. On both arms' per-draw annotation and records | Specification frozen at commit `61dbd96`, before the condition-wise counts were tabulated (declared); run once (declared) | Row A of its frozen table, always quoted with its qualifiers and class breakdown. Not separable from block order; no reading as intention; nothing beyond two models and eight contexts | Results, last |

Three things follow from the layering. Only the [Registered] layer is bound by the seal, and nothing
in the other three changes the reported branch or the sealed text of §8. The final row of the table
in §9, "Re-analysis of the completed run — Not performed", describes the sealed plan and is true of
that plan; the [Post hoc] layer is that re-analysis, carried out outside the plan and labelled as
such. And the [Held-out] layer tests a hypothesis the [Post hoc] layer produced, on draws collected
before its specification existed: it is a held-out check of a post hoc observation, and we do not
give it the standing of the sealed analysis. Its p-values are exact only if the draws within a
context are exchangeable across execution positions, which the fixed block order does not
guarantee.

---

## 2. Background

**Declared margins in language-model evaluation.** Singh [28] audits compressed language models
under a statistical toolkit built around declared-margin comparisons. That work establishes the
practice on which our margin handling rests, and fixes the scope of our own contribution: our
margin is an application of an existing method, not a methodological proposal.

**Total-variation estimation.** Price, Tian, Xun and Zhu [29] give sample-complexity results for
estimating total-variation distance in autoregressive models. Their estimand is sequence-level and
assumes richer access than we have. Ours is a decision-level five-way categorical distance measured
through sampled generations. The gap between the two is the main efficiency cost of our design and
is stated as a limitation (§12.3).

**Power in NLP evaluation.** Card and colleagues [35] document how frequently conclusions in NLP
rest on designs without the power to support them. This protocol is written to make the
power question answerable rather than assumed: the power attained by the realised design is
itself a pre-declared gate (R3, §8).

**Equivalence testing.** Lakens [36] gives the standard procedure for equivalence testing with
pre-specified bounds. We cite it as the standard reference for the practice of fixing a bound
before analysis. We do not run the procedure; §4.4 states our position precisely.

**Preregistration for agent experiments.** Vaccaro [37] discusses preregistration for experiments
with AI agents, which is the framework this submission sits inside.

**Validation of generative agent simulations.** Larooij and Törnberg [38] argue that validation,
rather than capability, is the central open problem for generative social simulation; Tomašević
and colleagues [39] report a replicated operational validation of an LLM-agent social simulation.
Both motivate measuring whether a wired mechanism propagates, rather than assuming it does.
Park and colleagues [2] provide the generative-agent architecture this apparatus descends from.

**Instrument artefact versus real effect.** Otterson [27] separates instrument artefacts from real
effects in a pre-registered causal setting; the separation logic is adjacent to ours, applied to a
different object.

---

## 3. The apparatus and the channel (completed preliminary study)

This section reports a completed preliminary study. It is not among the prospective analyses,
and no rule in §8 reads it except for the one constant named in §5.1; §9 audits that separation
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

**A second completed preliminary study (ES-1, a structured-probe determinism measurement) was
reported to establish the upstream determinism property of the same apparatus.** Its machine-readable
verdict record was not retained as a shipped artefact and is therefore not included in this
repository. Because this manuscript quotes only numbers that the extraction script can produce from
shipped data, no ES-1 quantity is quoted here. This is recorded as a provenance limitation
(§12.5). The determinism and byte-exact cross-platform replay properties of the upstream apparatus
are separately reported, with a publicly reproducible verification path, in [40]. That report is
not the ES-1 record and does not restore it, and no quantity from it is quoted here either.

---

## 4. Estimand, decision function, and the margin

### 4.1 Estimand

For each context *c* in a frozen bank of *K* = 8 contexts, the agent produces a five-way zone
decision. We compare the decision distribution under the channel switched on against the same
distribution with the channel removed:

> `P(zone | c, T_on)`  versus  `P(zone | c, T_off)`

where `T_on` supplies the locomotion state carrying the context's λ, and `T_off` removes
locomotion entirely. The zone is read before any bias is applied to it (§6.2).
The per-context distance is the total-variation distance between the two five-way distributions,
and the **primary estimand is `tv_bar`, the mean of that distance across the contexts.**

### 4.2 The decision function reads more than the primary estimand

The primary estimand is `tv_bar`, but the decision rules in §8 are not a function of `tv_bar`
alone. They read six quantities:

| Quantity | Read by | Role |
|---|---|---|
| `tv_bar` | R1, R2, R5 | The primary estimand; compared against the materiality margin |
| `rho_hat` | R1–R5 | Fraction of contexts whose per-context entropy of the zone distribution, pooled over both conditions with unparseable draws excluded, reaches `h_min_bits` (apparatus validity). It reads entropy, not the number of zones produced; the results section shows the two coming apart in both directions |
| `power` | R1–R3, R5 | Monte-Carlo power of a pooled one-sample chi-square goodness-of-fit test against an alternative built by moving mass from the largest to the smallest cell of the empirical channel-off distribution: the nominal sensitivity of a surrogate diagnostic. **This is not the power of the permutation test that produces `permutation_reject`**, which is the test the decision actually turns on; the two use different statistics and are not interchangeable (§12.6). At the registered `delta_tv` it is 1.0 for both bases §5.2 checks, near-uniform and degenerate, so a pass does not distinguish them; §5.1.1 shows its sensitivity when a cell of the base is empty |
| `permutation_reject` | R1, R2, R5 | Outcome of the permutation test at the declared α |
| `none_rate_max_observed` | R4 | The apparatus computes the fraction of draws yielding no parseable zone **per (context, condition) cell** and records the maximum across cells. No pooled figure is produced anywhere in the run output, so the maximum is the quantity R4 is evaluated on; earlier drafts of this protocol said "pooled", which named nothing that exists. The scorer independently returns `INCONCLUSIVE` if any single cell exceeds `none_rate_max`, so R4's second condition partly duplicates a gate upstream of it. It caps the rate in any one cell; it does not read how the rate differs between the conditions (§5.1.2 and the results section) |
| `verdict` | R5 | The categorical verdict emitted by the scorer for the control arm |

No threshold is added by listing these: `none_rate_max` is already among the values in §6.3, and
`verdict` is categorical.

Stating this explicitly matters: a protocol that named only `tv_bar` would understate what the
decision after the run actually depends on.

### 4.3 The margin is an interpretation rule, not a hypothesis

`delta_tv_min = 0.10` fixes, in advance, how an estimate will be read. It is not a prediction about
where the estimate will fall, and no directional claim is attached to it. Its function is to
foreclose the freedom to decide after the fact whether an observed distance is "small". The
practice of fixing such a bound before analysis is established [28, 36]; we follow it here.

**Where the value came from, and what is not added to it.** `0.10` was fixed upstream, with the
other thresholds, before the completed run was executed; §10.2 gives the commits and what checking
them establishes. This manuscript does not supply a substantive justification for the value after
the fact: one written with every result in hand would be a rationalisation of a sealed value rather
than a reason for it. The central claim of §1 does not use the value. Each gate is read at whatever
margin is registered, and the one row of the table in §1 that mentions the registered effect size
neither defends nor disputes it.

### 4.4 Relation to equivalence testing — stated precisely

Where a study aims at evidence of absence, the standard recommendation is a frequentist
equivalence test [36]. We have considered it, and **this protocol does not perform formal TOST or
Bayesian equivalence testing.** What it performs is estimation, comparison against a materiality margin declared in
advance, and a power guard. **We do not call this formal evidence of equivalence**, and we do not
claim that our procedure is the recommended framework under another name.

The permutation test in §4.2 is a nil-null test. It can fail to reject; failing to reject is not
evidence of equivalence, and nothing in §8 treats it as such. No additional statistic and no
additional threshold is introduced anywhere in this protocol beyond the eleven values listed in §6.3.

---

## 5. Completed preliminary studies and pilot data

Everything in this section is completed work. It is reported here because the protocol of §6-§8
is unreadable without it: §5.1 is the measurement the prospective arms repeat, §5.2 is the power
worksheet the sampling plan rests on, and §5.3 is the feasibility evidence that the second arm can
be run at all. None of it is re-analysed as part of the prospective plan, and §9 states, per
planned analysis, what that separation does and does not buy.

### 5.1 A completed run of the same measurement on one model

The measurement described in §4 was run once, to completion, on `qwen3:8b` under ollama 0.31.1,
with `think` disabled, at *M* = 300 draws per condition and *K* = 8 contexts (4,800 model calls).
The record is `data/raw/cproper-verdict.json` and `data/raw/cproper-manifest.json`.

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

This is the study that motivates the present protocol. It was executed under the thresholds listed
in §6.3, which had already been frozen upstream before it ran; §10.2 gives the provenance and the
scope of what that provenance establishes. The completed run is therefore not the origin of those
values.

It is reported here in full, and it is **not** re-analysed as part of the prospective plan. One
value of this record does enter §8, and we state it rather than leave it implicit: `tv_bar =
0.038065` is the pre-declared centre of the R5 tolerance band. It enters as a fixed constant
settled before any prospective draw exists, not as data to be re-analysed, and no other quantity
of this record is read by any rule in §8.

#### 5.1.1 The support of the read-out, and what the power gate can see of it

**[Post hoc]** The table above is the record as the scorer wrote it. Two further properties of the
same draws are not in that record and are not visible from it. Both are recomputed from the shipped
annotation by `analysis/scripts/collapse_and_floor.py` on every reproduction run, and are tabulated
in `data/derived/collapse-and-floor.md`. They are re-analyses of the completed run, made after its
verdict was known (§1.4).

**Two of the five zones are never produced in the condition the power calculation reads as its
base.** Pooled over the channel-off condition (2,276 draws that parsed), the read-out distribution
is:

| Zone | Count | Probability |
|---|---|---|
| `agora` | 0 | `0.0` |
| `chashitsu` | 0 | `0.0` |
| `garden` | 295 | `0.129613` |
| `peripatos` | 32 | `0.01406` |
| `study` | 1949 | `0.856327` |

`chashitsu` is not produced once in the whole run, under either condition; `agora` appears three
times, all in one context. Seven of the eight contexts have a combined support of three zones. The
estimand is defined over five categories and the apparatus offers five, but the decision space the
draws actually occupy is narrower than that, and the design was fixed without knowing it would be.
Both zeros are empirical: they are what these draws did, not a property the task imposes.

**The recorded `power = 1.0` does not depend on the empty cells.** At the registered `delta_tv` of
0.10, the same surrogate calculation returns `1.0000` for a near-uniform base as well as for a
degenerate one (§5.2). What the empty cells change is the calculation's sensitivity to much smaller
shifts. The gate takes the empirical channel-off distribution above as its base and builds the
alternative it tests against by moving probability mass from the largest cell to the *smallest*.
Here the smallest cell has probability exactly zero, and the chi-square statistic divides by the
expected count, which the implementation floors at a small positive constant to avoid dividing by
zero. A single draw landing in a cell to which the base assigns probability zero therefore produces
an enormous statistic. Against this base the surrogate behaves almost as a test of whether any draw
lands in a zone that was never seen. The whole sweep, as `collapse_and_floor.py` computes it:

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

So the surrogate does not discriminate among effect sizes here: it clears `0.8` at one hundredth of
the margin the study declared material, and a pass of it says almost nothing about whether the
design could detect a shift of the declared size. That is a statement about the surrogate. The power
of the permutation test the decision turns on is evaluated nowhere in this work (§12.6), and §7.2
records that R3 is retained as a planned check even so.

**The permutation-null mean of the estimate is `0.027813`.** Total variation is a non-negative
distance, so its expected value under the null is not zero. Permuting the condition labels within
each context -- the same null the scorer's own permutation test uses -- 2,000 times at seed
`20260708` gives a mean `tv_bar` of `0.027813` and a 95th percentile of `0.038839`. The observed
`0.038065` falls **below** that 95th percentile, which is the same fact the recorded
`permutation_p_value` of `0.057986` reports from the other side.

**An earlier reading of these numbers is withdrawn.** An earlier version of this section called the
permutation-null mean a floor under the estimate, read the ratio of the two as the share of the
estimate that floor accounts for, and argued that collapse raises it until it takes up much of the
declared margin. None of that holds. The permutation-null mean is the expected value of the
statistic under a finite-sample null: a reference value against which the observed statistic is
read, not an additive component that can be subtracted from it. And for a fixed number of draws the
null expectation of this plug-in distance does not rise as the base concentrates. To a first
approximation each zone contributes in proportion to the square root of p(1 - p), which is largest
when the base is spread evenly, so concentration lowers it. The earlier version also read the empty
cells as the reason the power gate passed, which the paragraph on `power = 1.0` above does not
support. What the numbers support is what the permutation test already reports: the observed value
is not distinguishable from the null at the declared α, and no threshold or decision rule changes
because of it.

#### 5.1.2 What the dropped draws are

**[Post hoc]** The estimand drops every draw whose pre-bias destination is recorded as `None` and
renormalises over the five zones. The sealed protocol chose that over a sixth category and made the
rate of such draws the quantity R4 reads (`seal/protocol.md` §1). In the completed run they are
124 of the 2,400 channel-off draws and 206 of the 2,400 channel-on draws, with more in the
channel-on condition in 8 of the 8 contexts. That observation was made after the run; it is
the hypothesis the held-out test of the results section examines, and it is not counted as evidence
here.

All 330 are the same thing: a response that followed the prompt template literally. The template
shows the field as `"destination_zone": "study|peripatos|chashitsu|agora|garden|null"`, with `null`
inside the quotation marks (`analysis/apparatus/erre_sandbox/cognition/prompting.py`, lines 48 and
71). In a free-text field that would do no harm. In `destination_zone` the parser validates the
value against the five zones and accepts only a JSON `null` as the empty value, so the string
`"null"` fails validation, the whole plan is rejected, and the record carries `None`. Re-parsing the
completed run's raw responses with the apparatus parser reproduces every recorded value, and all
330 `None` records are this string-`"null"` failure, with no JSON `null` and no missing key among
them. The estimand's word for these draws, "unparseable", is therefore exact.

Three things about the record are easy to misread. The annotation field `resolved_from` carries the
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

### 5.2 Power worksheet: for the surrogate, concentration is not what lowers the computed power

An a-priori calculation with the same pooled chi-square surrogate that R3 uses, reproduced by
`analysis/scripts/power_curve.py` at the frozen seed, gives:

| Base distribution | `delta_tv` | Power |
|---|---|---|
| near-uniform `[0.2, 0.2, 0.2, 0.2, 0.2]` | `0.10` | `1.0000` |
| near-uniform `[0.2, 0.2, 0.2, 0.2, 0.2]` | `0.01` | `0.1842` |
| degenerate `[0.96, 0.01, 0.01, 0.01, 0.01]` | `0.01` | `0.9533` |
| degenerate `[0.96, 0.01, 0.01, 0.01, 0.01]` | `0.10` | `1.0000` |

The third row is the one that matters for the surrogate. For this calculation the computed power is
governed by the size of the shift being looked for, not by how concentrated the base distribution
is: a degenerate base with a collapse-scale shift still attains `0.9533`. The `0.1842` figure
belongs specifically to a **near-uniform base with `delta_tv = 0.01`**, one tenth of the declared
margin, and is quoted only in that full form. The first and fourth rows are the ones §1 and §12.6
rely on: at the registered `delta_tv` the surrogate returns `1.0000` for both bases. All four rows
are properties of the surrogate; none of them is the power of the permutation test the decision
turns on (§12.6).

### 5.3 Feasibility pilot for the second model (no verdict computed)

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

**Parse quantities are recorded as three-level bands, not as rates.** The bands are `< 0.2`,
`[0.2, 0.8)` and `≥ 0.8`, and the band edges are deliberately not placed at `0.5`. The reason is
that rule R4 (§8) turns on a none-rate crossing `0.5`; recording an exact rate would let a reader
— and the authors — anticipate that rule's outcome. The bands are reported at the resolution that
answers the feasibility question and no finer. This resolution is not reduced later: the exact
rates are not restored anywhere in this manuscript.

No parse or zone quantity was collected for the reference model in the pilot, because that model is
the control arm of the prospective design and observing its parse behaviour would be observing a
component of R5.

---

## 6. Prospective design

### 6.1 Arms

| Arm | Model | Role | `think` regime |
|---|---|---|---|
| **control** | `qwen3:8b` (re-run) | Absorbs the backend upgrade from ollama 0.31.1 to 0.32.12, so that a change of model family is not read together with a change of platform version | disabled, as in §5.1 |
| **primary** | `llama3.1:8b` | Cross-family replication in a natively non-thinking model | none natively; the harness's disabled-`think` request is accepted (the pilot established acceptance, not behavioural inertness) |

`llama3.1:8b` was chosen because it is the same parameter scale as the reference model. A larger
model would move scale at the same time as family.

**The control arm is a comparison of statistics inside a declared band, not a bitwise comparison.**
Language-model draws do not reproduce exactly when regenerated. The bitwise agreement reported
elsewhere in this line of work is a property of replaying recorded outputs, not of regenerating
them, and it plays no part here.

### 6.2 Sampling plan

Both arms use *M* = 300 draws per condition and the same frozen bank of *K* = 8 contexts
(`cproper-ctx-0` … `cproper-ctx-7`) with the same per-context λ, giving 4,800 model calls per arm
and 9,600 in total. The read-out is the pre-bias destination (`pre_bias_destination_zone`): the
environment pins `ERRE_ZONE_BIAS_P = 0.2`, but no bias has been applied at the point at which the
zone is read, so the estimand is unaffected by it. The random seed is `20260708`. The apparatus
that performs the run is used unmodified; the arm driver lives outside the sealed measurement
package.

### 6.3 Thresholds — unchanged from the completed run

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
in §10.2 and is checked mechanically by `analysis/scripts/verify_threshold_freeze.py`.

---

## 7. Analysis plan

The prospective analysis plan contains two kinds of analysis, and **both are part of the plan.**
The labels below are roles, not a partition of the plan into included and excluded parts.

### 7.1 Role A — primary estimand

Estimate `tv_bar` in the primary arm as defined in §4.1, and evaluate the decision function of
§4.2 against §6.3 and the rules in §8.

### 7.2 Role B — planned quality-control and positive-control analyses

Three checks are planned, evaluated on prospectively collected draws, and consequential: each one
can change what may be concluded. They are part of the analysis plan and are not set aside.

| Check | What it protects | Declared pass criterion (fixed in advance) | Known at seal time? | Reported after the run |
|---|---|---|---|---|
| **R5** — control-arm concordance | That a change in backend version between the completed run and this one is not read as a family effect | The control arm reproduces the five quantities of §5.1 within the band given in §8 | **No** | All five quantities, and which fell outside the band if any did |
| **R4** — apparatus validity | That the estimand is measurable at all in the primary family (absence of a floor) | `rho_hat ≥ 0.5` and the per-cell maximum `none_rate ≤ 0.5` (§4.2) | **No** | Both quantities, against the R4 condition |
| **R3** — attained power | That the estimate is not vacated by insufficient power | `power ≥ 0.8` | **No** | The attained `power`, against `power_min` |

The consequence of each failure is fixed here and is not renegotiable after the data exist:
R5 failing stops interpretation of the primary arm; R4 failing narrows the conclusion to a
single-model scope; R3 failing yields an inconclusive-underpowered result that changes no claim.

### 7.3 Role C — completed preliminary studies

§3 and §5 are completed work. They are reported, not re-analysed. The single point of contact with
§8 is the one named in §5.1: the completed run's `tv_bar` fixes the centre of the R5 tolerance band
as a pre-declared constant. No rule in §8 re-analyses any of this material.

---

## 8. Decision rules

The following are **not predictions.** They are decision rules, fixed in advance, that determine
which scope of claim an estimate may be mapped onto once it is obtained. **R1, R2, R3 and R4 are
all permissible outcomes, and the authors do not predict which will occur.** The branch names are
category labels, not expectations.

**The rules below are not written here.** They are generated from `seal/decision-rules.json`, the
sealed machine-readable statement of them, by `analysis/scripts/render_decision_rules.py`, and step
12 of `repro.sh` fails if the block in this manuscript is not what that file renders to. This is
the whole of the pre-registration's mechanical content, and it is worth saying why it is arranged
this way. A protocol whose rules exist only as prose can be re-read after the data arrive, and
nothing catches it; under in-principle acceptance a recommender is what catches it. There is no
recommender here, so the rules are held instead by three checks that do not require one: the sealed
bytes (step 12), the generated text below (step 12), and the evaluator that applies the rules to
the recorded quantities and reports the branch it reaches (§13). None of the three establishes
*when* the rules were fixed. What they establish is that the branch reported after the run follows
from the rules as they stand here.

Before the block is read, one of its words needs a pointer. The estimand drops "unparseable" draws,
meaning every draw whose recorded destination is `None`. §5.1.2 shows what those draws are: in the
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
anything, and §12.2 records this limit.

## 9. Eligibility: what is known at seal time, and what is not

A protocol is pre-registered only for the outcomes its authors do not already know. That is a
statement about **realised outcomes**, not about data: a completed measurement may be reported in
full, at any length, without any realised outcome of a planned analysis being known. The audit
below is our answer to the question a reader is entitled to ask — *which of these did you already
have?*

Three things must be kept apart when reading the R5 row. The **baseline** — the completed run of
§5.1 — is known, and is reported here in full. The **declared pass criterion** — the band in §8 —
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
| `tv_bar` in `llama3.1:8b` | A — primary estimand | **No.** At the moment of sealing, not one draw had been collected from this model under the measurement | The estimate, and the branch of §8 it selects |
| Permutation test in `llama3.1:8b` | A — decision function | **No.** As above | `permutation_p_value` and `permutation_reject`, and their effect on the branch |
| Control-arm concordance on five quantities (R5) | B — planned QC | **No** — baseline known, band declared, **realised unknown**: whether version drift has occurred has not been observed | All five quantities, and which of them fell outside the band if any did |
| `rho_hat` and the per-cell maximum `none_rate` (R4) | B — planned QC | **No.** The Phase 0 pilot observed pooled parse and zone bands, which are adjacent information, not the R4 outcome (§5.3) | Both quantities, against the R4 condition |
| Attained-power check (R3) | B — planned QC | **No.** No value of `power` exists for the primary family | The attained `power`, against `power_min` |
| Re-analysis of the completed run | **Not performed** | (baseline known) | Nothing: it is excluded from the planned analyses and stays excluded |

The last row is a statement about the plan, and it stays true of the plan. Re-analyses of the
completed run are reported outside the plan, as the post hoc layer of §1.4 (§5.1.1 and §5.1.2).

---

## 10. Outcome-neutral checks and the provenance of the thresholds

### 10.1 Outcome-neutral checks

An outcome-neutral check is one whose pass criterion is **settled in advance by construction**, so
that writing the criterion down cannot reveal anything about the result. That is why stating those
criteria in §7.2 does not compromise the eligibility position of §9: declaring what would count as
a pass is not the same as knowing what will be observed. A positive control is one way to obtain
such a check, and this design has one; it is not the only way, and not every outcome-neutral check
here is of that kind.

The outcome-neutral checks in this design are R5, R4 and R3, and, from the completed work, the
zone-function positive control of §3, which shows that the upstream estimator can return zero, and
the ablation identity, which shows that removing the channel removes it without residue.

### 10.2 The thresholds were frozen before the completed run, and this is checkable

A reader is entitled to ask whether the materiality margin of `0.10` was chosen after seeing
`tv_bar = 0.038065`. The threshold constants live in two modules of the source repository, both of
which are shipped inside this repository under `analysis/apparatus/`, and both of which are public
and dated upstream.

| Shipped file | Upstream commit that froze it | Commit time (UTC) |
|---|---|---|
| `…/integration/embodied/bank_power.py` (eight constants, including `delta_tv_min`) | `2efe407cf7afd60e43f0a525a11a1739a8ca8d24` — the only commit ever to touch this file | 2026-07-07T17:08:49Z |
| `…/integration/embodied/bank_scorer.py` (`none_rate_max`) | `580b8aa8c884a35a761ed744b9f5a5f834a38137` | 2026-07-10T09:25:18Z |
| run artefact `verdict.json` of the completed study | `6cbffcb3191059d3c72bd4bd97670ea26d6cbaa1` — the only commit ever to add this file | 2026-07-10T12:25:06Z |

Both freeze commits are ancestors of the run commit. The records are at
<https://github.com/mikotomiura/ERRE-Sandbox>. `analysis/freeze-provenance.json` carries the
commit identifiers, the blob identifiers and the times; the URLs for following them by hand are in
`analysis/upstream-links.json`, kept separate because the provenance file is sealed and a
repository URL names its owner — see §11 and §13.

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

### 10.3 Claim-boundary enforcement

The claims this manuscript must not make are listed, with search patterns, in
`manuscript/CLAIM-BOUNDARY.md`. `analysis/scripts/check_claim_boundary.py` reads those patterns
from that file, requires that none of them matches this manuscript, and requires that every one of
them matches a fixture written to trip all of them. That fixture is
`manuscript/_claim_boundary_positive_control.md`; every sentence in it is deliberately false and it
exists only so that a silently broken pattern cannot report success. A pattern that stops matching
the fixture fails the run. A second fixture, `manuscript/_claim_boundary_negative_control.md`, holds
the opposite: sentences this manuscript and the seal must be able to say -- the sealed reading of R4,
the sealed note that the completed run attained power 1.0, the statement that the power of the
permutation test is evaluated nowhere, the withdrawal of an earlier reading -- and the run fails if
any pattern matches one of them. The block of §8 generated from the seal is scanned with the rest of
this manuscript, so a pattern that matched a sealed sentence could never be satisfied.

---

## 11. What the seal covers, and what breaks it

The two arms together require approximately 5.09 h of compute on the recorded hardware (§5.3), and
the run is executed once (§12.8 records the one restart, of a capture attempt that had produced no
verdict).

Before any prospective draw is collected, eleven files are sealed, in six groups:

| Group | Files | Why it has to be fixed |
|---|---|---|
| The rules | `seal/decision-rules.json` | The decision itself. Everything else exists to stop this changing quietly |
| The run | `seal/arm-spec.json` | Every value the list below calls a not-minor deviation |
| The protocol | `seal/protocol.md` | The part of this manuscript whose alteration would change how the result reads |
| The code that reads them | `apply_decision_rules.py`, `render_decision_rules.py`, `verify_seal.py`, `check_seal_scope.py`, `_provenance.py` | A checker that can be edited is not a check. The last of these supplies the hashing the others use, and was missing from an earlier version of this list — which is why the seal now also fails if a sealed script imports a local module that is not itself sealed |
| The code that reaches outside | `collect_zenodo_witness.py` | The only script here that touches the network. It reads an archive's public record and writes down the checksums and server-assigned times it finds, which is the one input to these checks that does not come from the author. A collector editable after the deposit could be taught to write down whatever made the comparison agree |
| The record and the command | `analysis/freeze-provenance.json`, `repro.sh` | The provenance of the frozen thresholds, and the fourteen steps that check all of the above |

`seal/SEAL-MANIFEST.json` records the SHA-256 of each and a self-hash over itself under a stated
canonicalisation, and step 12 of `repro.sh` fails if any of them has moved since (§13). What that
buys is narrow and worth naming exactly: the branch reported after the run can be re-derived, by
anyone, from the rules as they stood before it. It does not establish that the seal is old, and no
check that lives inside this repository could. That would take a copy held by somebody else. One
now exists, at `10.5281/zenodo.22735436`; §13 describes the step that compares these files against
it, together with the reason that comparison, even when it passes, bounds less than it appears to.

The following are **not** minor deviations:

- substituting a different model for `llama3.1:8b`;
- changing the backend version;
- changing any of the threshold values in §6.3;
- changing the seed `20260708`;
- changing *M* or *K*;
- substituting the frozen context bank.

Each of the six is recorded as a field in `seal/arm-spec.json` and compared against the run
manifest by `analysis/scripts/verify_seal.py`, so the list is checked rather than promised.

**If any of them occurs, the seal is broken, and we say so rather than repair the wording.** A
registered-report route would send a deviation of this kind to the recommender who granted
in-principle acceptance; there is no such third party here, and we do not put an assurance in the
place of the authority that is absent. The rule is a forfeit: should any of the six become necessary, it is reported as a
deviation in the completion report, and **that run is not presented as pre-registered.** Making the
claim again would require a fresh seal and a fresh run. This is a condition under which the
pre-registration lapses — not a licence to change the rules and carry on.

---

## Results of the prospective run

<!-- REPORTED-BRANCH: R4 -->

**[Registered]** Both arms were run on 2026-09-14 and 2026-09-15 at the sealed sampling plan of
§6.2 — *M* = 300 draws per condition over the same *K* = 8 frozen contexts, 4,800 model calls per
arm and 9,600 in total. Each arm produced one complete run; the control arm's first capture attempt
was stopped from outside before it had produced a verdict and was restarted from the beginning, and
§12.8 says where that is recorded. Each bundle was checked against the seal before its verdict was
landed, and the branch below was derived by hand from the two landed verdicts and
`seal/decision-rules.json`, quantity by quantity, in `manuscript/REPORTED-BRANCH.md`.

**[Registered] Control arm (`qwen3:8b`).** The recorded quantities are `verdict` =
NO_CHANNEL_CONFORMANCE, `rho_hat` = 1.0, `power` = 1.0, `tv_bar` = 0.030575 and
`permutation_reject` = false at permutation *p* = 0.43989, with `none_rate_max_observed` = 0.086667
across the arm's cells and all eight contexts passing the per-context gate. R5 is satisfied on all
six of its predicates: the estimate sits 0.007490 from the centre of a tolerance of 0.03. What that
states is band membership, and §12.2 records that it states nothing further about the backend
upgrade. Evaluation continues to the primary arm.

**[Registered] Primary arm (`llama3.1:8b`).** `rho_hat` = 0.0 with `effective_k` = 0 of 8. No
context reaches the per-context entropy floor of `h_min_bits` = 0.5: the per-context values run from
0.165654 to 0.274008. Draws are being produced and parsed — `none_rate_max_observed` = 0.066667, the
same order as the other arm — so what is low is not output but the entropy of each context's zone
distribution, which is not the same thing as the number of zones the draws reach. Because no context
is admitted, the scorer stops before forming the channel-on and channel-off contrast, and `tv_bar`,
`power` and `permutation_reject` are not produced at all. They are absent from the verdict rather
than small in it.

**[Registered] The branch is R4, apparatus validity.** R4 is evaluated ahead of the estimate
precisely so that a floor effect cannot be read as an absent effect, and `rho_hat` < 0.5 satisfies
it. The reading the sealed rule attaches is quoted in §8: that in the primary family "the substrate
does not license two or more zones", that the estimand is therefore not measurable in that family,
that this is **not** read as NO_CHANNEL_CONFORMANCE, and that the claim narrows to single-model
scope. The first part of that reading does not match the data literally, and the paragraph after
next says how. The `verdict` field of the primary bundle does carry the string
NO_CHANNEL_CONFORMANCE, because the scorer has one exit for a read-out it cannot score, and it must
not be quoted as though the comparison had been made. R3, R1 and R2 were not reached: evaluation
stops at the first rule whose action is `stop`.

**[Registered] The scorer's exit label, read across the three records.** The scorer writes
`NO_CHANNEL_CONFORMANCE` into all three records. The label is the scorer's output and a predicate of
R5, so it cannot be renamed; what can be done is to say, record by record, what produced it:

| Record | `verdict` | What the scorer recorded when it wrote the label | On/off comparison made |
|---|---|---|---|
| completed run | `NO_CHANNEL_CONFORMANCE` | `rho_hat` = 1.0, `power` = 1.0, `tv_bar` = 0.038065, `permutation_reject` = false | yes |
| control arm | `NO_CHANNEL_CONFORMANCE` | `rho_hat` = 1.0, `power` = 1.0, `tv_bar` = 0.030575, `permutation_reject` = false | yes |
| primary arm | `NO_CHANNEL_CONFORMANCE` | `rho_hat` = 0.0 (`effective_k` = 0 of 8); no estimate formed | no |

Only the first two rows are what the label's name describes.

**[Prospective, descriptive] What the entropy floor saw, and what it did not.** The rule fires on
`rho_hat`, and `rho_hat` is the fraction of contexts whose per-context entropy reaches
`h_min_bits`. As a paraphrase of that floor, "does not license two or more zones" is not accurate:
every one of the primary arm's 16 (context, condition) cells produces two or more zones, between
two and four. The reading is generated from the sealed rules (§8) and stands there as sealed; the
firing of the rule and the branch are unaffected, because the rule is written on `rho_hat` and not on
the paraphrase. The table sets the zones each run's parsed draws occupy beside what the gate
recorded. The completed run's row belongs to the post hoc layer, the two arms' rows to the
prospective descriptive layer:

| Run | Zones in the channel-off base | Zones under the channel on | Zones per (context, condition) cell | `rho_hat` |
|---|---|---|---|---|
| completed run (`qwen3:8b`) | 3 of 5 | 4 of 5 | 3–4 | `1.0` |
| control arm (`qwen3:8b`) | 3 of 5 | 4 of 5 | 3–4 | `1.0` |
| primary arm (`llama3.1:8b`) | 3 of 5 | 5 of 5 | 2–4 | `0.0` |

The gate admitted every context of the two runs whose channel-off bases occupy three zones and no
context of the run whose cells occupy two to four. Entropy measures how evenly a context's draws
spread, and support how many zones they reach; here the two come apart in both directions.

Two consequences are worth stating plainly. The question §1.2 puts — whether the narrow support of
the completed run belongs to the model or to the apparatus — is not answered in the primary family
by this run, because the quantity that would answer it was not estimable there. And the two arms
failed the gate quantities in different places: the completed `qwen3:8b` run admits all eight
contexts even though two of five zones are never produced in the channel-off condition, whereas the
primary arm has `effective_k` = 0 of 8 because none of its contexts clears `h_min_bits` = 0.5. These
are outcomes recorded of these runs under this apparatus, and they are not a comparison of how far
the decision spaces of two model families have collapsed: the two statements are about different
quantities, one the support of the read-out and the other a per-context entropy floor. What neither
licenses is reading an unmeasurable arm as agreement; §12.7 carries the reason a shared collapse
would not be a replication, and that reasoning applies with more force where there is no estimate
at all.

**[Post hoc and prospective, descriptive] An entropy floor cleared everywhere, on a base occupying
three of five zones.** The completed run of §5.1 admits all eight of its contexts: every one clears
the per-context entropy floor of `h_min_bits` = 0.5, which is what `rho_hat` = 1.0 records. It is the
same run whose channel-off base — the distribution the power calculation reads — never produces two
of the five zones, whose power gate clears `0.8` at one-hundredth of the declared margin (§5.1.1),
and seven of whose eight contexts have a combined support of three zones. The control arm records
`rho_hat` = 1.0 as well, and its channel-off base also never produces `agora` or `chashitsu`: of its
2,306 parsed channel-off draws, `garden` has 386, `study` 1,896 and `peripatos` 24.
**Clearing a per-context entropy floor therefore does not certify the support that the power
calculation depends on.** The two quantities are not interchangeable: a floor asks whether each
context varies enough to be scored, and the support count asks how many of the five categories the
base ever occupies. Clearing the floor does constrain the support, but only from below and only by
two, which is far short of what that calculation assumes of it.

That has a consequence for R4, the measurability gate of §8, which is written for the primary arm
and evaluated only there. Its two conditions are `rho_hat` < 0.5 and `none_rate_max_observed` >
0.5. Applied to the completed run and to the control arm, **neither condition is met** —
`rho_hat` is 1.0 in both, and `none_rate_max_observed` is 0.123333 and 0.086667 respectively. **At
the thresholds frozen in §6.3, a gate of this shape does not flag the regime of §5.1.1.** Two things
keep that from being true by construction. The gate is not inert: the same two conditions, at the
same thresholds, did fire on the primary arm, which is how this run reached R4 at all. And the
thresholds are what decide it rather than the shape of the rule — the completed run's per-context
entropies run from 0.628287 to 0.754149, so a floor set above 0.68 rather than at 0.5 would have put
`rho_hat` at 0.375 and fired R4 on the completed run too. What the paragraph above says about
certification holds at any floor; what this paragraph says about flagging is a statement about these
thresholds, and §10.2 records that they were fixed before any of this was computed. Detecting the
regime of §5.1.1 took the support and permutation-null diagnostics computed there, which run on
every reproduction but are not gates in this protocol. The reading here is not left to the prose:
step 9 re-derives each arm's `effective_k` and `rho_hat` from its own per-context entropies,
evaluates R4's sealed predicates against all three records, and requires the zero-probability zones
to be named in this manuscript (§12.8).

**[Registered] Neither run that produced an estimate returned one its own permutation test
rejected.** The paragraphs above should be set beside what the three runs of this measurement have
returned. The first line restates §5.1.1 rather than adding to it, which matters because a value
repeated in two places is a value the occurrence check no longer protects at either (§12.8). In the
completed run `tv_bar` = 0.038065 against a permutation-null mean of 0.027813 and a null 95th
percentile of 0.038839, so the observation falls below that percentile, which the recorded
`permutation_p_value` of 0.057986 reports from the other side — a margin of 0.000774 below the
percentile and 0.007986 above the α of 0.05, so neither is a comfortable distance. In the control
arm `tv_bar` = 0.030575 at a permutation *p* of 0.43989, and the test does not reject. In the
primary arm no estimate is produced at all. **Both runs that produced an estimate are `qwen3:8b`**,
so the *n* here is two runs of one model family; §12.7 gives the reason agreement across runs of
this apparatus would not establish what it appears to. It is a statement about what has been
observed, not about the power of any test — §12.6 records that the power of the permutation test is
evaluated nowhere in this work — and it changes no threshold and no decision rule. Whether the
read-out itself, the zone vocabulary, the parser and the frozen bank, is what holds the estimate
there is the question §12.7 raises, and this protocol cannot answer it: varying the read-out is a
change the seal does not permit (§11).

### A held-out test of the post hoc observation

**[Held-out]** The observation of §5.1.2 -- more dropped draws in the channel-on condition of the
completed run -- was made after that run, so it was tested once, on the two prospective arms, whose
draws had been collected without reference to it. The specification, the test and the
interpretation table were frozen at commit `61dbd96` (`analysis/heldout-stay/SPEC.ja.md`,
`freeze.json` and `analysis/scripts/heldout_stay_check.py`, which the `heldout-stay` workflow runs
on two operating systems), and the test was run once from that commit. It is not a formal
pre-registration: the prospective draws existed before the specification did, and that the
condition-wise counts had not been tabulated before the freeze is a declaration in the
specification, not something any check demonstrates. The outcome is whether a draw is recorded as
`None`. The test is an exact one-sided stratified test, with the eight contexts as strata and each
context's `None` total held fixed, at level 1/40, applied to the control arm first and counted for
the primary arm only if the control arm's test rejects.

Both rejected. That is row A of the frozen interpretation table, whose wording is: in both
prospective runs, recorded `None` was more frequent in the channel-on blocks than in the channel-off
blocks.

| Arm | `None`, channel-on blocks | `None`, channel-off blocks | one-sided *p* |
|---|---|---|---|
| control (`qwen3:8b`) | 156 | 94 | 3.415046e-05 |
| primary (`llama3.1:8b`) | 107 | 61 | 1.894707e-04 |

What was recorded as `None` differs between the arms, and the frozen specification requires the
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

In the control arm almost every `None` is an explicit `"null"`. In the primary arm almost every one
is a missing or malformed JSON object, and 41 of the primary arm's 46-draw excess in the
channel-on blocks is of that kind. The frozen qualifier for writing that outputs naming `null` as
the destination increased holds for the control arm, where the same test applied to the string and
JSON `null` alone gives *p* = 4.359535e-05, and not for the primary arm, where it gives
*p* = 2.263667e-01; for the primary arm, what increased is recorded `None` in general. **What
replicated is an operational outcome, the recorded `None`. It is mostly an explicit `"null"` in the
control arm and mostly missing or malformed JSON in the primary arm, so this is not a cross-family
replication of the same behavioural meaning or of the same parser-failure mechanism.**

The difference cannot be separated from execution order (§12.9). Every context was run as a block
of channel-on draws followed by a block of channel-off draws, so a difference between the conditions
is also a difference between earlier and later draws, and the *p*-values above are exact only if
the draws within a context are exchangeable over their positions in the run, which a fixed block
design does not guarantee. What the result does not license was fixed in the specification before
it was known: an effect of the channel separated from execution order; any attribution to λ,
locomotion, embodiment, temperature or top_p; reading `None` as an intention; reading the difference
in effect size between the arms as a difference between model families; and any statement beyond
two models and eight frozen contexts. A secondary six-category distance, with `None` as a sixth
category, is 0.047917 (permutation *p* = 0.061197) in the control arm and 0.030833 (*p* = 0.015049) in the
primary arm; it is reported without being judged against the margin of 0.10.

---

## 12. Limitations

### 12.1 Model family and think regime move together

The two arms differ in model family and, unavoidably, in think regime: within the available memory
budget there is no non-Qwen model at this scale with a native thinking regime, and the obvious
candidate distilled model belongs to the same family as the reference. The design therefore
attributes nothing to either factor alone, and no result under §8 licenses an attribution to one of
them. We declare this confound in advance and carry it as a limitation rather than presenting it as
resolved. In particular, obtaining R1 across the two arms does not license any statement about
which of the two factors is responsible.

### 12.2 What the control arm establishes

R5 compares five statistics against a declared band. A pass is a statement about band membership
and carries nothing further about the backend upgrade. If R5 fails, we report the control mismatch
and stop; the primary arm is not interpreted, and this manuscript does not speculate about what it
might have shown.

### 12.3 Sample access rather than logit access

The backend used here does not expose token-level logits, so the five-way decision distribution is
estimated from sampled generations. With logit access the same quantity would be obtainable far
more cheaply [29]. This is a constraint of the deployment, and it sets the cost of the design.

### 12.4 Bounded envelope

Every claim is bounded by a single apparatus, a single disabled-`think` regime, a frozen bank of
eight contexts, and a five-way zone decision. The subject is the channel described in §1. Nothing
here is a statement about human ambulation, about creative production, or about whether embodiment
matters in general.

### 12.5 Provenance gaps we are carrying

The ES-1 verdict record is not shipped (§3). The per-draw record of the completed run was, in
earlier versions of this compendium, referenced by hash rather than included, to keep the
repository small; since 2026-09-25 it is shipped byte for byte in `data/completed/`, checked by
step 3 against its size and digest in `data/data.md` and against the digest the run's own manifest
pinned, and re-parsed as §5.1.2 describes. A
separate report of the upstream apparatus's determinism properties is citable [40], but it is a
different body of evidence and does not stand in for the missing ES-1 record: the gap below is
stated, not closed.

One further gap concerns the ES-3 forensic record of §3. Its bytes are verifiably identical to the
blob registered upstream, but the upstream commit that carries it is a **relocation** commit: the
record was produced in June 2026 in a directory that was outside version control, and entered the
repository in September 2026 when it was moved, byte for byte, into a tracked path. Version history
therefore witnesses the record's *content*, not its *age*. The three records of the completed run
in §5.1 do not have this gap — their upstream commit is the run itself. This asymmetry is recorded
in `analysis/freeze-provenance.json` and is printed by the verification script rather than left to
the reader to discover.

All three gaps are stated rather than worked around.

### 12.6 The reported power is the nominal sensitivity of a surrogate, not the power of the test the decision turns on

Two different tests appear in this design and it matters that they are not confused. The decision
rests on the margin comparison and, for `permutation_reject`, on a stratified label-permutation
test of `tv_bar`. The quantity called `power` is the Monte-Carlo power of a pooled one-sample
**chi-square goodness-of-fit** test against a constructed alternative: the nominal sensitivity of a
surrogate diagnostic. The statistics differ, the tests differ, and the power of the permutation test
is evaluated nowhere in this work. Earlier drafts described `power` as the attained power of the
realised design, which overstated the connection.

Two consequences follow for what a pass of R3 can be read as. At the registered `delta_tv`, the
surrogate returns `1.0000` for both bases §5.2 checks, near-uniform and degenerate, so a pass does
not distinguish a collapsed base from a spread one; only those two bases were checked, and nothing
here says what the surrogate returns for bases in general. And against the completed run's
channel-off base, whose empty cells §5.1.1 describes, it clears its `0.8` threshold at effect sizes
two orders of magnitude below the declared margin. R3 is retained as a planned check, and its
failure would still be consequential, but a **pass** of R3 is not read here as evidence about the
power of the decision the design makes. We state that rather than let the word "power" carry a
weight the number cannot bear.

### 12.7 A shared collapse would not be a replication of the channel result

Under R1 the two arms agree. §12.1 records that family and think regime move together and that
neither can be credited. A second and distinct gate stays open, and the finding of §5.1.1 is what
opens it: the collapse of the decision space is at least as plausibly a property of the harness --
the prompt, the parser, the zone vocabulary, the frozen bank -- as of any model. Both arms run the
same harness on the same bank. If the same two zones go unproduced in both, the agreement between
them is evidence that the apparatus behaves consistently, not that the channel fails to propagate
in two model families.

The prospective design does not resolve this, and no rule in §8 attributes the agreement either
way. We name it in advance so that an R1 outcome is not read as more than it is. Distinguishing the
two would need the read-out varied -- a different zone vocabulary, a different parser, a different
bank -- which is outside this protocol and is not a change we may make to it (§11).

### 12.8 What the checks reach on the prospective arms, and what they do not

The reproduction script evaluates the sealed rules against the two landed verdicts, and, since
2026-09-25, step 5 also recomputes both verdicts from the arms' per-draw annotations and manifests
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
stopped attempt's partial record is shipped beside the control log, byte for byte as the driver
left it; it holds 41 complete per-call lines (call indices 1 to 41) followed by 594 NUL bytes and
no final newline. Step 9 counts both from the shipped files. What the files cannot show is that no
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
reported rather than pass. The rows of the tables in the results section are held by the rendered
comparison described in §13.

One thing is still outside all of it: the prose in §5.3, the timings and digests of the pilot,
exists in no shipped record at all, as §4 of `manuscript/CLAIM-BOUNDARY.md` states.

### 12.9 Condition is confounded with execution order

In all three runs the contexts were run in sorted order, and within each context the 300 channel-on
draws were requested before the 300 channel-off draws. The order is fixed by the upstream apparatus:
the loop at lines 276–284 of `src/erre_sandbox/integration/embodied/bank.py`, with the condition
order `("on", "off")` at line 118, at commit `4e45adb33d7472d2adf6da29a800bde9b8f58f9e` of the
upstream repository, the commit the prospective driver ran from; the file is unchanged there since
before the completed run. The shipped annotation files hold the draws in that order. Any difference
between the conditions -- the sealed estimate, the descriptive quantities of the results section
and the held-out difference in recorded `None` -- is therefore also a difference between earlier and
later draws of the same context, and elapsed time, server state or drift could produce it as well as
the channel could. The design does not separate them, and nothing in this manuscript assigns a
condition difference to the channel. Separating them would take an interleaved or randomised
condition order, which is a new run under a new seal.

---

## 13. Data, code and reproducibility

**Everything this manuscript refers to is reachable from one place.** The repository is
<https://github.com/mikotomiura/collapsed-decision-space>. Work continues on its default branch, so
a path named below is in general a moving target — with one exception, and it is the exception that
carries the pre-registration. The files listed in §11 are sealed by content: `seal/SEAL-MANIFEST.json`
records their SHA-256 and a self-hash over itself, and step 12 below fails if the checkout in front
of you does not hold exactly those bytes. **The pin is a hash, not a branch name and not a tag.**

The tag `stage1-submitted` in this repository marks the state submitted to PCI Registered Reports
in September 2026. It is kept as a record of that submission and is **not** the state of this
manuscript, which has since been rewritten.

The upstream source repository the apparatus and the provenance records come from is
<https://github.com/mikotomiura/ERRE-Sandbox>, and §10.2 gives the commit identifiers within it.
Apart from the archival deposit of the sealed files described in §13, there is no separate
supplementary archive: the data, the analysis scripts, the apparatus and the reproduction command
are all in the repository named here.

This repository contains the frozen inputs of the completed studies (`data/raw/`, each pinned by
SHA-256 and size in `data/data.md`), the analysis scripts (`analysis/scripts/`), and the measurement
apparatus as an import closure of 69 modules (`analysis/apparatus/`) reproduced byte-for-byte from
the upstream source repository. That closure covers the scoring and power machinery, which is what
the analyses in this repository exercise; it does not include the live driver that produced the
draws, since regenerating draws is out of scope here (§6.2). That driver is in the
upstream repository as `scripts/paper02_run_arms.py` at commit
`4e45adb33d7472d2adf6da29a800bde9b8f58f9e`, the commit it ran from, and the call order it inherits
from the apparatus is described in §12.9. Neither is checked by anything in this repository.

`bash repro.sh` performs fourteen steps, in order: environment installation from the lockfile; a
lint check; verification of the frozen inputs against both `data/data.md` and their upstream blobs;
verification of the threshold freeze and of the whole apparatus closure; **recomputation of the
completed run's verdict and of the two prospective verdicts from the shipped annotations and
manifests**; mechanical extraction of the
quantities quoted in §3 and §5.1; regeneration of the power table of §5.2; derivation of the
support of the decision space and of the permutation-null mean reported in §5.1.1; a character-level
comparison of the numbers quoted in this manuscript against the frozen inputs they come from; the
claim-boundary check of §10.3; a mutation sweep that measures what the seal and the decision rules
actually catch; verification of the seal itself, which includes requiring that the rule text in §8
and in `seal/protocol.md` be **generated from** the sealed rules rather than restated alongside
them; the evaluator of §8 applied to the recorded quantities; and, last, a comparison of the
sealed files against a recorded copy of the per-file checksums an archive publishes for them. It
exits non-zero if any step fails, and its closing line names any step that was skipped rather than
reporting a count of steps that passed.

The fourteen steps include no test suite and no `pytest` run: this repository has none, and its
checks run as the steps themselves and, for the held-out test, as the `heldout-stay` workflow. The
sealed `repro.sh` also describes step 8 in the vocabulary of an earlier version of §5.1.1, in which
the permutation-null mean was called a floor. Its comments and its progress line are sealed bytes
and keep that wording, and the script and output file names it calls are kept for the same reason;
the quantity the step computes is the permutation-null mean.

The thirteenth step is the third of the three checks named in §8. Both prospective verdicts are
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
both sides of any one of them in a single commit, which is why §11 says what it says. An archive
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

The deposit carries an earlier working title of this manuscript in its title field. Its metadata is
not edited, and no new version is created under the concept identifier: the deposit's last-modified
time is one of the server times the witness records, so an edit would move the anchor described above and the
collector would no longer reproduce the witness.

**What step 14 establishes is less than its name suggests, and we would rather say so than be
found out.** The step is offline. It establishes two things: that the recorded witness agrees with
these bytes, and that the witness is closed against itself — its anchor is the maximum of the
server-assigned times it carries, and those times are exactly the ones its own deposit listing
implies, one created and one updated per deposited file, with no invented name and no duplicate.
It does *not* establish that the witness is what the archive returned. It cannot: a file in this
repository is a file in this repository, whatever it describes. An independent review demonstrated
the gap by writing a witness from nothing — digests computed locally in an algorithm no archive
publishes, timestamps from the year 2000, a per-file time naming a file that did not exist — and an
earlier version of this check reported no problems at all. The closure requirements above are the
repair for what an offline check can repair; this paragraph is the repair for the rest.

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
altered in the manifest with and without recomputing the manifest's self-hash, the band moved in §8
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
completed run and, since 2026-09-25, `data/raw/control-verdict.json` and
`data/raw/primary-verdict.json` for the two arms. The whole of §5.1, and the two verdicts step 13
reads, are therefore derivable from this repository rather than merely quoted from it. The step
also alters each compared field of a copy of each record in turn and requires the comparison to
name it, so that a comparison unable to see a difference cannot pass. It takes under two
seconds.

The ninth step is what turns "these numbers were not transcribed by hand" from an assurance into
a check: it reads each quantity from the frozen JSON by key and requires the resulting literal to
appear in this manuscript, and -- for the subset the repository README quotes -- in that README
too. Its scope is bounded twice over, and we state both bounds rather than let the check sound
stronger than it is. It covers only the quantities obtainable mechanically from the frozen
inputs; numbers outside that set are not covered at all. And within that set it tests
**occurrence, not uniqueness**: several of these values appear at more than one point in this
manuscript, so altering one occurrence while leaving another intact would not fail the run. An
earlier version of this section said that a single altered digit fails the run, which is true
only of a quantity that occurs exactly once, and the check does not determine which those are.

For quantities whose literals are too common for that -- small counts, zone counts, the rows of the
tables in §5.1.1, §5.2 and the results section, and the counts and class breakdown of the held-out
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

## 14. AI usage disclosure

This work was developed with substantial AI assistance, disclosed here in full.

Claude (Anthropic; the Opus 4.8, Opus 5 and Sonnet 5 models, via Claude Code) was used for
implementing the measurement apparatus and the analysis and verification scripts shipped here, for
documentation, and for drafting the text of this manuscript. OpenAI Codex (`gpt-5.5`) was used for
independent design and code review. **No AI system is an author**, and **no figure in this
submission was generated by AI**: the manuscript contains no figures at all, so the prohibition is
satisfied by construction rather than by assurance.

The extent of that assistance is visible in the public record rather than asserted here, and the
counting method is stated so that a reader can reproduce the figures:

| Repository | Commits | Commits carrying at least one `Co-Authored-By` trailer naming the model |
|---|---|---|
| Upstream source, <https://github.com/mikotomiura/ERRE-Sandbox>, at commit `a2a19f9` | 305 | **205** |
| This repository, at commit `a32bcf3` | 20 | **18** |

Trailers are counted **case-insensitively, as commits rather than as trailer lines**, over the
history reachable from the commit named in each row. Both halves of that sentence are load-bearing.
A single commit may carry more than one trailer, so the upstream history holds 286 such lines
across those 205 commits, and a count of lines reported as a count of commits would overstate the
figure by two fifths. And a count with no commit pinned beside it cannot be reproduced at all,
because the next commit changes it -- these two rows were both wrong by the time anyone read them
once before, for exactly that reason. Each row is therefore true of the commit it names and of no
other, which is the most a count of this kind can be: the commit that records a figure cannot be
included in it, so the row for this repository names the last commit before the one that wrote the
row. It also has to name a commit a reader can still reach. The figure here was briefly pinned to a
commit on a feature branch, which the squash-merge of that branch left unreachable from `main`; the
row now names a commit on `main`, and the count fell from 30 to 20 because squashing is what the
public history actually records. Anyone can recompute both with `git log --format=%H%x01%B%x02` over the named commit and count
the entries whose body matches `co-authored-by:.*claude`, case-insensitively.

All AI-assisted output was reviewed, edited and validated by the human author, who made the
decisions that determine what this protocol claims: the choice of estimand and of the materiality
margin, the decision rules R1–R5 and the order in which they are evaluated, the eligibility
position of §9, the scope of every claim and of every limitation in §12, and the decision to seal
this protocol before collecting the prospective data. Validation is not self-reported: the numerical,
provenance and claim-boundary properties asserted in this manuscript are enforced by `repro.sh`
(§13) and re-run by public continuous integration on two operating systems, and the claim-boundary
guards are themselves checked against a fixture written to trip every one of them (§10.3), so a
guard that silently stopped working fails the run.

---

## 15. Ethics, funding and competing interests

This study involves no human or animal subjects. It measures the output distribution of
locally-run language models on a frozen bank of synthetic contexts, so no ethics approval is
required and none was sought.

This work received no financial support. The compute is a single desktop machine belonging to the
author, and the models are run locally; the projected cost of the full two-arm design is the 5.09 h
of that machine's time recorded in §5.3.

The author declares no competing interests.

---

The abstract at the head of this document and the `abstract` field of `CITATION.cff` are required
to be the same text; `analysis/scripts/check_claim_boundary.py` compares them on every
reproduction run, so the manuscript and the repository metadata cannot drift apart silently.

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

[37] Vaccaro, M. *Preregistration for Experiments with AI Agents.* arXiv:2606.11217, 2026. (The
arXiv identifier and the submission date reported by the arXiv API do not agree; both are recorded
as retrieved, without correction.)

[38] Larooij, M. and Törnberg, P. *Validation is the central challenge for generative social
simulation: a critical review of LLMs in agent-based modeling.* Artificial Intelligence Review,
59(1), article 15, 2025. doi:10.1007/s10462-025-11412-6

[39] Tomašević, A., Cvetković, D., Major, S., Maletić, S., Anđelković, M., Vranić, A., Stupovski,
B., Vudragović, D., Bogojević, A. and Mitrović Dankulov, M. *Towards operational validation of
LLM-agent social simulations: a replicated study of a Reddit-like technology forum.* EPJ Data
Science, 15(1), article 72, 2026. doi:10.1140/epjds/s13688-026-00674-x

[40] Miura, M. *Two-plane determinism: byte-exact cross-platform replay of LLM-in-the-loop agent
simulations.* Preprint, 2026. doi:10.5281/zenodo.22719772 (The concept identifier is cited, since
it resolves to the current version; the record carries no version string of its own.)

Reference numbers are permanent identifiers assigned in the author's central bibliography and are
not renumbered between manuscripts.
