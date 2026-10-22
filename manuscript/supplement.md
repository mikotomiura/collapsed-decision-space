# Supplementary Material

**Three gates, three proxies: auditing the null-report checks of a pre-registered LLM-agent evaluation**

This document holds the lettered sections that the paper cites but does not carry. Section numbers
§1 to §7 refer to the paper; §E and §K are appended to the paper itself. The works cited here are
listed in the paper's reference list.

The sections hold three kinds of material. §C, §D and §F to §H are the record of the sealed
protocol beside its decision rules (§E, in the paper): its design, analysis plan, eligibility
audit, checks and seal. §A, §B and §M hold further results: the channel study, the completed
preliminary studies and pilot, the simulation of the sealed pipeline, and further results of the
prospective run. §I, §J and §L hold further limitations, the reproduction path and the section
numbers that frozen files cite; §N discusses further related work, and §O states ethics, funding
and interests.

## A. The apparatus and the channel (completed preliminary study)

This section reports a completed preliminary study. It is not among the prospective analyses,
and no rule in §E reads it except for the one constant named in §B; §F audits that separation
quantity by quantity.

The agent moves on a discretized world. An exponential moving average over its recent moves yields
a scalar λ, and λ composes into the temperature used for the next generation. A forensic run
(`data/raw/es3-verdict-forensic.json`) established the properties of this channel. All values below
are extracted mechanically by `analysis/scripts/extract_verdict_table.py`; none are transcribed by
hand.

| Quantity | Value | What it says |
|---|---|---|
| `verdict` | `GO` | The channel is eligible to carry a downstream measurement |
| `d_loco` (the point estimate) | `0.04682681825722385` | Within-cell locomotion amplitude, normalized by headroom |
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
therefore characterize the estimator's sensitivity; they are not controls that produce a null, and
we do not present them as such. The control that does produce a null is the zone-function positive
control above.

**A second completed preliminary study (ES-1, a structured-probe determinism measurement) measured
the upstream determinism property of the same apparatus.** Its machine-readable
verdict record was not retained as a shipped artifact and is therefore not included in this
repository. Because this manuscript quotes only numbers that the extraction script can produce from
shipped data, no ES-1 quantity is quoted here. This is recorded as a provenance limitation
(§I.4).

---

## B. Completed preliminary studies and pilot data

Everything in this section is completed work. It is reported here because the protocol of §C-§E
is unreadable without it: §2.2 is the measurement the prospective arms repeat, §B.1 is the power
worksheet the sampling plan rests on, and §B.2 is the feasibility evidence that the second arm can
be run at all. None of it is re-analyzed as part of the prospective plan, and §F states, per
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
| per-context entropy H(zone \| c) | `0.628287` – `0.754149` bit |
| per-context TV distance | `0.010227` – `0.054712` |
| model digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |

Table: The record of the completed run, as the scorer wrote it.

The completed run of §2.2 is the study that motivates the present protocol. It was executed under the thresholds listed
in §C.4, which had already been frozen upstream before it ran; §G.2 gives the provenance and the
scope of what that provenance establishes. The completed run is therefore not the origin of those
values.

It is reported in §2.2 and §3 to §5, and it is **not** re-analyzed as part of the prospective plan. One
value of this record does enter §E, and we state it rather than leave it implicit: `tv_bar =
0.038065` is the pre-declared center of the R5 tolerance band. It enters as a fixed constant
settled before any prospective draw exists, not as data to be re-analyzed, and no other quantity
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

The third row is the one that matters for the surrogate. At the registered shift both bases return
`1.0000`, so there a pass does not tell a collapsed base from a spread one; at a tenth of it the two
part, and the degenerate base still attains `0.9533`. The `0.1842` figure
belongs specifically to a **near-uniform base with `delta_tv = 0.01`**, one tenth of the declared
margin, and is quoted only in that full form. The first and fourth rows are the ones §3
relies on: at the registered `delta_tv` the surrogate returns `1.0000` for both bases. All four rows
are properties of the surrogate; none of them is the power of the permutation test the decision
turns on (§3). That concentration is not what lowers the computed power follows from the form of
the statistic, which cells with small expected counts dominate (Balakrishnan & Wasserman, 2018).

**The sweep against the completed run's base.** §3 quotes one value of this sweep. Against the
completed run's channel-off base, whose two empty cells §4 describes, the same surrogate behaves
almost as a test of whether any draw lands in a zone that was never seen, because the alternative
moves mass into an empty cell. The sweep below is recomputed by
`analysis/scripts/collapse_and_floor.py` on every reproduction run:

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

The surrogate clears 0.8 at one hundredth of the margin that the study declared material.

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
| Disk | model 4.92 GB; projected artifacts ≈ 37 MB |

Table: The feasibility pilot for the second model.

**Parse quantities are recorded as three-level bands, not as rates.** The bands are `< 0.2`,
`[0.2, 0.8)` and `≥ 0.8`, and the band edges are deliberately not placed at `0.5`. The reason is
that rule R4 (§E) turns on a none-rate crossing `0.5`; recording an exact rate would let a reader
— and the authors — anticipate that rule's outcome. The bands are reported at the resolution that
answers the feasibility question and no finer. This resolution is not reduced later: the exact
rates are not restored anywhere in this manuscript.

No parse or zone quantity was collected for the reference model in the pilot, because that model is
the control arm of the prospective design and observing its parse behavior would be observing a
component of R5.

---

### B.3 Simulated operating characteristics: declaration, design and every declared cell

**[Post hoc]** This subsection holds the detail of §3.

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
empty zones in equal parts, or, on a base with no empty zone, into the two smallest cells other than
the one the mass leaves, as declared; and a mixture that moves in opposite directions in two halves of the
contexts. Every context is moved by the same total variation `delta_tv`, one of 0, 0.01, 0.02,
0.03, 0.04, 0.05, 0.075, 0.10 and 0.15. A direction a context cannot supply at a given size is
reported as infeasible rather than clipped. The draws with no zone are held at the counts of the run
the base comes from, so R4's condition on them does not fire anywhere in the grid. Each replicate
builds an annotation of the shipped shape, passes it to the vendored scorer with its defaults, and
applies the sealed rules R4, R3, R1, R2 to the result through the sealed evaluator; R5, which reads
the control arm, is left out. The grid comes to 117,000 scorer calls.

