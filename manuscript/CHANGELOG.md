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

The dates now name their time zone and follow the shipped attempt logs, which record UTC: both arms
ran on 2026-09-14 (UTC). The frozen held-out specification and some other records of this
repository give dates in Japan Standard Time, in which the captures finished on 2026-09-15.

### One sentence of the abstract

The sentence on the simulation of the power gate read: "On the first run's channel-off base, along
the surrogate's direction, a post hoc simulation declared in advance finds that test's rejection
rate at the surrogate's 1.0 from half the registered effect size upward, …". It now says what the
simulation does before what it finds: "A post hoc simulation of that test, fixed before it ran,
shifts the first run's channel-off distribution as the surrogate's alternative does: the test's
rejection rate stands at the surrogate's 1.0 from half the registered effect size upward, …". The
numbers, the base, the direction and the layer are unchanged, and so is the abstract of
`CITATION.cff`, which must be the same text.

### After the final review

- Every paragraph that reports an analysis outside the sealed rules now opens with its layer tag, as
  the analysis map says; eleven continuation paragraphs had none. The sentence on the surrogate's
  return of 1.0000 for two reference bases is back in the post hoc paragraph of the power gate.
- `P(R2)` is defined where it is introduced as the share of replicates that reach R2, with the two
  ways R2 is reached and the stops at R4 or R3 that do not count.
- The introduction says the checks redraw every figure and compare most quoted quantities with the
  data, which is what the reproduction section describes.
- The description of the anonymous build no longer speaks of a review supplement: the de-identified
  copy is an intermediate of the build and is not submitted. In the anonymous PDF, the deposit's
  identifiers and registration time are withheld, and the statements of what a reader can check
  say that they need the public compendium.
- To keep the references on page 12 after the additions above, these sentences left the body:
  "§I.6 says what a pass of R3 can be read as." (power gate); "§M.1 and §M.2 give the reasons in
  full." (entropy floor); "Each is stated by its input, what it looks at, what it can show, what it
  cannot, and the work it rests on." (the three diagnostics, which still follow that order);
  "§N.1 discusses this work further." (related work); "Obtaining R1 across the two arms would not
  have licensed any statement about which of the two factors is responsible." (model family and
  think regime); "§I.7 says what would distinguish the two." (a shared collapse). The appendix
  sections they pointed to are unchanged. Also: "§B.4 says what the annotation does not record
  about these draws, and how a reader re-parses them." (what the dropped draws are); "The shipped
  annotation files hold the draws in that order." and "Separating them would take a randomised or
  counterbalanced condition order, under assumptions about drift and serial dependence, in a new
  run under a new seal." (execution order; the setting and the third diagnostic state both); and the
  clause "and the obvious distilled candidate belongs to the same family as the reference" (model
  family and think regime). Figure 2's source moved to the end of the power gate's
  first subsection, which changes where the float is set and nothing in the text.

## 2026-10-01 — after a pre-submission review

A pre-submission review found the claims narrowly stated but the framing broader than the evidence
for two of the three gates, and the prose hard to follow for its code names and file paths. The
changes below narrow, separate and move what the manuscript says. None adds an analysis, a test or a
simulation, and every rendered number moved with its sentence.

### The abstract

Rebuilt around the setting, what each gate read, what each did to the decision, and the names of
the three diagnostics. It now says that the evaluation is the authors' own; that on the records each
condition was sampled at one fixed temperature and top-p, the channel-on block first; that the power gate agrees with the test at the margin in the simulation but passes a tenth
of it as well; that the entropy floor decided the outcome although every cell of the second model
produced two to four zones; and that the cap passed every run. "A held-out test found more such
draws" became "A test specified after that difference was seen, on draws already collected, found
such draws … more often", with the differences as rates and the assumption its *p*-values rest on.
The rendered phrase "from half the registered effect size upward" now reads "from half the margin
upward": the two named the same 0.10. The abstract of `CITATION.cff` is the same text.

### The introduction

- The opening of the second paragraph no longer states the three gates as what every pre-registered
  evaluation must have: "A pre-registered evaluation that may end in a null must fix in advance what
  a null is worth … It does so through gates" became "… has to settle in advance what a null will be
  worth … The one studied here does so through three gates".
- "We examine one sealed evaluation of this kind." became "We designed and sealed this evaluation
  ourselves, and examine it here."
- The paragraph on what each gate read now says what each did to the decision, and when each reading
  was first seen. It replaces "The prospective arms and a held-out test did not settle this; they
  exposed it." The title of the table of the three gates says that its right column was set after
  the results were seen.
- "they do not use the value of the margin" became "they do not rest on whether 0.10 was a
  well-chosen margin, although whether the power gate agrees with the test depends on that value";
  *Estimand, test, margin and gates* says the same in place of "The claims of this paper do not use
  the value."
- The first contribution is the case itself; "shipped with rules, records and checks that redraw
  every figure …" became a sentence that says where those are.
