# Declaration of the post hoc simulation (B3)

This file and `grid.json` in the same directory are the declaration required by the revision plan
for the post hoc simulation of the sealed decision pipeline: the grid, the seeds, the replicate
counts and the rules by which the results are read are fixed in a commit pushed before the first
full run. The commit is the one the annotated tag `autopsy-b3-declared` points at.

**Layer.** [Post hoc] (§1.4 of the manuscript). A seed-fixed simulation under known channel-off
bases. It is not a test of a hypothesis about the runs, and nothing here is blinded, because there
is nothing to blind: every input is a distribution this repository already ships.

**What it measures.** Two things, kept apart. First, how often the sealed pipeline -- the vendored
scorer with its defaults, then the sealed rules in the sealed order without R5 -- reaches each
branch. Second, how often the sealed stratified permutation test rejects when it is applied to all
eight contexts with no gate in front of it; this is the quantity the manuscript's statement that the
test's power was not evaluated refers to, and the first is not a substitute for it, because R2 is
also reached through `tv_bar >= 0.1` and the gates stop evaluation before the test is read. Both
are measured when the channel-off distribution of every context is known and the channel-on
distribution is moved from it by a declared total variation in a declared direction. **It says
nothing about the channel.** The bases come from runs; the shifts are put there by the simulation.

## What is declared

Everything in `grid.json`: the five bases, the six directions and how their cells are found, the
deltas, the replicate counts, the master seed and how every uniform is derived from it, the
pipeline and the quantities, the side analyses, and the reading rules. The reading rules are
applied by `render.py`, not by hand.

The code in this directory is committed with the declaration. A change to it after the declaration
that alters any output is a deviation, recorded as one.

## What was run before this commit, and what was seen

- `simulate.py --self-test`: the completed run's shipped annotation, passed through the same
  wrapper, reproduces every field of `data/raw/cproper-verdict.json`, and the sealed rules applied
  to it as a primary arm reach R1. The ungated test on the completed run's own draws gives the
  recorded `permutation_p_value`, and on a synthetic replicate whose eight contexts all clear the
  floor it equals the scorer's own test, which is why the scorer's result is reused in that case.
  Every run cell is at exact total variation delta in every
  context. The roles (hi, lo, second, smallest non-zero, empty) of each base, which the output
  lists, and the agreement of hi and lo with the sealed perturbation at every declared delta.
- `side_analyses.py --self-test`: the re-implementation with a variable floor agrees with the
  sealed surrogate bit for bit at the sealed floor; the pseudocount-0 row on the completed run
  equals `data/derived/collapse-and-floor.json`, which is a shipped number; one closed-form bound.
- `simulate.py --smoke`: six pipeline calls at master seed 1 (not the declared seed), to measure
  time: about 0.47 s per call on the author's machine. No rate was computed or shown.
- `render.py` on a constant, hand-built record in a scratch directory, to exercise the tables.
  The record contained no simulated value.

No cell of the declared grid was computed at the declared seed before this commit, and no output of
the side analyses was computed.

## How the declaration is bound to the results

- Every mode that produces or checks an output refuses to start unless the tag exists, the tagged
  commit is an ancestor of `HEAD`, and each file listed in `DECLARED_FILES` of `_common.py` -- the
  grid, the code in this directory, the data the bases are built from, the sealed files the
  pipeline calls, and `env/uv.lock` -- is byte-identical to its copy at the tagged commit, unless
  `DEVIATIONS.md` names it. `--check-rep0`, which CI runs on every push, applies the same check.
- The pull request that carries this work is merged with a merge commit, not squashed, so that the
  tagged commit stays in the history of the default branch; the ancestor check fails otherwise.
  The tag is a second anchor that survives even if that were lost.
- What a check cannot show is *when* the full run happened relative to the push of this commit.
  The pull request's timeline records the order of the pushes; nothing here claims more.

## Deviations

A change to the grid, the seeds, the replicate counts, the reading rules, or to code in a way that
alters an output, made after the tagged commit, is not folded in. The same holds if the two
operating systems' outputs differ from each other or from the committed files (`grid.json`,
`environment.cross_os`). It is recorded as a deviation in
`DEVIATIONS.md` in this directory, with its reason, and any cell it adds is reported separately
from the declared ones.
