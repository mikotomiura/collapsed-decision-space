"""ERRE-Sandbox: autonomous 3D society from thinkers' cognitive habits.

The main Contract surface is re-exported here so callers can write
``from erre_sandbox import AgentState`` instead of reaching into
``erre_sandbox.schemas``.
"""

from __future__ import annotations

from erre_sandbox.schemas import (
    SCHEMA_VERSION,
    AgentState,
    ControlEnvelope,
    MemoryEntry,
    Observation,
    PersonaSpec,
)

__version__ = "0.0.1"

__all__ = [
    "SCHEMA_VERSION",
    "AgentState",
    "ControlEnvelope",
    "MemoryEntry",
    "Observation",
    "PersonaSpec",
    "__version__",
]
