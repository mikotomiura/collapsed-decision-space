"""World zone geometry SSOT (M13 ECL v0, DA-ECLIMPL-1 / Codex LOW-1).

Relocated from :mod:`erre_sandbox.world.zones` so that the ECL v0 organ can
resolve **history-dependent destination geometry in the cognition layer**
(``cognition/embodiment.py``) while obeying the architecture-rules dependency
direction: ``cognition`` may import ``contracts`` but never ``world``. This
module is the *what* (the geometry values + pure geometry helpers), depending
only on :mod:`erre_sandbox.schemas` + stdlib — the same discipline as
:mod:`erre_sandbox.contracts.thresholds` (``M2_THRESHOLDS`` relocation, codex
review F5). ``world/zones.py`` is kept as a re-export shim so every existing
``from erre_sandbox.world.zones import ...`` keeps working.

Scope of the relocation (Codex LOW-1, `.steering/20260705-ecl-v0-code-impl/
decisions.md` G-9): only :data:`WORLD_SIZE_M` / :data:`ZONE_CENTERS` /
:func:`locate_zone` / :func:`default_spawn` move here, plus the ECL micro
geometry (:data:`CELL_MICRO_RADIUS_M` / :func:`disc_jitter` / :func:`reflect_clamp`,
design-copied — *not imported* — from the frozen
``evidence.d0_substrate.running.policy``). ``ZONE_PROPS`` and ``ADJACENCY``
stay in ``world/zones.py`` (Godot hard-coded sync note / world-walk use).

**Dependency direction (binding, Codex TASK-PRE MEDIUM)**: this module imports
only ``schemas`` + stdlib and **must never import ``world.zones``** — the
relocation is a one-way ``world.zones -> contracts.geometry`` edge, otherwise a
circular import breaks cold-importing either module.
"""

from __future__ import annotations

import math
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erre_sandbox.schemas import Position, Zone

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping


WORLD_SIZE_M: Final[float] = 100.0
"""Edge length (metres) of the square BaseTerrain plane.

Raised from 60 m (Slice α) to 100 m in Slice β so zone centroids spread over
a visibly larger area while 3-agent trajectories remain observable from a
single top-down camera preset. All dependent coordinates below derive from
this constant so future scaling is a one-line change.

Keep :data:`WORLD_SIZE_M` in sync with the ``PlaneMesh.size`` in
``godot_project/scenes/zones/BaseTerrain.tscn`` and the top-down camera
``max_distance`` in ``godot_project/scripts/CameraRig.gd``.
"""

_ZONE_OFFSET: Final[float] = WORLD_SIZE_M / 3.0
"""XZ offset of non-central zones from peripatos (world origin).

Non-central zones sit at (±_ZONE_OFFSET, 0, ±_ZONE_OFFSET), giving each zone
a ~_ZONE_OFFSET-radius Voronoi cell inside the terrain bounds. Re-exported by
``world/zones.py`` because ``ZONE_PROPS`` (which stays there) derives its prop
coordinates from it.
"""

ZONE_CENTERS: Final[Mapping[Zone, tuple[float, float, float]]] = MappingProxyType(
    {
        Zone.STUDY: (-_ZONE_OFFSET, 0.0, -_ZONE_OFFSET),
        Zone.PERIPATOS: (0.0, 0.0, 0.0),
        Zone.CHASHITSU: (_ZONE_OFFSET, 0.0, -_ZONE_OFFSET),
        Zone.AGORA: (0.0, 0.0, _ZONE_OFFSET),
        Zone.GARDEN: (_ZONE_OFFSET, 0.0, _ZONE_OFFSET),
    },
)
"""Five zone centroids in world XZ-plane coordinates.

The ``y`` component is kept at 0.0 for the MVP flat-ground assumption; it is
preserved in the tuple so future terrain work can extend the layout without a
breaking change to the shape of this mapping. All non-central centres are
derived from :data:`WORLD_SIZE_M` via :data:`_ZONE_OFFSET`.
"""

