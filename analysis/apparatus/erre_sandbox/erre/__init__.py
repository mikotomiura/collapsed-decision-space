"""Event-driven ERRE mode FSM (M5).

Public surface for the concrete :class:`ERREModeTransitionPolicy`
implementation that replaces the static ``_ZONE_TO_DEFAULT_ERRE_MODE`` in
``bootstrap.py`` with observation-driven mode selection. The FSM itself is
synchronous and pure; it is wired into the world tick loop by
``m5-world-zone-triggers`` and into the bootstrap composition root by
``m5-orchestrator-integration``.

Note: this package is the runtime **ERRE cognitive mode** FSM (see
``persona-erre`` skill §ルール 5). The documentation-level concept
**ERRE framework** (Extract / Reverify / Reimplement / Express) is an
unrelated pipeline DSL for persona authoring; if implemented, it should
live in a sibling package like ``erre_pipeline/`` to avoid overloading
this name.
"""

from __future__ import annotations

from erre_sandbox.erre.fsm import (
    SHUHARI_TO_MODE,
    ZONE_TO_DEFAULT_ERRE_MODE,
    DefaultERREModePolicy,
)
from erre_sandbox.erre.locomotion_sampling import locomotion_delta
from erre_sandbox.erre.sampling_table import SAMPLING_DELTA_BY_MODE
from erre_sandbox.erre.two_phase import (
    EVALUATION_MODES,
    GENERATION_MODES,
    TWO_PHASE_GAIN_P,
    TWO_PHASE_GAIN_R,
    TWO_PHASE_GAIN_T,
    TwoPhase,
    TwoPhaseKnob,
    phase_of_mode,
    two_phase_delta,
)

__all__ = [
    "EVALUATION_MODES",
    "GENERATION_MODES",
    "SAMPLING_DELTA_BY_MODE",
    "SHUHARI_TO_MODE",
    "TWO_PHASE_GAIN_P",
    "TWO_PHASE_GAIN_R",
    "TWO_PHASE_GAIN_T",
    "ZONE_TO_DEFAULT_ERRE_MODE",
    "DefaultERREModePolicy",
    "TwoPhase",
    "TwoPhaseKnob",
    "locomotion_delta",
    "phase_of_mode",
    "two_phase_delta",
]
