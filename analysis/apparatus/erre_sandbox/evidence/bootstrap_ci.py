"""Bootstrap confidence intervals for Tier A / Tier B metric aggregates.

Hierarchical bootstrap with **outer cluster (run) + inner block (circular
block of turn-level samples)** for autocorrelation-aware CI estimation. The
quorum semantics require CI width per sub-metric to gate ratio confirmation.

This module was drafted in P3a-decide (ahead of the formal P5 phase) so
the stimulus-side ratio sanity-check could run on the pilot DuckDB files
once they were rsync'd from G-GEAR. The P5 hardening pass adds:

* :func:`estimate_block_length` — Politis-White-inspired autocorrelation
  probe that returns a heuristic block length capped at ``max_block``.
  White-noise series collapse to ~1; strong AR(1) series grow toward
  ``max_block``.
* ``cluster_only`` flag on :func:`hierarchical_bootstrap_ci` — skips
  the inner block entirely and resamples whole clusters (used by the
  Tier B per-100-turn metric where the 25 windows / persona means the
  effective sample size is the cluster count and per-window
  autocorrelation is not measured).
* ``auto_block`` flag on :func:`hierarchical_bootstrap_ci` — passes the
  pooled stream through :func:`estimate_block_length` to pick the
  inner-block size at call time.

Quick reference:

* :func:`bootstrap_ci` — minimum viable percentile bootstrap. Pure
  numpy, deterministic under explicit ``seed``. Works for the P3a-decide
  use-case (per-cell aggregate metrics, no within-cell autocorrelation
  to model because each cell is one persona run).
* :func:`hierarchical_bootstrap_ci` — outer cluster + inner block
  resampling. Used by P3 / P3-validate when there are 5 runs × 500
  turns per persona; the inner block protects the CI from
  underestimating standard error when consecutive turns are correlated.
* :func:`estimate_block_length` — automatic block-length picker for the
  ``auto_block`` path of :func:`hierarchical_bootstrap_ci`.

All helpers return :class:`BootstrapResult` so plotting / quorum gates
can read ``point / lo / hi / width`` uniformly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_N_RESAMPLES: int = 2000
"""Default bootstrap iteration count.

2000 is enough for percentile CI stability at width <0.005 for
N>=30 sample sizes — the M8 baseline metric pipeline used the same
budget and shipped without observability complaints. For DB9 ratio
gating the stability matters more than the iteration count, so the
parameter is exposed and the script overrides up to 10K when running
overnight.
"""

DEFAULT_CI: float = 0.95
"""Default 2-sided percentile CI (95%)."""

MIN_SAMPLE_SIZE: int = 10
"""Minimum sample size for block-length estimation.
Samples with fewer finite values fall back to block length 1.
"""


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Bootstrap CI summary returned by every public helper here."""

    point: float
    """The point estimate computed from the original (un-resampled) sample."""
    lo: float
    """Lower percentile bound."""
    hi: float
    """Upper percentile bound."""
    width: float
    """``hi - lo``. Pre-computed because callers compare widths directly
    (DB9 quorum, ME-4 ratio decision) and the dataclass is frozen so
    storing the derived value is safe."""
    n: int
    """Effective sample size used (after dropping NaN/None)."""
    n_resamples: int
    """Bootstrap iteration count."""
    method: str
    """One of ``"percentile"`` / ``"hierarchical-block"``. Surfaced in
    the JSON output so the consumer knows which estimator produced the
    interval."""


