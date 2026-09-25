# Notes on the reference list

Reference numbers such as `[28]` are **permanent identifiers** drawn from the author's central,
append-only bibliography. They are not renumbered between manuscripts, which is why the numbers in
`main.md` are not consecutive. The full bibliographic entries a reader needs are in the References
section of `main.md`; this file records what each reference is doing in the argument.

## What each reference carries

| `[n]` | Role in this manuscript | Section |
|---|---|---|
| [2] | The generative-agent architecture this apparatus descends from | §2 |
| [27] | An adjacent case of separating an instrument artefact from a real effect | §2 |
| [28] | **Load-bearing, in two directions.** It shows that bringing declared-margin, equivalence-style reading to language-model evaluation is already established — which is what removes that framing from this paper's novelty — and it is what justifies declaring `delta_tv_min = 0.10` in advance as adherence to existing practice | §2, §3.3 |
| [29] | The formal reference point for the sample complexity of estimating total-variation distance. **The estimand differs**: sequence-level there, decision-level categorical here, and the manuscript says so. Also the source for why logit access would be cheaper, which is stated as a limitation | §2, §I.2 |
| [35] | The basis of the power discussion: conclusions in NLP often rest on designs without the power to support them. **An earlier version of this table called it load-bearing because the paper claimed the design was *not* underpowered; that claim is withdrawn** — the reported `power` is the nominal sensitivity of a surrogate; the sealed design did not evaluate the power of the decision's test, and §4.3 simulates it post hoc (§6.2) | §2 |
| [36] | The standard procedure for equivalence testing against pre-specified bounds. **Citing it does not mean performing it** — §3.4 states that no formal TOST or Bayesian equivalence test is run | §2, §3.3 |
| [37] | The preregistration framework this submission sits inside | §2 |
| [38], [39] | Validation of generative social simulation; positioning | §2 |
| [40] | **A reachable source for a gap, not a closure of it.** §A records that the ES-1 determinism record was not retained as a shipped artefact; [40] reports the determinism and byte-exact replay properties of the same upstream apparatus, with a public verification path. It is a different body of evidence, **no quantity from it is quoted**, and §I.4 still carries the gap | §A, §I.4 |
| [41] | A direct test of equivalence between two multinomial distributions under the L1 or maximum norm. **Cited to place the question, not as a method used**: this protocol runs no equivalence test (§3.4) | §1.2, §2 |
| [42] | Minimax estimation of the L1 distance between discrete distributions; in its large-alphabet, non-asymptotic setting the plug-in estimate is not rate-optimal. Supports the statement that estimating the distance is a problem in its own right. **No efficiency claim is made for `tv_bar`** | §1.2, §2 |
| [43] | Chi-square-type statistics are extremely sensitive to perturbations of small cells, and the classical test can have poor power when many cells are small. **Their setting is high-dimensional; ours has five cells**, and the manuscript says so. The sensitivity to small cells is what places §4.1 among known behaviour | §1.2, §2 |
| [44] | Power computed after the data cannot be used to interpret a non-significant result. Moves that reading of a power figure into the known column. **The sealed R3 comes close to that form** (computed after the draws on the run's own channel-off base, at the registered `delta_tv`, and a condition of R1); §2 says so, and the manuscript does not read a pass of R3 as evidence about the decision's power | §1.2, §2 |
| [45] | Meaning-preserving prompt-format changes move measured LLM performance. With [47], what makes the dropped draws of §4.2 an instance of a known class rather than a new finding | §1.2, §2 |
| [46] | LLMs prefer particular positions and identifiers among listed options. Names a perturbation (the fixed order in which the template lists the zones) that this apparatus does not vary | §2 |
| [47] | Requiring a structured output format such as JSON can lower LLM performance. Cited for the class of dependence, not for a mechanism of the `None` draws | §1.2, §2 |

## Verification caveats, stated rather than smoothed over

- Entries [27]–[31] were confirmed from abstracts only. Author order, affiliation and version are
  re-checked against the source before formal citation.
- **[37] has an internal inconsistency**: the arXiv identifier and the submission date returned by
  the arXiv API do not agree. Both are recorded exactly as retrieved, with no correction inferred.
  The manuscript notes this at the reference itself.
- Entries [35]–[39] were confirmed on 2026-09-12 by parsing the raw JSON returned by Crossref and
  the arXiv API directly. Intermediate summarisation was not relied on: a summarising step had
  dropped a diacritic from an author's name, which is the kind of error that survives review.
- **[40] was confirmed on 2026-09-15** by reading the archive's own JSON record rather than any
  local note: title, creator, `publication_date` 2026-09-13, concept identifier
  `10.5281/zenodo.22719772`, and the identifier of the current version. The record carries **no
  `version` field**, so no version number is written for it; the concept identifier is cited
  because it resolves to whatever the current version is. A working note held elsewhere called it
  "v4", which the record does not support, and the record is what is followed here.
- **[40] is prior work by the same author**, which is why it is not listed among the cited DOIs
  that `analysis/scripts/make_anonymous_bundle.py` declares to belong to other people. Declaring it
  there would silence the leak scan while a reviewer who followed the link arrived at a page
  carrying the author's name. It is substituted like this study's own deposit identifiers instead,
  which is what it is.
- **[41]–[47] were confirmed on 2026-09-25** from the raw JSON returned by Crossref, the arXiv API
  and OpenAlex, parsed directly. Initials are copied as the source gives them: [41] is written with
  initials because that is all Crossref holds, and no fuller form was taken from elsewhere. The page
  range of [43] is not in Crossref or OpenAlex; it was taken from the publisher's citation line and
  matched against an independent citation. [45] and [46] carry neither a DOI nor a journal
  reference and are cited as arXiv preprints; their records' comment fields name ICLR 2024, which is
  the authors' own statement and is not written into the entry.
- Sources cited in the published files of this repository must be reachable by a reader of it.
  Working directories that are not shipped here are not citable sources.
