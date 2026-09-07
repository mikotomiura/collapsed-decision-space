"""ECL B — a-priori categorical-multinomial power apparatus (doc-only pre-run).

Issue 004 (``loop/20260708-m13-b-code-impl/issues/004-power-worksheet.md``) of
the FROZEN ADR ``.steering/20260707-m13-b-impl-design/design-final.md`` (§I6
teeth named 閾値 proposal + power worksheet FROZEN 条件化). This module
computes an **a-priori** categorical multinomial power/MDE for the T_on vs
T_off 5-way zone-marginal shift the 反復 frozen-context bank is designed to
detect (ES-4 Phase 0 categorical-power lineage — Monte-Carlo simulated, no
scipy dependency, self-contained and deterministic under a fixed seed).

Pieces this module owns:

* :func:`categorical_multinomial_power` — the sole public entry point. Given
  an **assumed** base (T_off) zone distribution and an assumed
  total-variation shift ``delta_tv``, Monte-Carlo simulates a chi-square
  goodness-of-fit test (null critical value calibrated by simulating under
  the null, *not* an analytic chi-square table — no ``scipy`` import) at a
  fixed ``M_min``/``K``/pooling configuration and returns the estimated
  detection power.
* the named-threshold **proposal** constants (:data:`M_MIN` / :data:`K_MIN` /
  :data:`DELTA_TV_MIN` / :data:`POWER_MIN` / :data:`H_MIN_BITS` /
  :data:`RHO_MIN`) confirmed by ``experiments/20260708-m13-b-bank/
  power_worksheet.md`` (§I6, non-binding proposal → worksheet-confirmed).

**Scope guard (§I4/§I6, binding — mirrors ``live.py`` / ``live_v1.py`` /
``bank_fixtures.py``).** This is a *construction* apparatus, **NOT a
measurement line**. It is an a-priori, **assumed-distribution-only**
calculation:

* it never reads a real bank annotation side-file (no file I/O of any kind —
  every input is an in-memory ``base_dist`` array the caller supplies);
* it never imports the bank driver's measurement path, ``bank_fixtures``, or
  any sibling module under ``erre_sandbox.integration.embodied`` — it is
  fully self-contained (``numpy`` + stdlib only) so it can be built and
  exercised (I4) fully in parallel with I1-I3/I5;
* it computes no floor / landscape / verdict / divergence and is not an
  ``evidence.*`` measurement apparatus — it is a **buildability** proof: "can
  a categorical-power test detect the assumed shift at the proposed
  M_min/K?", never "does the real bank detect it" (that is C-proper, out of
  scope per the issue).

**Honest limit (§I6(i), non-reopenable).** ``H_min``/``rho`` are *empirical
gate targets*, not guarantees this apparatus (or B generally) can deliver.
:func:`categorical_multinomial_power` demonstrates the *dependency*
mechanically (see ``test_bank_power_collapse_kills_power``): when the real
achievable ``delta_tv`` collapses towards zero (the ``think=False``
zone-marginal-collapse regime that killed 壁1 and 壁4), power collapses too —
regardless of ``M_min``/``K`` — and no code in this module can prevent that,
because it depends on an *empirical* property of the real LLM output, not on
anything this doc-only apparatus controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- fixed Monte-Carlo calibration (deterministic, reproducibility-discipline) --

ALPHA_SIGNIFICANCE: Final[float] = 0.05
"""One-sided significance level for the chi-square goodness-of-fit rejection
region. The critical value is **Monte-Carlo calibrated by simulating under
the null** (see :func:`_null_critical_value`), not read off an analytic
chi-square table — this keeps the apparatus scipy-free (§I4 spend guard
scope: assumed-dist-only computation, no ``evidence`` dependency chain)."""

N_REPLICATES_DEFAULT: Final[int] = 4000
"""Default Monte-Carlo replicate count for both the null-calibration pass and
the power pass. Large enough that the ``power`` estimate's Monte-Carlo
standard error is small (``sqrt(0.5*0.5/4000) ≈ 0.008``) without being slow."""

POWER_SEED_DEFAULT: Final[int] = 20260708
"""Fixed default RNG seed (the issue's construction date) — deterministic,
result-independent (chosen before any Monte-Carlo run was inspected)."""

# --- §I6 named threshold proposal, confirmed by power_worksheet.md -------------

M_MIN: Final[int] = 300
"""Proposal (§I6(ii)): minimum draws per (context, condition)."""

K_MIN: Final[int] = 8
"""Proposal (§I6(ii)): minimum frozen-context count K."""

DELTA_TV_MIN: Final[float] = 0.10
"""Proposal (§I6(iii)): minimum detectable total-variation distance shift."""

POWER_MIN: Final[float] = 0.8
"""Proposal (§I6(iii)): minimum acceptable detection power at ``DELTA_TV_MIN``."""

H_MIN_BITS: Final[float] = 0.5
"""Proposal (§I6(i), empirical gate target, **not B-guaranteed**): minimum
per-context zone-marginal entropy for a context to count as non-degenerate."""

RHO_MIN: Final[float] = 0.5
"""Proposal (§I6(i), empirical gate target, **not B-guaranteed**): minimum
fraction of contexts required to clear ``H_MIN_BITS``."""


@dataclass(frozen=True)
class PowerResult:
    """A-priori power estimate + the inputs that produced it (worksheet-ready)."""

    power: float
    """Monte-Carlo estimated detection probability in ``[0, 1]``."""
    n_total: int
    """Total draws the test statistic is computed over (pooling-dependent)."""
    achieved_delta_tv: float
    """The total-variation distance actually realised by the perturbed
    alternative distribution (equals ``delta_tv`` unless clipped by the base
    distribution's available mass — see :func:`_perturb_to_delta_tv`)."""
    critical_value: float
    """The Monte-Carlo-calibrated chi-square rejection threshold used."""


def _perturb_to_delta_tv(
    base_dist: np.ndarray, delta_tv: float
) -> tuple[np.ndarray, float]:
    """Build a 5-way alternative distribution at total-variation distance ``delta_tv``.

    Moves probability mass ``shift = min(delta_tv, base_dist[hi])`` from the
    highest-probability cell to the lowest-probability cell of ``base_dist``.
    Because exactly two cells change by ``shift`` each,
    ``TV(base, alt) = 0.5 * sum(|base - alt|) = shift`` exactly (up to the
    clip). Returns ``(alt_dist, achieved_delta_tv)``.
    """
    order = np.argsort(base_dist)
    lo_idx = int(order[0])
    hi_idx = int(order[-1])
    shift = min(float(delta_tv), float(base_dist[hi_idx]))
    alt = base_dist.copy()
    alt[hi_idx] -= shift
    alt[lo_idx] += shift
    return alt, shift


def _chi2_stat(counts: np.ndarray, expected: np.ndarray) -> float:
    """Pearson chi-square goodness-of-fit statistic against ``expected`` counts."""
    expected_safe = np.where(expected > 0.0, expected, 1e-12)
    return float(np.sum((counts - expected) ** 2 / expected_safe))


def _null_critical_value(
    base_dist: np.ndarray,
    n_total: int,
    rng: np.random.Generator,
    n_replicates: int,
) -> float:
    """Monte-Carlo-calibrated ``1 - ALPHA_SIGNIFICANCE`` quantile of the null statistic.

    Simulates ``n_replicates`` multinomial draws of size ``n_total`` **from
    ``base_dist`` itself** (the null), computes the chi-square statistic
    against the same expected counts each time, and returns the empirical
    ``(1 - ALPHA_SIGNIFICANCE)`` quantile. This replaces an analytic
    chi-square table lookup (no ``scipy`` dependency) with a self-contained
    simulation, consistent with the ``synthetic_power_curve`` Monte-Carlo
    pattern already used elsewhere in this repository's evidence apparatus
    (design writ, not import — this module imports nothing from
    ``erre_sandbox.evidence``).
    """
    expected = n_total * base_dist
    stats = np.empty(n_replicates, dtype=np.float64)
    for i in range(n_replicates):
        counts = rng.multinomial(n_total, base_dist)
        stats[i] = _chi2_stat(counts, expected)
    return float(np.quantile(stats, 1.0 - ALPHA_SIGNIFICANCE))


def categorical_multinomial_power(
    *,
    base_dist: Sequence[float],
    delta_tv: float,
    m_draws: int,
    k_contexts: int,
    pooling: bool,
    n_replicates: int = N_REPLICATES_DEFAULT,
    seed: int = POWER_SEED_DEFAULT,
) -> PowerResult:
    """A-priori Monte-Carlo power of a 5-way categorical-multinomial shift test.

    ``base_dist`` is the **assumed** T_off zone-marginal distribution (any
    length ``>= 2``; the bank's real ``K = 5`` zones use length 5). The
    alternative (T_on) distribution is built by :func:`_perturb_to_delta_tv`
    at total-variation distance ``delta_tv`` from ``base_dist``.

    ``n_total`` is ``m_draws * k_contexts`` when ``pooling`` is ``True`` (the
    K frozen contexts are pooled into a single test — the §I6 K-pooling
    assumption the worksheet must state) and ``m_draws`` alone when
    ``pooling`` is ``False`` (each context tested independently at only its
    own ``m_draws`` — the conservative, no-pooling reading).

    Returns a :class:`PowerResult`. **Never reads a file, never imports a
    sibling ``erre_sandbox.integration.embodied`` module, never imports
    ``erre_sandbox.evidence`` — every input is the caller-supplied assumed
    distribution.**
    """
    base = np.asarray(base_dist, dtype=np.float64)
    total = float(base.sum())
    if total <= 0.0:
        msg = "base_dist must sum to a positive value"
        raise ValueError(msg)
    base = base / total

    n_total = int(m_draws) * int(k_contexts) if pooling else int(m_draws)
    if n_total <= 0:
        msg = "n_total (m_draws[, * k_contexts]) must be positive"
        raise ValueError(msg)

    rng = np.random.default_rng(seed)
    alt, achieved_delta = _perturb_to_delta_tv(base, delta_tv)
    critical = _null_critical_value(base, n_total, rng, n_replicates)

    expected = n_total * base
    rejections = 0
    for _ in range(n_replicates):
        counts = rng.multinomial(n_total, alt)
        if _chi2_stat(counts, expected) > critical:
            rejections += 1
    power = rejections / n_replicates

    return PowerResult(
        power=power,
        n_total=n_total,
        achieved_delta_tv=achieved_delta,
        critical_value=critical,
    )


__all__ = [
    "ALPHA_SIGNIFICANCE",
    "DELTA_TV_MIN",
    "H_MIN_BITS",
    "K_MIN",
    "M_MIN",
    "N_REPLICATES_DEFAULT",
    "POWER_MIN",
    "POWER_SEED_DEFAULT",
    "RHO_MIN",
    "PowerResult",
    "categorical_multinomial_power",
]
