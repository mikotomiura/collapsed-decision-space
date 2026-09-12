"""World simulation (tick loop, zones, physics) — depends on ``cognition``.

Public surface for T13:

* Scheduler — :class:`WorldRuntime`, :class:`AgentRuntime`,
  :class:`ScheduledEvent`
* Clock abstraction — :class:`Clock`, :class:`RealClock`, :class:`ManualClock`
* Physics — :class:`Kinematics`, :func:`step_kinematics`,
  :func:`apply_move_command`
* Zones — :data:`WORLD_SIZE_M`, :data:`ZONE_CENTERS`, :data:`ADJACENCY`,
  :func:`locate_zone`, :func:`default_spawn`, :func:`adjacent_zones`

Layer dependency (see ``architecture-rules`` skill):

* allowed: ``erre_sandbox.schemas``, ``erre_sandbox.cognition``,
  same-package siblings
* forbidden: ``erre_sandbox.ui``, ``erre_sandbox.memory``,
  ``erre_sandbox.inference`` (access them indirectly via ``cognition``)
"""

from erre_sandbox.world.physics import (
    Kinematics,
    apply_move_command,
    step_kinematics,
)
from erre_sandbox.world.tick import (
    AgentRuntime,
    Clock,
    ManualClock,
    RealClock,
    ScheduledEvent,
    WorldRuntime,
)
from erre_sandbox.world.zones import (
    ADJACENCY,
    WORLD_SIZE_M,
    ZONE_CENTERS,
    adjacent_zones,
    default_spawn,
    locate_zone,
)

__all__ = [
    "ADJACENCY",
    "WORLD_SIZE_M",
    "ZONE_CENTERS",
    "AgentRuntime",
    "Clock",
    "Kinematics",
    "ManualClock",
    "RealClock",
    "ScheduledEvent",
    "WorldRuntime",
    "adjacent_zones",
    "apply_move_command",
    "default_spawn",
    "locate_zone",
    "step_kinematics",
]