def _clean(values: Sequence[float | None]) -> np.ndarray:
    """Drop None / NaN entries and return a float array.

    Per the M8 ``compute_*`` contract, ``None``/``NaN`` mean "no
    measurement" rather than "zero". The bootstrap path drops those
    rows up front so the resampler does not propagate NaN.
    """
    cleaned = [
        float(v)
        for v in values
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    return np.asarray(cleaned, dtype=float)


def bootstrap_ci(
    values: Sequence[float | None],
    *,
    n_resamples: int = DEFAULT_N_RESAMPLES,
    ci: float = DEFAULT_CI,
    seed: int = 0,
    statistic: str = "mean",
) -> BootstrapResult:
    """Percentile bootstrap CI for ``statistic`` of ``values``.

    Args:
        values: Per-sample measurements (one per cell / turn / item).
            ``None``/``NaN`` entries are dropped via :func:`_clean`.
        n_resamples: Bootstrap iteration count.
        ci: Two-sided coverage in ``(0, 1)``.
        seed: Deterministic bitstream seed (``np.random.default_rng``).
        statistic: Either ``"mean"`` (default) or ``"median"``. The
            quorum thresholds in `design-final.md` use means, so the
            default is mean.

    Returns:
        :class:`BootstrapResult` with ``method="percentile"`` and
        ``n`` reflecting the sample size after dropping NaN/None.

    Raises:
        ValueError: If ``ci`` is not in ``(0, 1)``, ``n_resamples < 1``,
            or ``values`` is empty after cleaning.
    """
    if not 0.0 < ci < 1.0:
        raise ValueError(f"ci must be in (0, 1) (got {ci})")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1 (got {n_resamples})")
    if statistic not in {"mean", "median"}:
        raise ValueError(f"statistic must be 'mean' or 'median' (got {statistic!r})")

    cleaned = _clean(values)
    n = cleaned.size
    if n == 0:
        raise ValueError("values has 0 finite entries — cannot bootstrap")

    rng = np.random.default_rng(seed)
    point = (
        float(np.mean(cleaned)) if statistic == "mean" else float(np.median(cleaned))
    )

    indices = rng.integers(0, n, size=(n_resamples, n))
    samples = cleaned[indices]
    if statistic == "mean":
        replicate_stats = samples.mean(axis=1)
    else:
        replicate_stats = np.median(samples, axis=1)

    alpha = 1.0 - ci
    lo = float(np.quantile(replicate_stats, alpha / 2.0))
    hi = float(np.quantile(replicate_stats, 1.0 - alpha / 2.0))
    return BootstrapResult(
        point=point,
        lo=lo,
        hi=hi,
        width=hi - lo,
        n=n,
        n_resamples=n_resamples,
        method="percentile",
    )


def estimate_block_length(
    values: Sequence[float | None],
    *,
    max_block: int = 100,
) -> int:
    """Heuristic block length for circular-block bootstrap.

    Inspired by Politis-White (2004) automatic block-length selection: walks
    the sample autocorrelation function and returns the first lag at which
    ``|ρ̂(k)|`` falls below the noise floor ``2 / sqrt(n)``. White-noise-like
    series collapse to ~1; persistent AR-style series grow toward
    ``max_block``.

    The probe horizon is ``min(n // 4, ⌈5 · log10(n)⌉)`` so the routine is
    cheap (O(n · log10 n)) and the cap matches the rule-of-thumb upper
    bound for stationary block bootstrap (block ≤ ``n / 4``).

    Args:
        values: 1D sequence (NaN/None dropped via :func:`_clean`).
        max_block: Hard upper bound on the returned block length. Useful
            when the caller wants to cap the cost of inner-block resampling.

    Returns:
        Integer block length in ``[1, min(max_block, max(1, n // 4))]``.
        Returns 1 for series shorter than 10 finite samples or with zero
        variance (constant series).
    """
    if max_block < 1:
        raise ValueError(f"max_block must be >= 1 (got {max_block})")
    cleaned = _clean(values)
    n = cleaned.size
    if n < MIN_SAMPLE_SIZE:
        return 1

    centered = cleaned - cleaned.mean()
    var = float((centered * centered).mean())
    if var == 0.0:
        return 1

    cap = max(1, n // 4)
    k_max = min(cap, max(1, int(5.0 * math.log10(max(n, 10)))))
    threshold = 2.0 / math.sqrt(n)

    for k in range(1, k_max + 1):
        rho_k = float((centered[: n - k] * centered[k:]).mean() / var)
        if abs(rho_k) < threshold:
            return min(max(1, k), max_block, cap)

    # Every probed lag was above the noise floor: hand back the largest
    # length we are willing to use without exceeding the n // 4 ceiling.
    return min(k_max, max_block, cap)


def _compute_effective_block_length(
    cleaned_clusters: list[np.ndarray],
    pooled: np.ndarray,
    block_length: int,
    *,
    cluster_only: bool,
    auto_block: bool,
) -> tuple[str, int]:
    """Determine effective block length and method label.

    Returns (method_label, effective_block_length).
    """
    if cluster_only:
        return "hierarchical-cluster-only", block_length
    if auto_block:
        per_cluster_cap = max((c.size for c in cleaned_clusters), default=1)
        effective_block_length = estimate_block_length(
            pooled.tolist(),
            max_block=per_cluster_cap,
        )
        return "hierarchical-block", effective_block_length
    return "hierarchical-block", block_length


def _draw_one_replicate(
    cleaned_clusters: list[np.ndarray],
    rng: np.random.Generator,
    n_clusters: int,
    effective_block_length: int,
    *,
    cluster_only: bool,
) -> np.ndarray:
    """Draw one bootstrap replicate."""
    outer_idx = rng.integers(0, n_clusters, size=n_clusters)
    if cluster_only:
        return np.concatenate(
            [cleaned_clusters[ci_idx] for ci_idx in outer_idx],
        )
    replicate_concat: list[np.ndarray] = []
    for ci_idx in outer_idx:
        cluster = cleaned_clusters[ci_idx]
        cluster_n = cluster.size
        n_blocks = max(1, math.ceil(cluster_n / effective_block_length))
        starts = rng.integers(0, cluster_n, size=n_blocks)
        for s in starts:
            idx = (np.arange(effective_block_length) + s) % cluster_n
            replicate_concat.append(cluster[idx])
    return np.concatenate(replicate_concat)


def hierarchical_bootstrap_ci(
    values_per_cluster: Sequence[Sequence[float | None]],
    *,
    block_length: int = 50,
    cluster_only: bool = False,
    auto_block: bool = False,
    n_resamples: int = DEFAULT_N_RESAMPLES,
    ci: float = DEFAULT_CI,
    seed: int = 0,
) -> BootstrapResult:
    """Cluster + circular-block bootstrap for autocorrelated turn streams.

    Use this for P3 golden-baseline 5 runs × 500 turns:
    the outer level resamples runs (clusters) with replacement, and the
    inner level draws circular blocks of length ``block_length`` so the
    within-run autocorrelation is preserved.

    Args:
        values_per_cluster: ``runs`` outer × ``turns`` inner — one
            sequence per run (cluster). NaN/None within a cluster are
            dropped (per :func:`_clean`); a cluster that ends up empty
            is dropped from the outer resample.
        block_length: Inner circular block length (turns). For 500-turn
            runs the literature default 50 covers ~1 effective sample
            per 10 blocks. Ignored when ``cluster_only=True``; replaced
            when ``auto_block=True``.
        cluster_only: When ``True``, skip the inner block step and
            concatenate the entire selected cluster verbatim per outer
            draw. Use this for Tier B per-100-turn windowed metrics
            where the 25 windows / persona means the effective sample
            size is the cluster count and within-window autocorrelation
            is not modelled.
        auto_block: When ``True`` (and ``cluster_only=False``), call
            :func:`estimate_block_length` on the pooled stream and use
            that estimate as the inner block length. ``block_length``
            is ignored in this mode.
        n_resamples: Bootstrap iteration count.
        ci: Two-sided coverage in ``(0, 1)``.
        seed: Deterministic seed.

    Returns:
        :class:`BootstrapResult`. ``method`` is
        ``"hierarchical-cluster-only"`` when ``cluster_only=True`` and
        ``"hierarchical-block"`` otherwise. ``n`` is the total number of
        finite turn-level observations across non-empty clusters.

    Raises:
        ValueError: On invalid arguments or all-empty clusters.
    """
    if not 0.0 < ci < 1.0:
        raise ValueError(f"ci must be in (0, 1) (got {ci})")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1 (got {n_resamples})")
    if block_length < 1:
        raise ValueError(f"block_length must be >= 1 (got {block_length})")

    cleaned_clusters = [_clean(cluster) for cluster in values_per_cluster]
    cleaned_clusters = [c for c in cleaned_clusters if c.size > 0]
    if not cleaned_clusters:
        raise ValueError("no finite values in any cluster")

    rng = np.random.default_rng(seed)
    pooled = np.concatenate(cleaned_clusters)
    point = float(pooled.mean())
    n_total = pooled.size
    n_clusters = len(cleaned_clusters)

    method_label, effective_block_length = _compute_effective_block_length(
        cleaned_clusters,
        pooled,
        block_length,
        cluster_only=cluster_only,
        auto_block=auto_block,
    )

    replicate_means = np.empty(n_resamples, dtype=float)
    for r in range(n_resamples):
        replicate = _draw_one_replicate(
            cleaned_clusters,
            rng,
            n_clusters,
            effective_block_length,
            cluster_only=cluster_only,
        )
        replicate_means[r] = float(replicate.mean())

    alpha = 1.0 - ci
    lo = float(np.quantile(replicate_means, alpha / 2.0))
    hi = float(np.quantile(replicate_means, 1.0 - alpha / 2.0))
    return BootstrapResult(
        point=point,
        lo=lo,
        hi=hi,
        width=hi - lo,
        n=n_total,
        n_resamples=n_resamples,
        method=method_label,
    )


__all__ = [
    "DEFAULT_CI",
    "DEFAULT_N_RESAMPLES",
    "BootstrapResult",
    "bootstrap_ci",
    "estimate_block_length",
    "hierarchical_bootstrap_ci",
]
