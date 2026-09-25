# Three gates, three proxies

*An instrument autopsy of a sealed LLM-agent evaluation*

[![repro](https://github.com/mikotomiura/collapsed-decision-space/actions/workflows/repro.yml/badge.svg)](https://github.com/mikotomiura/collapsed-decision-space/actions/workflows/repro.yml)

This repository is the research compendium for **a sealed, pre-registered evaluation and an
autopsy of the gates that decided what its outcome is worth** (`manuscript/main.md`). It holds the
protocol, the frozen evidence the protocol builds on, the measurement apparatus, the per-draw data of
the completed run and of the two prospective arms, the arms' attempt logs, a held-out test of one
post hoc observation, and a single command that re-derives all three verdicts -- the completed
run's and the two prospective arms' -- from their shipped per-draw annotations and checks the
quantities the manuscript quotes against their sources. What that command does **not** reach is
set out in §12.8 of the manuscript.

**At the time of sealing, no prospective data had been collected.** The decision rules that read
the prospective arms are sealed before the arms are run: `seal/` holds them in machine-readable form and
`seal/SEAL-MANIFEST.json` fixes their bytes, so the branch reported afterwards can be re-derived
from the rules as they stood beforehand. Steps 12 and 13 of `repro.sh` are what check that, and
they need no network, no account and no trust in the author.

**Each arm has since produced one complete run**, and the sealed rules reach branch **R4
(apparatus validity)**: no context of the primary model family reaches the sealed per-context
entropy floor, so the estimand is not measured there. That is not read as a null result, and the
claim narrows to single-model scope. The control arm's first capture attempt was stopped from
outside before it produced a verdict and was restarted from the beginning; the attempt logs and
the stopped attempt's partial record are shipped in `data/attempts/` (§12.8 of the manuscript).
The results section of `manuscript/main.md` reports the branch and
`manuscript/REPORTED-BRANCH.md` records the derivation; step 13 re-derives the branch from the
sealed rules on every run.

What they cannot check is that the seal is old. The author can rebuild every sealed file and the
manifest in one commit, and no check living inside this repository would see it; that half needs a
copy held by someone else. Step 14 is the comparison against a recorded copy, and it says in its
own output whether there is one to compare — and even when it passes, it bounds when that copy was
last touched rather than when these files were written. `seal/protocol.md` §7 states that instead
of leaving a green badge to imply otherwise.

---

## What the study is about

An embodied language-model agent carries a scalar derived from its recent movement — an
exponential moving average over its moves — into the temperature used for its next generation.
That wiring is real: a completed forensic study shows the channel is causal, is separable from the
static location channel, and disappears without residue under ablation, while a positive control
shows that the same estimator is able to return zero.

The sealed evaluation asked whether the channel *propagates* into the agent's five-way zone
decision. What this compendium establishes is about the instrument rather than the channel. **Each
of the three gates that decide what a null report is worth ran as written, and each read a quantity
other than the one the reading of its result depends on:**

- the attained-power gate (R3) computes the power of a pooled chi-square surrogate, not of the
  permutation test the decision turns on. At the registered effect size the surrogate returns 1.0 for
  a near-uniform and a degenerate base alike, and against the completed run's channel-off base,
  where two of the five zones never occur, it clears 0.8 at one hundredth of the margin;
- the entropy floor (R4) reads per-context entropy, not the support of that base. The completed run
  and the control arm clear it everywhere while their channel-off draws never produce two of the five
  zones, and the second model fails it although each of its cells produces two or more;
- the cap on dropped draws (R4) reads the largest per-cell rate, not how the rate differs between the
  conditions. All three runs pass it, while a held-out test found more dropped draws in the
  channel-on blocks of both prospective arms -- mostly an explicit `"null"` in one arm and mostly
  missing or malformed JSON in the other, and confounded with the fixed on-then-off block order.

The prospective arms and the held-out test did not resolve this; they exposed it. The claim does not
depend on the value of the 0.10 margin, says nothing about the channel's effect, and is confined to
two models and eight frozen contexts. An earlier version of the manuscript drew a different
conclusion from the completed run; §5.1.1 of the manuscript says why that reading is withdrawn.

**Wherever this work speaks of an effect, its subject is the channel.** It is not walking, and it
is not creativity.

## What may and may not be claimed

The full guard list, with the search patterns used to enforce it, is in
[`manuscript/CLAIM-BOUNDARY.md`](manuscript/CLAIM-BOUNDARY.md). In summary:

**Supported by the evidence**

- the channel is wired non-degenerately, including that the positive control is able to read zero
- each of the three gates ran as written and read a proxy, as listed above — shown on this apparatus
  and recomputed on every run, **not** surveyed for how often it happens elsewhere
- for the chi-square surrogate the power gate computes, concentration of the base distribution is not
  itself what lowers the computed power; the power of the permutation test is evaluated nowhere
- the channel's downstream effect was not detected under a margin fixed before the data existed, in
  the two runs that produced an estimate
- effect-absent, low-power and apparatus-invalid are kept apart as three distinct outcomes
- clearing a per-context entropy floor everywhere **does not certify** the support the power
  calculation depends on — it is compatible with a base distribution missing two of five zones.
  What follows for the gate is threshold-bound: at the values fixed in advance R4 does not flag
  that case, but the same rule at a higher floor would
- in a held-out test, recorded `None` was more frequent in the channel-on blocks of both prospective
  runs — stated only with its qualifiers: the explicit-null qualifier holds for the control arm and
  not for the primary arm, what was recorded as `None` differs between the arms, the difference is
  confounded with execution order, and the test is not a formal pre-registration
- the envelope is bounded: one apparatus, one sampling regime, two model families, eight frozen
  contexts

**Out of reach of this design** (three of twenty-eight guards, quoted for orientation)

- any statement about human ambulation, or about creative production
- any general statement about whether embodiment matters
- any claim that declaring a margin in advance is itself new — that practice is established, and
  this work follows it

`analysis/scripts/check_claim_boundary.py` enforces the full list against the manuscript, this
README and the citation metadata on every run, and fails if a guard pattern stops firing against
its fixture, or starts matching one of the sentences its negative control lists as sayable.

## What is in here

| Path | Contents |
|---|---|
| `manuscript/main.md` | The protocol |
| `manuscript/CLAIM-BOUNDARY.md` | The claim guards and their search patterns |
| `manuscript/REPORTED-BRANCH.md` | How the reported decision branch is written, and what checking it establishes |
| `seal/` | The sealed decision rules, arm specification and protocol text, with their manifest |
| `data/raw/` | Frozen evidence from the completed studies, each pinned by SHA-256 and size, and the two landed prospective verdicts |
| `data/prospective/` | The per-draw annotations, raw records and run manifests of the two prospective arms |
| `data/completed/` | The completed run's per-draw record, pinned in `data/data.md` and by the run's own manifest |
| `data/attempts/` | The prospective arms' append-only attempt logs, and the partial record of the control arm's stopped first attempt |
| `analysis/heldout-stay/` | The held-out test of one post hoc observation: its specification, freeze record, result and witness |
| `data/data.md` | Provenance of every frozen input, and how it is verified |
| `analysis/apparatus/` | The measurement apparatus, 69 modules, byte-identical to the upstream source |
| `analysis/scripts/` | Verification and extraction scripts |
| `analysis/freeze-provenance.json` | Upstream commit and blob identifier of every shipped file that carries evidence |
| `analysis/upstream-links.json` | The URLs for following those commits by hand, kept out of the sealed file |
| `env/` | The lockfile the completed run was executed under |
| `repro.sh` | One command that runs all of the above |

## Reproducing

```bash
bash repro.sh
```

Requires [uv](https://docs.astral.sh/uv/) and network access for the first dependency
installation. The script runs fourteen steps and exits non-zero if any of them fails:

1. install the environment from the lockfile
2. lint
3. verify the frozen inputs against `data/data.md` **and** against their upstream blobs
4. verify the threshold freeze and the whole apparatus closure
5. **recompute the three recorded verdicts** -- the completed run's and the two prospective
   arms' -- from the shipped per-draw annotations, and require the verdict string, the nine gate
   read-outs and the four per-context maps of each to match
6. extract the quantities the protocol quotes
7. regenerate the power table
8. derive the support of the decision space and the permutation-null mean of the estimate (the
   sealed script labels this step in an earlier vocabulary; §13 of the manuscript says which)
9. compare the numbers quoted in the protocol and in this README against the frozen inputs,
   character for character
10. run the claim-boundary check together with its positive control
11. **measure what the seal and the decision rules actually catch**, by mutating what they are
    supposed to protect: synthetic arm records against the rules, a staged copy of the sealed
    tree against the seal checker, and the witness collector driven end to end against a
    synthetic archive response. Each failing case must fail with a diagnostic naming the thing
    that was changed, and five control cases must *not* fail at all
12. **verify the seal**: the sealed files hash to what the manifest records, the manifest's own
    self-hash is correct, every sealed script imports only sealed local modules, and the rule text
    in the protocol and the manuscript is *generated from* the sealed rules rather than restated
    beside them
13. **re-derive the reported branch** by applying the sealed rules to the prospective verdicts.
    Skips itself, loudly, while those files do not exist. It is wired in now because `repro.sh` is
    a sealed file: adding the step after the run would change the seal, with the results already
    in hand
14. **compare the sealed files with a recorded copy of an archive's own checksums.** Steps 3 to
    13 compare records inside this repository against one another, and one person can change both
    sides of any of them; this step reaches for a copy held by somebody else. It skips itself,
    loudly, until `seal/zenodo-witness.json` exists, and is wired early for the same reason as
    step 13.

    **It is offline, and that bounds it.** It establishes that the recorded witness agrees with
    these bytes, and that the witness is closed against itself: its anchor is the maximum of the
    server times it carries, and those times are exactly the ones its own deposit listing implies.
    It does *not* establish that the witness is what the archive returned — an independent review
    wrote a witness from nothing and an earlier version of this check passed it. Re-reading the
    record is what closes that, it is an online act, and the witness records the URL to re-read;
    `repro.sh` stays offline so that it also runs inside a de-identified copy. Two further limits:
    the published checksums are MD5, and a deposit stays editable by its owner for a period after
    publication with the identifier unchanged, so its times bound when it was last touched — not
    when these files were written, and not that no run preceded them

Both legs of the public CI run exactly this, on Ubuntu and on Windows, and a third job requires the
generated artefacts to be byte-identical across the two. The fourteen steps include no test suite
and no `pytest` run; the repository has none. The held-out test runs as its own workflow,
`heldout-stay`, on both operating systems.

If you have a clone of the upstream source repository, pointing at it also checks the upstream
commit dates and ancestry:

```bash
ERRE_SANDBOX_REPO=/path/to/ERRE-Sandbox bash repro.sh
```

## What the checks establish, and what they do not

The distinction matters more than the green badge, so it is stated here rather than left implicit.

**Established**

- The frozen inputs are byte-identical to the blobs registered in the public upstream repository.
- The decision thresholds shipped here are the exact bytes of the upstream commits that froze them,
  and those commits are ancestors of the commit carrying the completed run.
- The verdict of the completed run and the verdicts of the two prospective arms are
  **re-derivable** from the shipped annotations and the shipped apparatus: for each, the verdict
  string, all nine gate read-outs and all four per-context maps are recomputed and required to
  match.
- Every quantity in the list below occurs, as the frozen inputs render it, in the protocol -- and
  for the subset the README quotes, in this README too. The test is occurrence, not uniqueness: a
  value that appears in several places is not protected against one of them being altered.
- The sealed files are internally consistent, and the decision rules in the protocol are the ones
  the sealed file holds, because the rule text is generated from it rather than written twice.

**Not established**

- Regeneration of the draws themselves. Language-model draws do not recur when regenerated, so the
  per-draw record is treated as a frozen input rather than as something the script recreates.
- The upstream commit *dates*, unless you point the script at a clone of that repository. Offline,
  the checks establish content, not chronology; the two together are what supports the ordering
  claim, and `manuscript/main.md` §10.2 states this rather than implying either half carries it.
- The age of one record. The forensic record of the channel study entered version control through a
  relocation commit, so history witnesses its content but not when it was produced. This is
  recorded in `analysis/freeze-provenance.json` and disclosed in the protocol.
- **That the seal is old.** Step 12 shows the sealed files are the bytes the manifest records. It
  cannot show that a sealed file and the manifest were not edited together, and no check living
  inside this repository could. That half needs a third party holding a copy. Step 14 compares
  these files against a *recorded* copy of what an archive publishes, and says in its own output
  when there is none; being offline, it cannot establish that the record is what the archive
  returned, which takes re-reading the record at the URL the witness names. Even then it bounds
  when the copy was last touched rather than when these files were written. The protocol states
  all of that rather than letting a green badge imply otherwise.

## Key quantities

Every value below is produced by `analysis/scripts/extract_verdict_table.py`; none is transcribed
by hand. Step 8 of `repro.sh` checks these values against the frozen inputs here as well as in the
protocol. Until 2026-09-13 that step read the protocol only, so this sentence claimed a coverage
the check did not have; the list it now enforces is `README_QUANTITIES` in
`analysis/scripts/check_manuscript_numbers.py`.

**The channel study** (`data/raw/es3-verdict-forensic.json`)

| Quantity | Value |
|---|---|
| `d_loco`, the point estimate | 0.04682681825722385 |
| `ci_lower`, 90% percentile bootstrap | 0.04529199663455194, against a pre-registered floor of 0.02 |
| ablation, `loco_delta=None` against `gain=0` | bit-equal; `ablation_max_abs_diff` = 0.0 |
| `zone_function_d_loco` — the zone-function positive control, a **different field** from the point estimate above, showing that the estimator is able to read zero | 7.401486830834377e-17 |

**The completed measurement** (`data/raw/cproper-verdict.json`, `qwen3:8b`, 4,800 draws)

| Quantity | Value |
|---|---|
| `verdict` | `NO_CHANNEL_CONFORMANCE` |
| `tv_bar` | 0.038065, against a declared margin of 0.10 |
| `rho_hat` | 1.0 (8 of 8 contexts) |
| `power` | 1.0 |
| `permutation_p_value` | 0.057986 (`permutation_reject` = `False`) |

**Power** (`analysis/scripts/power_curve.py`)

| Base distribution | `delta_tv` | Power |
|---|---|---|
| near-uniform | 0.10 | 1.0000 |
| near-uniform | 0.01 | 0.1842 |
| degenerate | 0.01 | 0.9533 |
| degenerate | 0.10 | 1.0000 |

These are powers of the pooled chi-square surrogate the power gate computes, not of the permutation
test the decision turns on, whose power is evaluated nowhere. For that surrogate, power is governed
by the size of the shift being looked for, not by how concentrated the base distribution is — the
third row carries that point, and the first and fourth show that at the registered `delta_tv` it
returns 1.0000 for both bases, so a pass does not tell them apart. The 0.1842 figure belongs
specifically to a near-uniform base at `delta_tv` = 0.01, one tenth of the declared margin, and is
only meaningful when quoted in that full form.

## Status

The decision rules were sealed and deposited with an archive before any prospective draw was
collected. Each prospective arm then produced one complete run, and the sealed rules reached R4. A
held-out test of one post hoc observation was frozen at commit `61dbd96` and run once; its result
is `analysis/heldout-stay/result.json`, and the `heldout-stay` workflow recomputes it on every
change.

The deposit carries an earlier working title of the manuscript in its title field. Its metadata is
not edited, because the deposit's last-modified time is one of the server times the recorded witness
anchors on, and an edit would move that anchor.

One preliminary study is reported in the protocol but its machine-readable record was not retained,
so no quantity from it is quoted anywhere. That gap is disclosed rather than worked around.

## Citation

See [`CITATION.cff`](CITATION.cff). Reference numbers in the manuscript are permanent identifiers
from the author's bibliography and are not renumbered between manuscripts, which is why they are not
consecutive.

## Licence

| Part | Licence |
|---|---|
| Code (`analysis/`, `repro.sh`) | Apache-2.0 OR MIT — see `LICENSE` and `LICENSE-MIT` |
| Manuscript and figures (`manuscript/`) | CC BY 4.0 — see `LICENSE-CC-BY-4.0.txt` |
| Frozen data (`data/raw/`) | Research data generated by the author; provenance in `data/data.md` |
