"""Frozen §A thresholds for the M13-ES1 SPDM Gate 1 / Gate 2 verdict.

This module is the **single source of truth** for every value the SPDM
pre-registration freeze fixed **before** any probe result was seen (forking-paths
guard, mirroring :mod:`erre_sandbox.evidence.live_carry.constants`). A value can
only change by a deliberate edit here, which itself requires a **superseding
ADR**. No value is read off a result and then tuned.

The verdict thresholds are **inherited** from the III-a live §5.3 freeze
(:mod:`erre_sandbox.evidence.live_carry.constants`) rather than newly invented:
the SPDM Gate-2 statistic is a Jaccard-distance separation between two retrieval
landscapes, structurally the same readout the III-a cross-arm scorer gates, so
the same scale-free ratio gate (``R_MIN``), practical-effect floor
(``DEGENERATE_NULL_FLOOR``), and ON-noise → INCONCLUSIVE rule (``NULL_NOISE_FACTOR``)
apply. Re-using the frozen numbers removes the arbitrariness a freshly chosen
threshold would introduce. The inheritance is asserted USE-only in
``tests/test_evidence/test_spdm_constants.py``.

Claim boundary (Codex HIGH-2 of the *parent design* review): GO = "eligible to
proceed to ES-2", *not* "full-hypothesis sub-claim established". See the package
docstring.

Codex pre-register review (2026-06-24, gpt-5.5/xhigh, verdict REVISE → all 5 HIGH
reflected here before freeze; see ``.steering/20260624-m13-es1-spdm/codex-review.md``):

* **HIGH-1** — ② (same-content/different-location) is the *signal*, not a null. It
  is removed from the verdict-null denominator (:data:`VERDICT_NULL_KEYS`) and
  judged separately as a **positive control** (:data:`POSITIVE_CONTROL_RATIO_MIN`).
* **HIGH-2** — the landscape Jaccard is computed over a **canonical content id**
  shared across arms, never the raw ``MemoryEntry.id`` (which differs per arm by
  construction → would measure fixture ID separation, not the landscape). See
  :data:`LANDSCAPE_KEY`. A ``spatial_weight=0`` ablation that fails to collapse to
  ``<= DEGENERATE_NULL_FLOOR`` marks the apparatus INVALID → INCONCLUSIVE.
* **HIGH-3** — the query battery must not mutate ``recall_count`` (it would make
  earlier queries perturb later ones = measurement-order artifact). The probe runs
  retrieval with :data:`MARK_RECALLED_DURING_PROBE` = ``False``.
* **HIGH-4** — ``spread`` / ``baseline`` / ③ tolerance are now fully numeric:
  :data:`SPREAD_STAT` (= IQR over seeds), :data:`NO_SPURIOUS_TOL_ABS`.
* **HIGH-5** — ``median(D_obs) >= DEGENERATE_NULL_FLOOR`` is an **always-on** GO
  condition (minimum practical effect), not only the degenerate-null fallback.
"""

from __future__ import annotations

from typing import Final

from erre_sandbox.evidence.live_carry.constants import (
    DEGENERATE_NULL_FLOOR as _IIIA_DEGENERATE_NULL_FLOOR,
)
from erre_sandbox.evidence.live_carry.constants import (
    R_MIN as _IIIA_R_MIN,
)

# --- A1 estimand geometry (pre-registered apparatus, deterministic) -----------

Q_BATTERY_MIN: Final[int] = 12
"""Minimum number of **zone-vocabulary-free** queries in the landscape battery
(parent design §3.3 / Codex HIGH-3 of the parent review).

The retrieval-landscape divergence ``D`` is averaged over this battery; below it
the per-individual landscape estimate is underpowered → INCONCLUSIVE_LOW_POWER.
Zone tokens (``agent at {zone}``) are stripped so a PASS cannot ride on the
zone-string lexical confound rather than the spatial-binding term."""

K_RETRIEVE: Final[int] = 8
"""Top-k retrieved memories per query (= ``retrieval.DEFAULT_K_AGENT``, per-agent
scope). Re-used so the probe ranks with the same depth production retrieval uses;
not an independently tuned probe knob."""

M_MEMORIES: Final[int] = 20
"""Formation-memory count formed per path arm. **Matched across path-A / path-B**
(path-length / dwell-time / memory-count match, parent design §3.3). Both arms
form the same ``M_MEMORIES`` contents; only the formation *locations* differ."""

N_SEED: Final[int] = 8
"""Deterministic fixture-seed count used to estimate the null-battery spread.

The probe is deterministic, so a "seed" selects the content/location assignment
and the query-battery instantiation; 8 seeds give a stable median + cross-seed
spread cheaply (distinct from III-a's ``N_SEED=3``, which paid GPU per seed)."""

