"""Minimal per-agent kinematics used by the world tick loop (T13).

The ``schemas.Position`` type is the **external** contract (sent to Godot, the
T14 gateway, persistence); it intentionally carries no velocity or movement
target. This module keeps the **internal** mutable state (``destination``,
``speed_mps``) in :class:`Kinematics` so adding or changing fields never
requires a wire-format change.

Movement is modelled as constant-speed linear interpolation in the XZ plane,
mirroring the MASTER-PLAN R8 MVP assumption of "立方体 + 色マテリアル"
avatars without NavMesh. The only non-trivial detail is zone-change
detection: whenever :func:`step_kinematics` returns a new position whose
:func:`locate_zone` differs from the previous one, it also returns the new
zone so the caller can emit a :class:`ZoneTransitionEvent`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from erre_sandbox.schemas import MoveMsg, Position, Zone
from erre_sandbox.world.zones import locate_zone


@dataclass(slots=True)
class Kinematics:
    """Mutable per-agent kinematic state.

    The class is NOT a Pydantic model and NOT part of the public schema: it is
    world-internal bookkeeping, and exists only so the tick loop can update
    ``destination`` (from :class:`MoveMsg`) and walk the agent toward it
    without polluting :class:`AgentState`.
    """

    position: Position
    destination: Position | None = None
    speed_mps: float = 1.3


def step_kinematics(
    kin: Kinematics,
    dt_seconds: float,
) -> tuple[Position, Zone | None]:
    """Advance ``kin`` by ``dt_seconds`` of constant-speed motion.

    The mutation is confined to ``kin.position`` (and, when the agent reaches
    its destination, ``kin.destination`` is cleared). The return value lets
    the caller decide whether to log an :class:`AgentUpdateMsg` and whether
    to emit a :class:`ZoneTransitionEvent`.

    Args:
        kin: The agent's kinematics — updated in place.
        dt_seconds: Wall-clock time that has elapsed since the last step.

    Returns:
        A 2-tuple ``(new_position, zone_changed_to)``. ``zone_changed_to`` is
        ``None`` when the agent stayed in the same zone (or did not move at
        all); otherwise it is the :class:`Zone` the agent has just entered.
    """
    prev_zone = kin.position.zone
    dest = kin.destination

    if dest is None or dt_seconds <= 0.0:
        return kin.position, None

    # Defend against NaN / Inf slipping in from LLM-generated MoveMsg targets:
    # once a non-finite coordinate hits the arithmetic below, Position would
    # carry NaN forever and locate_zone would silently snap to the first zone.
    if not (math.isfinite(dest.x) and math.isfinite(dest.y) and math.isfinite(dest.z)):
        kin.destination = None
        return kin.position, None

    dx = dest.x - kin.position.x
    dz = dest.z - kin.position.z
    remaining = math.hypot(dx, dz)
    travel = kin.speed_mps * dt_seconds

    if remaining <= travel or remaining == 0.0:
        # Snap to destination and clear it so the agent stops. Re-run
        # locate_zone on the dest coordinates so a caller that filled
        # MoveMsg.target with a stale / wrong zone tag cannot poison the
        # subsequent zone-transition detection.
        new_pos = Position(
            x=dest.x,
            y=dest.y,
            z=dest.z,
            zone=locate_zone(dest.x, dest.y, dest.z),
            yaw=dest.yaw,
            pitch=dest.pitch,
        )
        kin.destination = None
    else:
        ratio = travel / remaining
        new_pos = Position(
            x=kin.position.x + dx * ratio,
            y=kin.position.y,
            z=kin.position.z + dz * ratio,
            zone=locate_zone(
                kin.position.x + dx * ratio,
                kin.position.y,
                kin.position.z + dz * ratio,
            ),
            yaw=kin.position.yaw,
            pitch=kin.position.pitch,
        )

    kin.position = new_pos
    zone_changed = new_pos.zone if new_pos.zone is not prev_zone else None
    return new_pos, zone_changed


def apply_move_command(kin: Kinematics, move: MoveMsg) -> None:
    """Update ``kin`` with the target and speed from an inbound :class:`MoveMsg`.

    A zero or negative speed is coerced to :attr:`Kinematics.speed_mps`'s
    default (1.3 m/s, roughly a walking pace) to avoid a stuck-agent hazard;
    the Pydantic validator on :class:`MoveMsg` already forbids negative
    values, so this coercion is defensive.
    """
    kin.destination = move.target
    kin.speed_mps = move.speed if move.speed > 0.0 else 1.3
