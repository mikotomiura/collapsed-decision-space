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

## Verification caveats, stated rather than smoothed over

- Entries [27]–[31] were confirmed from abstracts only. Author order, affiliation and version are
  re-checked against the source before formal citation.
- **[37] has an internal inconsistency**: the arXiv identifier and the submission date returned by
  the arXiv API do not agree. Both are recorded exactly as retrieved, with no correction inferred.
  The manuscript notes this at the reference itself.
- Entries [35]–[39] were confirmed on 2026-09-12 by parsing the raw JSON returned by Crossref and
  the arXiv API directly. Intermediate summarisation was not relied on: a summarising step had
  dropped a diacritic from an author's name, which is the kind of error that survives review.
- Sources cited in the published files of this repository must be reachable by a reader of it.
  Working directories that are not shipped here are not citable sources.