LANDSCAPE_KEY: Final[str] = "canonical_content_id"
"""Comparison key for the landscape Jaccard (Codex HIGH-2, frozen).

``D`` is a Jaccard distance over the set of **canonical content ids** a query
retrieves, NOT raw ``MemoryEntry.id``. Both arms form the same logical contents at
different locations, so each content carries a stable ``canonical_content_id``
shared across arms; comparing raw row ids would yield ``D≈1`` even with the spatial
term OFF (it would measure fixture ID separation, not the retrieval landscape).
The ``spatial_weight=0`` ablation must collapse to ``<= DEGENERATE_NULL_FLOOR`` on
this key; failure to collapse ⇒ apparatus INVALID ⇒ INCONCLUSIVE (never NO-GO)."""

MARK_RECALLED_DURING_PROBE: Final[bool] = False
"""The probe runs retrieval with the ``recall_count`` side effect **off** (Codex
HIGH-3, frozen).

``Retriever.retrieve`` bumps ``recall_count`` for returned memories; running the
12-query battery with the bump on would let earlier queries perturb the scores of
later ones (a measurement-order artifact, not path-dependent retrieval). The probe
passes ``mark_recalled=False`` so ``recall_count`` is invariant across the battery.
Production retrieval keeps the default ``True`` (pre-SPDM behaviour bit-identical)."""

# --- A3 Gate-2 verdict thresholds (inherited from III-a freeze, USE-only) ------

R_MIN: Final[float] = _IIIA_R_MIN
"""``median(D_obs) / max(verdict-null D) >= this`` (scale-free magnitude gate).

Inherited from :data:`live_carry.constants.R_MIN` (= 2.0). A separation that
merely matches the verdict-null floor cannot pass; the ratio is scale-free so the
gate is robust to the unknown absolute scale of the Jaccard-distance readout.
The denominator uses only signal-destroying nulls (:data:`VERDICT_NULL_KEYS`),
**not** the ② positive control (Codex HIGH-1)."""

DEGENERATE_NULL_FLOOR: Final[float] = _IIIA_DEGENERATE_NULL_FLOOR
"""Minimum practical-effect floor: ``median(D_obs) >= this`` is an **always-on** GO
condition (Codex HIGH-5), AND the absolute fallback when every verdict-null is
exactly 0 (ratio undefined).

Inherited from :data:`live_carry.constants.DEGENERATE_NULL_FLOOR` (= 0.10). Without
the always-on floor a thin effect (e.g. ``max_null=0.02, D_obs=0.05`` → ratio 2.5)
could GO on a practically negligible top-k reshuffle. Also the collapse target for
the ``spatial_weight=0`` ablation: with the spatial term off the observed
separation must fall **to** this floor (= the separation is the spatial term, not
content/recency). See ``decisions.md`` DA-SPDM-3 for the top-k-swap interpretation
(Codex MEDIUM-1): on a ``k=8`` battery, ``0.10`` ≈ at least one stable id swap per
~1.25 queries, i.e. not a single-query boundary jitter."""

VERDICT_NULL_KEYS: Final[tuple[str, ...]] = (
    "path_label_permutation",  # ① path structure destroyed, nuisance matched
    "same_terminal_same_query_w0",  # ④ content-only floor (spatial term OFF)
)
"""The matched nulls whose ``D`` enters the ratio / CI denominator (Codex HIGH-1).

ONLY signal-destroying nulls belong here: ① permutes the path-label→formation
assignment (destroys the A/B path structure, matches every nuisance), ④ holds the
terminal location + query fixed with the spatial term off (content-only floor).
② (same-content/different-location) is the *signal* and is judged as a positive
control instead (:data:`POSITIVE_CONTROL_RATIO_MIN`); ③ is the no-spurious control
(:data:`NO_SPURIOUS_TOL_ABS`). Neither ② nor ③ is a verdict-null."""

POSITIVE_CONTROL_RATIO_MIN: Final[float] = _IIIA_R_MIN
"""② location-driven positive control: ``D(②, w=ON) / D(②, w=0) >= this`` (Codex
HIGH-1).

With content identical and only location differing, the spatial term ON must
produce ≥ ``R_MIN``× the separation it produces OFF — proof the divergence is
*location-driven*, not content-driven. Tracks ``R_MIN`` (= 2.0); a separate name so
the two gates can diverge under a superseding ADR without coupling."""

NO_SPURIOUS_TOL_ABS: Final[float] = 0.05
"""③ no-spurious control: ``D(③, w=ON) <= D(③, w=0) + this`` (absolute Jaccard
distance, Codex HIGH-4).

With location identical and only content differing, the spatial term must add
**no** separation beyond what content alone yields. ``0.05`` = one ``VALUE_STEP``-scale
absolute slack (half of :data:`DEGENERATE_NULL_FLOOR`), tight enough that a spatial
term injecting spurious separation on co-located memories fails the control."""

SPREAD_STAT: Final[str] = "iqr"
"""Cross-seed dispersion statistic for the noise gate (Codex HIGH-4, frozen).

``spread`` = inter-quartile range over the ``N_SEED`` seeds. The noise gate
(:data:`NULL_NOISE_FACTOR`) compares ``IQR(seed-wise D_obs)`` against
``IQR(seed-wise max-verdict-null)``. IQR (not max) is the robust choice for 8
deterministic seeds; the III-a freeze used ``max`` on 3 GPU seeds where IQR is
ill-defined. This deviation is recorded in ``decisions.md`` DA-SPDM-2."""

