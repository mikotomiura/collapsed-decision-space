"""Frozen conjunctive verdict for the M13-ES3 locomotion conformance (§4).

Pure decision logic over the pooled :class:`~...decomposition.Decomposition` and
the :class:`~...controls.ControlResults`. Every threshold is read from
:mod:`erre_sandbox.evidence.es3_locomotion.constants`; this module holds **no**
tunable literal of its own. The structure mirrors ES-1 ``spdm.verdict_report`` /
ES-2 ``es2_replay.verdict_report``: the INCONCLUSIVE gate is evaluated **first**
(so an under-powered or invalid measurement is never reported as a progressive
NO_GO), then the single NO_GO condition, then GO.

Verdict vocabulary (``design-final.md`` §0, kept distinct):

* **GO** — apparatus valid ∧ ``CI_lower(D_loco) ≥ AMP_FLOOR``: the locomotion
  channel traverses a non-negligible fraction of the available headroom within
  static cells. Means *eligible to proceed to ES-4 / divergence measurement*,
  **not** a test of walking → divergence (over-claim guard §8).
* **NO_GO** — apparatus valid ∧ **headroom sufficient**, yet
  ``CI_lower(D_loco) < AMP_FLOOR``: the channel cannot convert the available
  headroom into effective modulation. A **progressive finding**, not a refutation.
* **INCONCLUSIVE** — apparatus invalid (ablation not bit-equal / zone-function
  control ≠ 0 / repeat_penalty not invariant) or under-powered (too few valid
  walk-seeds / headroom-valid cells / within-cell n / within-cell λ spread /
  headroom-valid fraction). Never conflated with NO_GO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from erre_sandbox.evidence.bootstrap_ci import bootstrap_ci
from erre_sandbox.evidence.es3_locomotion import constants as _c

if TYPE_CHECKING:
    from erre_sandbox.evidence.es3_locomotion.controls import ControlResults
    from erre_sandbox.evidence.es3_locomotion.decomposition import Decomposition

Verdict = Literal["GO", "NO_GO", "INCONCLUSIVE"]


@dataclass(frozen=True)
class Es3Verdict:
    """The ES-3 verdict and the statistics that produced it."""

    verdict: Verdict
    reasons: tuple[str, ...]
    n_cells: int
    n_headroom_valid: int
    headroom_valid_fraction: float
    n_n_valid: int
    n_spread_valid: int
    n_measurement_valid: int
    n_valid_walk_seeds: int
    d_loco: float
    ci_lower: float
    ci_upper: float
    max_repeat_penalty_var: float
    ablation_bit_equal: bool
    ablation_max_abs_diff: float
    zone_function_d_loco: float
    n_hist_history_shuffle_d_loco: float
    n_hist_lambda_shuffle_d_loco: float
    n_top_p_headroom_valid: int
    median_top_p_amplitude: float


def _ci_bounds(per_seed: tuple[float, ...], bootstrap_seed: int) -> tuple[float, float]:
    """One-sided-relevant bootstrap CI of the per-walk-seed ``D_loco^(b)`` mean."""
    if not per_seed:
        return 0.0, 0.0
    ci = bootstrap_ci(
        list(per_seed),
        n_resamples=_c.N_RESAMPLES,
        ci=1.0 - _c.CI_ALPHA,
        seed=bootstrap_seed,
        statistic="mean",
    )
    return ci.lo, ci.hi


def _inconclusive_reason(  # noqa: PLR0911 — pre-registered guard sequence (§4.1)
    decomp: Decomposition,
    controls: ControlResults,
) -> str | None:
    """First INCONCLUSIVE trigger (§4.1), else None.

    Checked before NO_GO/GO so an under-powered or invalid measurement is never
    reported as a (progressive) NO_GO finding. Apparatus-validity failures
    (ablation, zone-function, repeat_penalty) live here, not in NO_GO.
    """
    if decomp.n_valid_walk_seeds < _c.MIN_WALK_SEEDS:
        return (
            f"valid walk-seeds {decomp.n_valid_walk_seeds} < MIN_WALK_SEEDS "
            f"{_c.MIN_WALK_SEEDS}"
        )
    if decomp.n_headroom_valid < _c.MIN_CELLS:
        return (
            f"headroom-valid cells {decomp.n_headroom_valid} < MIN_CELLS {_c.MIN_CELLS}"
        )
    if decomp.n_n_valid < _c.MIN_CELLS:
        return (
            f"within-cell-n-valid cells {decomp.n_n_valid} < MIN_CELLS "
            f"{_c.MIN_CELLS} (most cells under-sampled vs MIN_CELL_N {_c.MIN_CELL_N})"
        )
    if decomp.n_spread_valid < _c.MIN_CELLS:
        return (
            f"λ-spread-valid cells {decomp.n_spread_valid} < MIN_CELLS "
            f"{_c.MIN_CELLS} (λ ~zone-determined; var < LOCO_SPREAD_MIN "
            f"{_c.LOCO_SPREAD_MIN})"
        )
    if decomp.headroom_valid_fraction < _c.HEADROOM_VALID_FRAC:
        return (
            f"headroom-valid fraction {decomp.headroom_valid_fraction:.3f} < "
            f"HEADROOM_VALID_FRAC {_c.HEADROOM_VALID_FRAC} (base+mode saturated)"
        )
    if decomp.n_measurement_valid < _c.MIN_CELLS:
        return (
            f"measurement-valid cells {decomp.n_measurement_valid} < MIN_CELLS "
            f"{_c.MIN_CELLS} (headroom∧spread∧n)"
        )
    if not controls.ablation_bit_equal:
        return (
            f"ablation not bit-equal (max |Δ| {controls.ablation_max_abs_diff:.2e} "
            f"> ZERO_TOL {_c.ZERO_TOL}); apparatus invalid"
        )
    if controls.zone_function_d_loco > _c.ZERO_TOL:
        return (
            f"zone-function control D_loco {controls.zone_function_d_loco:.2e} > "
            f"ZERO_TOL {_c.ZERO_TOL} (separation broken); apparatus invalid"
        )
    if decomp.max_repeat_penalty_var > _c.ZERO_TOL:
        return (
            f"repeat_penalty not invariant (max var "
            f"{decomp.max_repeat_penalty_var:.2e} > ZERO_TOL {_c.ZERO_TOL}); "
            "design violation"
        )
    return None


def _pack(
    verdict: Verdict,
    reasons: tuple[str, ...],
    decomp: Decomposition,
    controls: ControlResults,
    ci_lower: float,
    ci_upper: float,
) -> Es3Verdict:
    return Es3Verdict(
        verdict=verdict,
        reasons=reasons,
        n_cells=decomp.n_cells,
        n_headroom_valid=decomp.n_headroom_valid,
        headroom_valid_fraction=decomp.headroom_valid_fraction,
        n_n_valid=decomp.n_n_valid,
        n_spread_valid=decomp.n_spread_valid,
        n_measurement_valid=decomp.n_measurement_valid,
        n_valid_walk_seeds=decomp.n_valid_walk_seeds,
        d_loco=decomp.d_loco,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        max_repeat_penalty_var=decomp.max_repeat_penalty_var,
        ablation_bit_equal=controls.ablation_bit_equal,
        ablation_max_abs_diff=controls.ablation_max_abs_diff,
        zone_function_d_loco=controls.zone_function_d_loco,
        n_hist_history_shuffle_d_loco=controls.n_hist_history_shuffle_d_loco,
        n_hist_lambda_shuffle_d_loco=controls.n_hist_lambda_shuffle_d_loco,
        n_top_p_headroom_valid=decomp.n_top_p_headroom_valid,
        median_top_p_amplitude=decomp.median_top_p_amplitude,
    )


def evaluate_verdict(
    decomp: Decomposition,
    controls: ControlResults,
    *,
    bootstrap_seed: int = 0,
) -> Es3Verdict:
    """Render the frozen ES-3 verdict from the decomposition + control battery.

    ``bootstrap_seed`` makes the per-walk-seed CI reproducible. All thresholds
    come from :mod:`constants`; nothing here is tuned post-result.
    """
    ci_lower, ci_upper = _ci_bounds(decomp.per_seed_d_loco, bootstrap_seed)

    incon = _inconclusive_reason(decomp, controls)
    if incon is not None:
        return _pack("INCONCLUSIVE", (incon,), decomp, controls, ci_lower, ci_upper)

    if ci_lower < _c.AMP_FLOOR:
        return _pack(
            "NO_GO",
            (
                f"CI_lower(D_loco) {ci_lower:.4f} < AMP_FLOOR {_c.AMP_FLOOR} "
                "(headroom sufficient, effective modulation insufficient)",
            ),
            decomp,
            controls,
            ci_lower,
            ci_upper,
        )

    return _pack(
        "GO",
        (
            "apparatus valid ∧ CI_lower(D_loco) ≥ AMP_FLOOR; "
            "eligible to proceed to ES-4",
        ),
        decomp,
        controls,
        ci_lower,
        ci_upper,
    )


__all__ = ["Es3Verdict", "Verdict", "evaluate_verdict"]
