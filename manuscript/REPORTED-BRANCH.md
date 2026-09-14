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
is sealed and this cannot be repaired there. If the branch is R2, read
`detail[-1].value` in `data/derived/decision-report.json` — `true` is the finding, `false` is the
defect condition — and record which in the section below and in the manuscript. Carry the
ambiguity itself as a limitation; it is a property of the pre-registered rules, not of the run.

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
| Branch reached by hand | |
| If R2: `detail[-1].value` | |
