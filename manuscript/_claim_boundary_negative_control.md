# Negative-control fixture — sentences the manuscript must be able to say

> **This is a test fixture, not a statement of results.** Its only purpose is to keep the search
> patterns in `CLAIM-BOUNDARY.md` away from sentences a correct account of this study needs, and
> from sentences the seal fixes. `analysis/scripts/check_claim_boundary.py` requires that **no
> pattern matches anything in this file**, and that the list below holds exactly the number of
> items it expects, so an item cannot drop out silently.
>
> The items are written by hand. They are **not** extracted from `main.md`: a list of allowed
> sentences taken from the text under check would make the check agree with itself. Items 1 to 4
> are copied from the sealed rules (`seal/decision-rules.json`), because the checker scans the block
> of the manuscript that is generated from them and a pattern matching sealed text could never be
> satisfied.
>
> Each item is one line, so that the item count is a count of lines beginning with a dash.

- In the primary family the substrate does not license two or more zones, so this estimand is not measurable in that family. This is NOT read as NO_CHANNEL_CONFORMANCE. The claim narrows to single-model scope.
- Mean across the K frozen contexts of the total-variation distance between the channel-on and channel-off distributions over the five zones, computed after dropping unparseable draws and renormalising over the five zones. Materiality margin: 0.1.
- power_min = 0.8 is frozen with the other constants. The completed run attained power 1.0 at these same values of M and K, which is why the prospective design is run at those values rather than smaller ones.
- Monte-Carlo power of a chi-square goodness-of-fit test against an alternative built by moving mass from the largest to the smallest cell of the empirical channel-off distribution. It is NOT the power of the permutation test that produces permutation_reject.
- The sealed design did not evaluate the power of the permutation test; a post hoc simulation reports its simulated rejection rate under assumed bases.
- At the registered delta_tv on the completed run's channel-off base, the sealed pipeline reaches R2 in every simulated replicate and the test alone rejects in every one.
- The parser documents None in this field as stay put; that is a statement of the parser's design, quoted as such, and not a description of what any recorded None is.
- The deposit carries an earlier working title of this manuscript in its title field, and its metadata is not edited.
- An earlier version of this section called the permutation-null mean a floor under the estimate and argued that collapse raises it until it takes up much of the declared margin; that reading is withdrawn.
- Each context ran its channel-on block first, so the difference is confounded with execution order, and nothing here assigns it to the channel.
- It is not a formal pre-registration: the prospective draws existed before the specification did.
- That the condition-wise counts had not been tabulated before the freeze is a declaration in the specification, not something any check demonstrates.
- Failing to reject is not evidence of equivalence, and nothing in the decision rules treats it as such.
- The six-category distance is reported without being judged against the margin of 0.10.
- The only difference between the conditions is sampling: temperature 0.70 against 0.82 and top_p 0.90 against 0.94.
- The sealed repro.sh describes step 8 in the vocabulary of an earlier version of this section, in which the permutation-null mean was called a floor.
- Both zeros are empirical: they are what these draws did, not a property the task imposes.
- The estimand was not measurable in the second family, so that question is not answered by this run.
- What replicated is an operational outcome, the recorded None, and this is not a cross-family replication of the same behavioural meaning or of the same parser-failure mechanism.
- The design must have been able to detect a shift of that size had one been there.
- Declaring a materiality margin in advance for an equivalence-style reading of language-model evaluation is established.
- At the registered delta_tv the surrogate returns 1.0000 for both bases checked, near-uniform and degenerate, so a pass does not distinguish a collapsed base from a spread one.
- Reading None as an intention, and any attribution to λ, locomotion, embodiment, temperature or top_p, are not licensed.
- Reading the difference in effect size between the arms as a difference between model families is not licensed.
