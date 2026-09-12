"""Frozen §0 thresholds for the III-a live §5.3 cross-arm verdict scorer.

This module is the **single source of truth** for every value the GPU 前
threshold freeze ADR (``.steering/20260616-iiia-live-pregpu-freeze/``, ACCEPTED
2026-06-16, binding=user) pre-registered in its §0 table. Like the frozen
:mod:`erre_sandbox.evidence.saturation.constants`, every value here was fixed
**before** any live-exec result was seen (ADR forking-paths guard): a value can
only change by a deliberate edit here, which itself requires a **superseding
ADR**. No value is read off a result and then tuned.

Cap geometry the scorer inherits from the intervention spec is **not re-tuned**
here: ``M2_CAP`` is imported from the evidence-layer mirror
(:data:`erre_sandbox.evidence.saturation.constants.MAX_TOTAL_MODULATION`) so the
boundedness gate tracks the same ``floor +/- 0.15`` cap the reconcile kernel
enforces, and ``M2_TRANSIENT_TOL`` mirrors ``cognition.world_model.VALUE_STEP``
as a **local** constant — the evidence package never imports ``cognition`` (the
same boundary pattern :mod:`erre_sandbox.evidence.saturation.constants` uses).

``STM_HORIZON`` (=16) is part of the ADR §9 frozen-non-touch set but is consumed
by **no** M0/M1/M2 gate here (M3 growth is diagnostic-only, not a gate), so it is
deliberately **not** imported — its non-touch is proven by the sentinel test
(the diff never reaches ``cognition.world_model``), not by an unused binding.
"""

from __future__ import annotations

from typing import Final

from erre_sandbox.evidence.saturation.constants import (
    MAX_TOTAL_MODULATION as _MAX_TOTAL_MODULATION,
)

# --- M1 distal-separation magnitude gate (ADR §0 / §2) ------------------------

R_MIN: Final[float] = 2.0
"""``median(S(ON-OFF)) / max(S(OFF/OFF null)) >= this`` (magnitude sanity, ADR §0/§2).

The minimum ratio of the paired ON-OFF separation to the OFF/OFF run-to-run noise
floor. A trivial-small separation that merely matches noise cannot pass."""

DEGENERATE_NULL_FLOOR: Final[float] = 0.10
"""Absolute Jaccard-distance floor ``median(S(ON-OFF)) >= this`` used **only** when
every valid null is exactly 0 (ratio undefined, ADR §0/§2 MED-3).

A degenerate all-zero null makes the ratio undefined; the separation must then
clear this absolute floor instead. Distinct from *no* valid null (INCONCLUSIVE)."""

ON_NOISE_FACTOR: Final[float] = 1.5
"""``max(S(ON/ON)) <= this * max(S(OFF/OFF))`` or ON-specific noise is suspected
(ADR §0/§2). Exceeding it downgrades the verdict to INCONCLUSIVE_LOW_POWER — the
ON arm may be fabricating separation through its own run-to-run noise."""

COVERAGE_MIN: Final[float] = 0.50
"""Per-seed ``valid_tick_pairs / aligned_tick_pairs >= this`` (ADR §0/§2, HIGH-1).

Below this the seed is underpowered for the Jaccard estimate → INCONCLUSIVE_LOW_POWER
(never a NO_DETECTABLE)."""

MIN_TICK_PAIRS: Final[int] = 10
"""Per-seed minimum ``valid_tick_pairs`` count (ADR §0/§2, HIGH-1).

A coverage *ratio* alone can pass on a handful of ticks; this absolute floor keeps
the estimate from resting on too few aligned ``(individual, tick)`` pairs →
INCONCLUSIVE_LOW_POWER when unmet."""

# --- M0 manipulation / fidelity gate (ADR §0 / §6) ----------------------------

M0_ENGAGEMENT_FLOOR: Final[int] = 5
"""Per-seed minimum ON replicate-0 cross-fp retained-offset event count (ADR §0/§6).

A retained-offset event = a saturation-trace floor-fingerprint change accompanied
by a non-zero ``|modulated - base_floor|`` offset (the carry survived a churn).
``0`` events = carry never fired → INVALID_MEASUREMENT (manipulation absent, kept
distinct from NO_DETECTABLE); ``1..4`` = under-engaged → INCONCLUSIVE_LOW_POWER;
``>= this`` is the strong-verdict precondition. Scale follows
``saturation.versioned_constants.CROSSFP_CHANNEL_MIN`` (=5)."""

