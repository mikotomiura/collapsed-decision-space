"""Integration contract for T14 gateway + T19/T20 — depends on ``schemas`` only.

This module is the **contract boundary** between:

* the simulation/inference side (``world``, ``cognition``, ``memory``,
  ``inference`` modules), which **produces**
  :class:`~erre_sandbox.schemas.ControlEnvelope` messages and acts on
  :class:`~erre_sandbox.schemas.Observation` events;
* the T14 gateway (WebSocket server) and its downstream consumers (Godot
  viewer, future monitor dashboards), which **consume** the envelopes.

The on-wire message types themselves live in :mod:`erre_sandbox.schemas` §7
(``HandshakeMsg``, ``AgentUpdateMsg``, ``SpeechMsg``, ``MoveMsg``,
``AnimationMsg``, ``WorldTickMsg``, ``ErrorMsg``, aggregated as
``ControlEnvelope``). This module owns the **operational** augmentations:

* :mod:`.protocol` — session lifecycle constants + :class:`SessionPhase` enum
* :mod:`.scenarios` — frozen :class:`Scenario` tuples for M2 E2E tests
* :mod:`.metrics` — :class:`Thresholds` Pydantic model + ``M2_THRESHOLDS`` instance
* :mod:`.acceptance` — :class:`AcceptanceItem` dataclass + ``ACCEPTANCE_CHECKLIST``

Layer dependency (see ``architecture-rules`` skill + decisions.md D2):

* allowed: :mod:`erre_sandbox.schemas`, ``pydantic``
* forbidden: ``inference``, ``memory``, ``cognition``, ``world``, ``ui``

The T14 ``gateway`` submodule added later may import from ``world`` /
``cognition`` / ``memory`` — that extension is scoped to ``gateway.py`` and
is explicitly called out when it lands.
"""

from erre_sandbox.integration.acceptance import ACCEPTANCE_CHECKLIST, AcceptanceItem
from erre_sandbox.integration.dialog import AgentView, InMemoryDialogScheduler
from erre_sandbox.integration.gateway import Registry, make_app
from erre_sandbox.integration.metrics import M2_THRESHOLDS, Thresholds
from erre_sandbox.integration.protocol import (
    HANDSHAKE_TIMEOUT_S,
    HEARTBEAT_INTERVAL_S,
    IDLE_DISCONNECT_S,
    MAX_ENVELOPE_BACKLOG,
    SCHEMA_VERSION_HEADER,
    SessionPhase,
)
from erre_sandbox.integration.scenarios import (
    M2_SCENARIOS,
    SCENARIO_MEMORY_WRITE,
    SCENARIO_TICK_ROBUSTNESS,
    SCENARIO_WALKING,
    Scenario,
    ScenarioStep,
)

__all__ = [
    "ACCEPTANCE_CHECKLIST",
    "HANDSHAKE_TIMEOUT_S",
    "HEARTBEAT_INTERVAL_S",
    "IDLE_DISCONNECT_S",
    "M2_SCENARIOS",
    "M2_THRESHOLDS",
    "MAX_ENVELOPE_BACKLOG",
    "SCENARIO_MEMORY_WRITE",
    "SCENARIO_TICK_ROBUSTNESS",
    "SCENARIO_WALKING",
    "SCHEMA_VERSION_HEADER",
    "AcceptanceItem",
    "AgentView",
    "InMemoryDialogScheduler",
    "Registry",
    "Scenario",
    "ScenarioStep",
    "SessionPhase",
    "Thresholds",
    "make_app",
]
