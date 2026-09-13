# A powered null on a verified channel: separating effect-absent from low power in embodied LLM agents

**Stage 1 Registered Report protocol** — submitted to PCI Registered Reports (standard track).

| | |
|---|---|
| Author | Mikoto Miura |
| ORCID | [0009-0000-4196-0508](https://orcid.org/0009-0000-4196-0508) |
| Affiliation | Independent Researcher |
| Correspondence | via the PCI RR submission system |
| Level declaration | Prospective draws: **Level 6**. Completed preliminary studies: **outside the level scheme** (§9) |
| Code and data | <https://github.com/mikotomiura/powered-null>, at the tag <https://github.com/mikotomiura/powered-null/tree/stage1-submitted>, which is the state this manuscript was produced from. Development continues on the default branch, so the tag rather than the branch is what this manuscript refers to (§13) |
| Licence | Code: Apache-2.0 OR MIT. Manuscript and figures: CC BY 4.0 |
| Protocol status | No prospective draw has been collected. Data collection begins after in-principle acceptance (§11) |

---

## Abstract

An exponential moving average over an embodied language-model agent's recent movement modulates
the temperature used for its next generation. A completed forensic study establishes that this
channel is causal, is separable from the static location channel, and vanishes without residue
under ablation, while a positive control shows that the same estimator can return zero. A
completed measurement on a single model then found no shift in a five-way zone decision exceeding
the materiality margin fixed in advance: a mean total-variation distance of 0.038065 against a
margin of 0.10, obtained at full nominal power over 4,800 draws. This Stage 1 protocol estimates the
same quantity in a second model family, with a control arm that re-runs the original model to
absorb a backend version change. Thresholds, decision rules and outcome-neutral checks are fixed
before any prospective draw exists, and no directional expectation is stated.

---

## 1. Introduction

An embodied language-model agent is usually built by wiring a mechanism and then assuming the
mechanism matters. This study takes the assumption apart into two separable questions, and
addresses only the second.

The apparatus under study modulates decode-time sampling from an agent's recent movement
history: an exponential moving average over the agent's moves produces a scalar, and that scalar
composes into the temperature used for the next generation. The wiring question — *is this a real
causal channel, or an artefact?* — has already been answered in a completed preliminary study
(§3): the channel is causal, it is separable from the static location channel, and it vanishes
bit-for-bit under ablation, while a positive control shows that the same estimator can return
zero. The propagation question — *does that channel move the agent's downstream discrete
choices?* — is what this protocol addresses.

The subject of every claim in this manuscript is **the channel**. It is not walking, and it is
not creativity. The estimand is defined over a frozen bank of contexts and a five-way zone
decision; nothing in the design licenses a statement about human ambulation or about creative
production.

A completed run of exactly this measurement on one model returned a null under a pre-declared
materiality margin while retaining full nominal power (§5.1). A null of that shape is only worth
reporting if two things are true: that the instrument could have read a non-zero value, and that
the design could have detected one of the declared size. Both are addressed here by outcome-neutral
checks that are specified before any prospective draw exists (§10).

### 1.1 What this protocol estimates

Following PCI RR criterion 1B — *"The inclusion of hypotheses is not required – a Stage 1 RR can
instead propose estimation or measurement of phenomena without expecting a specific observation"*
— this is written as an estimation problem. We estimate, in a second model family, the magnitude
of the channel's downstream effect on a five-way categorical decision, and we compare that
estimate against a materiality margin that was fixed before any of the data existed. We do not
state a directional expectation about where the estimate will fall, and the decision rules in §8
are written so that every outcome category is an acceptable Stage 2 result.

### 1.2 What is new here, and what is not

Two things in this work are, to our knowledge, not already standard:

1. the estimand is *an agent-internal modulation acting on a downstream categorical choice*,
   rather than agreement between two models' output distributions; and
2. the demonstration that a near-uniform categorical substrate does not imply low detection
   power (§5.2), which runs against a common intuition.

Everything else is the deliberate application of existing practice. In particular, declaring a
materiality margin in advance for an equivalence-style reading of language-model evaluation is
already established [28]; this protocol follows that practice rather than originating it.

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

This section reports a completed preliminary study. Under PCI RR §2.6 the level scheme
*"do[es] not apply to any completed preliminary studies or pilot data that are reported at
Stage 1"*; §9 states the declaration explicitly.

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
(§12.5).

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
| `rho_hat` | R1–R5 | Fraction of contexts for which the substrate licenses at least two zones (apparatus validity) |
| `power` | R1–R3, R5 | Attained detection power of the realised design |
| `permutation_reject` | R1, R2, R5 | Outcome of the permutation test at the declared α |
| pooled `none_rate` | R4 | Fraction of draws yielding no parseable zone; compared against `none_rate_max` |
| `verdict` | R5 | The categorical verdict emitted by the scorer for the control arm |

No threshold is added by listing these: `none_rate_max` is already among the values in §6.3, and
`verdict` is categorical.

Stating this explicitly matters: a protocol that named only `tv_bar` would understate what the
Stage 2 decision actually depends on.

### 4.3 The margin is an interpretation rule, not a hypothesis

`delta_tv_min = 0.10` fixes, in advance, how an estimate will be read. It is not a prediction about
where the estimate will fall, and no directional claim is attached to it. Its function is to
foreclose the freedom to decide after the fact whether an observed distance is "small". The
practice of fixing such a bound before analysis is established [28, 36]; we follow it here.

### 4.4 Relation to equivalence testing — stated precisely

PCI RR §2.3 recommends frequentist equivalence testing where a study aims at evidence of absence.
We have considered it, and **this protocol does not perform formal TOST or Bayesian equivalence
testing.** What it performs is estimation, comparison against a materiality margin declared in
advance, and a power guard. **We do not call this formal evidence of equivalence**, and we do not
claim that our procedure is the recommended framework under another name.

The permutation test in §4.2 is a nil-null test. It can fail to reject; failing to reject is not
evidence of equivalence, and nothing in §8 treats it as such. No additional statistic and no
additional threshold is introduced anywhere in this protocol beyond the eleven values listed in §6.3.

---

## 5. Completed preliminary studies and pilot data

Everything in this section is completed work, reported under PCI RR §2.7, which states that
authors *"are welcome to include preliminary studies in their Stage 1 submissions ... or to
demonstrate the feasibility of their proposed methods"*. Under §2.6 these data are outside the
level scheme (§9).

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

### 5.2 Power worksheet: a near-uniform substrate does not imply low power

An a-priori categorical-multinomial power calculation, reproduced by
`analysis/scripts/power_curve.py` at the frozen seed, gives:

| Base distribution | `delta_tv` | Power |
|---|---|---|
| near-uniform `[0.2, 0.2, 0.2, 0.2, 0.2]` | `0.10` | `1.0000` |
| near-uniform `[0.2, 0.2, 0.2, 0.2, 0.2]` | `0.01` | `0.1842` |
| degenerate `[0.96, 0.01, 0.01, 0.01, 0.01]` | `0.01` | `0.9533` |
| degenerate `[0.96, 0.01, 0.01, 0.01, 0.01]` | `0.10` | `1.0000` |

The third row is the one that matters. Detection power is governed by the size of the shift being
looked for, not by how concentrated the base distribution is: a degenerate base with a
collapse-scale shift still attains `0.9533`. The `0.1842` figure belongs specifically to a
**near-uniform base with `delta_tv = 0.01`**, one tenth of the declared margin, and is quoted only
in that full form.

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
that rule R4 (§8) turns on a pooled rate crossing `0.5`; recording an exact rate would let a reader
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

| Check | What it protects | Declared pass criterion (fixed in advance) | Realised outcome |
|---|---|---|---|
| **R5** — control-arm concordance | That a change in backend version between the completed run and this one is not read as a family effect | The control arm reproduces the five quantities of §5.1 within the band given in §8 | **Unknown** |
| **R4** — apparatus validity | That the estimand is measurable at all in the primary family (absence of a floor) | `rho_hat ≥ 0.5` and pooled `none_rate ≤ 0.5` | **Unknown** |
| **R3** — attained power | That the estimate is not vacated by insufficient power | `power ≥ 0.8` | **Unknown** |

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
all permissible Stage 2 outcome categories, and the authors do not predict which will occur.**
R5 is evaluated first. The branch names are category labels, not expectations.

### R5 — control-arm concordance (evaluated first)

The control arm (`qwen3:8b`, re-run) **passes** when all of the following hold:

| Quantity | Pass condition |
|---|---|
| `verdict` | `== NO_CHANNEL_CONFORMANCE` |
| `rho_hat` | `>= 0.75` (that is, at least 6 of 8 contexts pass the validity condition) |
| `power` | `>= 0.8` |
| `tv_bar` | `< 0.10` **and** `\|tv_bar − 0.038065\| <= 0.03` (interval `[0.008, 0.068]`) |
| `permutation_reject` | `== False` |

- **R5 pass** → proceed to interpret the primary arm (R1–R4).
- **R5 fail** → **stop.** Report first that the control arm did not reproduce the declared band,
  naming which of the five quantities fell outside it. Only where the control arm's `verdict`
  itself differs do we report that the backend version change moved the verdict; a failure
  confined to the `tv_bar` tolerance or to `rho_hat` does not license that stronger statement.
  **The primary arm is not interpreted.**

The `rho_hat` bound of `0.75` is tighter than the `rho_min` of `0.5` used inside the verdict logic,
and tolerates variation in at most two contexts. The `tv_bar` tolerance of `0.03` is set against
the distance of `0.062` between the completed run's value and the materiality floor: a movement
larger than `0.03` consumes more than 48% of the margin's interpretive room and is treated as a
sign of version drift.

**What a pass states.** A pass states that the five quantities fall inside the declared band. That
is the whole of its content. It is not a statement about whether the backend upgrade changed
anything, and §12.2 records this limit.

### Primary-arm branches (evaluated only after R5 passes)

**R4 is evaluated before R1–R3.** The conditions below are stated exactly as pre-registered and are
not mutually exclusive as written; fixing the evaluation order removes the ambiguity without
altering any condition.

| Branch | Condition | Consequence for this paper |
|---|---|---|
| **R1 — replication** | `rho_hat >= 0.5` ∧ `power >= 0.8` ∧ `tv_bar < 0.10` ∧ `permutation_reject == False` | The null also holds in a non-Qwen natively non-thinking regime. The claim moves from "single model only" to "reproduced across two model families". The generality in the title is supported. **The gate that stays open (§12.1) is stated as a limitation.** |
| **R2 — non-replication** | `rho_hat >= 0.5` ∧ `power >= 0.8` ∧ (`tv_bar >= 0.10` ∨ `permutation_reject == True`) | The null is specific to `qwen3:8b` under the disabled-`think` regime. The central claim narrows to that apparatus and model, and "in embodied LLM agents" is removed from the title, which PCI RR §2.10 permits at Stage 2. **This is a finding, not a failure.** |
| **R3 — insufficient power** | `rho_hat >= 0.5` ∧ `power < 0.8` | `INCONCLUSIVE_UNDERPOWERED`. The result budget is not consumed. A re-run at larger *M*/*K* is sought separately. **No claim changes under this branch.** |
| **R4 — invalid apparatus** | `rho_hat < 0.5` ∨ pooled `none_rate > 0.5` | This is **not** read as `NO_CHANNEL_CONFORMANCE`. In the primary family the substrate does not license two or more zones, so **this estimand is not measurable in that family**. The claim narrows to single-model scope. |

### 8.1 Study design table

PCI RR asks for a study design template linking the research question to the sampling plan, the
analysis, and the interpretation fixed in advance for each outcome. The table below is that
template. **It introduces nothing.** Every cell restates §4, §5.2, §6, §7 or §8, and no threshold,
statistic, or claim appears here that is not already fixed there. Where the two could ever be read
as differing, the numbered sections govern.

**The hypothesis column is deliberately absent, not omitted by oversight.** PCI RR states that the
hypothesis column *"can be omitted where the study is not hypothesis-driven"*, and §1.1 writes this
study as an estimation problem under criterion 1B. No directional expectation is stated anywhere in
this protocol, so a hypothesis column could only be filled with something the design does not
contain.

The final column departs from the template's usual framing for the same reason, and we say so
rather than let the substitution pass unremarked. That column is ordinarily the theory the outcomes
could show wrong. Only the first row carries a claim of that kind; the remaining three are
outcome-neutral checks, and what they bear on is the admissibility of an interpretation rather than
a theory. The column is therefore headed by what each outcome bears on, and the first row answers
the template's question directly.

| Question | Sampling plan | Analysis plan | Rationale for the sensitivity of the design | Interpretation given different outcomes | What the outcome bears on |
|---|---|---|---|---|---|
| **Primary.** In a second model family (`llama3.1:8b`), what is the magnitude of the channel's downstream effect on the five-way zone decision — that is, what is `tv_bar` (§4.1)? | *M* = 300 draws per condition over the frozen bank of *K* = 8 contexts, both conditions, seed `20260708`: 4,800 model calls in the primary arm (§6.2). Read-out is the pre-bias destination zone. | Estimate `tv_bar` as the mean across contexts of the total-variation distance between the channel-on and channel-off five-way distributions (§4.1), then evaluate the decision function of §4.2 against the thresholds of §6.3 in the fixed order R5 → R4 → R1–R3 (§8). | The a-priori worksheet of §5.2 gives power `1.0000` at `delta_tv = 0.10` for a near-uniform base, and `0.9533` at `delta_tv = 0.01` for a degenerate base: what governs detection power is the size of the shift sought, not how concentrated the base distribution is. The power the realised design actually attains is not assumed — it is gated by R3. | **R1, R2, R3 and R4 exactly as written in §8.** All four are permissible Stage 2 outcomes; which occurs is not predicted, and the scope of claim each licenses is fixed there. Under R1 the confound of §12.1 is carried as a limitation rather than resolved. | Whether the channel shown in §3 to be causal, separable and ablatable propagates to a downstream discrete choice outside the model family in which it was measured. |
| **R5 — control-arm concordance (evaluated first).** Does `qwen3:8b`, re-run under ollama 0.32.12, reproduce the five quantities of §5.1 inside the band declared in §8? | Same *M* = 300, *K* = 8, same frozen bank and seed: a further 4,800 model calls, with `think` disabled as in §5.1 (§6.1). 9,600 calls in total across both arms. | Evaluate the five R5 pass conditions of §8: `verdict == NO_CHANNEL_CONFORMANCE`, `rho_hat >= 0.75`, `power >= 0.8`, `tv_bar < 0.10` together with `\|tv_bar − 0.038065\| <= 0.03`, and `permutation_reject == False`. | The `rho_hat` bound of `0.75` is tighter than the `rho_min` of `0.5` inside the verdict logic and tolerates variation in at most two of the eight contexts. The `tv_bar` tolerance of `0.03` is set against the distance of `0.062` between the completed run's value and the materiality floor (§8). | **Pass** → proceed to interpret the primary arm. **Fail** → stop, and report which of the five quantities fell outside the band; the primary arm is not interpreted (§8). A pass states band membership and nothing further (§12.2). | Whether the backend version change between ollama 0.31.1 and 0.32.12 moved the measured quantities outside the declared band. Only a differing `verdict` licenses the stronger statement that the version change moved the verdict. |
| **R4 — apparatus validity.** Is the estimand measurable at all in the primary family: does the substrate license at least two zones, and are draws parseable? | No additional collection. Evaluated on the same prospective draws as the primary row. | `rho_hat >= 0.5` and pooled `none_rate <= 0.5` (§7.2). Evaluated before R1–R3. | `rho_min = 0.5` and `none_rate_max = 0.5` are among the constants frozen before the completed run and checked mechanically (§6.3, §10.2). The Phase 0 pilot recorded parse and zone quantities only as three-level bands whose edges are deliberately not at `0.5`, so that pilot cannot anticipate this rule (§5.3). | **Fail** → R4: in the primary family the substrate does not license two or more zones, so the estimand is not measurable there and the claim narrows to single-model scope. This is **not** read as `NO_CHANNEL_CONFORMANCE` (§8). | Whether a floor effect, rather than an absent effect, accounts for a small estimate. |
| **R3 — attained power.** Does the realised design attain the declared detection power? | No additional collection. Evaluated on the same prospective draws as the primary row. | `power >= 0.8` (§7.2). | `power_min = 0.8` is frozen with the other constants (§6.3). The completed run attained `power` of `1.0` at these same values of *M* and *K* (§5.1), which is why the prospective design is run at those values rather than smaller ones. | **Fail** → `INCONCLUSIVE_UNDERPOWERED`. No claim changes, the result budget is not consumed, and a re-run at larger *M*/*K* is sought separately (§8). | Nothing is licensed about the estimand when this check fails. The branch exists so that a small estimate cannot be read as an absent effect by default. |


---

## 9. Level declaration and eligibility self-audit

### 9.1 Declaration

> **Draws collected prospectively — the 4,800 for the primary arm and the 4,800 for the control
> re-run — are declared at Level 6. Completed preliminary studies (§3, §5) fall outside the level
> scheme.**

This declaration rests on two clauses read together: PCI RR §2.6, *"these levels apply only to data
that form the focus of the prospective (planned) analyses ... and do not apply to any completed
preliminary studies or pilot data that are reported at Stage 1"*, and §2.7 on the admissibility of
preliminary and feasibility work. It is a reading we consider defensible; PCI RR does not state it
as a guarantee, and we do not represent it as one.

### 9.2 Eligibility

PCI RR §2.6 also states that PCI RR *"will not consider studies where the authors already know the
outcomes of the prospective (planned) analyses at the point of Stage 1 submission."* That clause is
about realised outcomes. Our answer is that **no realised outcome of any planned analysis is
known**, and the table below is our audit of that answer.

Three things must be kept apart when reading the R5 row. The **baseline** — the completed run of
§5.1 — is known, and is reported here in full. The **declared pass criterion** — the band in §8 —
is fixed in advance, which is what an outcome-neutral check requires. The **realised outcome** —
whether the control re-run under ollama 0.32.12 actually lands inside that band — is unknown,
because R5 exists precisely to detect a version drift whose presence or absence we have not
observed. The same three-way distinction applies to R4 and R3.

| Planned analysis | Role | Realised outcome known? | Basis |
|---|---|---|---|
| `tv_bar` in `llama3.1:8b` | A — primary estimand | **No** | Not one draw has been collected from this model under the measurement |
| Permutation test in `llama3.1:8b` | A — decision function | **No** | As above |
| Control-arm concordance on five quantities (R5) | B — planned QC | **No** — baseline known, expected declared, **realised unknown** | Whether version drift has occurred has not been observed |
| `rho_hat` and `none_rate` check (R4) | B — planned QC | **No** — but *full R4 outcome unknown; Phase 0 only pooled feasibility bands* | §5.3: the pilot observed pooled parse and zone bands, which are adjacent information, not the R4 outcome |
| Attained-power check (R3) | B — planned QC | **No** | No value of `power` exists for the primary family |
| Re-analysis of the completed run | **Not performed** | (baseline known) | Deliberately excluded from the planned analyses |

---

## 10. Outcome-neutral checks and the provenance of the thresholds

### 10.1 Outcome-neutral checks

PCI RR criterion 1E requires sufficient outcome-neutral conditions, and gives positive controls as
an example of such a condition. We read it that way: 1E does not make a positive control compulsory
for every study. What it does imply, and what matters here, is that an outcome-neutral check is one
whose pass criterion is settled in advance by construction — which is why stating those criteria
in §7.2 does not compromise the eligibility position in §9.2. Declaring what would count as a pass
is not the same as knowing what will be observed.

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
<https://github.com/mikotomiura/ERRE-Sandbox>, and `analysis/freeze-provenance.json` carries the
commit identifiers, the times, and the URLs.

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
the fixture fails the run.

---

## 11. Timeline and permitted deviations

Data collection begins only after in-principle acceptance. The two arms together require
approximately 5.09 h of compute on the recorded hardware (§5.3), and the run is executed once.

The following are **not** treated as minor deviations. If any becomes necessary, we will consult
the recommender before data collection is complete, as PCI RR §2.10 provides:

- substituting a different model for `llama3.1:8b`;
- changing the backend version;
- changing any of the threshold values in §6.3;
- changing the seed `20260708`;
- changing *M* or *K*;
- substituting the frozen context bank.

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

The ES-1 verdict record is not shipped (§3), and the 17.7 MB per-draw record of the completed run
is referenced by hash in `data/data.md` rather than included, to keep the repository small.

One further gap concerns the ES-3 forensic record of §3. Its bytes are verifiably identical to the
blob registered upstream, but the upstream commit that carries it is a **relocation** commit: the
record was produced in June 2026 in a directory that was outside version control, and entered the
repository in September 2026 when it was moved, byte for byte, into a tracked path. Version history
therefore witnesses the record's *content*, not its *age*. The three records of the completed run
in §5.1 do not have this gap — their upstream commit is the run itself. This asymmetry is recorded
in `analysis/freeze-provenance.json` and is printed by the verification script rather than left to
the reader to discover.

All three gaps are stated rather than worked around.

---

## 13. Data, code and reproducibility

**Everything this manuscript refers to is reachable from one place, pinned to one version.** The
repository is <https://github.com/mikotomiura/powered-null>, and the state this manuscript was
produced from is the tag `stage1-submitted`:

> <https://github.com/mikotomiura/powered-null/tree/stage1-submitted>

Work continues on the default branch after submission, so every path named below should be read at
that tag rather than on the branch. The upstream source repository the apparatus and the provenance
records come from is <https://github.com/mikotomiura/ERRE-Sandbox>, and §10.2 gives the commit
identifiers within it. There is no separate supplementary archive: the data, the analysis scripts,
the apparatus and the reproduction command are all in the repository named here.

This repository contains the frozen inputs of the completed studies (`data/raw/`, each pinned by
SHA-256 and size in `data/data.md`), the analysis scripts (`analysis/scripts/`), and the measurement
apparatus as an import closure of 69 modules (`analysis/apparatus/`) reproduced byte-for-byte from
the upstream source repository. That closure covers the scoring and power machinery, which is what
the analyses in this repository exercise; it does not include the live driver that produced the
draws, since regenerating draws is out of scope here (§6.2).

`bash repro.sh` performs, in order: environment installation from the lockfile; a lint check;
verification of the frozen inputs against both `data/data.md` and their upstream blobs;
verification of the threshold freeze and of the whole apparatus closure; **recomputation of the
completed run's verdict from the shipped annotation and manifest**; mechanical extraction of the
quantities quoted in §3 and §5.1; regeneration of the power table of §5.2; a character-level
comparison of the numbers quoted in this manuscript against the frozen inputs they come from; and
the claim-boundary check of §10.3. It exits non-zero if any step fails.

The recomputation step is the strongest of these. Every other step compares a record against a
shipped file; this one runs the scorer on the shipped per-draw annotation, at the sealed
Monte-Carlo settings, and requires the resulting verdict string, all nine gate read-outs and all
four per-context maps to agree with `data/raw/cproper-verdict.json`. The whole of §5.1 is therefore
derivable from this repository rather than merely quoted from it. It takes under two seconds.

The eighth step is what turns "these numbers were not transcribed by hand" from an assurance into
a check: it reads each quantity from the frozen JSON by key and requires the resulting literal to
appear in this manuscript, and -- for the subset the repository README quotes -- in that README
too. Its scope is bounded twice over, and we state both bounds rather than let the check sound
stronger than it is. It covers only the quantities obtainable mechanically from the frozen
inputs; numbers outside that set are not covered at all. And within that set it tests
**occurrence, not uniqueness**: several of these values appear at more than one point in this
manuscript, so altering one occurrence while leaving another intact would not fail the run. An
earlier version of this section said that a single altered digit fails the run, which is true
only of a quantity that occurs exactly once, and the check does not determine which those are.

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

This work was developed with substantial AI assistance, disclosed here in full under PCI RR §2.28.

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
| Upstream source, <https://github.com/mikotomiura/ERRE-Sandbox>, at commit `f23f179` | 301 | **201** |
| This repository, at commit `02a40c0` | 7 | **6** |

Trailers are counted **case-insensitively, as commits rather than as trailer lines**. The
distinction is not pedantry: the upstream history carries 276 such lines across those 201 commits,
because a single commit may carry more than one, and a count of lines reported as a count of commits
would overstate the figure by a third.

All AI-assisted output was reviewed, edited and validated by the human author, who made the
decisions that determine what this protocol claims: the choice of estimand and of the materiality
margin, the decision rules R1–R5 and the order in which they are evaluated, the level declaration
of §9, the scope of every claim and of every limitation in §12, and the decision to submit this
protocol before collecting the prospective data. Validation is not self-reported: the numerical,
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

Reference numbers are permanent identifiers assigned in the author's central bibliography and are
not renumbered between manuscripts.
