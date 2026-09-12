"""Frozen Gate 1 / Gate 2 verdict for the M13-ES1 SPDM probe.

Implements the pre-registered decision rule (``.steering/20260624-m13-es1-spdm/``
decisions DA-SPDM-5, all 5 Codex HIGH reflected before freeze). Every threshold is
read from :mod:`erre_sandbox.evidence.spdm.constants`; this module contains **no**
tunable literals of its own — it is pure decision logic over pre-frozen numbers.

Verdict vocabulary (kept distinct, mirroring III-a ``live_carry``):

* **GO** — Gate 1 healthy ∧ the observed path-A/path-B retrieval-landscape
  divergence clears the scale-free ratio gate, the always-on practical floor, the
  one-sided bootstrap CI, and both attribution controls, with adequate power. Means
  *eligible to proceed to ES-2*, **not** "full-hypothesis sub-claim established"
  (claim boundary, parent design §1).
* **NO_GO** — adequate power ∧ valid apparatus ∧ tight null, yet the divergence is
  insufficient. A **progressive finding** ("this minimal primitive does not, on its
  own, accumulate path-dependence in the retrieval layer → ES-2 is needed"), *not* a
  refutation of the living hypothesis.
* **INCONCLUSIVE** — low power, an invalid apparatus (the ``spatial_weight=0``
  ablation failed to collapse), or a null too noisy to distinguish. Never conflated
  with NO_GO.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from erre_sandbox.evidence.bootstrap_ci import bootstrap_ci
from erre_sandbox.evidence.spdm import constants as _c
from erre_sandbox.evidence.spdm.probe import iqr

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.evidence.spdm.probe import SeedResult

Verdict = Literal["GO", "NO_GO", "INCONCLUSIVE"]


@dataclass(frozen=True)
class Gate1Result:
    """Apparatus-health gate: does the spatial binding change retrieval at all?

    PASS requires (parent design §3.3, all on a single query): the observed
    single-query Jaccard distance clears ``R_MIN``× the location-shuffle null, the
    ``spatial_weight=0`` ablation collapses to ``<= DEGENERATE_NULL_FLOOR``, and the
    zone-vocabulary-free query retains a ratio ``>= R_MIN``.
    """

    single_query_distance: float
    location_shuffle_null: float
    ablation_w0_distance: float
    zone_free_distance: float
    zone_free_null: float

    @property
    def ratio(self) -> float:
        return _ratio(self.single_query_distance, self.location_shuffle_null)

    @property
    def zone_free_ratio(self) -> float:
        return _ratio(self.zone_free_distance, self.zone_free_null)

    @property
    def ablation_collapsed(self) -> bool:
        return self.ablation_w0_distance <= _c.DEGENERATE_NULL_FLOOR

    @property
    def passed(self) -> bool:
        return (
            self.ratio >= _c.R_MIN
            and self.ablation_collapsed
            and self.zone_free_ratio >= _c.R_MIN
        )


@dataclass(frozen=True)
class Gate2Verdict:
    """The Gate 2 sub-claim verdict and the statistics that produced it."""

    verdict: Verdict
    reasons: tuple[str, ...]
    n_valid_seeds: int
    n_queries: int
    median_d_obs: float
    max_verdict_null: float
    ratio: float
    ci_lower: float
    ci_upper: float
    obs_spread: float
    null_spread: float
    positive_control_ratio: float
    no_spurious_margin: float
    w0_floor_median: float


def _ratio(numerator: float, denominator: float) -> float:
    """Scale-free ratio with degenerate-null handling.

    A zero denominator (every matched null exactly 0) makes the ratio undefined; we
    return ``inf`` so the caller falls back to the absolute floor on the numerator
    (:data:`DEGENERATE_NULL_FLOOR`; parent design §3.3 / Codex HIGH-5).
    """
    if denominator <= 0.0:
        return float("inf") if numerator > 0.0 else 0.0
    return numerator / denominator


@dataclass(frozen=True)
class _Metrics:
    """Pre-computed Gate-2 statistics shared by the INCONCLUSIVE / GO / NO_GO arms."""

    n_valid: int
    median_obs: float
    worst_null: float
    ratio: float
    obs_spread: float
    null_spread: float
    w0_median: float
    pos_ctrl: float
    no_spurious_margin: float
    ci_lower: float
    ci_upper: float


def _compute_metrics(valid: list[SeedResult], bootstrap_seed: int) -> _Metrics:
    d_obs = [s.d_obs for s in valid]
    max_nulls = [s.max_verdict_null for s in valid]
    w0 = [s.d_null_w0 for s in valid]
    sl_on = [s.d_control_same_loc_on for s in valid]
    sl_off = [s.d_control_same_loc_off for s in valid]

    median_obs = statistics.median(d_obs) if d_obs else 0.0
    # Paired per-seed difference (observed − worst matched null) for the one-sided CI.
    diffs = [s.d_obs - s.max_verdict_null for s in valid]
    if diffs:
        ci = bootstrap_ci(
            diffs,
            n_resamples=_c.N_RESAMPLES,
            ci=1.0 - _c.CI_ALPHA,
            seed=bootstrap_seed,
            statistic="mean",
        )
        ci_lower, ci_upper = ci.lo, ci.hi
    else:
        ci_lower = ci_upper = 0.0

    return _Metrics(
        n_valid=len(valid),
        median_obs=median_obs,
        worst_null=max(max_nulls) if max_nulls else 0.0,
        ratio=_ratio(median_obs, max(max_nulls) if max_nulls else 0.0),
        obs_spread=iqr(d_obs),
        null_spread=iqr(max_nulls),
        w0_median=statistics.median(w0) if w0 else 0.0,
        pos_ctrl=_ratio(median_obs, statistics.median(w0) if w0 else 0.0),
        no_spurious_margin=(
            (statistics.median(sl_on) - statistics.median(sl_off)) if sl_on else 0.0
        ),
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def _inconclusive_reason(m: _Metrics, gate1: Gate1Result, n_queries: int) -> str | None:
    """First INCONCLUSIVE trigger, else None (low power / Gate 1 / invalid / noise).

    Checked before the GO/NO_GO arms so an unreliable measurement is never reported
    as a (progressive) NO_GO finding.
    """
    if n_queries < _c.Q_BATTERY_MIN:
        return f"query battery {n_queries} < Q_BATTERY_MIN {_c.Q_BATTERY_MIN}"
    if m.n_valid < _c.MIN_VALID_SEEDS:
        return f"valid seeds {m.n_valid} < MIN_VALID_SEEDS {_c.MIN_VALID_SEEDS}"
    if not gate1.passed:
        return "Gate 1 (apparatus health) did not pass"
    if m.w0_median > _c.DEGENERATE_NULL_FLOOR:
        # spatial_weight=0 ablation failed to collapse ⇒ the readout is not the
        # spatial term (canonical-id metric or fixture wiring is broken). HIGH-2.
        return (
            f"w0 ablation did not collapse (median {m.w0_median:.4f} "
            f"> DEGENERATE_NULL_FLOOR {_c.DEGENERATE_NULL_FLOOR}); apparatus invalid"
        )
    # Noise reference = max(null spread, practical floor): a perfectly tight null
    # (IQR 0) is *good*, so we must not skip the gate then (that would let a wildly
    # unstable observed arm through). Reuses a frozen constant, not a new magic
    # number (decisions DA-SPDM-6).
    noise_ref = max(m.null_spread, _c.DEGENERATE_NULL_FLOOR)
    if m.obs_spread > _c.NULL_NOISE_FACTOR * noise_ref:
        return (
            f"observed arm too noisy: IQR(D_obs) {m.obs_spread:.4f} > "
            f"{_c.NULL_NOISE_FACTOR} * max(IQR(max_null) {m.null_spread:.4f}, "
            f"floor {_c.DEGENERATE_NULL_FLOOR})"
        )
    return None


def _go_failures(m: _Metrics) -> list[str]:
    """Unmet GO conditions; empty ⇒ every condition passed (parent design §3.3)."""
    failures: list[str] = []
    if m.median_obs < _c.DEGENERATE_NULL_FLOOR:
        failures.append(
            f"median D_obs {m.median_obs:.4f} < practical floor "
            f"{_c.DEGENERATE_NULL_FLOOR} (HIGH-5)"
        )
    if m.ratio < _c.R_MIN:
        failures.append(f"ratio {m.ratio:.3f} < R_MIN {_c.R_MIN}")
    if m.ci_lower <= 0.0:
        failures.append(f"bootstrap CI lower {m.ci_lower:.4f} <= 0 (90% CI)")
    if m.pos_ctrl < _c.POSITIVE_CONTROL_RATIO_MIN:
        failures.append(
            f"② positive control {m.pos_ctrl:.3f} < "
            f"POSITIVE_CONTROL_RATIO_MIN {_c.POSITIVE_CONTROL_RATIO_MIN}"
        )
    if m.no_spurious_margin > _c.NO_SPURIOUS_TOL_ABS:
        failures.append(
            f"③ no-spurious margin {m.no_spurious_margin:.4f} > "
            f"NO_SPURIOUS_TOL_ABS {_c.NO_SPURIOUS_TOL_ABS}"
        )
    return failures


def _pack(
    verdict: Verdict, reasons: tuple[str, ...], m: _Metrics, n_queries: int
) -> Gate2Verdict:
    return Gate2Verdict(
        verdict=verdict,
        reasons=reasons,
        n_valid_seeds=m.n_valid,
        n_queries=n_queries,
        median_d_obs=m.median_obs,
        max_verdict_null=m.worst_null,
        ratio=m.ratio,
        ci_lower=m.ci_lower,
        ci_upper=m.ci_upper,
        obs_spread=m.obs_spread,
        null_spread=m.null_spread,
        positive_control_ratio=m.pos_ctrl,
        no_spurious_margin=m.no_spurious_margin,
        w0_floor_median=m.w0_median,
    )


def evaluate_gate2(
    seeds: Sequence[SeedResult],
    gate1: Gate1Result,
    *,
    n_queries: int,
    bootstrap_seed: int = 0,
) -> Gate2Verdict:
    """Render the frozen Gate 2 verdict from per-seed divergences + Gate 1.

    ``bootstrap_seed`` makes the CI reproducible (the resampling RNG seed). All
    thresholds come from :mod:`constants`; nothing here is tuned post-result.
    """
    valid = [s for s in seeds if s.valid]
    m = _compute_metrics(valid, bootstrap_seed)

    incon = _inconclusive_reason(m, gate1, n_queries)
    if incon is not None:
        return _pack("INCONCLUSIVE", (incon,), m, n_queries)

    failures = _go_failures(m)
    if not failures:
        return _pack(
            "GO",
            ("all GO conditions met; eligible to proceed to ES-2",),
            m,
            n_queries,
        )
    return _pack("NO_GO", tuple(failures), m, n_queries)


__all__ = ["Gate1Result", "Gate2Verdict", "Verdict", "evaluate_gate2"]
