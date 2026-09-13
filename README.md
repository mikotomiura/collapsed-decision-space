# When the power gate cannot fail

*Collapsed decision spaces defeat margin-and-power null reporting in LLM agents*

[![repro](https://github.com/mikotomiura/collapsed-decision-space/actions/workflows/repro.yml/badge.svg)](https://github.com/mikotomiura/collapsed-decision-space/actions/workflows/repro.yml)

This repository is the research compendium for a **pre-registered protocol with a completed
preliminary measurement reported in full** (`manuscript/main.md`). It holds the protocol, the
frozen evidence the protocol builds on, the measurement apparatus, and a single command that
re-derives every number the protocol quotes.

**No prospective data has been collected.** The decision rules that will read the prospective arms
are sealed before the arms are run: `seal/` holds them in machine-readable form and
`seal/SEAL-MANIFEST.json` fixes their bytes, so the branch reported afterwards can be re-derived
from the rules as they stood beforehand. Step 12 of `repro.sh` is what checks that, and it needs no
network, no account and no trust in the author.

---

## What the study is about

An embodied language-model agent carries a scalar derived from its recent movement — an
exponential moving average over its moves — into the temperature used for its next generation.
That wiring is real: a completed forensic study shows the channel is causal, is separable from the
static location channel, and disappears without residue under ablation, while a positive control
shows that the same estimator is able to return zero.

The open question is whether the channel *propagates*. A completed measurement on one model found
no shift in the agent's five-way zone decision exceeding a materiality margin declared in advance,
while the power gate reported full nominal power — and looking at the support of that read-out
afterwards showed why neither number was carrying information. Two of the five zones are never
produced at all; the chi-square power gate is inflated by the empty cell, and the null floor of the
distance statistic eats most of the declared margin. **That joint failure is the paper.** The
protocol then estimates the same quantity in a second model family, with a control arm that re-runs
the original model, to find out whether the failure mode belongs to the model or to the apparatus.

**The subject of every claim here is the channel.** It is not walking, and it is not creativity.

## What may and may not be claimed

The full guard list, with the search patterns used to enforce it, is in
[`manuscript/CLAIM-BOUNDARY.md`](manuscript/CLAIM-BOUNDARY.md). In summary:

**Supported by the evidence**

- the channel is wired non-degenerately, including that the positive control is able to read zero
- the channel's downstream effect was not detected under a margin fixed before the data existed
- the margin-and-power pairing fails in both directions at once when the decision space collapses —
  demonstrated on this apparatus and recomputed on every run, **not** surveyed for how often it
  occurs elsewhere
- concentration of the base distribution is not itself what reduces detection power
- effect-absent, low-power and apparatus-invalid are kept apart as three distinct outcomes
- the envelope is bounded: one apparatus, one sampling regime, eight frozen contexts

**Out of reach of this design** (three of thirteen guards, quoted for orientation)

- any statement about human ambulation, or about creative production
- any general statement about whether embodiment matters
- any claim that declaring a margin in advance is itself new — that practice is established, and
  this work follows it

`analysis/scripts/check_claim_boundary.py` enforces the full list against the manuscript, this
README and the citation metadata on every run, and fails if a guard pattern stops firing against
its fixture.

## What is in here

| Path | Contents |
|---|---|
| `manuscript/main.md` | The protocol |
| `manuscript/CLAIM-BOUNDARY.md` | The claim guards and their search patterns |
| `seal/` | The sealed decision rules, arm specification and protocol text, with their manifest |
| `data/raw/` | Frozen evidence from the completed studies, each pinned by SHA-256 and size |
| `data/data.md` | Provenance of every frozen input, and how it is verified |
| `analysis/apparatus/` | The measurement apparatus, 69 modules, byte-identical to the upstream source |
| `analysis/scripts/` | Verification and extraction scripts |
| `analysis/freeze-provenance.json` | Upstream commit and blob identifier of every shipped file that carries evidence |
| `env/` | The lockfile the completed run was executed under |
| `repro.sh` | One command that runs all of the above |

## Reproducing

```bash
bash repro.sh
```

Requires [uv](https://docs.astral.sh/uv/) and network access for the first dependency
installation. The script runs twelve steps and exits non-zero if any of them fails:

1. install the environment from the lockfile
2. lint
3. verify the frozen inputs against `data/data.md` **and** against their upstream blobs
4. verify the threshold freeze and the whole apparatus closure
5. **recompute the completed run's verdict** from the shipped per-draw annotation
6. extract the quantities the protocol quotes
7. regenerate the power table
8. derive the support of the decision space and the null floor of the estimand
9. compare the numbers quoted in the protocol and in this README against the frozen inputs,
   character for character
10. run the claim-boundary check together with its positive control
11. **measure what the seal and the decision rules actually catch**, by mutating what they are
    supposed to protect: synthetic arm records against the rules, and a staged copy of the sealed
    tree against the seal checker. Each failing case must fail with a diagnostic naming the thing
    that was changed, and three control cases must *not* fail at all
12. **verify the seal**: the sealed files hash to what the manifest records, the manifest's own
    self-hash is correct, and the rule text in the protocol and the manuscript is *generated from*
    the sealed rules rather than restated beside them

Both legs of the public CI run exactly this, on Ubuntu and on Windows, and a third job requires the
generated artefacts to be byte-identical across the two.

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
- The verdict of the completed run is **re-derivable** from the shipped annotation and the shipped
  apparatus: the verdict string, all nine gate read-outs and all four per-context maps are
  recomputed and required to match.
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
  inside this repository could. That half needs a third party holding a copy, and the protocol says
  so rather than letting the green badge imply otherwise.

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

Detection power here is governed by the size of the shift being looked for, not by how concentrated
the base distribution is — the third row is the one that carries that point. The 0.1842 figure
belongs specifically to a near-uniform base at `delta_tv` = 0.01, one tenth of the declared margin,
and is only meaningful when quoted in that full form.

## Status

The protocol is written, the evidence it rests on is frozen and verifiable, and the decision rules
are sealed. The prospective run — two arms, 9,600 draws, roughly five hours of compute — happens
once and without tuning, after the seal.

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
