"""Exact blind-walk scenario generator for the M13-ES3 locomotion verdict (§1.1).

The apparatus is **independent of the live cognition wiring**: it generates its
own kinetic histories from a verdict-blind movement model and composes sampling
the same way ``inference/sampling.py`` does, then hands the resulting
``temperature`` ensemble to :mod:`decomposition` / :mod:`verdict_report`.

The blind walk is the exact generator frozen at pre-registration (Codex HIGH-3):
at each step the walker picks uniformly from ``ADJACENCY[z] ∪ {z}`` (``self`` =
stay), so the **stay probability ``1/(deg(z)+1)`` is graph-determined, not a
designer knob**. The per-step ``move_t ∈ {0, 1}`` ("did the containing zone
change") therefore fluctuates, and the EMA
``λ_t = (1-α)·λ_{t-1} + α·move_t`` (``λ_0 = 0``) rises on a walking streak and
decays on stay — varying *within* a zone visit, so λ is **not** a deterministic
function of the zone (the separation the zone-function control in
:mod:`controls` falsifies).

The reduced-model location component is the **static ERRE mode per zone**
(``ZONE_TO_DEFAULT_ERRE_MODE`` → ``SAMPLING_DELTA_BY_MODE``); it is used directly
from :mod:`erre_sandbox.erre` (an allowed ``evidence → erre`` dependency), while
the world geometry (zones / adjacency) is **mirrored** as ordered tuples and
pinned byte-for-byte to ``erre_sandbox.world.zones`` in the scenario test (so
``random.choice`` is reproducible and the mirror cannot silently drift — the same
discipline as ``evidence.spdm.scenario``).

Claim boundary (``design-final.md`` §0 / §8): the ``temperature`` ensemble this
emits is the channel substrate; a GO over it means the locomotion → sampling
channel is wired (eligible for ES-4), **not** a test of walking → divergence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from erre_sandbox.erre import SAMPLING_DELTA_BY_MODE, ZONE_TO_DEFAULT_ERRE_MODE
from erre_sandbox.erre.locomotion_sampling import locomotion_delta
from erre_sandbox.evidence.es3_locomotion import constants as _c
from erre_sandbox.inference.sampling import compose_sampling
from erre_sandbox.schemas import LocomotionState, SamplingBase, SamplingDelta, Zone

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- world-geometry mirror (pinned to erre_sandbox.world.zones in the test) ----

ZONES: tuple[Zone, ...] = (
    Zone.STUDY,
    Zone.PERIPATOS,
    Zone.CHASHITSU,
    Zone.AGORA,
    Zone.GARDEN,
)
"""The five zones in ``Zone`` declaration order (deterministic across interpreters)."""

ADJACENCY: dict[Zone, tuple[Zone, ...]] = {
    Zone.STUDY: (Zone.PERIPATOS,),
    Zone.PERIPATOS: (Zone.STUDY, Zone.CHASHITSU, Zone.AGORA, Zone.GARDEN),
    Zone.CHASHITSU: (Zone.PERIPATOS, Zone.GARDEN),
    Zone.AGORA: (Zone.PERIPATOS, Zone.GARDEN),
    Zone.GARDEN: (Zone.PERIPATOS, Zone.CHASHITSU, Zone.AGORA),
}
"""Walkable adjacency mirrored from ``world.zones.ADJACENCY`` (neighbour tuples in
``ZONES`` order so ``random.choice`` is reproducible). Pinned in the test."""

# Static ERRE mode delta per zone = the reduced-model location component (the
# ``peripatetic`` zone-triggered bump etc.). Used directly from ``erre`` (not
# mirrored); the canonical mapping is pinned in the scenario test.
MODE_DELTA_BY_ZONE: dict[Zone, SamplingDelta] = {
    z: SAMPLING_DELTA_BY_MODE[ZONE_TO_DEFAULT_ERRE_MODE[z]] for z in ZONES
}


def walk_options(zone: Zone) -> tuple[Zone, ...]:
    """``ADJACENCY[zone] ∪ {zone}`` as an ordered tuple (self = stay, §1.1)."""
    return (*ADJACENCY[zone], zone)


@dataclass(frozen=True)
class WalkTrajectory:
    """One blind walk: the zone occupied and the move indicator at each step.

    ``moves[t]`` = 1 iff ``zones[t] != zones[t-1]`` (``moves[0] = 0``: no prior).
    λ is *not* stored here — it is derived by :func:`ema_lambda` so the
    N_hist control can shuffle ``moves`` and recompute λ from the same EMA.
    """

    seed: int
    start: Zone
    zones: tuple[Zone, ...]
    moves: tuple[int, ...]


def blind_walk(start: Zone, steps: int, rng: random.Random) -> WalkTrajectory:
    """A length-``steps`` blind walk over ``ADJACENCY[z] ∪ {z}`` from ``start``.

    ``zones[t]`` is the zone occupied at step ``t``; the walker then picks the
    next zone uniformly from :func:`walk_options` (self included = stay). Fully
    determined by ``rng``; ``zones[0] == start``.
    """
    here = start
    prev: Zone | None = None
    zones: list[Zone] = []
    moves: list[int] = []
    for _ in range(steps):
        move_t = 0 if prev is None else int(here != prev)
        zones.append(here)
        moves.append(move_t)
        prev = here
        here = rng.choice(walk_options(here))
    return WalkTrajectory(
        seed=-1,  # set by the caller (default_seed_bank driver)
        start=start,
        zones=tuple(zones),
        moves=tuple(moves),
    )


def ema_lambda(moves: Sequence[int], alpha: float) -> list[float]:
    """EMA locomotion intensity ``λ_t = (1-α)·λ_{t-1} + α·move_t`` (``λ_0`` via 0).

    With ``moves[0] = 0`` the recurrence starts at ``λ_0 = α·0 = 0`` (ADR §1.1).
    """
    lam = 0.0
    out: list[float] = []
    for m in moves:
        lam = (1.0 - alpha) * lam + alpha * float(m)
        out.append(lam)
    return out


def trajectory(seed: int) -> WalkTrajectory:
    """The blind walk for scenario ``seed`` (start drawn by the same blind RNG)."""
    rng = random.Random(f"es3-walk-{seed}")  # noqa: S311 — deterministic science RNG
    start = ZONES[rng.randrange(len(ZONES))]
    walk = blind_walk(start, _c.T, rng)
    return WalkTrajectory(
        seed=seed, start=walk.start, zones=walk.zones, moves=walk.moves
    )


@dataclass(frozen=True)
class StepObservation:
    """One ensemble unit ``u = (walk_seed b, step t, persona p)`` readout (§2.1).

    ``e_abl`` is the ablation temperature (no locomotion delta) and is constant
    within a static cell ``s = (persona, zone)``; ``e_full`` adds the λ-driven
    locomotion delta. ``top_p_*`` / ``repeat_penalty_full`` feed the secondary /
    invariance controls.
    """

    walk_seed: int
    persona_id: str
    zone: Zone
    lam: float
    e_full: float
    e_abl: float
    top_p_full: float
    top_p_abl: float
    repeat_penalty_full: float


def _observe(
    walk_seed: int,
    persona_id: str,
    base: SamplingBase,
    zone: Zone,
    lam: float,
) -> StepObservation:
    mode_delta = MODE_DELTA_BY_ZONE[zone]
    loco = locomotion_delta(
        LocomotionState(lam=lam),
        gain_t=_c.LOCO_GAIN_T,
        gain_p=_c.LOCO_GAIN_P,
    )
    full = compose_sampling(base, mode_delta, loco)
    abl = compose_sampling(base, mode_delta)  # bit-identical None path (the ablation)
    return StepObservation(
        walk_seed=walk_seed,
        persona_id=persona_id,
        zone=zone,
        lam=lam,
        e_full=full.temperature,
        e_abl=abl.temperature,
        top_p_full=full.top_p,
        top_p_abl=abl.top_p,
        repeat_penalty_full=full.repeat_penalty,
    )


def observe_trajectory(
    walk: WalkTrajectory,
    lams: Sequence[float],
) -> list[StepObservation]:
    """Build the per-(persona, step) observations of one walk under given λ.

    ``lams`` is supplied separately so the apparatus (blind EMA λ), the
    zone-function control (λ = h(z)), and the N_hist control (shuffled-history λ)
    all reuse this one composition path.
    """
    obs: list[StepObservation] = []
    for persona_id, base in _c.PERSONA_ROSTER:
        for zone, lam in zip(walk.zones, lams, strict=True):
            obs.append(_observe(walk.seed, persona_id, base, zone, lam))
    return obs


def build_observations(seed_bank: Sequence[int]) -> list[StepObservation]:
    """The canonical blind ensemble: every walk × persona under blind EMA λ."""
    obs: list[StepObservation] = []
    for seed in seed_bank:
        walk = trajectory(seed)
        lams = ema_lambda(walk.moves, _c.ALPHA)
        obs.extend(observe_trajectory(walk, lams))
    return obs


def default_seed_bank() -> tuple[int, ...]:
    """The pre-registered blind seed bank: ``range(B)`` (= 0..63).

    Fixed before the run; no seed is added or dropped after seeing a result
    (forking-paths guard). A superseding ADR is required to change it.
    """
    return tuple(range(_c.B))


__all__ = [
    "ADJACENCY",
    "MODE_DELTA_BY_ZONE",
    "ZONES",
    "StepObservation",
    "WalkTrajectory",
    "blind_walk",
    "build_observations",
    "default_seed_bank",
    "ema_lambda",
    "observe_trajectory",
    "trajectory",
    "walk_options",
]
