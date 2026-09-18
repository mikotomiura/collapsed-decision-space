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
| [28] | **Load-bearing, in two directions.** It shows that bringing declared-margin, equivalence-style reading to language-model evaluation is already established — which is what removes that framing from this paper's novelty — and it is what justifies declaring `delta_tv_min = 0.10` in advance as adherence to existing practice | §2, §4.3 |
| [29] | The formal reference point for the sample complexity of estimating total-variation distance. **The estimand differs**: sequence-level there, decision-level categorical here, and the manuscript says so. Also the source for why logit access would be cheaper, which is stated as a limitation | §2, §12.3 |
| [35] | The basis of the power discussion. Load-bearing, because this paper's claim is precisely that the design is *not* underpowered | §2 |
| [36] | The standard procedure for equivalence testing against pre-specified bounds. **Citing it does not mean performing it** — §4.4 states that no formal TOST or Bayesian equivalence test is run | §2, §4.3 |
| [37] | The preregistration framework this submission sits inside | §2 |
| [38], [39] | Validation of generative social simulation; positioning | §2 |
| [40] | **A reachable source for a gap, not a closure of it.** §3 records that the ES-1 determinism record was not retained as a shipped artefact; [40] reports the determinism and byte-exact replay properties of the same upstream apparatus, with a public verification path. It is a different body of evidence, **no quantity from it is quoted**, and §12.5 still carries the gap | §3, §12.5 |

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
- Sources cited in the published files of this repository must be reachable by a reader of it.
  Working directories that are not shipped here are not citable sources.