CELL_MICRO_RADIUS_M: Final[float] = 10.0
"""Within-zone micro geometry radius for the ECL destination jitter/clamp.

Value-identical to ``evidence.d0_substrate.constants.CELL_MICRO_RADIUS_M`` and
consistent with the live :data:`WORLD_SIZE_M` = 100 m world (both share the
same 100 m plane): the nearest zone-centroid distance is
``_ZONE_OFFSET·sqrt(2) ~= 47.14`` m, so the Voronoi boundary sits ``~23.57`` m
from any centroid and a ``10.0`` m disc stays safely inside the occupied zone's
cell, so :func:`locate_zone` on a jittered ``(x, z)`` agrees with the source
zone. Frozen by this geometric margin (grill G-4 / DA-ECLIMPL-2), never tuned
to pass a gate.
"""


def locate_zone(x: float, y: float, z: float) -> Zone:
    """Return the zone whose centroid is nearest in the XZ plane.

    The ``y`` coordinate is currently ignored but kept in the signature so the
    caller's code does not need to strip it when future terrain support lands.

    Args:
        x: World X coordinate (metres).
        y: World Y coordinate (metres, reserved).
        z: World Z coordinate (metres).

    Returns:
        The :class:`Zone` with minimal Euclidean distance in the XZ plane.
        Ties are broken by the iteration order of :data:`ZONE_CENTERS`
        (``Zone`` enum declaration order: study, peripatos, chashitsu, agora,
        garden), which is deterministic across interpreters.
    """
    del y  # reserved for future vertical layout; see module docstring.
    best_zone: Zone | None = None
    best_d2: float = float("inf")
    for zone, (cx, _cy, cz) in ZONE_CENTERS.items():
        dx = cx - x
        dz = cz - z
        d2 = dx * dx + dz * dz
        if d2 < best_d2:
            best_d2 = d2
            best_zone = zone
    assert best_zone is not None  # ZONE_CENTERS is non-empty by construction
    return best_zone


def default_spawn(zone: Zone) -> Position:
    """Return the centroid of ``zone`` as a :class:`Position` with that zone.

    Used by the runtime to place a freshly registered agent at a sensible
    starting point inside its home zone, and by the ECL organ as the
    history-independent negative-control destination (design-final §論点2/§論点4).
    """
    cx, cy, cz = ZONE_CENTERS[zone]
    return Position(x=cx, y=cy, z=cz, zone=zone)


def disc_jitter(rng: random.Random) -> tuple[float, float]:
    """Area-preserving disc-uniform offset within :data:`CELL_MICRO_RADIUS_M`.

    Design-copied byte-for-byte from the frozen
    ``evidence.d0_substrate.running.policy._disc_jitter`` (polar, area-preserving
    ``r = R·sqrt(u)`` radius draw, ``θ ~ U(0, 2π)``) so the ECL micro-walk stays
    within a ``CELL_MICRO_RADIUS_M``-radius disc rather than a ±radius square
    (whose corners reach ``radius·sqrt(2)``). The frozen module is **not**
    imported (evidence layer is USE-only / mirror-copy; DRY < frozen-immutability).
    """
    r = CELL_MICRO_RADIUS_M * math.sqrt(rng.random())
    theta = rng.uniform(0.0, 2.0 * math.pi)
    return r * math.cos(theta), r * math.sin(theta)


def reflect_clamp(
    dest_x: float, dest_z: float, zone: Zone
) -> tuple[float, float, bool]:
    """Radially clamp a destination back into ``zone``'s Voronoi cell.

    ``dest' = c + (dest − c)·min(1, ρ_max/‖dest − c‖)`` with
    ``ρ_max = CELL_MICRO_RADIUS_M``, fired only when ``locate_zone(dest) != zone``.
    Returns ``(x, z, clamp_fired)``; the clamped point is within ``ρ_max``
    (< half the Voronoi boundary distance), so :func:`locate_zone` agrees with
    ``zone`` afterwards. Design-copied from the frozen
    ``evidence.d0_substrate.running.policy._reflect_clamp`` (not imported).
    """
    if locate_zone(dest_x, 0.0, dest_z) == zone:
        return dest_x, dest_z, False
    cx, _cy, cz = ZONE_CENTERS[zone]
    dx = dest_x - cx
    dz = dest_z - cz
    norm = math.hypot(dx, dz)
    if norm == 0.0:
        return cx, cz, True
    scale = min(1.0, CELL_MICRO_RADIUS_M / norm)
    return cx + dx * scale, cz + dz * scale, True


__all__ = [
    "CELL_MICRO_RADIUS_M",
    "WORLD_SIZE_M",
    "ZONE_CENTERS",
    "default_spawn",
    "disc_jitter",
    "locate_zone",
    "reflect_clamp",
]
