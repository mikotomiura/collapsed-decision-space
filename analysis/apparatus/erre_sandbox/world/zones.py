"""Static spatial representation of the five world zones (T13).

Zones are modelled as **Voronoi-lite partitions** around five centroids in the
XZ plane: any ``(x, y, z)`` point is assigned to the zone whose centroid is
nearest in the XZ plane, which means :func:`locate_zone` never raises and
every world coordinate has a well-defined zone. A rectangular AABB layout was
considered in ``design-v1.md`` but rejected because it leaves "outside any
zone" gaps whose handling adds branches without buying expressive power at
the MVP stage (no walls, no NavMesh — see MASTER-PLAN R8).

The module is pure: no logging, no I/O, no mutable state. The only exported
constants (:data:`ZONE_CENTERS`, :data:`ADJACENCY`, :data:`ZONE_PROPS`) are
wrapped in :class:`types.MappingProxyType` so callers cannot silently mutate
the layout.

**M13 ECL v0 relocation (DA-ECLIMPL-1 / Codex LOW-1)**: the pure geometry SSOT
(:data:`WORLD_SIZE_M`, :data:`ZONE_CENTERS`, :func:`locate_zone`,
:func:`default_spawn`, plus the ECL micro geometry) was relocated to
:mod:`erre_sandbox.contracts.geometry` so the ``cognition`` layer can resolve
history-dependent destinations without importing ``world`` (architecture-rules
dependency direction). This module re-exports them as a shim so every existing
``from erre_sandbox.world.zones import ...`` keeps working — the same discipline
as ``contracts.thresholds`` re-exporting ``M2_THRESHOLDS``. ``ZONE_PROPS`` and
:data:`ADJACENCY` stay here (Godot hard-coded sync note / world-walk use).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple

from erre_sandbox.contracts.geometry import (
    _ZONE_OFFSET,
    WORLD_SIZE_M,
    ZONE_CENTERS,
    default_spawn,
    locate_zone,
)
from erre_sandbox.schemas import Zone

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ADJACENCY",
    "WORLD_SIZE_M",
    "ZONE_CENTERS",
    "ZONE_PROPS",
    "PropSpec",
    "adjacent_zones",
    "default_spawn",
    "locate_zone",
]


class PropSpec(NamedTuple):
    """Static world prop that emits :class:`AffordanceEvent` on agent proximity.

    Fields mirror :class:`AffordanceEvent` so the firing path in
    :mod:`erre_sandbox.world.tick` can translate 1:1 without re-mapping.
    Positions are in world XZ-plane coordinates at a fixed ``y`` (the prop
    height doesn't affect the current 2D affordance-radius check but is
    preserved for Godot scene wiring).
    """

    prop_id: str
    prop_kind: str
    x: float
    y: float
    z: float
    salience: float = 0.5


ZONE_PROPS: Final[Mapping[Zone, tuple[PropSpec, ...]]] = MappingProxyType(
    {
        Zone.CHASHITSU: (
            PropSpec(
                prop_id="chawan_01",
                prop_kind="tea_bowl",
                x=_ZONE_OFFSET - 0.5,
                y=0.4,
                z=-_ZONE_OFFSET + 0.5,
                salience=0.7,
            ),
            PropSpec(
                prop_id="chawan_02",
                prop_kind="tea_bowl",
                x=_ZONE_OFFSET + 0.5,
                y=0.4,
                z=-_ZONE_OFFSET - 0.5,
                salience=0.6,
            ),
        ),
        Zone.STUDY: (),
        Zone.PERIPATOS: (),
        Zone.AGORA: (),
        Zone.GARDEN: (),
    },
)
"""Zone-indexed prop tables driving :class:`AffordanceEvent` firing (M7 B1).

MVP scope: chashitsu carries two ``tea_bowl`` props; the other four zones
start empty. Adding props for a new zone is a pure data change — the firing
loop in :mod:`erre_sandbox.world.tick` iterates over every entry and emits
an affordance event to agents within
:data:`erre_sandbox.world.tick._AFFORDANCE_RADIUS_M`.

Keep this table in sync with the Godot scene files under
``godot_project/scenes/zones/`` — the GDScript ``BoundaryLayer`` uses the
same coordinates hard-coded until the schema wiring lands in the next PR.
"""

ADJACENCY: Final[Mapping[Zone, frozenset[Zone]]] = MappingProxyType(
    {
        Zone.STUDY: frozenset({Zone.PERIPATOS}),
        Zone.PERIPATOS: frozenset(
            {Zone.STUDY, Zone.CHASHITSU, Zone.AGORA, Zone.GARDEN},
        ),
        Zone.CHASHITSU: frozenset({Zone.PERIPATOS, Zone.GARDEN}),
        Zone.AGORA: frozenset({Zone.PERIPATOS, Zone.GARDEN}),
        Zone.GARDEN: frozenset({Zone.PERIPATOS, Zone.CHASHITSU, Zone.AGORA}),
    },
)
"""Walkable adjacency graph between zones (symmetric, anchored at peripatos)."""


def adjacent_zones(zone: Zone) -> frozenset[Zone]:
    """Return the set of zones directly walkable from ``zone`` (excludes self)."""
    return ADJACENCY[zone]
