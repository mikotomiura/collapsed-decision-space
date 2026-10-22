# Declaration of the post hoc simulation on the primary arm's base

This file, `grid.json` and `simulate_primary.py` in the same directory are the declaration of a
second post hoc simulation: the grid, the seeds, the replicate counts and the rules by which the
results are read are fixed in a commit made before the first full run. The commit is the one the
annotated tag `autopsy-primary-declared` points at, and `simulate_primary.py --run` and `--render`
refuse to start unless every file in its `DECLARED_FILES` is byte-identical to its copy at that tag.

**Why it exists.** The manuscript said that the entropy floor changed the evaluation because it
decided the reported branch. Review of the revised manuscript pointed out that deciding the branch
is not yet a consequence: the declared simulation (`analysis/autopsy/`) left the primary arm's base
out, so nothing showed what a gate that reads support would have done there. This simulation is
the counterfactual that question needs. It was added after the results of every run were known.

**Layer.** Post hoc. A seed-fixed simulation under a known channel-off base. Nothing is blinded,
because every input is a distribution this repository already ships.

**What it measures.** On base P (the primary arm's per-context channel-off distribution), with the
channel-on distribution moved by a declared total variation in a declared direction, three things on
the same draws: how often the sealed pipeline reaches each branch, how often a pipeline that differs
from it only by admitting every context whose pooled zones number two or more reaches each branch,
and how often the sealed permutation test rejects with no gate in front of it. **It says nothing
about the channel.** The primary arm's channel-on draws are not read.

## What is declared

Everything in `grid.json`, including the sentence the manuscript may write for each case of the
reading rule. Directions, deltas, roles, sampling and the pipeline are those of the declared
simulation, by reference.

## What was run before this commit, and what was seen

- `simulate_primary.py --self-test`: base P occupies three zones pooled; the run-time replacement of
  the scorer's floor is confined to the counterfactual call; on the completed run's shipped
  annotation, where every context clears both floors, the two pipelines give the same verdict; the
  count of feasible, infeasible and alias cells.

No cell of the declared grid was computed before this commit, and no rate was seen. The primary
arm's channel-on draws were not read by any code in this directory.
