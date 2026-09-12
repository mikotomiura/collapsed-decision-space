"""Cognition layer — 1-tick CoALA + ERRE pipeline on top of memory + inference.

Public surface:

* :class:`CognitionCycle` / :class:`CycleResult` / :class:`CognitionError` —
  orchestrator
* :class:`LLMPlan` / :func:`parse_llm_plan` — LLM output contract
* :class:`StateUpdateConfig` / :func:`advance_physical` /
  :func:`apply_llm_delta` — pure CSDG half-step math
* :func:`estimate_importance` — event-type-based MVP importance heuristic
* :func:`build_system_prompt` / :func:`build_user_prompt` /
  :func:`format_memories` — pure prompt assembly

Layer dependency (see ``architecture-rules`` skill):

* allowed: ``erre_sandbox.schemas``, ``erre_sandbox.memory``,
  ``erre_sandbox.inference``, same-package siblings
* forbidden: ``world``, ``ui``
"""

from erre_sandbox.cognition.cycle import (
    BiasFiredEvent,
    CognitionCycle,
    CognitionError,
    CycleResult,
)
from erre_sandbox.cognition.importance import estimate_importance
from erre_sandbox.cognition.parse import LLMPlan, parse_llm_plan
from erre_sandbox.cognition.prompting import (
    RESPONSE_SCHEMA_HINT,
    RESPONSE_SCHEMA_HINT_WITH_UPDATE,
    build_system_prompt,
    build_user_prompt,
    format_memories,
    format_world_model_entries,
    visible_entry_citations,
)
from erre_sandbox.cognition.reflection import (
    DEFAULT_REFLECTIVE_ZONES,
    ReflectionPolicy,
    Reflector,
    build_reflection_messages,
)
from erre_sandbox.cognition.state import (
    DEFAULT_CONFIG,
    StateUpdateConfig,
    advance_physical,
    apply_llm_delta,
)
from erre_sandbox.cognition.world_model import (
    WorldModelRuntimeState,
    apply_world_model_update_hint,
    reconcile_world_model,
    synthesize_world_model,
)

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_REFLECTIVE_ZONES",
    "RESPONSE_SCHEMA_HINT",
    "RESPONSE_SCHEMA_HINT_WITH_UPDATE",
    "BiasFiredEvent",
    "CognitionCycle",
    "CognitionError",
    "CycleResult",
    "LLMPlan",
    "ReflectionPolicy",
    "Reflector",
    "StateUpdateConfig",
    "WorldModelRuntimeState",
    "advance_physical",
    "apply_llm_delta",
    "apply_world_model_update_hint",
    "build_reflection_messages",
    "build_system_prompt",
    "build_user_prompt",
    "estimate_importance",
    "format_memories",
    "format_world_model_entries",
    "parse_llm_plan",
    "reconcile_world_model",
    "synthesize_world_model",
    "visible_entry_citations",
]
