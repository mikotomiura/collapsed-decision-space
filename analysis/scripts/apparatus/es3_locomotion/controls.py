"""Validity gate / control battery for the M13-ES3 verdict (§3, pre-registered).

Three controls plus two diagnostics, all driven from the same blind generator:

* **Ablation identity (iii)** — the ``loco_delta=None`` path and the ``gain=0``
  path must be **bit-equal** (Codex L2): "``None`` path vs ``gain=0`` path bit
  equality", not "difference from a full-gain run". A non-zero difference means
  the third additive term is not a clean identity → apparatus INVALID.
* **Zone-function control (ii)** — re-run with λ forced to a deterministic zone
  function ``h(z)``. Then λ is constant within every cell, so the within-cell
  residual (and hence ``D_loco``) must **collapse to 0** (≤ ``ZERO_TOL``). A
  non-zero value would mean the reduced model failed to absorb the zone-mean
  locomotion → the separation is broken → apparatus INVALID (the ES-2
  temporal-control analogue: it demonstrates the estimand *can* read 0).
* **N_hist sensitivity (non-primary, M5)** — two **separately recorded**
  diagnostics that stratify the claim, never a gate: the *history-recompute*
  shuffle (permute the move sequence, **recompute** λ via the EMA) probes whether
  λ carries movement *history*; the *λ-multiset* shuffle (permute the λ values
  within a walk, decoupling them from the zone timing) is the contrast.

The repeat-penalty zero-variance invariant and the within-cell λ-spread gate live
on the :class:`~...decomposition.Decomposition` itself (read by the verdict).

``numpy``/stdlib only; verdict-blind.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from erre_sandbox.erre.locomotion_sampling import locomotion_delta
from erre_sandbox.evidence.es3_locomotion import constants as _c
from erre_sandbox.evidence.es3_locomotion.decomposition import (
    cell_statistics,
    decompose,
)
from erre_sandbox.evidence.es3_locomotion.scenario import (
    MODE_DELTA_BY_ZONE,
    ema_lambda,
    observe_trajectory,
    trajectory,
)
from erre_sandbox.inference.sampling import compose_sampling
from erre_sandbox.schemas import LocomotionState, Zone

if TYPE_CHECKING:
    from collections.abc import Sequence

# Deterministic zone → λ function for the separation falsifiability control.
# Evenly spaced by zone so λ is constant within every cell (var_within = 0).
ZONE_FUNCTION_LAMBDA: dict[Zone, float] = {
    Zone.STUDY: 0.0,
    Zone.PERIPATOS: 0.25,
    Zone.CHASHITSU: 0.5,
    Zone.AGORA: 0.75,
    Zone.GARDEN: 1.0,
}


@dataclass(frozen=True)
class ControlResults:
    """The control battery readouts the verdict consumes / records."""

    ablation_bit_equal: bool
    ablation_max_abs_diff: float
    zone_function_d_loco: float
    n_hist_history_shuffle_d_loco: float
    n_hist_lambda_shuffle_d_loco: float


def ablation_identity(seed_bank: Sequence[int]) -> tuple[bool, float]:
    """Bit-equality of the ``loco_delta=None`` path and the ``gain=0`` path (iii).

    Returns ``(bit_equal, max_abs_diff)`` over the full blind ensemble. ``gain=0``
    yields the all-zero delta, so the composed ``temperature`` must equal the
    ``None``-path temperature exactly (within ``ZERO_TOL`` for float epsilon).
    """
    max_diff = 0.0
    for seed in seed_bank:
        walk = trajectory(seed)
        lams = ema_lambda(walk.moves, _c.ALPHA)
        for _persona_id, base in _c.PERSONA_ROSTER:
            for zone, lam in zip(walk.zones, lams, strict=True):
                mode_delta = MODE_DELTA_BY_ZONE[zone]
                temp_none = compose_sampling(base, mode_delta).temperature
                gain0 = locomotion_delta(
                    LocomotionState(lam=lam), gain_t=0.0, gain_p=0.0
                )
                temp_gain0 = compose_sampling(base, mode_delta, gain0).temperature
                max_diff = max(max_diff, abs(temp_none - temp_gain0))
    return max_diff <= _c.ZERO_TOL, max_diff


def zone_function_d_loco(seed_bank: Sequence[int]) -> float:
    """``D_loco`` with λ = h(z): must collapse to ~0 (ii, separation falsifiability).

    Computed as the median amplitude over **headroom-valid** cells (not the
    measurement-valid subset, which the spread gate would empty trivially) so the
    residual collapse is shown directly: λ constant in a cell ⇒ ``std(E_full)=0``
    ⇒ ``a_s=0``.
    """
    obs = []
    for seed in seed_bank:
        walk = trajectory(seed)
        lams = [ZONE_FUNCTION_LAMBDA[z] for z in walk.zones]
        obs.extend(observe_trajectory(walk, lams))
    cells = cell_statistics(obs)
    amps = [c.amplitude for c in cells if c.headroom_valid]
    return float(np.median(amps)) if amps else 0.0


def _shuffled(seq: Sequence[float] | Sequence[int], tag: str) -> list[float]:
    rng = random.Random(tag)  # noqa: S311 — deterministic science RNG
    out = [float(x) for x in seq]
    rng.shuffle(out)
    return out


def n_hist_history_shuffle_d_loco(seed_bank: Sequence[int]) -> float:
    """``D_loco`` when the move *history* is permuted and λ **recomputed** (M5)."""
    obs = []
    for seed in seed_bank:
        walk = trajectory(seed)
        moves = [int(m) for m in _shuffled(walk.moves, f"es3-nhist-{seed}")]
        lams = ema_lambda(moves, _c.ALPHA)
        obs.extend(observe_trajectory(walk, lams))
    return decompose(obs).d_loco


def n_hist_lambda_shuffle_d_loco(seed_bank: Sequence[int]) -> float:
    """``D_loco`` when the λ values are permuted within a walk (terminal contrast)."""
    obs = []
    for seed in seed_bank:
        walk = trajectory(seed)
        lams = _shuffled(ema_lambda(walk.moves, _c.ALPHA), f"es3-lamshuf-{seed}")
        obs.extend(observe_trajectory(walk, lams))
    return decompose(obs).d_loco


def run_controls(seed_bank: Sequence[int]) -> ControlResults:
    """Run the full control battery over the blind seed bank."""
    bit_equal, max_diff = ablation_identity(seed_bank)
    return ControlResults(
        ablation_bit_equal=bit_equal,
        ablation_max_abs_diff=max_diff,
        zone_function_d_loco=zone_function_d_loco(seed_bank),
        n_hist_history_shuffle_d_loco=n_hist_history_shuffle_d_loco(seed_bank),
        n_hist_lambda_shuffle_d_loco=n_hist_lambda_shuffle_d_loco(seed_bank),
    )


__all__ = [
    "ZONE_FUNCTION_LAMBDA",
    "ControlResults",
    "ablation_identity",
    "n_hist_history_shuffle_d_loco",
    "n_hist_lambda_shuffle_d_loco",
    "run_controls",
    "zone_function_d_loco",
]
