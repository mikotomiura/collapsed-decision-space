"""Frozen observation parameters for the SWM saturation probe (ADR section 3.0).

This module is the **single source of truth** for every frozen value the
saturation ADR pre-registered. The ADR section 3.0 table is the only thing the
ADR froze; the trace builder, the loader, and the tests all import these
constants instead of re-spelling a literal, so a value can only change by a
deliberate edit here (which itself requires an ADR revision, ADR section 7 —
forking-paths guard). No value is read off a result and then tuned.

All thresholds mirror saturation ADR section 3.0 verbatim. ``MAX_TOTAL_MODULATION``
and ``FINGERPRINT_PRECISION`` mirror their cognition-layer twins
(``cognition.world_model.MAX_TOTAL_MODULATION`` / ``_FLOOR_FINGERPRINT_PRECISION``)
as **local** constants rather than importing across the ``evidence -> cognition``
boundary (the same pattern ``evidence.individuation.trace_ddl`` uses for
``_EVIDENCE_FLOAT_PRECISION``).
"""

from __future__ import annotations

from typing import Final

# --- cap geometry (mirrors cognition.world_model, ADR section 2 / 3.0) --------
MAX_TOTAL_MODULATION: Final[float] = 0.15
"""Hard cap an entry's modulation may drift from its floor (``floor +/- 0.15``).

Mirrors ``cognition.world_model.MAX_TOTAL_MODULATION`` (ADR section 3.0). Local
copy — the probe never imports cognition."""

BOUNDARY_FLOOR_THRESHOLD: Final[float] = 0.85
"""``|floor| > 0.85`` (= ``1 - MAX_TOTAL_MODULATION``) marks a boundary-floor
channel whose effective room is clipped below 0.15 by the ``[-1, 1]`` clamp
(ADR section 2.2). Diagnostic only — never part of a verdict."""

FINGERPRINT_PRECISION: Final[int] = 6
"""Decimal places the floor fingerprint rounds value/confidence to.

Mirrors ``cognition.world_model._FLOOR_FINGERPRINT_PRECISION`` (ADR section 3.0,
``_FINGERPRINT_PRECISION``). Used by the trace builder's
``floor_fingerprint_hash`` so the loader can recompute drops (ADR section 5)."""

# --- saturation-statistic thresholds (ADR section 3.0 / 3.2) ------------------
EPSILON_MOD: Final[float] = 0.025
"""``epsilon_mod`` — a channel is *actively-modulated* when its evaluation-window
peak magnitude is >= this (half a ``VALUE_STEP``). ADR section 3.0."""

ETA_PINNED: Final[float] = 0.01
"""``eta`` — *pinned* when the terminal-window mean **effective** cap_distance
(ADR section 2.2) is <= this. ADR section 3.0."""

SLOPE_TOL: Final[float] = 0.002
"""``slope_tol`` per tick — *flat* when the terminal magnitude OLS slope is
**two-sided** ``|slope| <= slope_tol`` (HIGH-1). ADR section 3.0."""

W_TERM: Final[int] = 5
"""Terminal-window length in ticks. ADR section 3.0."""

T_WARMUP: Final[int] = 10
"""Warmup ticks — a channel-tick with ``tick < t_warmup`` is excluded from
analysis (SWM still populating). ADR section 3.0."""

T_RUN_MIN: Final[int] = 25
"""Minimum horizon — a seed whose max tick ``T_run < T_RUN_MIN`` is INVALID
(underpowered). ADR section 3.0 / 3.5."""

TERMINAL_PRESENCE_MIN: Final[int] = 3
"""A channel is terminal-assessable when it appears at >= this many of the
``W_TERM`` terminal ticks. ADR section 3.0 / 3.1."""

# --- validity gates (ADR section 3.0 / 3.3) -----------------------------------
ENGAGEMENT_MIN: Final[float] = 0.10
"""``engagement_min`` — ``#active / total_channels_s`` must be >= this.
ADR section 3.0."""

MIN_ACTIVE_CHANNELS: Final[int] = 5
"""Absolute floor on ``#active`` per seed. ADR section 3.0."""

DROP_HIGH: Final[float] = 0.50
"""``drop_rate >= drop_high`` -> INCONCLUSIVE (floor churn). ADR section 3.0."""

TRANSIENT_HIGH: Final[float] = 0.50
"""``transient_active_rate >= transient_high`` -> INCONCLUSIVE (survivor bias,
HIGH-2). ADR section 3.0."""

# --- 3-way decision thresholds (ADR section 3.0 / 4.1) ------------------------
THETA_HIGH: Final[float] = 0.50
"""``median sat_frac >= theta_high`` (+ gates + N=3 agreement) -> SATURATED.
ADR section 3.0."""

THETA_LOW: Final[float] = 0.10
"""``median sat_frac <= theta_low`` (+ gates + N=3 agreement) -> NON-SATURATED.
ADR section 3.0.

The conservative gap ``theta_low < sat_frac < theta_high`` is INCONCLUSIVE so a
marginal result is never forced into a conclusion."""

N_SEEDS: Final[int] = 3
"""Paired-seed count; a verdict binds only when all N seeds agree.
ADR section 3.0 / 3.4."""

__all__ = [
    "BOUNDARY_FLOOR_THRESHOLD",
    "DROP_HIGH",
    "ENGAGEMENT_MIN",
    "EPSILON_MOD",
    "ETA_PINNED",
    "FINGERPRINT_PRECISION",
    "MAX_TOTAL_MODULATION",
    "MIN_ACTIVE_CHANNELS",
    "N_SEEDS",
    "SLOPE_TOL",
    "TERMINAL_PRESENCE_MIN",
    "THETA_HIGH",
    "THETA_LOW",
    "TRANSIENT_HIGH",
    "T_RUN_MIN",
    "T_WARMUP",
    "W_TERM",
]
