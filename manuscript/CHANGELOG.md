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

### Sentences about earlier versions, rewritten as present facts

The appendices described several earlier states of the compendium. Each now states the present
fact; the earlier state is recorded here. The three disclosures of a sealed text that does not match
the data or the run output stay in the manuscript: the sealed reading of R4 (*What the sealed rules
returned*), the sealed word "pooled" (*The six quantities the rules read*), and the sealed script's
word "floor" (*Data, code and reproducibility*).

- *The six quantities the rules read*: "earlier drafts of this protocol said 'pooled', which named
  nothing that exists" is now "the sealed text's word 'pooled' names a quantity the run output does
  not contain".
- *Claim-boundary enforcement*: the negative control's sentence is described as "a sentence that
  corrects an earlier reading" rather than "the withdrawal of an earlier reading". The fixture is
  unchanged.
- *What the seal covers*: the provenance module "was missing from an earlier version of this list —
  which is why the seal now also fails if a sealed script imports a local module that is not itself
  sealed".
- *Provenance gaps* and *What the checks reach*: the per-draw record of the completed run was, in
  earlier versions of the compendium, referenced by hash rather than included, to keep the
  repository small; it has been shipped since 2026-09-25, when the recomputation of the two
  prospective verdicts was added as well.
- *Data, code and reproducibility*:
  - The paragraph on the tag `stage1-submitted`, which marks the state submitted to PCI Registered
    Reports in September 2026, moved to the README.
  - The sealed `repro.sh` "describes step 8 in the vocabulary of an earlier version" of the section on
    the support of the read-out, "in which the permutation-null mean was called a floor".
  - "The deposit carries an earlier working title of this manuscript in its title field."
  - On step 14: "we would rather say so than be found out", and "An independent review demonstrated
    the gap by writing a witness from nothing … and an earlier version of this check reported no
    problems at all. The closure requirements above are the repair for what an offline check can
    repair; this paragraph is the repair for the rest."
  - On step 9: "An earlier version of this section said that a single altered digit fails the run".
- *AI usage disclosure*: "these two rows were both wrong by the time anyone read them once before",
  and "The figure here was briefly pinned to a commit on a feature branch, which the squash-merge of
  that branch left unreachable from `main`; the row now names a commit on `main`, and the count fell
  from 30 to 20 because squashing is what the public history actually records."
- *Section numbers cited by files that cannot change*: "This manuscript was reordered for submission:
  the body comes first, then the references, then the appendices, and its sections were renumbered"
  (2026-09-26). The table's column "Earlier number" is now "Number cited".

### The anonymous build

`analysis/scripts/make_pdf_source.py` no longer rewrites the sentence on the tag of an earlier
submission, because the sentence left the manuscript. `analysis/scripts/check_pdf_identity.py` still
fails the anonymous build if the tag or that venue reaches the page.

## 2026-09-30 — references, and what the anonymous PDF withholds

### References

- **Removed**: the author's own prior preprint on the upstream apparatus's determinism. The two
  sentences that pointed to it, at the end of the appendix on the apparatus and in *Provenance gaps*,
  left with it. The gap they sat beside, the record of the determinism study that is not shipped, is
  still stated in both places.
- **Removed**: the note at the preregistration entry that its arXiv identifier and its submission
  date do not agree. The entry gives the year, on which both agree; `manuscript/refs.md` records the
  disagreement.
- **Added**, each where one of the three diagnostics names the work it rests on: a guide to choosing
  significance tests in NLP, and a tutorial on simulation studies (the first diagnostic, and the
  simulation of the power gate); a standard text on missing data (the third diagnostic).
- **Changed to say what the source says**, after every entry was checked against its abstract and,
  for the preprints of 2026, their full text: the access models of the total-variation estimation
  paper; the sentence in *Sample access rather than logit access*, which said that logit access would
  make this quantity far cheaper; the review of generative social simulation, which does not
  contrast validation with capability; "small and empty cells", now "small cells"; and the sentence
  in which the preregistration paper was said to frame this paper's question. The margin rests on the
  equivalence-testing primer; the audit of compressed models is its application in language-model
  evaluation.

### The anonymous build

The anonymous PDF is built for a submission with no supplement. It defines "this repository" and
"shipped" once, in *Data, code and reproducibility*, as the compendium made public after review, and
rewrites the sentences that name a location, a supplement, or a file name specific to the upstream
project. `analysis/scripts/check_pdf_identity.py` fails the anonymous build if any of those words
reaches the page or the source the page is set from.

### The dates of the prospective runs

The dates now name their time zone: "2026-09-14 and 2026-09-15 (Japan Standard Time)". The attempt
logs shipped in `data/attempts/` record their times in UTC, in which both runs fall on 2026-09-14;
the frozen held-out specification and the other records of this repository give the dates in Japan
Standard Time.

### One sentence of the abstract

The sentence on the simulation of the power gate read: "On the first run's channel-off base, along
the surrogate's direction, a post hoc simulation declared in advance finds that test's rejection
rate at the surrogate's 1.0 from half the registered effect size upward, …". It now says what the
simulation does before what it finds: "A post hoc simulation of that test, fixed before it ran,
shifts the first run's channel-off distribution as the surrogate's alternative does: the test's
rejection rate stands at the surrogate's 1.0 from half the registered effect size upward, …". The
numbers, the base, the direction and the layer are unchanged, and so is the abstract of
`CITATION.cff`, which must be the same text.