**Rates.** `P(R2)` is reached through a permutation reject or through `tv_bar` ≥ 0.10, and R4 or R3
can stop evaluation before either is read. Each rate is a count out of the replicates, 4,000 under
the null and 1,000 (base `C`) or 500 (other bases) per shifted cell, with a Wilson 95% interval and
the label declared for it. The counts were declared with the grid, not derived from a target Monte
Carlo error; at them the interval lies within about 0.007 of a rate near 0.05 under the null, and
within about 0.044 (500) or 0.031 (1,000) of any rate per shifted cell. On the degenerate base `G`, D4 and D6 are
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

At the registered shift on the completed run's base, the pipeline reaches R2 in 1,000 of 1,000
replicates in each of the four feasible directions (D1, D2, D3, D5), and the test alone rejects in
1,000 of 1,000; D4 and D6 are infeasible there, because one context holds less than 0.10 in `garden`.
These are not four independent confirmations: the replicates share their channel-off draws, and D1
and D5 give identical statistics there from `delta_tv` = 0.05 upward. The two rates are not computed on the
same contexts. The pipeline's test runs on the contexts the entropy floor admits; the test alone runs
on all eight. Where all eight are admitted the two are the same call, and where they are not the
two can differ: at `C|D1|0.02`, two replicates admitted seven contexts, the pipeline's test did not
reject on those seven, the test alone rejected on all eight, and P(R2) is 390 where P(test_reject)
is 392. Along D1, as the table shows,
the test's rejection rate equals the surrogate's 1.0 from `delta_tv` = 0.05 upward along the
surrogate's direction and is below it at smaller shifts. At the registered shift the test's rate
reaches 0.8 in every base and direction the declared grid runs at that size, which is not every
direction on every base.

Two observations bear on §4. Filling the completed run's two empty zones (`Cs`) moves the shift at
which the test reaches 0.8 by at most one grid step, so the empty zones matter to the surrogate's
calculation more than to the test that decides. On the degenerate base, whose entropy is below the
floor, the test alone already rejects in most replicates at a shift where the pipeline stops at R4.
The primary arm's own base is simulated separately, in §B.5.

