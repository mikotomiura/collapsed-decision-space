# Notes on the reference list

Reference numbers such as `[28]` are **permanent identifiers** drawn from the author's central,
append-only bibliography. They are not renumbered between manuscripts, which is why the numbers in
`main.md` are not consecutive. The full bibliographic entries are held as data in `refs.json`, a
CSL-JSON array, and the References section of `main.md` is rendered from it by
`analysis/scripts/render_references.py`, which also fails if the two disagree. This file records
what each reference is doing in the argument.

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
| [54] | A practical guide to Registered Reports in neuroscience: a design is meant to make a null result credible, and the sample size is to be calculated for the tests proposed. Cited as the guide's recommendation, not as a methodological source | §1 |
| [55] | In a Registered Report, peer review and the decision to publish take place before the results are known. Only that sentence is cited; the paper's comparison of positive-result rates is not used | §1 |
| [56] | What a Registered Report asks of a protocol at Stage 1: outcome-neutral conditions (positive controls, the absence of floor and ceiling effects), specified before the results are known and independent of the primary outcome measures. **An organisation's web page, not a peer-reviewed source.** **This protocol's own use of "outcome-neutral" (§G.1) is narrower** -- pass criteria fixed in advance -- and the manuscript says so; it does not claim that the gates meet the requirement, and states that the protocol was not reviewed as a Registered Report | §1, §7.2 |
| [57] | An audit of adherence to plans and of the disclosure of deviations, in the 27 preregistered studies published in *Psychological Science* from February 2015 to November 2017 | §1, §7.2 |
| [58] | In the public review histories of 201 PLOS articles, someone reported accessing the preregistration for 14%. The figure is per article (it is 5% per editor or reviewer, of 689), and "reported accessing" is the source's own wording, not a statement that the preregistration was checked | §1, §7.2 |
| [59] | In a sample of preregistrations, 5 of the 13 completely reported power analyses addressed a test other than the main test of the hypothesis. **The denominator is 13**, and the manuscript gives it | §1, §7.2 |
| [60] | Power computed at the effect estimated from the data adds no information beyond the *p* value; a sensitivity analysis over the smallest effect size of interest and a realistic range of expected effects is recommended instead. **The sealed R3 is computed at the registered margin, not at an observed effect**, so the manuscript says how it differs from that form, as §N.1 does with [44], and does not call it that error | §7.2 |
| [61] | Equivalence bounds are fixed before the results are known, and the value of an equivalence test rests on how well its bounds are justified. **Not used to justify the margin of 0.10 after the fact** (§2.3, §N.2), and no equivalence test is run | §7.2 |
| [62] | A non-significant result is not evidence that an effect is absent | §7.2 |
| [63] | In online experiments, participants who drop out of conditions for different reasons can confound the comparison between them. **An analogy, stated as such**: the dropped draws here are outputs the parser could not read, not participants leaving, and the manuscript applies neither source to them | §1 |
| [64] | In clinical trials, a difference in dropout rates does not by itself establish bias. **An analogy**, as for [63] | §1 |

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
  carries those initials and no middle initials; none were taken from elsewhere. Crossref writes the
  edition into the title ("…, Third Edition") while its edition-number field says 1; the OpenLibrary
  record of the same book (ISBN 9780470526798) gives the title without it. Since 2026-10-04 the
  entry holds the title alone and the edition (3) as its own field. The statement cited is from the abstract of the book's chapter 3, "Complete-Case and Available-Case
  Analysis, Including Weighting Methods".
- **[54] to [64]** were confirmed on 2026-10-03 in the same two steps: the bibliographic fields from
  the raw Crossref records (read again on 2026-10-04, when the entries were added), and each citing
  sentence beside the source's own words -- the full text for all but [55] (its abstract) and [56]
  (the page itself). **[56]** is an organisation's web page, read on 2026-10-03; it shows no date and
  is cited "n.d.". **[58]**: the year is that of the issue that carries the article (2026, volume 6,
  issue 1); the article itself was first published on 2025-04-01. **[62]**: Crossref's title has a
  non-breaking space before "frameworks", written here as an ordinary space. **[64]**: Crossref
  holds the authors' initials only, and the entry carries no more.
- Initials are copied as the source gives them: [41] is written with initials because that is all
  Crossref holds, and no fuller form was taken from elsewhere. [45] and [46] carry neither a DOI nor
  a journal reference and are cited as arXiv preprints; their records' comment fields name ICLR
  2024, which is the authors' own statement and is not written into the entry. The same holds for
  the comment field of [37].
- **Titles are in sentence case** since 2026-10-04: the first word, the first word after a colon, a
  question mark or a dash, proper nouns and acronyms keep their capitals, and nothing else in an
  entry changed. **[2]**'s six authors, which the printed entry shortens to "et al.", are held in
  `refs.json` as the arXiv API record lists them, reduced to initials.
- Sources cited in the published files of this repository must be reachable by a reader of it.
  Working directories that are not shipped here are not citable sources.