NULL_NOISE_FACTOR: Final[float] = 1.5
"""``IQR(seed-wise D_obs) <= this * max(IQR(seed-wise max-verdict-null),
DEGENERATE_NULL_FLOOR)`` or the observed arm is too noisy to trust →
INCONCLUSIVE_LOW_POWER (Codex HIGH-4).

Mirrors :data:`live_carry.constants.ON_NOISE_FACTOR` (= 1.5): the observed (ON) arm
must not fabricate separation through its own run-to-run noise. Codex HIGH-1 of the
parent review: a permuted/random null can itself be *high-variance*, so the gate is
two-sided in spirit — a noisy observed arm relative to the null is downgraded, not
forced to GO/NO-GO. The reference uses ``max(null_spread, DEGENERATE_NULL_FLOOR)`` so
a perfectly tight null (IQR 0) does not *skip* the gate (which would let a wildly
unstable observed arm through); the floor keeps the comparison well-defined without a
new magic number (decisions DA-SPDM-6). Held as a local literal (the III-a name is
arm-specific) but the value tracks the inherited 1.5."""

CI_ALPHA: Final[float] = 0.10
"""Two-sided alpha for the bootstrap CI of ``(D_obs - max-verdict-null)`` (90% CI).

GO requires the CI **lower** bound > 0; a CI straddling 0 is INCONCLUSIVE (not
NO-GO). Consumed via :func:`erre_sandbox.evidence.bootstrap_ci.bootstrap_ci` with
a deterministic seed so the verdict is reproducible in CI."""

N_RESAMPLES: Final[int] = 2000
"""Bootstrap resample count (= ``bootstrap_ci.DEFAULT_N_RESAMPLES``). Inherited so
the CI stability matches the established metric pipeline."""

MIN_VALID_SEEDS: Final[int] = 5
"""Minimum valid seeds (of :data:`N_SEED`) for a strong verdict; below it →
INCONCLUSIVE_LOW_POWER.

Same low-power role as :data:`live_carry.constants.COVERAGE_MIN` /
``MIN_TICK_PAIRS``: a separation resting on too few valid fixture instantiations
cannot earn a GO / NO-GO, only INCONCLUSIVE."""

# --- B3 scorer spatial term (apparatus knobs, not verdict thresholds) ----------

SPATIAL_GAMMA: Final[float] = 0.5
"""Spatial-proximity decay in ``proximity = exp(-SPATIAL_GAMMA * d_norm)`` where
``d_norm`` is the **normalised** distance (see :data:`SPATIAL_COORD_NORMALIZED`).

This is an **apparatus knob** (it shapes the spatial term), not a verdict gate: the
Gate-2 verdict is scale-free (``R_MIN`` ratio) and the confound controls hold for
any positive gamma, so the GO/NO-GO conclusion does not hinge on this value.
Pre-registered for reproducibility; a gamma sweep is **diagnostic-only, verdict
non-using** (Codex MEDIUM-2)."""

SPATIAL_COORD_NORMALIZED: Final[bool] = True
"""Proximity distance is normalised before the exp decay (Codex MEDIUM-2, frozen).

``d_norm = euclidean(now_xyz, formed_xyz) / SPATIAL_COORD_REF`` so ``SPATIAL_GAMMA``
is invariant to the arbitrary scale of the Godot/world coordinate frame — otherwise
a GO would track coordinate-design rather than spatial substrate. Zone-crossing
distance is the same Euclidean over the shared world frame (no special zone term);
the probe fixtures place zone centroids on a fixed reference lattice so the
normalised distances are stable across seeds."""

SPATIAL_COORD_REF: Final[float] = 1.0
"""Reference scale (world units) the proximity distance is divided by before decay
(see :data:`SPATIAL_COORD_NORMALIZED`). The probe fixtures normalise zone-centroid
coordinates to a unit reference lattice, so ``1.0`` keeps ``d_norm`` in a stable
range; production callers that pass raw world coordinates set this to the world
diameter (an apparatus knob, not a verdict gate)."""

__all__ = [
    "CI_ALPHA",
    "DEGENERATE_NULL_FLOOR",
    "K_RETRIEVE",
    "LANDSCAPE_KEY",
    "MARK_RECALLED_DURING_PROBE",
    "MIN_VALID_SEEDS",
    "M_MEMORIES",
    "NO_SPURIOUS_TOL_ABS",
    "NULL_NOISE_FACTOR",
    "N_RESAMPLES",
    "N_SEED",
    "POSITIVE_CONTROL_RATIO_MIN",
    "Q_BATTERY_MIN",
    "R_MIN",
    "SPATIAL_COORD_NORMALIZED",
    "SPATIAL_COORD_REF",
    "SPATIAL_GAMMA",
    "SPREAD_STAT",
]
