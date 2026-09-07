"""Nested reduced-model decomposition + headroom-normalised ``D_loco`` (§2.2-§2.3).

This is the measurable estimand of the ES-3 freeze (Codex HIGH-1/HIGH-2). The
**reduced model** ``R: E ~ C(p, z)`` is the per-static-cell mean of the divergence
coordinate ``E = temperature``: it absorbs the persona default *and* the static
ERRE-mode (location) contribution, including the cell's mean locomotion, so the
**within-cell residual is by construction the within-zone locomotion signal**
(the standalone N_zone null was vacuous → replaced by this nested model).

Because the apparatus is deterministic, the classical η² (which assumes a noise
residual) is degenerate; the primary statistic is instead **headroom-normalised**
and **roster-independent** (HIGH-2): for each static cell ``s = (persona, zone)``,

* ``E_abl,s`` = the ablation temperature (no locomotion delta), constant in the
  cell, so headroom ``H_s = TEMP_MAX − E_abl,s`` is cell-constant;
* amplitude ``a_s = std_within_s(E_full) / H_s`` = "what fraction of the available
  headroom locomotion traverses in within-cell std";
* primary ``D_loco`` = the **cell-equal-weighted median of ``a_s``** over the
  headroom-∧-spread-∧-n-valid cells.

The bootstrap unit is the **per-walk-seed aggregate ``D_loco^(b)``** (HIGH-4): a
step-row bootstrap would inflate precision through the EMA autocorrelation, so the
CI in :mod:`verdict_report` is taken over the per-seed values this module emits.

``numpy``/stdlib only; verdict-blind (reads the ``temperature`` ensemble
:mod:`scenario` emits and nothing else).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from erre_sandbox.evidence.es3_locomotion import constants as _c

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.evidence.es3_locomotion.scenario import StepObservation
    from erre_sandbox.schemas import Zone


@dataclass(frozen=True)
class CellStat:
    """Per-static-cell ``s = (persona, zone)`` reduced-model readout."""

    persona_id: str
    zone: Zone
    n: int
    e_abl: float
    """Ablation temperature (cell-constant); the reduced-model location value."""
    headroom: float
    """``TEMP_MAX − e_abl`` = the divergence-direction clamp headroom."""
    headroom_valid: bool
    lam_var: float
    """Within-cell var(λ); the separation signal (0 ⇒ λ is zone-determined)."""
    spread_valid: bool
    n_valid: bool
    e_full_std: float
    """Within-cell std of the full (locomotion-on) temperature."""
    amplitude: float
    """``e_full_std / headroom`` = ``a_s`` (the headroom-normalised statistic)."""
    repeat_penalty_var: float
    """Within-cell var(repeat_penalty); must be 0 (divergence-specific invariant)."""
    top_p_abl: float
    top_p_headroom: float
    top_p_full_std: float

    @property
    def measurement_valid(self) -> bool:
        """Headroom ∧ within-cell λ spread ∧ within-cell n are all adequate."""
        return self.headroom_valid and self.spread_valid and self.n_valid


def _cell_stat(persona_id: str, zone: Zone, items: list[StepObservation]) -> CellStat:
    lam = np.fromiter((it.lam for it in items), dtype=np.float64)
    e_full = np.fromiter((it.e_full for it in items), dtype=np.float64)
    rp = np.fromiter((it.repeat_penalty_full for it in items), dtype=np.float64)
    top_p_full = np.fromiter((it.top_p_full for it in items), dtype=np.float64)
    e_abl = items[0].e_abl
    top_p_abl = items[0].top_p_abl
    n = len(items)
    headroom = _c.TEMP_MAX - e_abl
    lam_var = float(np.var(lam))
    top_p_headroom = 1.0 - top_p_abl
    amplitude = float(np.std(e_full)) / headroom if headroom > 0.0 else 0.0
    return CellStat(
        persona_id=persona_id,
        zone=zone,
        n=n,
        e_abl=e_abl,
        headroom=headroom,
        headroom_valid=headroom > _c.HEADROOM_MIN,
        lam_var=lam_var,
        spread_valid=lam_var >= _c.LOCO_SPREAD_MIN,
        n_valid=n >= _c.MIN_CELL_N,
        e_full_std=float(np.std(e_full)),
        amplitude=amplitude,
        repeat_penalty_var=float(np.var(rp)),
        top_p_abl=top_p_abl,
        top_p_headroom=top_p_headroom,
        top_p_full_std=float(np.std(top_p_full)),
    )


def cell_statistics(obs: Sequence[StepObservation]) -> list[CellStat]:
    """Group observations into static cells ``(persona, zone)`` and reduce each."""
    groups: dict[tuple[str, Zone], list[StepObservation]] = defaultdict(list)
    for o in obs:
        groups[(o.persona_id, o.zone)].append(o)
    return [_cell_stat(pid, z, items) for (pid, z), items in groups.items()]


def _median(values: Sequence[float]) -> float:
    return float(np.median(values)) if values else 0.0


def d_loco_from_cells(cells: Sequence[CellStat]) -> float:
    """Cell-equal-weighted median ``a_s`` over **headroom-valid** cells (ADR §2.3).

    Per the frozen ADR §2.3 the primary ``D_loco`` is the median over *headroom-
    valid* cells, **not** the measurement-valid subset: a cell whose within-cell λ
    spread has collapsed is still headroom-valid but contributes ``a_s ≈ 0``, which
    correctly drags ``D_loco`` down — that is the separation falsifiability (§2.4
    #1), not noise to be filtered out. Within-cell λ spread and within-cell n
    adequacy are *separate* INCONCLUSIVE gates on cell **counts** (§4.1), never a
    filter on this median. (When pooled over all walk-seeds every cell has ample n,
    so this equals the measurement-valid median unless λ is zone-determined.)
    """
    amps = [c.amplitude for c in cells if c.headroom_valid]
    return _median(amps)


@dataclass(frozen=True)
class Decomposition:
    """Pooled decomposition + per-walk-seed aggregates for the verdict."""

    cells: tuple[CellStat, ...]
    n_cells: int
    n_headroom_valid: int
    headroom_valid_fraction: float
    n_n_valid: int
    n_spread_valid: int
    n_measurement_valid: int
    d_loco: float
    """Pooled cell-equal-weighted median ``a_s`` (point estimate)."""
    max_repeat_penalty_var: float
    """Max within-cell var(repeat_penalty) over measurement-valid cells (→ 0)."""
    per_seed_d_loco: tuple[float, ...]
    """``D_loco^(b)`` for each bootstrap-valid walk-seed (the bootstrap units)."""
    n_valid_walk_seeds: int
    n_top_p_headroom_valid: int
    median_top_p_amplitude: float
    """Secondary (M3): median top_p ``a_s`` over top_p-headroom-valid cells."""


def _per_seed_d_loco(obs: Sequence[StepObservation]) -> tuple[float, ...]:
    """``D_loco^(b)`` for every walk-seed that has ≥1 headroom-∧-n-valid cell.

    The per-walk-seed aggregate is the bootstrap unit (HIGH-4). Unlike the pooled
    primary (where every cell has ample n), a *single* walk visits some zones too
    few times for a stable within-cell std, so per-seed cells are additionally
    required to clear ``MIN_CELL_N`` (the documented purpose of that constant).
    Spread-collapsed but n-adequate cells **stay in** (contributing ``a_s ≈ 0``),
    preserving the separation falsifiability at the per-seed level too.
    """
    by_seed: dict[int, list[StepObservation]] = defaultdict(list)
    for o in obs:
        by_seed[o.walk_seed].append(o)
    values: list[float] = []
    for seed in sorted(by_seed):
        cells = cell_statistics(by_seed[seed])
        amps = [c.amplitude for c in cells if c.headroom_valid and c.n_valid]
        if amps:
            values.append(_median(amps))
    return tuple(values)


def decompose(obs: Sequence[StepObservation]) -> Decomposition:
    """Full pooled + per-seed decomposition over the blind ensemble."""
    cells = cell_statistics(obs)
    measurement_valid = [c for c in cells if c.measurement_valid]
    n_cells = len(cells)
    n_headroom_valid = sum(1 for c in cells if c.headroom_valid)
    top_p_valid = [c for c in cells if c.top_p_headroom > _c.HEADROOM_MIN]
    per_seed = _per_seed_d_loco(obs)
    return Decomposition(
        cells=tuple(cells),
        n_cells=n_cells,
        n_headroom_valid=n_headroom_valid,
        headroom_valid_fraction=(n_headroom_valid / n_cells if n_cells else 0.0),
        n_n_valid=sum(1 for c in cells if c.n_valid),
        n_spread_valid=sum(1 for c in cells if c.spread_valid),
        n_measurement_valid=len(measurement_valid),
        d_loco=d_loco_from_cells(cells),
        max_repeat_penalty_var=max(
            (c.repeat_penalty_var for c in measurement_valid), default=0.0
        ),
        per_seed_d_loco=per_seed,
        n_valid_walk_seeds=len(per_seed),
        n_top_p_headroom_valid=len(top_p_valid),
        median_top_p_amplitude=_median(
            [
                c.top_p_full_std / c.top_p_headroom
                for c in top_p_valid
                if c.top_p_headroom > 0.0
            ]
        ),
    )


__all__ = [
    "CellStat",
    "Decomposition",
    "cell_statistics",
    "d_loco_from_cells",
    "decompose",
]
