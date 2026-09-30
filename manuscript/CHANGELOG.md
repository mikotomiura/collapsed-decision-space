# Changes to the manuscript

This file records what left `manuscript/main.md` and where moved content went, so that nothing leaves
silently. Sections are named by title, not by number, because numbers change between versions. The
file is not part of the submission PDF, and it changes nothing that the sealed rules, the frozen
files or the checks say.

## 2026-09-30 — restructured around the three gates

The body now runs: introduction; setting and protocol; what the sealed rules returned; one section per
gate (power, entropy floor, cap on draws with no recorded zone); lessons and related work;
limitations. The appendices keep their letters. Every rendered number the checks hold moved with its
sentence, word for word.

### Where the content of the earlier body went

| Earlier section (by title) | Now |
|---|---|
| Introduction, and its table of the three gates | Introduction (the gates in words, no numbers); *What the sealed rules returned* (what the runs show at each gate, with the rendered numbers) |
| The apparatus, and what the claims are about | *Setting and protocol*: the agent, the world and the read-out |
| What is new here, and what is not | Introduction (three contributions); appendix *Further related work* (the standard results); the power worksheet (the observation that concentration is not what lowers the surrogate's power) |
| Analysis map | *Setting and protocol*: analysis map. The commit and the tag left the table; the held-out freeze commit is in the title of the held-out test's table |
| Background | *Lessons and related work*: related work; appendix *Further related work* |
| Estimand, decision function, and the margin | *Setting and protocol*: estimand, test, margin and gates; appendix *The margin, and why no equivalence test is run* |
| A completed run of the same measurement on one model | *Setting and protocol*: the manipulation and the runs |
| The support of the read-out, and what the power gate can see of it | *Gate 1*: the surrogate and its sweep; *Gate 2*: the support; the permutation-null mean moved to the appendix section *The estimates the permutation test did not reject*, under its own post hoc tag |
| What the dropped draws are | *Gate 3*: what the dropped draws are |
| Simulated operating characteristics of the sealed pipeline | *Gate 1*: simulated operating characteristics; the definition of the rates and the details of the degenerate base moved to the appendix on the simulation |
| Results of the prospective run | *What the sealed rules returned* (the registered paragraphs and the sealed reading of R4 beside the data); *Gate 2* (the descriptive paragraphs and the table of zones) |
| A held-out test of the post hoc observation | *Gate 3*: a held-out test of the post hoc observation |
| Limitations | *Limitations* (model family and think regime; execution order; a shared collapse); the paragraph on the surrogate's power moved to *Gate 1* |
| Appendix N, notes to the introduction and the background | The two notes of scope → *What the sealed rules returned*; how the runs exposed the rows, and what recurred → *Gate 3*; the earlier reading, withdrawn → this file; further related work → appendix N |

### Added

- **The setting every draw was made in**, read from the per-draw records of the three runs and tagged
  post hoc: one system prompt and one user prompt across all 14,400 draws, the sampling of each
  condition, and eight pairs of blocks per run. The phrases are rendered from the records and held
  by the checks. The sealed words "contexts" and "per-context λ" are kept, with the statement that
  on the records a context is a pair of blocks of one prompt.
- The scope sentences the manuscript states for itself now read "two models and one frozen prompt
  run in eight pairs of blocks". Quotations of the frozen held-out specification keep its words.
- A guide at the head of the appendices, and a title above every table.

### Removed from the manuscript, and recorded here

**The earlier reading, withdrawn** (formerly the fourth note of appendix N). An earlier version of
the manuscript, under a different title, read the completed run as a statement about how the margin
and the power gate behave when some zones are never produced. That reading is withdrawn, with the
first item of the earlier list of what is new. In brief, at the registered effect size the surrogate
returns full power on a near-uniform base as well, so the empty zones are not shown to be why the
power gate passed; and the permutation-null mean of the distance is a finite-sample reference value,
not a part of the estimate that can be subtracted from it.

An earlier version of the section on the support of the read-out called the permutation-null mean a
floor under the estimate, read the ratio of the two as the share of the estimate that floor accounts
for, and argued that collapse raises it until it takes up much of the declared margin. None of that
holds. The permutation-null mean is the expected value of the statistic under a finite-sample null: a
reference value against which the observed statistic is read, not an additive component that can be
subtracted from it. For a fixed number of draws the null expectation of this plug-in distance does
not rise as the base concentrates; the appendix on the simulation states the approximation. The
earlier version also read the empty cells as the reason the power gate passed, which the
surrogate's return of 1.0 on a near-uniform base does not support. What the numbers support is what
the permutation test already reports: the observed value is not distinguishable from the null at the
declared α, and no threshold or decision rule changes because of it.

The earlier list of what is new opened with an item about how the margin and the power gate behave
together when some zones are never produced. That item is withdrawn with the reading it stated; its
last item, on placing a measurement-validity gate ahead of the estimate, is folded into the first
contribution. The note that the phrase *instrument autopsy* also appeared in the title of an
adjacent paper is removed with it.

**Other sentences that described earlier versions.**

- From the limitations, on the surrogate's power: "Earlier drafts described `power` as the attained
  power of the realised design, which overstated the connection."
- From the introduction: the pointer to "the reading of an earlier version of this manuscript that
  is withdrawn", and the list item "kept from an earlier version of this list".
- From the appendix section on the estimates the permutation test did not reject: the sentence that
  its first line restated the section on the support, which no longer holds once the body stopped
  quoting the permutation-null mean.
- From the list of what is new: the item on the estimand itself (an agent-internal modulation acting
  on a downstream categorical choice, rather than agreement between two models' output
  distributions). It is not among the three contributions of the restructured introduction.

**Registered-report vocabulary.** The preface to the decision rules and the section on what breaks
the seal no longer name in-principle acceptance, a recommender or a completion report. The rule
block generated from the seal is unchanged.