# --- M2 boundedness / non-inferiority gate (ADR §0 / §5) ----------------------

M2_CAP: Final[float] = _MAX_TOTAL_MODULATION
"""``|modulated_value - base_floor_value| <= this`` (= frozen ``floor +/- 0.15``).

Imported (USE-only) from the evidence-layer mirror of
``cognition.world_model.MAX_TOTAL_MODULATION`` — the scorer must not introduce a
second, tunable copy of the frozen cap (ADR §0/§5/§9)."""

M2_TRANSIENT_TOL: Final[float] = 0.05
"""One ``VALUE_STEP`` of transient slack permitted at injection before the next
reconcile re-clamps (ADR §0/§5). Mirrors ``cognition.world_model.VALUE_STEP`` as a
local constant (evidence never imports cognition); USE-only, not independently tuned."""

M2_CAP_FLOAT_TOL: Final[float] = 1e-9
"""IEEE-754 boundary tolerance for the cap comparison — **not** a §0 threshold and
**not** a relaxation of the frozen cap.

The carry saturates at exactly ``M2_CAP`` = ``3 * VALUE_STEP``, but ``3 * 0.05``
evaluates to ``0.15000000000000002`` in IEEE-754, i.e. ``> M2_CAP`` by ~2e-17. A
strict ``offset > M2_CAP`` comparison therefore mis-flags a *legal* at-cap offset
(ADR §5 caps the offset at ``<= M2_CAP``) as a sustained over-cap. This tolerance
absorbs that representation error so the comparison implements the ADR's ``<=``
semantics; a genuine over-cap (``offset > M2_CAP + 1e-9``, e.g. 0.16) still violates.
The cap is therefore not *substantively* relaxed — only the sub-``ulp`` band
``(M2_CAP, M2_CAP + 1e-9]`` is tolerated, which the reconcile kernel can never
produce (it clamps to the cap). ``1e-9`` is ~7 orders of magnitude above the
few-``ulp`` arithmetic error yet ~8 orders below the cap. Discovered on the live
12-run (false INVALID_MEASUREMENT, DA-6); superseding micro-ADR
``cap-float-boundary-fix-adr.md``."""

M2_COHERENCE_MARGIN: Final[float] = 0.10
"""Non-inferiority slack: ``median coherence(ON r0) >= median coherence(OFF r0) - this``
(ADR §0/§5). A violation is INVALID_MEASUREMENT (carry degraded the agent, so the
separation cannot be trusted), not a diagnostic flag (MED-4)."""

M2_THROUGHPUT_RATIO: Final[float] = 0.90
"""Non-inferiority slack: ``total_ticks(ON r0) >= this * total_ticks(OFF r0)``
(ADR §0/§5). Violation = INVALID_MEASUREMENT (the ON arm ran materially shorter)."""

# --- §4 reachability positive-control (frozen routing, ADR §0 / §4) -----------

REACH_NULL_MAX: Final[float] = 0.05
"""Reachability (a): an identical non-empty floor on both arms must yield
``S <= this`` (null side healthy, ADR §0/§4)."""

REACH_POS_MIN: Final[float] = 0.90
"""Reachability (b): a key-disjoint non-empty floor must yield ``S >= this``
(positive side healthy, ADR §0/§4)."""

# --- capture matrix (ADR §0 / §3) ---------------------------------------------

N_SEED: Final[int] = 3
"""Seed-repetition count (kant single-persona). Distinct from the upstream
population ``N=21`` agents / ``I=6`` interactions — a different axis (ADR §0 LOW-2)."""

RERUN_PER_ARM: Final[int] = 1
"""Each seed runs each arm twice (replicate 0/1) for the run-to-run null; i.e.
``RERUN_PER_ARM`` extra replicate beyond replicate 0 = 4 runs/seed = 12 total
(ADR §0/§3)."""

__all__ = [
    "COVERAGE_MIN",
    "DEGENERATE_NULL_FLOOR",
    "M0_ENGAGEMENT_FLOOR",
    "M2_CAP",
    "M2_CAP_FLOAT_TOL",
    "M2_COHERENCE_MARGIN",
    "M2_THROUGHPUT_RATIO",
    "M2_TRANSIENT_TOL",
    "MIN_TICK_PAIRS",
    "N_SEED",
    "ON_NOISE_FACTOR",
    "REACH_NULL_MAX",
    "REACH_POS_MIN",
    "RERUN_PER_ARM",
    "R_MIN",
]
