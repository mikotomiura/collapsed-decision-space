# The reported branch: how it is written, and what checking it establishes

Step 13 of `repro.sh` applies the sealed decision rules to the recorded quantities of the two
arms, reaches a branch, and fails if that branch is not the one this repository reports. The
branch it compares against is read from `manuscript/reported-branch.txt`.

This file says when that branch is written, by whom, on what basis — and, at the end, what the
comparison does *not* establish. The last part matters most.

## The tension, stated plainly

There are two obvious ways to write the reported branch, and both are wrong.

**Write it before the results exist.** Then it is a prediction. §8 of the manuscript says the
opposite in as many words: *"R1, R2, R3 and R4 are all permissible outcomes, and the authors do
not predict which will occur."* A branch committed in advance would contradict the sealed text of
the protocol.

**Write it after the results exist, by copying the evaluator's output.** Then step 13 compares a
number with itself. The check would pass on any input at all, and passing would mean nothing.

Neither is available, so the branch is written as a **claim the manuscript makes**, and step 13
checks that claim against the rules. The rest of this file is the procedure that keeps it a claim
rather than a transcription — and the honest account of how far that succeeds.

## One statement, not two

`manuscript/reported-branch.txt` is **generated**, never edited by hand.

The single statement is a marker in the results section of `manuscript/main.md`:

```
<!-- REPORTED-BRANCH: R1 -->
```

`analysis/scripts/render_reported_branch.py` renders it into `manuscript/reported-branch.txt`, and
step 9 (`check_manuscript_numbers.py`) fails if the two disagree.

This is the arrangement §8 already uses for the decision rules themselves, for the reason the
manuscript gives there: *two statements of the same rules drift; one statement and a renderer
cannot.* If the branch were written into both the prose and the compared file, revising one and
forgetting the other would leave a repository whose results section says one thing and whose
mechanical check confirms another, and nothing would catch it.

Two smaller consequences of the file being sealed-adjacent are worth knowing:

- **It cannot hold a reason.** `repro.sh` reads it as
  `--expect-branch "$(tr -d '[:space:]' < manuscript/reported-branch.txt)"` — the whole file with
  all whitespace removed. A comment line does not annotate the branch; it becomes part of it.
  That is why the derivation lives here and not there.
- **The marker does not appear in the rendered manuscript.** It is an HTML comment. It binds the
  source a reviewer reads in the repository, not the page a reader sees in the PDF.

## Procedure

1. **Run each arm and verify it.** `paper02_run_arms.py --capture --arm <arm>`, then
   `--verify --arm <arm>`. The verify step must exit **0**. Exit **2** means a bundle that is
   internally consistent but not of the sealed size — a harness result, not a prospective one.
   Run `control` first: R5 gates the primary arm.

2. **Land each verdict.**
   `python analysis/scripts/land_prospective_verdict.py --arm <arm> --from <artefact dir>`.
   Do not copy or rename by hand; `data/data.md` records why.

3. **Derive the branch by hand.** Read `rho_hat`, `power`, `tv_bar`, `permutation_reject`,
   `none_rate_max_observed` and `verdict` out of the two landed files, and walk
   `seal/decision-rules.json` in its sealed order — R5, R4, R3, R1, R2 — stopping at the first
   rule whose action is `stop`. **Write the walk out in the section below**, quantity by
   quantity, before running step 13. This is double entry: the hand derivation and the
   evaluator's are produced separately and then compared.

4. **Write the marker** into the results section of `manuscript/main.md`, beside the claim it
   licenses, and write the results prose to the same branch.

5. **Render**: `python analysis/scripts/render_reported_branch.py`.

6. **Run `bash repro.sh`.** Step 13 now compares the hand derivation with the sealed evaluator.

## If the branch is R2, say which R2

The sealed evaluator returns the *rule identifier* as the branch, and R2 is the one rule that
stops on both outcomes:

| | meaning | reported branch |
|---|---|---|
| R2 satisfied | non-replication: the result is specific to `qwen3:8b` under the disabled-think regime. **A finding, not a failure** | `R2` |
| R2 not satisfied | `UNREACHABLE` — R1 and R2 partition the remaining space, so this indicates a defect in the rules or the inputs, and **must not be interpreted** | `R2` |

`--expect-branch R2` therefore does not distinguish them. `analysis/scripts/apply_decision_rules.py`
is sealed and this cannot be repaired there. So if the branch is R2, **evaluate R2's own condition
by hand** from the landed verdicts — `rho_hat` ≥ 0.5 ∧ `power` ≥ 0.8 ∧ (`tv_bar` ≥ 0.1 ∨
`permutation_reject`) — and record `true` or `false` in the section below, with the quantities it
was read from. Carry the ambiguity itself as a limitation; it is a property of the pre-registered
rules, not of the run.

It is recorded by hand rather than copied out of `data/derived/decision-report.json` for the same
reason the branch is. That file is the evaluator's own output, written by step 13 *after* the
check that reads the record has already run; copying it would make the record a transcript of the
thing it is meant to be compared with. On a fresh checkout it is not there to copy at all, since
`data/derived/` is regenerated and untracked. The report is the right place to *confirm* the hand
evaluation afterwards. It is not the place to source it.

## What checking the branch establishes, and what it does not

**Establishes:** the branch this repository reports is the branch the sealed rules reach when
applied to the recorded quantities, and the manuscript and the file step 13 reads say the same
thing. Moving a threshold, reordering the evaluation, or rewriting a rule to reach a different
branch changes the bytes of a sealed file, which step 12 rejects.

**Does not establish: that the author wrote the branch without having seen the evaluator's
output first.** Nothing here can. The order is unobservable after the fact — `data/derived/` is
regenerated on every run and is not tracked, and commit order is the author's to arrange. The
same author writes the manuscript's claim and performs the hand derivation, so the double entry
above reduces the chance of an honest mistake, not the possibility of a dishonest one.

This is the same boundary §13 of the manuscript draws around the deposit witness: an offline
check can establish that two records agree and that a record is closed against itself. It cannot
reach outside the repository. Stating the limit is the repair available for the part that no
check repairs.

## Record of the hand derivation

> Empty until the arms have run. It is filled in at step 3 above, **before** `repro.sh` is run
> with both verdicts in place.

| | |
|---|---|
| Date | |
| `control` verdict: `verdict` / `rho_hat` / `power` / `tv_bar` / `permutation_reject` | |
| `primary` verdict: `rho_hat` / `power` / `tv_bar` / `permutation_reject` / `none_rate_max_observed` | |
| R5 (control) — satisfied? | |
| R4 (primary) — satisfied? | |
| R3 (primary) — satisfied? | |
| R1 (primary) — satisfied? | |
| R2 (primary) — satisfied? | |
| **Branch reached by hand** | |
| **If the branch is R2, its condition evaluated by hand** | |

The last two rows are **machine-checked**. Their labels are checked on every run, so this template
and the checker cannot drift apart — an independent review found them already drifted, because the
self-check's fixtures carried the checker's own wording and agreed with it whatever this file said.
Once both verdicts have landed, step 9 also fails if the branch row is empty or names a different
branch from the marker in `main.md`, and — when the branch is R2 — unless the second row records
`true` or `false`.

The rows above them are the working, and are **not** checked. A check that a prose cell is
non-empty measures that text exists, not that it says anything, and calling that verification would
be the error this repository keeps trying to remove.

What the two checked rows establish is that the claim appears in two places that were written
separately, and that they agree. They do **not** establish that the derivation was performed before
the evaluator was run, or performed at all: a field can be filled in afterwards. That residue is the
one named above, and no check here reaches it.