The smallest declared `delta_tv` at which each rate reaches 0.8, as a point estimate and as the lower
limit of its interval, for every base and direction the grid declares (on `K`, only D1 and D3) (D1 the surrogate's direction, D2 to the smallest
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
what the model does. The surrogate's sweep in §B.1 does not depend on the numerical floor under
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

### B.4 What the record of the dropped draws does not show, and the prompts

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
repository re-parses the two prospective arms as well, whose records are shipped too
(§I.5). The template quoted in §5 is at `analysis/apparatus/erre_sandbox/cognition/prompting.py`,
lines 48 and 71.

Every draw of the three runs was sent the same two prompts, given here as the per-draw records carry
them; the Japanese characters are part of the prompt as sent. The system prompt:

```text
You are an autonomous agent living in ERRE-Sandbox, a 3D world with five zones (study / peripatos / chashitsu / agora / garden). Each tick represents ten seconds of wall-clock time. Respond in character, following the cognitive habits of the persona described below. The ``utterance`` field MUST be written in Japanese (日本語) so the researcher observing the 3D scene can read it at a glance — original-language key terms (Kant のドイツ語/ラテン語, Nietzsche のドイツ語など) may appear parenthetically inside the Japanese sentence. Keep utterances under 80 Japanese characters.

Persona: Bank Neutral Agent (n/a).
Personality (Big Five, [0,1]): openness=0.50 conscientiousness=0.50 extraversion=0.50 agreeableness=0.50 neuroticism=0.50.
Aesthetic sensibility: wabi=0.50 ma_sense=0.50.
Preferred zones: .
Cognitive habits (fact / legend / speculative):


Current tick: 0.
Location: agora. ERRE mode: shallow.
Physical — sleep_quality=0.70, physical_energy=0.70, fatigue=0.00, cognitive_load=0.20.
Cognitive — valence=0.00, arousal=0.00, motivation=0.50, stress=0.00.
```

The user prompt:

```text
Recent observations:
[affordance] bank_cue_prop#bank-cue-study in study (distance=3.0m, salience=0.60)
[zone_transition] agora -> study
[affordance] bank_cue_prop#bank-cue-garden in garden (distance=3.0m, salience=0.60)
[zone_transition] agora -> garden

Relevant memories:
- [episodic strength=0.60] a vivid recollection formed while lingering near study
- [episodic strength=0.60] a vivid recollection formed while lingering near garden
- [episodic strength=0.50] [affordance] bank_cue_prop#bank-cue-study in study (distance=3.0m, salience=0.60)
- [episodic strength=0.50] [zone_transition] agora -> study
- [episodic strength=0.50] [affordance] bank_cue_prop#bank-cue-garden in garden (distance=3.0m, salience=0.60)
- [episodic strength=0.50] [zone_transition] agora -> garden

Decide what to do in the next ten seconds.

Respond with a SINGLE JSON object matching this schema (all deltas in [-1.0, 1.0], importance_hint in [0.0, 1.0]; use null for optional fields you intentionally skip). The last three keys (salient / decision / next_intent) are the reasoning trace shown to the researcher observing you — keep each under 80 characters of natural Japanese and be honest about why you act; leave them null only if genuinely not applicable:
{
  "thought": "internal monologue",
  "utterance": "speech bubble text or null",
  "destination_zone": "study|peripatos|chashitsu|agora|garden|null",
  "animation": "walk|idle|sit_seiza|bow|null",
  "valence_delta": 0.0,
  "arousal_delta": 0.0,
  "motivation_delta": 0.0,
  "importance_hint": 0.5,
  "salient": "what you found most salient this tick or null",
  "decision": "the one-sentence reason for your action or null",
  "next_intent": "what you plan to do next or null"
}
Return ONLY the JSON object. No prose outside the braces.
```

### B.5 What the entropy floor withheld on the primary arm's base

**[Post hoc, declared before it ran]** The simulation of §B.3 left the primary arm's base out. This
one was declared after both prospective arms had been seen and after an internal pre-submission
review of this manuscript asked what a pipeline admitting contexts by
support would have done on that base. Its grid, seeds, replicate counts and reading rules,
including the sentence the paper may write in each case, are in `analysis/autopsy-primary/grid.json`
and `DECLARATION.md`, committed at `074e000`, which the tag `autopsy-primary-declared` points at, and
pushed before the first full run. That the push preceded the run is recorded by the repository
host's timeline, not by any check. Before the declaration two computations touched this base: the
count of the primary arm's channel-off draws by zone that §4 reports, and the script's self-test,
which checks which cells are feasible and that the sealed floor is restored after the call that
replaces it, scores one synthetic annotation for that purpose without reporting it, and computes no
declared cell. `analysis/autopsy-primary/simulate_primary.py --run` and `--render` refuse to start
unless every declared file is byte-identical to its copy at that tag. Every declared cell is in
`data/posthoc/primary/summary.md`, rendered from the per-replicate record
`data/posthoc/primary/replicates.tsv`.

**Design.** The base is the primary arm's per-context channel-off distribution (base `P`). The
directions, deltas, roles and sampling of draws are those of §B.3, by reference, with 4,000
replicates under the null and 500 per shifted cell. Two pipelines and one test are applied to the
same draws: the sealed pipeline; the same pipeline without the floor, in which the scorer's entropy
floor is replaced, for that call only, by 1e-9, so that a context is admitted when its pooled draws
occupy two or more zones; and the permutation test on all eight contexts. Every context of base `P`
occupies two or more zones, so the pipeline without the floor admits all eight contexts in every
replicate but five, all at D6 and 0.02, which admit seven;
the declaration and the rendered summary call it the support gate. It was chosen knowing that every
cell of the primary arm produces two or more zones (§4). The primary arm's channel-on draws are not
read. D4 is feasible only at 0.01 and D6 only up to 0.02, because one context holds too little mass
in the cell they move from. As in §B.3, a replicate's draws are shared across the directions and
shifts, so the four directions at the registered shift are not independent confirmations; the scorer
permutes with one fixed seed, so replicates share their permutations too, and the Wilson intervals
do not allow for that; and the zones the
base leaves empty are read as exact zeros; D5 moves mass into those zones.

**Results.** Under the null the sealed pipeline stops at R4 in 4,000 of 4,000 replicates; the
pipeline without the floor reaches R2 in 187/4000 = `0.04675` [0.040632, 0.053738], compatible with
0.05, and the test alone rejects in the same 187/4000, compatible. At the registered shift:

| Direction | P(test_reject) | P(R2), without the floor | P(R4), sealed | P(R2), sealed | Sealed branches |
|---|---|---|---|---|---|
| D1 | 500/500 = `1.0` [0.992376, 1.0] | 500/500 = `1.0` [0.992376, 1.0] | 353/500 = `0.706` [0.664617, 0.744242] | 147/500 = `0.294` [0.255758, 0.335383] | R4 353, R2 147 |
| D2 | 500/500 = `1.0` [0.992376, 1.0] | 500/500 = `1.0` [0.992376, 1.0] | 452/500 = `0.904` [0.875013, 0.926826] | 48/500 = `0.096` [0.073174, 0.124987] | R4 452, R2 48 |
| D3 | 500/500 = `1.0` [0.992376, 1.0] | 500/500 = `1.0` [0.992376, 1.0] | 500/500 = `1.0` [0.992376, 1.0] | 0/500 = `0.0` [0.0, 0.007624] | R4 500 |
| D5 | 500/500 = `1.0` [0.992376, 1.0] | 500/500 = `1.0` [0.992376, 1.0] | 49/500 = `0.098` [0.074924, 0.127206] | 451/500 = `0.902` [0.872794, 0.925076] | R4 49, R2 451 |

Table: The primary arm's base at the registered shift, per feasible direction. Rates are k/n with Wilson 95% intervals; the pipeline without the floor ends at R2 in all 500 replicates of each direction.

Without the floor every replicate at the registered shift reaches R2 through a permutation
rejection. The pipeline without the floor first reaches 0.8 at `delta_tv` = 0.02 along D1, D2, D5 and D6 and
at 0.03 along D3. Along D5 the shift moves mass into the zones the base leaves empty, which raises
the pooled entropy the floor reads, and from 0.075 upward the sealed floor stops fewer replicates.

The declared reading rule puts the result in its case C, which the declaration states as "(C)
otherwise the text reports the directions one by one and makes no summary statement." Under every
case it requires that "the comparison is between two pipelines on an assumed truth taken from the
primary arm's channel-off draws, at the declared directions, deltas and numbers of draws only." The
paper accordingly gives the four directions one by one, here and in §4, and states nothing that
summarizes what the firing withheld.

## C. Prospective design

### C.1 What this protocol estimates

The sealed protocol is written as an estimation problem rather than a hypothesis test: it
estimates, in a second model family, the magnitude of the channel's downstream effect on a five-way
categorical decision, and compares that estimate against a materiality margin fixed before any of
the data existed. We state no directional expectation about where the estimate will fall, and the
decision rules in §E are written so that every outcome category is an acceptable result.

The second arm had a second purpose, given that the completed run's channel-off draws never produce
two of the five zones (§4), and it is worth naming because it changes what the arm is for. If
the same collapse appears in a different model family running the same harness, the collapse is
more plausibly a property of the apparatus -- the prompt, the parser, the zone vocabulary -- than of
any model. If it does not appear, the completed run's numbers are specific to that model in a way
§4 could not establish on its own. Either way the second arm is informative, which is not
something we could have said of a replication attempt whose only purpose was to see the null again.

Neither of those two cases is what occurred. The sealed rules stopped at R4 in the second family,
where the scorer admitted no context and produced no estimate, so the arm reached neither side of
the disambiguation set out here, and the question remains open. What the arm did show is the second
gate at work (§4): the entropy floor fired on an arm each of whose cells produced two or more
zones.

### C.2 Arms

| Arm | Model | Role | `think` regime |
|---|---|---|---|
| **control** | `qwen3:8b` (re-run) | Absorbs the backend upgrade from ollama 0.31.1 to 0.32.12, so that a change of model family is not read together with a change of platform version | disabled, as in §2.2 |
| **primary** | `llama3.1:8b` | Cross-family replication in a natively non-thinking model | none natively; the harness's disabled-`think` request is accepted (the pilot established acceptance, not behavioral inertness) |

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

§A, §B and the completed run of §2.2 are completed work. They are reported, not re-analyzed. The single point of contact with
§E is the one named in §B: the completed run's `tv_bar` fixes the center of the R5 tolerance band
as a pre-declared constant. No rule in §E re-analyzes any of this material.

---

### D.4 The quantities the sealed rules read, and how the rules are held

The rules themselves are in §E of the paper. This subsection says what each quantity they read is,
and what the arrangement of §E does and does not establish.

| Quantity | Read by | Role |
|---|---|---|
| `tv_bar` | R1, R2, R5 | The primary estimand; compared against the materiality margin |
| `rho_hat` | R1–R5 | Fraction of contexts whose per-context entropy of the zone distribution, pooled over both conditions with unparseable draws excluded, reaches `h_min_bits` (apparatus validity). It reads entropy, not the number of zones produced; §4 shows the two coming apart in both directions |
| `power` | R1–R3, R5 | Monte-Carlo power of a pooled one-sample chi-square goodness-of-fit test against an alternative built by moving mass from the largest to the smallest cell of the empirical channel-off distribution: the nominal sensitivity of a surrogate diagnostic. **This is not the power of the permutation test that produces `permutation_reject`**, which is the test the decision actually turns on; the two use different statistics and are not interchangeable, and §3 simulates the second post hoc. At the registered `delta_tv` it is 1.0 for both bases §B.1 checks, near-uniform and degenerate, so a pass does not distinguish them; §3 shows its sensitivity when a cell of the base is empty |
| `permutation_reject` | R1, R2, R5 | Outcome of the permutation test at the declared α |
| `none_rate_max_observed` | R4 | The apparatus computes the fraction of draws yielding no parseable zone **per (context, condition) cell** and records the maximum across cells. No pooled figure is produced anywhere in the run output, so the maximum is the quantity R4 is evaluated on. The sealed text's word "pooled" names a quantity the run output does not contain. The scorer independently returns `INCONCLUSIVE` if any single cell exceeds `none_rate_max`, so R4's second condition partly duplicates a gate upstream of it. It caps the rate in any one cell; it does not read how the rate differs between the conditions (§5) |
| `verdict` | R5 | The categorical verdict emitted by the scorer for the control arm |

Table: The six quantities the sealed rules read.

No threshold is added by listing these: `none_rate_max` is already among the values in §C.4, and
`verdict` is categorical.

Stating this explicitly matters: a protocol that named only `tv_bar` would understate what the
decision after the run actually depends on.

The rules of §E are **not predictions.** They are decision rules, fixed in advance, that determine
which scope of claim an estimate may be mapped onto once it is obtained. **R1, R2, R3 and R4 are
all permissible outcomes, and the authors do not predict which will occur.** The branch names are
category labels, not expectations.

**The rules in §E are not written there by hand.** They are generated from `seal/decision-rules.json`, the
sealed machine-readable statement of them, by `analysis/scripts/render_decision_rules.py`, and step
12 of `repro.sh` fails if the block in the paper is not what that file renders to. This is
the whole of the pre-registration's mechanical content, and it is worth saying why it is arranged
this way. A protocol whose rules exist only as prose can be re-read after the data arrive, and
nothing catches it unless a third party holds the rules. There is no such third party here, so the rules are held instead by three checks that do not require one: the sealed
bytes (step 12), the generated text of §E (step 12), and the evaluator that applies the rules to
the recorded quantities and reports the branch it reaches (§J). None of the three establishes
*when* the rules were fixed. What they establish is that the branch reported after the run follows
from the rules as they stand in §E.

One word of the block needs a pointer. The estimand drops "unparseable" draws,
meaning every draw whose recorded destination is `None`. §5 shows what those draws are: in the
completed run the word is exact for all 330 of them, and in the prospective arms for all but
two of the 418, the other two being a JSON `null` and an absent destination key, which the parser
treats as an empty destination rather than an error.

**What an R5 pass states.** A pass states that the five quantities fall inside the declared band.
That is the whole of its content. It is not a statement about whether the backend upgrade changed
anything, and §I.1 records this limit.

## F. Eligibility: what is known at seal time, and what is not

A protocol is pre-registered only for the outcomes its authors do not already know. That is a
statement about **realized outcomes**, not about data: a completed measurement may be reported in
full, at any length, without any realized outcome of a planned analysis being known. The audit
below is our answer to the question a reader is entitled to ask — *which of these did you already
have?*

Three things must be kept apart when reading the R5 row. The **baseline** — the completed run of
§2.2 — is known, and is reported here in full. The **declared pass criterion** — the band in §E —
is fixed in advance, which is what an outcome-neutral check requires. The **realized outcome** —
whether the control re-run under ollama 0.32.12 actually lands inside that band — is not known at
seal time, because R5 exists precisely to detect a version drift whose presence or absence has not
been observed. The same three-way distinction applies to R4 and R3.

The table is written in two tenses on purpose. The third column is a fact about the **sealed
state**, and it does not stop being true when the run completes. The fourth says what is reported
**after** the run, whichever way each analysis falls. A table with a single "not yet known" column
would contradict itself the moment the arms were executed; this one does not have to be rewritten
to stay honest.

| Planned analysis | Role | Realized outcome known at seal time? | Reported after the run |
|---|---|---|---|
| `tv_bar` in `llama3.1:8b` | A — primary estimand | **No.** At the moment of sealing, not one draw had been collected from this model under the measurement | The estimate, and the branch of §E it selects |
| Permutation test in `llama3.1:8b` | A — decision function | **No.** As above | `permutation_p_value` and `permutation_reject`, and their effect on the branch |
| Control-arm concordance on five quantities (R5) | B — planned QC | **No** — baseline known, band declared, **realized unknown**: whether version drift has occurred has not been observed | All five quantities, and which of them fell outside the band if any did |
| `rho_hat` and the per-cell maximum `none_rate` (R4) | B — planned QC | **No.** The Phase 0 pilot observed pooled parse and zone bands, which are adjacent information, not the R4 outcome (§B.2) | Both quantities, against the R4 condition |
| Attained-power check (R3) | B — planned QC | **No.** No value of `power` exists for the primary family | The attained `power`, against `power_min` |
| Re-analysis of the completed run | **Not performed** | (baseline known) | Nothing: it is excluded from the planned analyses and stays excluded |

Table: What was known at seal time, analysis by analysis.

The last row is a statement about the plan, and it stays true of the plan. Re-analyses of the
completed run are reported outside the plan, as the post hoc layer of §2.5 (§3, §4 and §5).

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
| run artifact `verdict.json` of the completed study | `6cbffcb3191059d3c72bd4bd97670ea26d6cbaa1` — the only commit ever to add this file | 2026-07-10T12:25:06Z |

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
canonicalization, and step 12 of `repro.sh` fails if any of them has moved since (§J). What that
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
pre-registration lapses — not a license to change the rules and carry on.

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
models, logit access lowers the number of queries an estimate needs, compared with sampling (Price et al., 2026);
how much it would lower the cost of this decision-level distance is not examined here. This is a
constraint of the deployment, and it sets the cost of the design.

### I.3 Bounded envelope

Every claim is bounded by a single apparatus, thinking disabled or absent in every run, one frozen prompt
run in eight pairs of blocks (the frozen bank of eight contexts, §2.2), and a five-way zone decision. The subject is the channel described in §2.1. Nothing
here is a statement about human ambulation, about creative production, or about whether embodiment
matters in general.

### I.4 Provenance gaps we are carrying

The ES-1 verdict record is not shipped (§A). The per-draw record of the completed run is shipped byte for byte in
`data/completed/`, checked by step 3 against its size and digest in `data/data.md` and against the digest the run's own manifest
pinned, and re-parsed as §5 describes.

One further gap concerns the ES-3 forensic record of §A. Its bytes are verifiably identical to the
blob registered upstream, but the upstream commit that carries it is a **relocation** commit: the
record was produced in June 2026 in a directory that was outside version control, and entered the
repository in September 2026 when it was moved, byte for byte, into a tracked path. Version history
therefore witnesses the record's *content*, not its *age*. The three records of the completed run
in §2.2 do not have this gap — their upstream commit is the run itself. This asymmetry is recorded
in `analysis/freeze-provenance.json` and is printed by the verification script rather than left to
the reader to discover.

Both gaps are stated rather than worked around.

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
that commit is not recorded, and this repository does not check it. At that commit the order of the
conditions (§7.2) is fixed by the loop at lines 276–284 of
`src/erre_sandbox/integration/embodied/bank.py`, with the condition order `("on", "off")` at line
118, and the file is unchanged there since before the completed run. What the files cannot show is that no
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
if the recorded summary stops following from the map it summarizes. It evaluates R4's sealed
predicates — read from `seal/decision-rules.json`, not restated in the checker — against all three
records, so the reading above fails if any of them comes to stand differently. And it requires the
zones of probability zero to be *named* in this manuscript, because `agora` and `chashitsu` are
distinctive enough for an occurrence test while "two of five" is not. Twelve mutations and one
positive control are run against copies of the real records on every reproduction, three of them
against the sealed rule itself, so a checker that had quietly stopped reading the seal would be
reported rather than pass. The rows of the tables in §4 and §5 are held by the rendered
comparison described in §J.

One thing is still outside all of it: the prose in §B.2, the timings and digests of the pilot,
exists in no shipped record at all, as §4 of `manuscript/CLAIM-BOUNDARY.md` states.

### I.6 What the post hoc simulation adds to the reading of R3

The sweep of §B.1 has two consequences for what a pass of R3 can be read as. At the registered `delta_tv`, the
surrogate returns `1.0000` for both bases §B.1 checks, near-uniform and degenerate, so a pass does
not distinguish a collapsed base from a spread one; only those two bases were checked, and nothing
here says what the surrogate returns for bases in general. And against the completed run's
channel-off base, whose empty cells §4 describes, it clears its `0.8` threshold at effect sizes
two orders of magnitude below the declared margin. R3 is retained as a planned check, and its
failure would still be consequential, but a **pass** of R3 is not read here as evidence about the
power of the decision the design makes. We state that rather than let the word "power" carry a
weight the number cannot bear.

**[Post hoc]** What the simulation of §3 adds holds for the bases and directions it declared and
for no others (§3, §B.3, §B.5). It does not change how a pass of R3 is read here: a figure that
agrees with the test at one effect size and not at others does not measure it. And the simulation
is a property of the design under assumed distributions; it does not bear on the completed run's
estimate (§3; Hoenig & Heisey, 2001, on why a power figure computed at an observed effect cannot
interpret a non-significant result).

### I.7 What would distinguish a shared collapse from a replication

The prospective design does not resolve this, and no rule in §E attributes the agreement either
way. We name it in advance so that an R1 outcome is not read as more than it is. Distinguishing the
two would need the read-out varied -- a different zone vocabulary, a different parser, a different
bank -- which is outside this protocol and is not a change we may make to it (§H).

## J. Data, code and reproducibility

**Everything this manuscript refers to is reachable from one place,** except the pilot's timings
and digests of §B.2, which exist in no shipped record (§I.5). The repository is
<https://github.com/mikotomiura/collapsed-decision-space>. Work continues on its default branch, so
a path named below is in general a moving target — with one exception, and it is the exception that
carries the pre-registration. The files listed in §H are sealed by content: `seal/SEAL-MANIFEST.json`
records their SHA-256 and a self-hash over itself, and step 12 below fails if the checkout in front
of you does not hold exactly those bytes. **The pin is a hash, not a branch name and not a tag.**

The upstream source repository the apparatus and the provenance records come from is
<https://github.com/mikotomiura/ERRE-Sandbox>, and §G.2 gives the commit identifiers within it.
Apart from the archival deposit of the sealed files described below, there is no separate
supplementary archive: the data, the analysis scripts, the apparatus and the reproduction command
are all in the repository named here.

**Only the paper's source is maintained; every other form of it is derived and read back.** The
`.docx` submitted to this journal is built from `manuscript/main.md` by
`analysis/scripts/make_docx_source.py` with pandoc 3.5. Its citations and its reference list are set
from `manuscript/refs.json` by pandoc's citeproc, in the APA style of the Citation Style Language
project (vendored in `manuscript/docx/` and pinned there by SHA-256), and its three figures are drawn
by `analysis/scripts/make_figures.py` from the shipped data, each typeset on its own and read back
for its numbers before it is converted to an image. The conversion records every change it makes:
the title page and the Author Note, which take the author table and the AI-use disclosure of §K,
the citations, the reference list, the labels of the figures and tables, each figure's caption set
as a title above the figure and a note below it, and what it leaves out.
`analysis/scripts/check_docx_text.py` then reads the `.docx` back. It enumerates the same changes
from the inputs on its own and checks each against the file, compares the rest of the text with the
source word for word, and requires each figure's picture to be the image recorded for that figure;
copies of the file broken one way at a time must each be reported for what was broken. The manual
`apa-docx` workflow performs all of it.

A second form, a PDF in the style of a venue this work was earlier prepared for (vendored in
`manuscript/tmlr/`), is derived from the same source by `analysis/scripts/make_pdf_source.py` and
read back by `check_pdf_text.py` and `check_claim_boundary.py` in the manual `submission-pdf`
workflow. It is not the submitted form and is kept as a further check that the source sets
correctly.

**The paper and this Supplementary Material are two files under one numbering.** The paper is
`manuscript/main.md`, which carries §E and §K after its references; this document is
`manuscript/supplement.md`, which carries the other lettered sections. Both derived forms above set
the paper only. The `apa-docx` workflow also converts this document to a `.docx` with the same
reference document, but does not read that file back. What holds this document is what holds the
paper's text: `check_manuscript_numbers.py` counts the quoted quantities across both files,
`check_claim_boundary.py` scans both, and `check_crossrefs.py` resolves every `§` reference in
either file against the headings of both.

This repository contains the frozen inputs of the completed studies (`data/raw/`, each pinned by
SHA-256 and size in `data/data.md`), the analysis scripts (`analysis/scripts/`), and the measurement
apparatus as an import closure of 69 modules (`analysis/apparatus/`) reproduced byte-for-byte from
the upstream source repository. That closure covers the scoring and power machinery, which is what
the analyses in this repository exercise; it does not include the live driver that produced the
draws, since regenerating draws is out of scope here (§C.3). That driver is in the
upstream repository as `scripts/paper02_run_arms.py` at commit
`4e45adb33d7472d2adf6da29a800bde9b8f58f9e`, the commit it was run at (with a working tree that
was not clean, §I.5), and the call order it inherits
from the apparatus is described in §7.2. Neither is checked by anything in this repository.

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
checks run as the steps themselves and, for the held-out test, as the `heldout-stay` workflow, which
runs `analysis/scripts/heldout_stay_check.py` on two operating systems against the specification and
freeze record under `analysis/heldout-stay/` (§5). The
sealed `repro.sh` names step 8, and the script and output file it calls, with the word "floor"
(`collapse_and_floor`). Those names are sealed bytes and stay as they are. The quantity the step
computes is the permutation-null mean of §M.3, a reference value for the observed statistic rather
than a floor under it.

The post hoc simulations of §3 and §4 are outside the fourteen steps, because `repro.sh` is sealed
and a step cannot be added to it. `repro.sh` itself is sealed, but of the scripts its steps call only
those of steps 11 to 14 are (§H); the others, step 9's checker among them, can change after the
seal, and that checker has. The first's code, grid and declaration are in `analysis/autopsy/`
and its outputs in `data/posthoc/`. The `autopsy` workflow runs on two operating systems on every change:
it checks that the declared files are those of the tagged declaration, runs the fidelity
self-tests, recomputes the side analyses and the summaries and requires them to equal the committed
files, recomputes the first replicate of every cell and requires it to equal the committed record
byte for byte, and compares the two systems' outputs. The `autopsy-full` workflow recomputes the
whole grid, split into sixteen shards on each system, and requires both results to equal the
committed record; it runs when the simulation or its inputs change. The second's code, grid and
declaration are in `analysis/autopsy-primary/` and its outputs in `data/posthoc/primary/`; its script
refuses to run unless the declared files are those of the tagged declaration, and no workflow
recomputes its grid, which is the second's limit. The numbers §3, §4, §B.3 and §B.5 quote are read
from those records by the character-level comparison of step 9, like the others, and step 9 also
requires the rows of `data/posthoc/primary/summary.md` that §B.5 quotes to be what the per-replicate
record gives.

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
tables in §3, §4, §5 and §B.1, and the counts and class breakdown of the held-out
test -- the ninth step renders the expected row or phrase from its source (the per-draw
annotations, the verdict records, the derived artifacts, and `analysis/heldout-stay/result.json`
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

## L. Section numbers cited by files that cannot change

Some files cite a section of this manuscript by a number it no longer carries, and cannot be
edited, because the seal (§H), the freeze of the held-out test (§5) or the declarations
of the post hoc simulations (§3, §4) bind their bytes. Each such citation is listed below with the
section it now means. `analysis/scripts/check_crossrefs.py` requires every row to match the file it
names, and fails if any other file in those groups cites a section of the manuscript.

| File | Line | Number cited | Now |
|---|---|---|---|
| `analysis/autopsy/DECLARATION.md` | 8 | 1.4 | §2.5 |
| `analysis/autopsy/grid.json` | 38 | 5.2 | §B.1 |
| `analysis/autopsy/grid.json` | 46 | 5.2 | §B.1 |
| `analysis/freeze-provenance.json` | 4 | 10.2 | §G.2 |
| `analysis/freeze-provenance.json` | 82 | 12.5 | §I.4 |
| `analysis/heldout-stay/SPEC.ja.md` | 21 | 8 | §E |
| `analysis/heldout-stay/SPEC.ja.md` | 147 | 12.1 | §7.1 |
| `analysis/heldout-stay/SPEC.ja.md` | 169 | 6.3 | §C.4 |
| `analysis/heldout-stay/freeze.json` | 133 | 12.1 | §7.1 |
| `analysis/heldout-stay/result.json` | 668 | 12.1 | §7.1 |
| `data/posthoc/pipeline.md` | 21 | 5.2 | §B.1 |
| `data/posthoc/pipeline.md` | 22 | 5.2 | §B.1 |
| `data/prospective/README.md` | 3 | 6 | §C |
| `repro.sh` | 52 | 6.3 | §C.4 |

Table: Section numbers cited by files that cannot change, with the section each now means.

## M. Further results of the prospective run

### M.1 What R4 does and does not flag at the frozen thresholds

The entropy-floor paragraph of §4 has a consequence for R4, the measurability gate of §E, which is written for the primary arm
and evaluated only there. Its two conditions are `rho_hat` < 0.5 and `none_rate_max_observed` >
0.5. Applied to the completed run and to the control arm, **neither condition is met** —
`rho_hat` is 1.0 in both, and `none_rate_max_observed` is 0.123333 and 0.086667 respectively. **At
the thresholds frozen in §C.4, a gate of this shape does not flag the regime of §4.** Two things
keep that from being true by construction. The gate is not inert: the same two conditions, at the
same thresholds, did fire on the primary arm, which is how this run reached R4 at all. And the
thresholds are what decide it rather than the shape of the rule — the completed run's per-context
entropies run from 0.628287 to 0.754149, so a floor set above 0.68 rather than at 0.5 would have put
`rho_hat` at 0.375 and fired R4 on the completed run too. What the entropy-floor paragraph of §4 says about
certification holds at any floor; what this paragraph says about flagging is a statement about these
thresholds, and §G.2 records that they were fixed before any of this was computed. Detecting the
regime of §4 took the support and permutation-null diagnostics of §4 and §M.3, which run on
every reproduction but are not gates in this protocol. The reading here is not left to the prose:
step 9 re-derives each arm's `effective_k` and `rho_hat` from its own per-context entropies,
evaluates R4's sealed predicates against all three records, and requires the zero-probability zones
to be named in this manuscript (§I.5).

### M.2 What the two arms' gate quantities do and do not compare

**[Post hoc]** The completed run's channel-off read-out, pooled over the contexts (2,276 draws that
parsed), which §4 gives as counts:

| Zone | Count | Probability |
|---|---|---|
| `agora` | 0 | `0.0` |
| `chashitsu` | 0 | `0.0` |
| `garden` | 295 | `0.129613` |
| `peripatos` | 32 | `0.01406` |
| `study` | 1949 | `0.856327` |

Table: The completed run's channel-off read-out, pooled over the contexts.

Two consequences of the table of zones in §4 are worth stating plainly. The question §C.1 puts — whether the narrow support of
the completed run belongs to the model or to the apparatus — is not answered in the primary family
by this run, because the registered scoring procedure returned no estimate there. And the completed
run and the primary arm stand differently against the gate quantities: the completed `qwen3:8b` run admits all eight
contexts even though two of five zones are never produced in the channel-off condition, whereas the
primary arm has `effective_k` = 0 of 8 because none of its contexts clears `h_min_bits` = 0.5. These
are outcomes recorded of these runs under this apparatus, and they are not a comparison of how far
the decision spaces of two model families have collapsed: the two statements are about different
quantities, one the support of the read-out and the other a per-context entropy floor. What neither
licenses is reading an unmeasurable arm as agreement; §7.3 carries the reason a shared collapse
would not be a replication, and that reasoning applies with more force where there is no estimate
at all.

**The frozen qualifier on explicit `null`.** The held-out specification allows the paper to write
that outputs naming `null` as the destination increased only if the same test, applied to the string
and JSON `null` alone, rejects. It does in the control arm, where it gives *p* = 4.359535e-05, and
not in the primary arm, where it gives *p* = 2.263667e-01.

**[Held-out] What each draw recorded as `None` held.** Each one's raw response was classified with
the parser's own steps; §5 quotes the string `"null"` and the absence of a usable JSON object.

| What `destination_zone` held | control, on | control, off | primary, on | primary, off |
|---|---|---|---|---|
| the string `"null"` | 154 | 94 | 5 | 2 |
| a JSON `null` | 1 | 0 | 0 | 0 |
| no `destination_zone` key | 0 | 0 | 1 | 0 |
| a valid zone name, with the plan rejected on another field | 0 | 0 | 0 | 0 |
| some other value | 0 | 0 | 3 | 2 |
| no usable JSON object | 1 | 0 | 98 | 57 |

Table: What `destination_zone` held in each draw recorded as `None`, by arm and condition.

### M.3 The estimates the permutation test did not reject

**[Registered] Neither run that produced an estimate returned one its own permutation test
rejected.** The results of §2.4 should be set beside what the three runs of this measurement have
returned. In the completed run `tv_bar` = 0.038065 at a recorded `permutation_p_value` of 0.057986,
0.007986 above the α of 0.05. In the control
arm `tv_bar` = 0.030575 at a permutation *p* of 0.43989, and the test does not reject. In the
primary arm no estimate is produced at all. **Both runs that produced an estimate are `qwen3:8b`**,
so the *n* here is two runs of one model family; §7.3 gives the reason agreement across runs of
this apparatus would not establish what it appears to. It is a statement about what has been
observed, not about the power of any test — the sealed design did not evaluate the power of the
permutation test, and the post hoc simulation of §3 describes the design under assumed
distributions, not this run's estimate — and it changes no threshold and no decision rule. Whether the
read-out itself, the zone vocabulary, the parser and the frozen bank, is what holds the estimate
there is the question §7.3 raises, and this protocol cannot answer it: varying the read-out is a
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

## N. Further related work and notes

### N.1 Further related work

**Standard results this paper rests on.** The power that bears on a decision is the power of the
test the decision uses; a figure computed for another statistic does not carry over, and using a
power figure computed at an observed effect to interpret a non-significant result is a documented misuse
(Hoenig & Heisey, 2001). Card et al. (2020) document how often conclusions in NLP rest on designs without the
power to support them. The sealed rules come close to the form that Hoenig and Heisey (2001) warn
against: `power` is
computed after the draws, on the run's own channel-off distribution, though at the registered
`delta_tv` rather than at an observed effect, and clearing the power gate (`power` ≥ 0.8) is required
before R1 can be reached (§E). A Pearson goodness-of-fit statistic is highly sensitive to cells with
small expected counts, and the classical chi-square test can have poor power when many cells are
small relative to the sample size (Balakrishnan & Wasserman, 2018). The truncated statistic discussed there bounds each cell's
denominator from below so that small cells cannot dominate it. The surrogate behind R3 is a five-cell
statistic, not a high-dimensional one, but its base has empirically empty cells, and its
implementation floors the denominators only at a small constant that avoids dividing by zero, which
leaves that sensitivity in place (§3). Entropy and support are different summaries of a
distribution: a distribution can clear an entropy floor while occupying few categories, or fall below
it while occupying several. Dropping a category and renormalizing over the rest removes from the
comparison any difference between conditions in how often that category occurs.

**Total-variation estimation and equivalence.** Price et al. (2026) give sample-complexity
results for estimating total-variation distance in autoregressive models. Their estimand is
sequence-level, and their access models (samples of the next token after any prefix, or its logits)
are richer than independent whole generations; ours is a decision-level five-way
categorical distance, and the gap between the two is a possible efficiency cost of this design, whose size is not examined here (§I.2).
Jiao et al. (2018) give minimax rates for estimating the L1 distance, twice the
total-variation distance, between two discrete distributions from samples, and show that in a
large-alphabet, non-asymptotic setting the plug-in estimate needs more samples than a rate-optimal
one. Our alphabet has five categories; `tv_bar` averages plug-in distances, and we make no claim about
its efficiency. Bastian et al. (2024) construct a bootstrap test of whether two
multinomial distributions are equivalent, in the sense that a norm of the difference between their
class probabilities, the L1 norm included, lies below a threshold. It is a direct test of the
question that a margin on a total-variation distance points toward, and this protocol runs neither it
nor any other equivalence test (§N.2).

**Surface sensitivity of language-model evaluation.** Sclar et al. (2023) show that
meaning-preserving changes to prompt formatting can move a model's measured performance by large
amounts, and that performance across formats correlates only weakly between models. Zheng and
colleagues (2023) show that models prefer particular option positions and identifiers when choosing
among listed options. Tam et al. (2024) find that requiring output in a structured format such
as JSON lowers models' performance on reasoning tasks, more so the stricter the format. What the fixed
template, zone order and output schema of this apparatus contribute to the read-out is not measured
in this work.

**Preregistration, validation and adjacent audits.** Vaccaro (2026) discusses preregistration for
experiments with AI agents. Larooij and Törnberg (2025) argue that validation is the central challenge
for generative social simulation, and Tomašević et al. (2026)
report a replicated operational validation of an LLM-agent social simulation. Both motivate measuring
whether a wired mechanism propagates rather than assuming that it does. Park et al. (2023)
provide the generative-agent architecture this apparatus descends from. Singh (2026) audits compressed
language models with a statistical toolkit built around equivalence testing at a declared margin:
the practice of fixing a bound in advance (Lakens, 2017), applied to language-model evaluation, which this
protocol follows. Otterson (2026) separates instrument artifacts from real
effects in a pre-registered causal setting; the separation logic is adjacent to ours, applied to a
different object.

### N.2 The margin, and why no equivalence test is run

**Where the value came from, and what is not added to it.** `delta_tv_min = 0.10` was fixed upstream,
with the other thresholds, before the completed run was executed; §G.2 gives the commits and what
checking them establishes. Fixing such a bound before analysis is established practice (Lakens, 2017), and has
been applied to language-model evaluation (Singh, 2026). No substantive justification for the value is
supplied after the fact: one written with every result in hand would be a rationalization of a sealed
value rather than a reason for it. Each gate is read at whatever margin is registered. The claims of the paper do not depend on whether
the value is well chosen, although whether a pass of the power gate agrees with the test that
decides does depend on it (§3).

**Relation to equivalence testing.** Where a study aims at evidence of absence, the standard
recommendation is a frequentist equivalence test (Lakens, 2017). **This protocol does not perform formal TOST
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

The abstract of the paper and the `abstract` field of `CITATION.cff` are required to be the same
text; `analysis/scripts/check_claim_boundary.py` compares them on every
reproduction run, so the manuscript and the repository metadata cannot drift apart silently.
