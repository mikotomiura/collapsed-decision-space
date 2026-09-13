# Sealed protocol

**This file is sealed.** Its SHA-256 is recorded in `seal/SEAL-MANIFEST.json`, and step 12 of
`repro.sh` fails if a byte of it changes. It is the part of `manuscript/main.md` whose alteration
after the run would change how the result is read; everything left out of it is background,
motivation, provenance narrative, limitation prose, or disclosure — material a reader can
re-examine at any time without the reported branch moving.

That is the whole of the inclusion criterion, and it was applied one section at a time:

> *If this were rewritten after the arms had been run, would the reading of the result change?*

Two things follow from writing it down this way. **The seal is small on purpose** — a seal over the
entire manuscript would forbid correcting a typo in the background section, and a rule nobody can
keep is not a rule. And **the seal is not a record of when it was written.** It fixes content. What
establishes order is a third party holding a copy; §7 below says exactly how far that goes.

The manuscript is the document to read. This is the document to check it against.

---

## 1. Estimand, and how it is computed

The quantity estimated is `tv_bar`, defined in the generated block of §3 and stated identically in
`seal/decision-rules.json`, from which that block is produced.

Two properties of the computation are load-bearing and are named here rather than left to the code:

- **Unparseable draws are dropped and the remaining mass is renormalised over the five zones.** The
  alternative — treating an unparseable draw as a sixth category — would define a different
  estimand. The rate of such draws is not discarded: it is the quantity R4 turns on.
- **The five zones are `agora`, `chashitsu`, `garden`, `peripatos`, `study`**, and the read-out is
  the pre-bias destination zone. The environment pins a zone-bias probability, but the read-out is
  taken before any bias is applied, so the estimand does not depend on it.

The materiality margin against which the estimate is read is `0.10`. It is an interpretation rule
fixed in advance, not a prediction about where the estimate will fall, and no directional claim is
attached to it.

## 2. Arms and sampling plan

`seal/arm-spec.json` is the machine-readable authority for this section and carries every value
below, plus the model digests, the context identifiers and the bank checksum. It is sealed with
this file.

| | Control arm | Primary arm |
|---|---|---|
| Model | `qwen3:8b` | `llama3.1:8b` |
| `think` | disabled | disabled (the model has no native thinking regime) |
| Role | re-run of the reference model, evaluated first, gates the primary arm | cross-family replication |

*M* = 300 draws per condition over *K* = 8 frozen contexts, both conditions, seed `20260708`:
4,800 model calls per arm, 9,600 in total. Backend: ollama 0.32.12. The context bank is frozen and
identified by checksum.

**The `think` disclosure.** The pilot established that the harness's disabled-`think` request is
accepted by the primary model. Acceptance is not behavioural inertness, and no claim rests on it.

## 3. Decision rules

The rules below are **generated** from `seal/decision-rules.json` by
`analysis/scripts/render_decision_rules.py`. They are not written here and not written in the
manuscript either: both carry the same generated block, and step 12 of `repro.sh` fails if either
copy is not what the sealed file renders to. Editing a threshold in prose therefore fails, and
editing it in the sealed file fails the seal hash. There is no third place to edit.

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

`analysis/scripts/apply_decision_rules.py` — sealed with this file — applies these rules to the
recorded quantities of each arm and emits the branch, the truth value of every predicate, and where
evaluation stopped. A quantity that is missing, null, `NaN`, of the wrong type, or a number written
as a string is an error rather than a false predicate.

## 4. What is known at the moment of sealing, and what is not

The completed measurement of the reference model is known and is reported in full in the
manuscript. Its `tv_bar` enters the rules above as one pre-declared constant — the centre of the R5
tolerance band — and in no other way.

Not known at the moment of sealing:

| Planned analysis | Why it cannot be known here |
|---|---|
| `tv_bar` in the primary arm | Not one draw has been collected from that model under this measurement |
| The permutation test in the primary arm | As above |
| R5, the control-arm concordance | The baseline is known and the band is declared; whether the re-run under the new backend version lands inside it has not been observed, which is the reason R5 exists |
| R4, apparatus validity | The pilot recorded parse and zone quantities as three-level bands whose edges are deliberately not at `0.5`, so it cannot anticipate this rule |
| R3, attained power | No value of `power` exists for the primary family |

