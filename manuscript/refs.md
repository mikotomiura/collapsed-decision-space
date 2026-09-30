# Notes on the reference list

Reference numbers such as `[28]` are **permanent identifiers** drawn from the author's central,
append-only bibliography. They are not renumbered between manuscripts, which is why the numbers in
`main.md` are not consecutive. The full bibliographic entries a reader needs are in the References
section of `main.md`; this file records what each reference is doing in the argument.

## What each reference carries

| `[n]` | Role in this manuscript | Section |
|---|---|---|
| [2] | The generative-agent architecture this apparatus descends from | §1, §2.1, §N.1 |
| [27] | An adjacent case of separating an instrument artefact from a real effect, in a pre-registered setting | §7.2, §N.1 |
| [28] | An application of equivalence testing at a declared margin to language-model evaluation (claims that a compressed model is equivalent to its original). It places the margin of this protocol within existing practice; the grounding for fixing a bound in advance is [36], and [28] is the example of that practice in language-model evaluation | §7.2, §N.1, §N.2 |
| [29] | The formal reference point for the sample complexity of estimating total-variation distance. **The estimand and the access differ**: sequence-level there, with samples of the next token after any prefix or its logits; decision-level categorical here, from independent whole generations, and the manuscript says so. Also the source for logit access lowering the number of queries, which §I.2 states for autoregressive models and not for this quantity | §7.2, §I.2, §N.1 |
| [35] | The basis of the power discussion: conclusions in NLP often rest on designs without the power to support them. The reported `power` is the nominal sensitivity of a surrogate; the sealed design did not evaluate the power of the decision's test, and §4.2 simulates it post hoc (§4.1) | §1, §7.1, §N.1 |
| [36] | The standard procedure for equivalence testing against pre-specified bounds, and the grounding for fixing a bound in advance. **Citing it does not mean performing it** — §2.3 and §N.2 state that no formal TOST or Bayesian equivalence test is run | §1, §2.3, §7.2, §N.1, §N.2 |
| [37] | An argument for preregistration in experiments with AI agents | §7.2, §N.1 |
| [38], [39] | Validation of generative social simulation; positioning | §1, §7.2, §N.1 |
| [41] | A direct test of equivalence between two multinomial distributions under the L1 or maximum norm. **Cited to place the question, not as a method used**: this protocol runs no equivalence test (§2.3) | §2.3, §7.2, §N.1 |
| [42] | Minimax estimation of the L1 distance between discrete distributions; in its large-alphabet, non-asymptotic setting the plug-in estimate is not rate-optimal. Supports the statement that estimating the distance is a problem in its own right. **No efficiency claim is made for `tv_bar`** | §7.2, §N.1 |
| [43] | Chi-square-type distances are extremely sensitive to small perturbations of small cells, and the classical test can have poor power in the high-dimensional setting; the truncated statistic bounds each cell's denominator from below. **Their setting is high-dimensional; ours has five cells**, and the manuscript says so. The sensitivity to small cells is what places §4.1 among known behaviour | §4.1, §7.1, §B.1, §N.1 |
| [44] | Power computed after the data cannot be used to interpret a non-significant result. Moves that reading of a power figure into the known column. **The sealed R3 comes close to that form** (computed after the draws on the run's own channel-off base, at the registered `delta_tv`, and a condition of R1); §N.1 says so, and the manuscript does not read a pass of R3 as evidence about the decision's power | §1, §4.1, §7.1, §I.6, §N.1 |
| [45] | Meaning-preserving prompt-format changes move measured LLM performance. With [47], what makes the dropped draws of §6.1 an instance of a known class rather than a new finding | §6.1, §7.1, §7.2, §N.1 |
| [46] | LLMs prefer particular positions and identifiers among listed options. Names a perturbation (the fixed order in which the template lists the zones) that this apparatus does not vary | §7.2, §N.1 |
| [47] | Requiring a structured output format such as JSON can lower LLM performance. Cited for the class of dependence, not for a mechanism of the `None` draws | §6.1, §7.1, §7.2, §N.1 |
| [48] | Which significance test suits an NLP comparison depends on its evaluation measure and setup. Supports the first diagnostic of §7.1: the power that matters is that of the test actually chosen | §7.1 |
| [49] | Simulation studies, in which the data-generating mechanism sets the truth, are the standard way to evaluate a statistical method's properties. Places the simulation of §4.2 and the first diagnostic of §7.1 among standard practice. **The simulation here is a property of the design under assumed distributions**, as §4.2 says | §4.2, §7.1 |
| [50] | Complete-case analysis, which confines an analysis to the units with no missing value, can be biased, and weighting is one way to adjust for it. Supports the third diagnostic of §7.1: dropping the draws with no recorded zone and renormalising is such an analysis. No adjustment is applied here | §7.1 |

## Verification caveats, stated rather than smoothed over

- **Every entry was re-confirmed on 2026-09-30**, in two steps. First, the bibliographic fields,
  from the raw records returned by Crossref, the arXiv API and OpenAlex, parsed directly (authors in
  order, title, year, venue, volume, issue, pages, identifier). Second, the content: each citing
  sentence was set beside the source's abstract, and for the four preprints of 2026 ([27], [28],
  [29], [37]) beside the sentences of their full text on arXiv. Where a sentence said more than the
  source, the sentence was changed: [29]'s access models are now stated as that paper defines them,
  and §I.2 no longer says that logit access would make this quantity far cheaper; [38] is no longer
  said to contrast validation with capability; §7.1 no longer says "empty" cells for [43]; and [37]
  is cited for its argument, not as framing the question of this paper.
- **[37]**: the arXiv identifier (2606, June 2026) and the submission date on both the API record and
  the abstract page (3 May 2026, a single version) do not agree. The entry gives the year, on which
  both agree, and nothing is inferred about which is right.
- **[41]** has no abstract in Crossref or OpenAlex; its content was checked against the abstract of
  its arXiv version (2305.08609), which names the maximum and L1 norms.
- **[43]**: the page range is not in Crossref, OpenAlex or Semantic Scholar, and the publisher's page
  could not be read by a script on 2026-09-30. It was taken on 2026-09-25 from the publisher's
  citation line and matched against an independent citation. Its content was checked against the
  full text of its arXiv version (1712.06120).
- **[50]**: Crossref gives the authors' given names as "Roderick" and "Donald" only, so the entry
  carries those initials and no middle initials; none were taken from elsewhere. The edition is in
  the title, as Crossref records it (its edition-number field says 1, which the title contradicts).
  The statement cited is from the abstract of the book's chapter 3, "Complete-Case and Available-Case
  Analysis, Including Weighting Methods".
- Initials are copied as the source gives them: [41] is written with initials because that is all
  Crossref holds, and no fuller form was taken from elsewhere. [45] and [46] carry neither a DOI nor
  a journal reference and are cited as arXiv preprints; their records' comment fields name ICLR
  2024, which is the authors' own statement and is not written into the entry. The same holds for
  the comment field of [37].
- Sources cited in the published files of this repository must be reachable by a reader of it.
  Working directories that are not shipped here are not citable sources.
