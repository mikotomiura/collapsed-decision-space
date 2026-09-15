# Claim boundary — what the manuscript may say, and what it may not

> Kept in a separate file from the manuscript **on purpose**, so that whoever writes the manuscript
> cannot satisfy themselves by reading the manuscript alone.
>
> The manuscript is written in English, which is the submission language, so the search patterns
> below are English regular expressions.
>
> `analysis/scripts/check_claim_boundary.py` reads the table in §2 from this file and enforces it.
> This file is the single source of the patterns: the checker never takes them from the text it is
> checking, because a text that carries its own forbidden-phrase list would trivially agree with
> itself.

---

## 1. What the evidence supports

- The channel is wired non-degenerately (from the channel study and the determinism study),
  **including that the positive control is able to return zero**.
- The channel's downstream effect was not detected under a materiality margin declared in advance.
- **Concentration of the base distribution is not itself what reduces detection power** — what
  reduces it is a small attainable shift. This runs against a common intuition. Stated this way
  because the worksheet's own near-uniform row reaches `power = 0.1842` at `delta_tv = 0.01`, so
  "a near-uniform substrate does not imply low power", which earlier drafts wrote here, is
  contradicted by the table it was meant to summarise.
- **The margin-and-power pairing fails in both directions at once when the decision space
  collapses**: the chi-square power gate is inflated by empty cells, and the null floor of the
  total-variation estimand consumes much of the declared margin. Demonstrated on this apparatus and
  recomputed on every run; **not** surveyed for how often it occurs elsewhere.
- Effect-absent, low-power and apparatus-invalid are kept apart as **three distinct outcomes**.
- **A measurement-validity gate evaluated ahead of the estimate reaches the case where the estimand
  cannot be measured, and does not reach the case this paper is about.** Applied to the completed
  run and to the control arm, neither of R4's two conditions is met, while the base distribution of
  the power calculation is missing two of five zones. What may be said is that clearing a
  per-context entropy floor everywhere does not certify that support; what may **not** be said is
  that one arm's decision space collapsed further than another's — support size and per-context
  entropy are different quantities, and the records do not order the arms on either.
- **No run of this apparatus has returned an estimate its own permutation test rejected.** This is
  a statement about what has been observed across three runs, not about the power of any test
  (§12.6), and not about whether the read-out could have detected a material shift.
- The envelope is bounded and stated: one apparatus, one sampling regime, one model in the
  completed measurement.

---

## 2. What must not be written (G1–G13)

The **search pattern** in each row is what the checker applies to the manuscript, this repository's
README and the citation metadata. If a pattern matches, **the prose is fixed; the pattern is not
relaxed.**

