# Deviations from the declaration of the post hoc simulation (B3)

Each entry is a departure from what was fixed at the commit tagged `autopsy-b3-declared`. None is
folded into the declared grid; each says what changed, why, and what it touches.

A bound file (`DECLARED_FILES` in `_common.py`) may differ from its declared bytes only if an entry
below carries a line of exactly the form `- **Waives**: ` followed by the path in backticks. A path
mentioned anywhere else in this file waives nothing, and a waiver of a file that does not differ,
or is not bound, fails the check.

## DV-1 — a generated file in the binding list

- **Waives**: `data/derived/collapse-and-floor.json`
- **Found**: 2026-09-25, when the first full run was started at the declaration commit. The run
  stopped at the binding check before computing any cell.
- **What**: the binding list names the file the side analysis compares its pseudocount-0 row with.
  That file is not tracked: step 8 of `repro.sh` writes it on every run and `.gitignore` excludes
  the directory it is in. It has no blob at the tagged commit, so the binding check could never
  pass while it was listed.
- **Handling**: the file is waived here. Its content is still bound indirectly: the sealed
  `repro.sh` regenerates it from the completed run's annotation, which is itself bound and
  unchanged, and the side analysis's self-test compares with it at run time.
- **What it touches**: no cell, seed, replicate count, reading rule or output.

## DV-2 — the binding check read waivers from prose; two declared scripts changed

- **Waives**: `analysis/autopsy/_common.py`
- **Waives**: `analysis/autopsy/simulate.py`
- **Found**: 2026-09-26, in the review before the pull request (code-reviewer, MEDIUM 3; Codex,
  MEDIUM 1).
- **What**: the declared check waived a bound file whenever this ledger contained its path in
  backticks anywhere. The explanation under DV-1 mentioned the completed run's annotation in
  backticks, so that bound input was waived by accident from the moment DV-1 was written. It had
  not changed, so no output was affected, but the check no longer guaranteed what it said.
- **Change**: `_common.py` now reads waivers only from `Waives` lines, fails on a waiver that covers
  nothing, and treats an absent file as a difference; the comparison is a pure function.
  `simulate.py --self-test` gains (f), which exercises that function on synthetic bytes (a one-byte
  change fails, a mention in prose waives nothing, a waiver line waives, an idle waiver fails), and
  (g), which requires the full-grid workflow's path filter to cover every bound file.
- **What it touches**: no cell, seed, replicate count, reading rule or output. After the change the
  replicate-0 check, the side analyses and the summaries were recomputed and equal the committed
  files byte for byte.