- Removed: "§2 sets out the agent, the manipulation, the estimand and the gates. §3 reports what the
  sealed rules returned, and §4 to §6 take the three gates in turn. §7 states the diagnostics, and §8
  the limitations."

### Setting and protocol

- Removed: "§C gives the sealed design, and §I.2 the cost of sample access."
- "Stratifying by block does not make the draws within a block exchangeable over their positions,
  and the held-out test states that as an assumption (§6.2)." left *The manipulation and the runs*;
  the title of the held-out test's table now carries the assumption.
- After the analysis map, three sentences that restated its rows left: "The [Post hoc] layer is the
  re-analysis of the completed run that the sealed plan excludes (§F), carried out outside that plan
  and labelled as such. The [Held-out] layer tests a hypothesis the [Post hoc] layer produced, on
  draws collected before its specification existed, and is not given the standing of the sealed
  analysis." The map's post hoc row points to the appendix on eligibility instead of to a section of
  `seal/protocol.md`.

### What the sealed rules returned

- The recorded quantities are named in words (the recorded power, the estimate, the share of
  admitted contexts, the largest rate of draws with no recorded zone); the appendix *The six
  quantities the rules read* gives the record's name for each. A sentence says that values are
  quoted to the digits the records carry.
- "The branch below was derived by hand from the two landed verdicts and `seal/decision-rules.json`,
  quantity by quantity, in `manuscript/REPORTED-BRANCH.md`." became "the branch below was also
  derived by hand from the two verdicts and the sealed rules (§J)"; the figure's caption names "the
  sealed rule file". Removed: "and 9,600 in total"; "the estimate sits 0.007490 from the centre of a
  tolerance of 0.03" became "the estimate lying within the tolerance of 0.03 around the completed
  run's".
- The sealed reading of R4 is quoted word for word, and the text says in its own words that the
  registered scoring returned no estimate, while each condition's zone distribution can still be
  described.
- Removed: "§M gives further results of the run, including the scorer's exit label record by record
  (§M.4)." The exit-label sentence points to that appendix section.

### The three gates

- *Gate 1*: Figure 2's caption says that the rates are Monte Carlo estimates with intervals in the
  appendix on the simulation, and that shifts one grid step apart are not distinguished; "not an
  estimate of any effect of the channel" and "It estimates nothing the channel did" left, since the
  introduction and the limitations say it. The simulation paragraph now says that at the margin the
  test's rate reaches 0.8 in every base and direction the declared grid runs at that size, which
  is not every direction on every base. "§B.3 gives the declaration, the design and every declared
  cell." left the end of the section on the simulation: the caption of Figure 2 points to the same
  appendix section.
- *Gate 2*: a post hoc paragraph says what the simulation shows about the empty zones (one grid step
  at most for the test) and about the degenerate base, and that the primary arm's base was not
  simulated.
- *Gate 3*: the prompting module's path and line numbers moved to the appendix *What the record of
  the dropped draws does not show*; the held-out test's file names moved to *Data, code and
  reproducibility*; a section of `seal/protocol.md` became a reference to the sealed rules. The
  differences between conditions are stated as rates. The sentence on exchangeability moved into
  the title of the held-out test's table. The order paragraph names the higher temperature and top-p
  of the channel-on blocks.
- The appendix section *The secondary six-category distance of the held-out test* moved into the
  held-out test's section, beside the control arm's five-zone estimate; the appendix section is gone.

### Lessons and limitations

- "it measures the power the decision actually has" became "it measures the power the decision would
  have under the simulated bases and shifts".
- "Dropping them is a complete-case analysis, which can be biased when the dropped units differ from
  those kept" became a sentence that says what the estimand then describes, and for which reading it
  can be biased.
- *Condition is confounded with execution order*: the file, the lines and the commit that fix the
  order moved to *What the checks reach on the prospective arms*; a clause names a generic effect of
  the higher temperature and top-p among the alternatives.
- *What the two arms' gate quantities do and do not compare*: "the quantity that would answer it was
  not estimable there" became "the registered scoring procedure returned no estimate there".

## 2026-10-01 — a reading of the final PDF before submission

Three sentences of the appendices had not followed earlier changes. None moves a claim or a number.

- *AI usage disclosure*: the Claude models now include Opus 5.5, and the Codex models `gpt-6-astra`.
  Both were used after the list was written: the commits of this repository name Opus 5.5 in their
  trailers, and `gpt-6-astra` reviewed the revisions of 2026-09-30 and 2026-10-01.
- *Provenance gaps we are carrying*: "All three gaps are stated" became "Both gaps are stated". The
  third, the per-draw record of the completed run, has been shipped since 2026-09-25, and the
  paragraph already said so.
- *What the record of the dropped draws does not show*: "(results section)" became "(§I.5)". The
  unnumbered results section it named became *What the sealed rules returned* on 2026-09-30, and the
  shipped records of the two arms are described in *What the checks reach on the prospective arms*.