This table is a statement about the sealed state. It does not stop being true when the arms are
run; what changes then is that the realised outcomes are reported alongside it.

## 5. What is not pre-registered

- **Re-analysis of the completed run.** It is excluded from the planned analyses and stays
  excluded. The one point of contact is the constant named in §4.
- **The generation of the draws.** Language-model draws do not recur when regenerated. The
  per-draw record is a frozen input, not something a reproduction recreates.
- **Anything in the manuscript outside this file.** Background, related work, limitations
  discussion, provenance narrative and disclosure are not sealed, and are not claimed to be.

## 6. Deviations, and the condition under which this seal lapses

The following are **not** minor deviations:

1. substituting a different model for either arm;
2. changing the backend version;
3. changing any of the eleven threshold values;
4. changing the seed;
5. changing *M* or *K*;
6. substituting the frozen context bank.

Each is a field of `seal/arm-spec.json`, and `analysis/scripts/verify_seal.py --run-manifest`
compares it against the corresponding field of a run manifest through the field map recorded there.
The list is therefore checked, not promised.

**If any of the six occurs, this seal is broken for that run.** A registered-report route would
send a deviation of this kind to the recommender who granted in-principle acceptance. There is no
such third party here, and an assurance is not a substitute for the authority that is absent. The
rule is a forfeit instead: the deviation is reported in the completion report, and **that run is
not presented as pre-registered.** Making the claim again would require a fresh seal and a fresh
run. This is a condition under which the pre-registration lapses — not a licence to change the
rules and carry on.

## 7. What the seal establishes, and what it does not

**Establishes.** The bytes of the sealed files are what `seal/SEAL-MANIFEST.json` records; the
manifest's own self-hash is correct under the canonicalisation stated inside it; the rule text in
the manuscript is a function of the sealed rules; and the branch reported after the run follows
from these rules applied to the recorded quantities. Every one of those is checkable offline,
without an account, without resolving any identifier, and without trusting the author. That last
property is what lets the checks run inside a de-identified copy of this repository: they need
nothing that de-identification removes.

**It does not follow that the copy is anonymous.** The apparatus is vendored from a named public
project, and the provenance checks work by showing that the shipped modules are byte-identical to
that project's blobs, so the package name is load-bearing and cannot be redacted: proving *which*
upstream the apparatus came from and concealing *which* upstream it is are not jointly
satisfiable. A reader who searches the name reaches the author. That is a property of this
compendium, it is measured rather than estimated — the build reports the count on every run — and
it is reported to a double-blind venue as a limitation rather than presented as solved.

**Does not establish.** That these files are old. That a sealed file and the manifest were not
edited together in one commit. That no draw was taken before the seal. No check that lives inside
this repository can reach any of the three, and this file does not imply otherwise.

**The external half does not exist yet, and this file will not pretend otherwise.** At the time
this protocol is sealed there is no deposit and no `seal/zenodo-witness.json`; `repro.sh` passes no
`--witness`, and the code path that would compare a deposit's checksums against these files has
therefore never run against a real record. Everything above is the internal half, and the internal
half is all a reader currently has.

What the external half *is to be*, stated so that its absence is legible rather than implied away:
a deposit in a public archive, which publishes a per-file checksum anyone can read without an
account. `verify_seal.py --witness` compares those checksums against the local sealed files, and
the completion report will say whether that comparison was made, against which record, and with
what result — or that it was not made.

Its bound is worth stating in advance, because it is smaller than it sounds. **A deposit record
remains editable by its owner for a period after publication, with the identifier unchanged**, so
the deposit's timestamps bound when the files were last touched, not when they were first written.
Even in the best case the external half witnesses *a* time, not the absence of an earlier run. The
content-binding above is what does the work; the deposit would be corroboration, and is described
as corroboration.