| # | Claim that must not appear | Why it is out of reach | Search pattern (case-insensitive) |
|---|---|---|---|
| G1 | Walking, or movement itself, does not produce creative divergence | **Not measured.** The subject is the channel, not walking and not creativity | `locomotion (does not\|doesn't) (produce\|generate\|cause)`, `walking (does not\|doesn't)`, `no creative divergence` |
| G2 | Embodiment is meaningless | Extends a result obtained inside a bounded envelope into a general proposition | `embodiment is (meaningless\|useless\|irrelevant)`, `embodiment does not matter` |
| G3 | Introducing a pre-declared margin is novel | **Already established** in prior work; this study follows the practice rather than originating it | `(we\|this paper) (introduce\|propose)[a-z ]*(declared\|pre-declared\|pre-registered) margin`, `novel(ty)? (of\|is)[a-z ]*equivalence` |
| G4 | The design separates a model-family effect from a think-regime effect | A gate the design **cannot close**: the two factors move together and the protocol says so | `(separat\|disentangl\|decoupl)[a-z]* (the )?(family\|model family)[a-z ]*(from )?[a-z ]*think`, `isolates? the (family\|think)[a-z ]*effect` |
| G5 | The disabled think regime was shown — or ruled out — as the cause | Same gate as G4, reached from the other side | `think=false (is\|was) the cause`, `(shows?\|demonstrates?\|proves?) that think=false` |
| G6 | The control arm was a bitwise comparison | The control compares **statistics inside a declared band**. Bitwise agreement is a property of replaying recorded output, not of regenerating it | `byte-(identical\|exact)[a-z ]*control`, `control[a-z ]*byte-(identical\|exact)` |
| G7 | A collapsed distribution reduces detection power | **The measurement says otherwise**: a degenerate base with a collapse-scale shift still reaches `power = 0.9533`. What reduces power is a **small attainable `delta_tv`**, not concentration | `collapsed? (base )?distribution[a-z ]*(low\|reduced\|kills?) power`, `degenerate[a-z ]*(low\|reduced) power` |
| G8 | The completed run's result is a prediction for the second model | Would make a realised outcome of a planned analysis known in advance; the completed run is not the focus of the planned analyses | `we (expect\|predict\|anticipate)[a-z ]*llama`, `llama[a-z0-9.: ]*will (also )?(show\|reproduce\|replicate)` |
| G9 | Level 6 is guaranteed | **Retained after the level declaration was removed.** The manuscript no longer declares a level, so this guard now has nothing to fire on there; it is kept because the level scheme belongs to a venue the submission plan keeps as a fallback, and because a level declaration is a defensible reading of two clauses read together rather than a guarantee stated by anyone. A guard that is inert costs a line; a guard removed and needed again costs the claim | `level 6 is (guaranteed\|assured\|preserved)`, `guarantees? level 6` |
| G10 | The point estimate is `7.40e-17` | **A field mix-up.** `7.401486830834377e-17` belongs to `zone_function_d_loco`, the zone-function positive control. The point estimate is `d_loco = 0.04682681825722385`. **The lookbehind carries the distinction**: `zone_function_d_loco = 7.401486830834377e-17` is *true* and must remain sayable, so the guard must not fire on an identifier that merely ends in `d_loco` | `(?<![a-z_])D_loco *= *7\.4`, `(?<![a-z_])D_loco[^\n]{0,40}e-17` |
| G11 | A control-arm pass proves that no version drift occurred | A pass states only that the quantities fall **inside the declared band** | `(proves?\|demonstrates?\|establishes?)[a-z ]*no (version )?drift`, `rules? out[a-z ]*version drift` |
| G12 | Speculation about the primary arm after a control-arm failure | Defeats the purpose of a stopping rule | `(had\|if)[a-z ]*r5[a-z ]*(failed\|fails)[^.]*primary[^.]*would` |
| G13 | Replication across two families therefore separated family from regime | A paraphrase that returns to G4 through the replication branch | `(two\|both) (model )?famil(y\|ies)[a-z ,]*(therefore\|thus\|hence)[a-z ]*(separat\|disentangl\|isolat)` |

---

## 3. How the check is built so that it cannot pass vacuously

A check of the form "none of these patterns appears" passes trivially if the patterns are broken,
misparsed, or empty. **Being green and having been checked are different facts.** Four properties
are therefore required, and each was confirmed by breaking it deliberately and observing the
failure.

1. **The patterns are not taken from the text being checked.** Their single source is §2 of this
   file. A manuscript that listed its own forbidden phrases and confirmed it did not match itself
   would be checking nothing.

2. **Exactly thirteen guards, in order, must parse.** A parser that silently yields zero guards
   reports "no hits" against any text whatsoever, so the count and the identifiers are pinned.

3. **A positive control accompanies the "zero hits is correct" check.** The checker must be able to
   say both of the following:
   - no pattern matches `main.md`, this README or the citation metadata;
   - **every individual pattern** matches `_claim_boundary_positive_control.md`, a fixture whose
     every sentence is deliberately false and written in ordinary prose.

   Requiring it per *guard* is not enough: a guard with two patterns would still pass with one of
   them broken. That case was observed in testing, which is why the requirement is per *pattern*.

4. **Matching ignores line breaks.** The prose is hard-wrapped, so a forbidden phrase can straddle a
   line ending. Scanning line by line misses those; the checker normalises whitespace first. This
   too was found by a phrase that split across a wrap and went undetected.

---

## 4. Conventions for sourcing

- Numbers the manuscript draws from the frozen inputs, and from the derived artefacts regenerated
  on every run, are checked by `analysis/scripts/check_manuscript_numbers.py` against those sources.
  Two limits on that, both of which earlier drafts of this file omitted. **The check tests
  occurrence, not uniqueness**: a value appearing in several places is not protected against one of
  them being altered. And **its scope is the listed quantities only** — in particular the pilot
  figures in §5.3 (timings, digests, peak memory, the projected run length) exist in no frozen input
  and are covered by nothing. They are transcribed by hand, and saying otherwise here would be the
  same error this file exists to prevent.
- Sources cited in published files must be reachable by a reader of this repository. Working
  directories that are not shipped here are not citable sources.
- When `power ≈ 0.18` is quoted, the base distribution and the `delta_tv` it belongs to are quoted
  with it (G7).
- The point estimate and the zone-function positive control are presented together, so that neither
  can be read as the other (G10).
