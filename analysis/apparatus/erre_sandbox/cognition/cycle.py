"""One-tick CoALA + ERRE cognition pipeline (T12, MVP M2).

The :class:`CognitionCycle` class orchestrates the 9 micro-steps that turn
``(AgentState, Observation[]) -> (AgentState', ControlEnvelope[])`` for a
single 10-second tick of a single agent. It deliberately keeps all numeric
math in :mod:`cognition.state`, all string building in
:mod:`cognition.prompting`, and all LLM-output decoding in
:mod:`cognition.parse` so this module reads as an integration recipe.

Scope boundary:

* **In**: one agent, one tick, write observations as Episodic memory,
  CSDG Physical update, **ERRE mode FSM transition (M5)**, retrieve
  memories, call LLM, parse the plan, compose Cognitive update, emit
  ``AgentUpdate`` / ``Move`` / ``Speech`` / ``Animation`` envelopes.
* **Out**: PIANO parallelism (M4+), multi-agent ``asyncio.gather`` (T13),
  30Hz tick loop (T13), WebSocket transport (T14).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from random import Random
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from erre_sandbox.cognition.development import (
    DevelopmentEvidence,
    belief_signature,
    maybe_advance_development,
)

# ``resolve_destination`` is called at runtime; ``EclDestination`` is a Pydantic field
# annotation on ``CycleResult`` below, so it must be importable at runtime too (Pydantic
# resolves it at model-build time).
from erre_sandbox.cognition.embodiment import EclDestination, resolve_destination
from erre_sandbox.cognition.hint_engagement import (
    LLM_STATUS_UNAVAILABLE,
    LLM_STATUS_UNPARSEABLE,
    build_emitted_disposition,
    build_not_emitted_disposition,
)
from erre_sandbox.cognition.importance import estimate_importance
from erre_sandbox.cognition.narrative import (
    compute_coherence,
    render_swm_for_embedding,
    synthesize_narrative_arc,
)
from erre_sandbox.cognition.parse import parse_llm_plan
from erre_sandbox.cognition.prompting import (
    build_system_prompt,
    build_user_prompt,
    visible_entry_citations,
)
from erre_sandbox.cognition.reflection import Reflector
from erre_sandbox.cognition.state import (
    DEFAULT_CONFIG,
    StateUpdateConfig,
    advance_physical,
    apply_llm_delta,
)
from erre_sandbox.cognition.world_model import (
    WorldModelRuntimeState,
    apply_world_model_update_hint,
    collect_promoted_evidence_units,
    project_world_model_snapshot,
    reconcile_world_model,
    synthesize_world_model,
)

# NarrativeArc / DevelopmentState / PromotedEvidenceUnit / WorldModelSnapshot are
# Pydantic field annotations on ``CycleResult`` below (and ``DevelopmentState`` is
# also constructed at runtime), so they must be importable at runtime (Pydantic
# resolves them at model-build time).
from erre_sandbox.contracts.cognition_layers import (
    DevelopmentState,
    NarrativeArc,
    PromotedEvidenceUnit,
    WorldModelHintDisposition,
    WorldModelSnapshot,
)
from erre_sandbox.erre import SAMPLING_DELTA_BY_MODE
from erre_sandbox.erre.locomotion_sampling import (
    DEFAULT_LOCO_ALPHA,
    DEFAULT_LOCO_GAIN_P,
    DEFAULT_LOCO_GAIN_T,
    advance_lambda,
    locomotion_delta,
)
from erre_sandbox.erre.two_phase import (
    TWO_PHASE_GAIN_P,
    TWO_PHASE_GAIN_R,
    TWO_PHASE_GAIN_T,
    phase_of_mode,
    two_phase_delta,
)
from erre_sandbox.inference import (
    ChatMessage,
    OllamaChatClient,
    OllamaUnavailableError,
    compose_sampling,
)
from erre_sandbox.memory import EmbeddingClient, EmbeddingUnavailableError
from erre_sandbox.schemas import (
    AffordanceEvent,
    AgentState,
    AgentUpdateMsg,
    AnimationMsg,
    BiorhythmEvent,
    Cognitive,
    ControlEnvelope,
    DialogTurnMsg,
    ERREMode,
    ERREModeShiftEvent,
    ERREModeTransitionPolicy,
    InternalEvent,
    LocomotionState,
    MemoryEntry,
    MemoryKind,
    MoveMsg,
    Observation,
    Physical,
    ProximityEvent,
    ReasoningTrace,
    ReasoningTraceMsg,
    ReflectionEvent,
    ReflectionEventMsg,
    SpatialContext,
    SpeechMsg,
    TriggerEventTag,
    Zone,
    ZoneTransitionEvent,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from erre_sandbox.cognition.embodiment import EclRecordMode
    from erre_sandbox.cognition.parse import LLMPlan
    from erre_sandbox.contracts.cognition_layers import (
        IndividualLayerConfig,
        SubjectiveWorldModel,
        WorldModelEntry,
    )
    from erre_sandbox.erre.two_phase import TwoPhaseKnob
    from erre_sandbox.memory import MemoryStore, RankedMemory, Retriever
    from erre_sandbox.schemas import (
        ERREModeName,
        PersonaSpec,
        Position,
        SamplingDelta,
        SemanticMemoryRecord,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BiasFiredEvent:
    """Structured record of one ``_bias_target_zone`` firing.

    Emitted by :func:`_bias_target_zone` via an optional sink when the helper
    actually replaces the LLM-chosen ``destination_zone`` with a persona
    preferred zone. Process-internal (not a wire envelope) — consumers are
    expected to persist or aggregate in-process (see bootstrap's
    ``_persist_bias_event`` closure for the canonical downstream).

    ``from_zone`` / ``to_zone`` carry the :class:`~erre_sandbox.schemas.Zone`
    enum values (``.value`` strings) so sinks can persist without re-importing
    the enum.
    """

    tick: int
    agent_id: str
    from_zone: str
    to_zone: str
    bias_p: float


def _advance_locomotion(
    locomotion: LocomotionState | None,
    *,
    destination_zone: Zone | None,
    current_zone: Zone,
) -> LocomotionState | None:
    """Advance the M13-ES3 locomotion intensity λ by this tick's movement.

    ``move_t`` = 1 when the agent commits to a zone change this tick (a MoveMsg
    to a different zone is emitted), else 0; λ follows the frozen EMA
    ``(1-α)·λ + α·move_t``. Returns the locomotion state with the updated λ, or
    ``None`` when the agent has no locomotion channel — keeping the pre-ES3
    behaviour bit-identical and the apparatus (``evidence.es3_locomotion``)
    independent of this live wiring.
    """
    if locomotion is None:
        return None
    move_t = int(destination_zone is not None and destination_zone != current_zone)
    return locomotion.model_copy(
        update={"lam": advance_lambda(locomotion.lam, move_t, DEFAULT_LOCO_ALPHA)},
    )


_REFLECTION_ZONES: Final[frozenset[Zone]] = frozenset({Zone.PERIPATOS, Zone.CHASHITSU})

_ECL_FORAGE_QUERY: Final[str] = "ecl v0 forage prompt"
"""Deterministic, zone-vocabulary-free forage query for the ECL move channel.

Mirrors the frozen ``running/policy.py`` ``_FORAGE_QUERY`` idiom (design §論点2): the
resolver's ranking is decided by the memories' spatial term, not this text, so the
query is a fixed constant — never a tune-to-pass knob. Passed to
:func:`~erre_sandbox.cognition.embodiment.resolve_destination` only on ECL record-mode
ticks; the flag-off live path never reads it."""

_PEER_TURNS_LIMIT: Final[int] = 3
"""Cap on peer-persona dialog turns surfaced to reflection (M7γ D1).

Three is the same shoulder used elsewhere in the prompt builder for
"recent X" sections — large enough to hint at conversational dynamics,
small enough that the prompt stays under the working-context budget.
"""

_TRACE_OBSERVED_OBJECTS_LIMIT: Final[int] = 3
"""Cap on :attr:`ReasoningTrace.observed_objects` (M7γ D3).

Top-3 by :attr:`AffordanceEvent.salience`; ties resolved by stable sort
order (insertion order from the observation stream)."""

_TRACE_NEARBY_AGENTS_LIMIT: Final[int] = 2
"""Cap on :attr:`ReasoningTrace.nearby_agents` (M7γ D3).

Two is the typical PIANO co-walking pair size; agents in larger crowds
will report the two who most recently entered proximity rather than a
saturated list."""

_TRACE_RETRIEVED_MEMORIES_LIMIT: Final[int] = 3
"""Cap on :attr:`ReasoningTrace.retrieved_memories` (M7γ D3).

Mirrors the retriever's typical top-k (per-agent + per-world) so the
xAI panel never exceeds three citation chips per tick."""


_BIORHYTHM_THRESHOLD: Final[float] = 0.5
"""Mid-level threshold for fatigue / hunger that drives
:class:`~erre_sandbox.schemas.BiorhythmEvent` emission (M6-A-2b).

Chosen as a single mid-band boundary rather than a multi-level
(low/mid/high) scheme so the LLM sees at most one biorhythm event per
signal per tick. Multi-level crossings would require dedup logic and
would pull agents out of their current mode on every small fluctuation,
which contradicts the ERRE "意図的非効率性" principle. If an agent's
personality demands a finer granularity, extend this to a per-persona
threshold via :class:`~erre_sandbox.schemas.PersonaSpec`.
"""


class CycleResult(BaseModel):
    """Outcome of one :meth:`CognitionCycle.step` call.

    ``llm_fell_back`` is the explicit flag the T14 gateway will surface as a
    metric — without it, callers would have to diff ``envelopes`` to infer
    whether the agent "decided to do nothing" vs "the LLM was unreachable".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_state: AgentState
    envelopes: list[ControlEnvelope] = Field(default_factory=list)
    new_memory_ids: list[str] = Field(default_factory=list)
    reflection_triggered: bool = False
    llm_fell_back: bool = False
    reflection_event: ReflectionEvent | None = None
    """Produced reflection, if any. ``None`` means the policy declined *or*
    the distillation path failed (LLM / embedding outage) — the
    ``reflection_triggered`` flag distinguishes the two."""
    follow_up_observations: list[Observation] = Field(default_factory=list)
    """Observations deferred to the next tick (M6-A-2b).

    Stress :class:`~erre_sandbox.schemas.BiorhythmEvent` crossings are the
    only current consumer: they are detected in Step 8 **after** the LLM's
    delta has already been applied, so there is no way to feed them into
    the current prompt. The caller (:meth:`WorldRuntime._consume_result`)
    appends this list to the agent's ``pending`` buffer so the next tick's
    observation stream surfaces the signal one tick late — the intended
    semantics for a post-LLM-derived readout."""
    world_model_runtime: WorldModelRuntimeState | None = None
    """Carried-out individual-layer world-model state (M10-C, flag-on only).

    ``None`` on every flag-off tick (the layer is inert). When the individual
    layer is enabled this is the reconciled SWM **plus** any adopted
    :class:`WorldModelUpdateHint` nudge; the caller
    (:meth:`WorldRuntime._consume_result`) writes it back to ``AgentRuntime`` so
    the next tick reconciles against it. On a flag-on LLM/parse fallback it is
    the pre-LLM reconciled state, so a transient outage cannot wipe an agent's
    accumulated modulations (DA-M10C-7)."""
    narrative_arc: NarrativeArc | None = None
    """Diagnostic narrative arc distilled this tick (M11-A, flag-on only).

    ``None`` flag-off, and also on any flag-on tick that could not synthesise an
    honest arc (silent turn, empty SWM, no episodic pointer, embedding outage).
    The caller (:meth:`WorldRuntime._consume_result`) writes a non-``None`` arc
    back to ``AgentRuntime`` and leaves a stale one untouched on ``None`` so the
    last good arc carries forward (DA-M11A-7). Diagnostic only — it never drives
    a state transition / sampling / drift (diagnostic ⊥ control)."""
    development_state: DevelopmentState | None = None
    """Evidence-driven development stage advanced this tick (M11-B, flag-on only).

    ``None`` flag-off, and also on any flag-on tick without a fresh narrative arc
    (silent / outage / no-episodic-pointer) — those are non-observations, not
    transitions. On a fresh-evidence tick this is the updated
    :class:`DevelopmentState` from :func:`maybe_advance_development`. The caller
    (:meth:`WorldRuntime._consume_result`) writes a non-``None`` state back to
    ``AgentRuntime`` and leaves the prior one untouched on ``None`` (carry-forward,
    mirroring ``narrative_arc``). Unlike ``narrative_arc`` this *is* control — but
    it is driven only by LLM-independent observables (DA-M11B-1)."""
    world_model_evidence: list[PromotedEvidenceUnit] | None = None
    """Per-dyad raw promoted evidence units this tick (M10-A 段B, flag-on only).

    ``None`` flag-off (the individual layer is inert and beliefs are never read).
    Flag-on this is the matched ``(record, bond)`` evidence projected by
    :func:`~erre_sandbox.cognition.world_model.collect_promoted_evidence_units` —
    the *same* dyads ``synthesize_world_model`` derived this tick's SWM entries
    from — so it may be an empty list when no dyad is promoted yet. Sourced here in
    the cycle's async block (the beliefs are already read for the SWM floor) and
    carried out so the trace sink in ``world`` never imports ``memory`` (DA-M11C2-2
    / DA-SB-1), mirroring ``belief_classes``. The caller
    (:meth:`WorldRuntime._consume_result`) writes it to ``individual_state_trace``
    as ``world_model_evidence_json``; the loader reads it back as the H2
    value-aware conformance substrate (stage-A ADR §6). Substrate only — it never
    drives control, and the H2 gate verdict itself is a separate task."""
    belief_classes: list[str] | None = None
    """Promoted-belief class labels this individual holds this tick (M11-C2,
    flag-on only).

    ``None`` flag-off (the individual layer is inert and beliefs are never read).
    Flag-on this is the full promoted-belief set — every ``belief_kind`` from
    :meth:`MemoryStore.list_semantic_beliefs` for the agent — so it may be an
    empty list when the agent has promoted no beliefs yet (DA-M11C2-3, "whole
    promoted set" semantics). Sourced here in the cycle's async context rather
    than in :mod:`world` so the trace sink never imports :mod:`memory` directly
    (the ``world → memory`` dependency is forbidden). The caller
    (:meth:`WorldRuntime._consume_result`) writes it to ``individual_state_trace``
    as ``belief_classes_json``; the loader expands it for ``belief_variance``.
    Class-wise, not dyadic; the weighting unit is the belief, not the tick.
    Diagnostic substrate — it never drives control."""
    world_model_saturation: WorldModelSnapshot | None = None
    """Post-reconcile, **pre-nudge** SWM snapshot for the saturation probe
    (saturation ADR section 2.1 / 5, flag-on only).

    ``None`` flag-off. Flag-on this is ``project_world_model_snapshot(reconciled)``
    captured **immediately after** :func:`reconcile_world_model` and **before** any
    adopted :class:`WorldModelUpdateHint` nudge — so the modulated values it carries
    are cap-re-clamped (``floor +/- MAX_TOTAL_MODULATION``), unlike the post-hint
    carry-out on ``world_model_runtime`` which can transiently sit one step past the
    cap. The saturation trace must observe this pre-nudge view or it would
    over-estimate cap occupancy (DA-IMPL-1 / saturation ADR section 2.1). Deep-copied
    by ``project_world_model_snapshot`` so it never aliases the reconcile state.
    The caller (:meth:`WorldRuntime._emit_saturation_trace`) explodes it into
    ``swm_modulation_saturation_trace`` rows. Substrate only — never drives control."""
    world_model_hint_engagement: WorldModelHintDisposition | None = None
    """This tick's world-model update-hint disposition (engagement instrument ADR §3,
    flag-on only).

    ``None`` flag-off. Flag-on this is the :class:`WorldModelHintDisposition` built in
    step 7.5 (or on a fallback tick, as ``not_emitted`` with a non-``ok``
    ``llm_status`` — Codex HIGH-1, recorded as provenance so an outage is a known tick,
    not a silent gap; the loader excludes non-``ok`` ticks from the eligible
    population). The
    ``adopted`` headline reads the authority's real ``apply_world_model_update_hint``
    return; only the reject reason is the shadow classifier's. The caller
    (:meth:`WorldRuntime._emit_hint_engagement_trace`) writes it to
    ``swm_hint_engagement_trace``. Substrate only — never drives control."""
    ecl_destination: EclDestination | None = None
    """This tick's resolved ECL move-decision provenance (Issue 003, record-mode only).

    ``None`` on every flag-off tick (``ecl_mode is None``) **and** on any record-mode
    tick whose plan does not move (``destination_zone is None``). When present it is the
    :class:`~erre_sandbox.cognition.embodiment.EclDestination` returned by
    :func:`~erre_sandbox.cognition.embodiment.resolve_destination` — the candidate
    selection trail (``centroid`` / ``provenance`` memory ids / ``jitter`` /
    ``pre_clamp`` / ``post_clamp`` / ``resolved_from``) behind the emitted MoveMsg
    target. Surfaced here so the I4 construction harness assembles Plane 1 at the
    ``agent_tick`` axis from the logged transform inputs — never an absolute-target
    replay — so the continuity gate's causal ablation actually bites (design §論点3/
    §論点4). Provenance only; it never drives control."""


class CognitionError(RuntimeError):
    """Unexpected error inside the cycle that is NOT a recoverable outage.

    Raised (not caught) when the failure is bug-shaped — e.g. an
    ``AttributeError`` from a malformed ``Observation`` — so we don't
    silently fall back and hide the defect. See error-handling skill §ルール 5.
    """


class CognitionCycle:
    """Stateful orchestrator for a single agent's cognition loop.

    Hold one instance per agent in M4+ multi-agent runs. The store /
    embedding / llm / retriever dependencies are safe to share across
    instances (they carry their own clients or are stateless).
    """

    DEFAULT_DESTINATION_SPEED: ClassVar[float] = 1.3
    REFLECTION_IMPORTANCE_THRESHOLD: ClassVar[float] = 1.5
    """Sum-of-importances over the tick that triggers a reflection window.

    The 150 value quoted in ``docs/functional-design.md`` §2 applies to the
    long-horizon accumulator that M4 reflection will maintain. Per-tick we
    use a much smaller threshold (≈ 3 high-importance events) so the MVP
    can demonstrate the trigger path.
    """

    DEFAULT_TICK_SECONDS: ClassVar[float] = 10.0

    LOW_COHERENCE_THRESHOLD: ClassVar[float] = 0.0
    """Coherence below which M11-A adds one reflection-deepening signal.

    ``0.0`` = fire only when the utterance is *clearly opposite* (negative
    cosine) to the held world model. Deliberately conservative: M11-A measures
    the false-positive rate of this diagnostic; a positive hard-gate threshold is
    deferred to M11-B (design-final §6, DA-M11A-8). Document/document embeddings
    cluster positive, so production firing is expected to be near-zero until then.
    """

    def __init__(
        self,
        *,
        retriever: Retriever,
        store: MemoryStore,
        embedding: EmbeddingClient,
        llm: OllamaChatClient,
        rng: Random | None = None,
        update_config: StateUpdateConfig | None = None,
        reflector: Reflector | None = None,
        erre_policy: ERREModeTransitionPolicy | None = None,
        erre_sampling_deltas: Mapping[ERREModeName, SamplingDelta] | None = None,
        bias_sink: Callable[[BiasFiredEvent], None] | None = None,
        individual_layer: IndividualLayerConfig | None = None,
        ecl_mode: EclRecordMode | None = None,
        two_phase_knob: TwoPhaseKnob | None = None,
    ) -> None:
        self._retriever = retriever
        self._store = store
        self._embedding = embedding
        self._llm = llm
        self._rng = rng
        self._update_config = update_config or DEFAULT_CONFIG
        # Default reflector uses the same infra as the cycle. Injecting an
        # explicit instance is the supported extension point for tests and
        # for multi-agent orchestration (#6) that want to share a single
        # policy across all agents.
        self._reflector = reflector or Reflector(
            store=store,
            embedding=embedding,
            llm=llm,
        )
        # Optional ERRE mode FSM (M5 `m5-world-zone-triggers`). When None
        # (default) the cycle preserves pre-M5 behaviour: ``agent_state.erre``
        # is only set at boot and never changes thereafter. Wiring the
        # concrete :class:`~erre_sandbox.erre.DefaultERREModePolicy` is the
        # responsibility of ``m5-orchestrator-integration``.
        self._erre_policy = erre_policy
        # Override the per-mode sampling delta table. Defaults to the
        # production :data:`SAMPLING_DELTA_BY_MODE`. Tests may inject a
        # custom mapping (e.g. all-zero deltas) to isolate FSM-transition
        # behaviour from the production table without monkey-patching the
        # module constant. ``is not None`` rather than ``or`` so an
        # explicitly-empty mapping does not silently fall back to production.
        self._erre_sampling_deltas = (
            erre_sampling_deltas
            if erre_sampling_deltas is not None
            else SAMPLING_DELTA_BY_MODE
        )
        # Slice β: probability that a destination_zone landing outside the
        # persona's preferred_zones is resampled toward the preferred list.
        # Read once at construction — per-tick env reads would obscure the
        # experiment's knob and violate the "cognition has no env
        # dependencies" invariant the rest of this module relies on. Tune
        # via ``ERRE_ZONE_BIAS_P`` between runs.
        self._zone_bias_p = float(os.environ.get("ERRE_ZONE_BIAS_P", "0.2"))
        # Bias uses a persistent RNG (shared with ``self._rng`` when one is
        # injected, otherwise its own ``Random()`` so consecutive ticks draw
        # from a coherent sequence rather than fresh entropy per step).
        # Separate field from ``self._rng`` so the ``apply_llm_delta`` noise
        # contract ("no rng → deterministic") stays intact for callers that
        # deliberately pass ``None``.
        self._bias_rng = rng or Random()  # noqa: S311 — non-crypto bias nudge
        # M8 baseline-quality-metric: optional sink receiving one
        # :class:`BiasFiredEvent` per firing. None in unit tests and the
        # pre-M8 bootstrap; the production bootstrap wires it to a closure
        # that persists events via ``MemoryStore.add_bias_event_sync``
        # (see decisions D2/D5).
        self._bias_sink = bias_sink
        # M10-B individual layer toggle. ``None`` / ``enabled=False`` keeps the
        # cycle on the pre-M10-B path (no SWM synthesis, byte-identical prompts);
        # only when enabled does ``step`` distil a read-only SubjectiveWorldModel
        # and inject its bounded top-K into the USER prompt (DA-M10B-5). Follows
        # the same optional-collaborator idiom as ``erre_policy`` / ``reflector``.
        self._individual_layer = individual_layer
        # ECL v0 record mode (Issue 003). ``None`` (default) keeps the cycle on the
        # byte-identical live path: no history-dependent move resolution, ``uuid4`` /
        # wall-clock memory formation, wall-clock envelope ``sent_at``, and the
        # reflection LLM enabled. Only when a construction driver injects an
        # :class:`~erre_sandbox.cognition.embodiment.EclRecordMode` does ``step`` pin
        # Plane 1 and route the MoveMsg target through ``resolve_destination`` (design
        # §論点1/§論点3). Same optional-collaborator idiom as ``erre_policy`` /
        # ``individual_layer``.
        self._ecl_mode = ecl_mode
        # aha!/DMN-ECN Phase 4 (construction-only) two-phase locomotion knob.
        # ``None`` (default) keeps the frozen ES-3 ``locomotion_delta`` path so
        # every existing sealed golden stays byte-identical; an injected
        # :class:`~erre_sandbox.erre.two_phase.TwoPhaseKnob` makes the locomotion
        # sampling term phase-signed (see :meth:`_locomotion_delta_for`). Same
        # presence-gated optional-collaborator idiom as ``ecl_mode`` /
        # ``individual_layer``. Boolean causal-wiring only — measurement 非 authorize.
        self._two_phase_knob = two_phase_knob

    async def step(  # noqa: PLR0915 — central cognition orchestrator; +1 stmt for the saturation snapshot capture (ADR section 2.1)
        self,
        agent_state: AgentState,
        persona: PersonaSpec,
        observations: Sequence[Observation],
        *,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
        world_model_runtime: WorldModelRuntimeState | None = None,
        development_state: DevelopmentState | None = None,
        self_other_context: str | None = None,
    ) -> CycleResult:
        """Run the 9-step cognition pipeline for one tick.

        ``tick_seconds`` is accepted for symmetry with T13 (which may pass a
        measured wall-clock delta) but is not yet consumed by the MVP math —
        :mod:`cognition.state` expects a fixed tick. It is deliberately left
        in the signature so T13 doesn't have to reshape the call.

        ``world_model_runtime`` (M10-C, flag-on only) is the agent's carried
        world-model state from the previous tick, owned by ``AgentRuntime``.
        ``None`` on every flag-off tick. When the individual layer is enabled it
        is reconciled against this tick's fresh evidence floor and returned on
        :attr:`CycleResult.world_model_runtime` for write-back.

        ``development_state`` (M11-B, flag-on only) is the agent's carried
        :class:`DevelopmentState`, likewise owned by ``AgentRuntime`` and ``None``
        flag-off. On a fresh-evidence tick it is folded with this tick's
        LLM-independent evidence by :func:`maybe_advance_development` and returned
        on :attr:`CycleResult.development_state` for write-back.

        ``self_other_context`` (M2 Layer2 mirror-sim, transient) is a pre-rendered
        bounded SimToM segment (the deterministic render of *other* agents'
        prior-window observed behaviour, built by
        :func:`~erre_sandbox.integration.embodied.society.build_self_other_context`).
        ``None`` (the default, and every live / non-Layer2 caller) threads through
        as ``""`` to :func:`~erre_sandbox.cognition.prompting.build_user_prompt`,
        keeping the prompt byte-identical. When present it is injected into the
        **user** prompt only and — crucially — is **never written to episodic
        memory** (it does not pass through Step 1's ``_write_observations``): the
        mirror-sim circularity guard (design-final.md §L6) keeps the observed
        input stream disjoint from the memory sink. NOT a structural-floor
        verdict; verdict は holding.
        """
        _ = tick_seconds  # reserved for T13, intentionally unused here

        # Step 1: write observations as Episodic memories. ``agent_tick`` / ``here``
        # are consumed only on an ECL record-mode tick (deterministic id + tick-derived
        # ``created_at`` + a formation ``location`` at the agent's current place, Codex
        # HIGH-2); the flag-off path ignores them and stays byte-identical.
        new_memory_ids = await self._write_observations(
            observations,
            agent_id=agent_state.agent_id,
            agent_tick=agent_state.tick,
            here=agent_state.position,
        )

        # Step 2: update Physical (pure, CSDG half-step).
        new_physical = advance_physical(
            agent_state.physical,
            observations,
            config=self._update_config,
            rng=self._rng,
        )

        # Step 2.25 (M6-A-2b): detect biorhythm threshold crossings. Emitted
        # BEFORE the FSM / retrieve / LLM so the mode policy can react to the
        # crossing and the LLM prompt can surface "I got tired" to the agent
        # narrating in first person. Stress crossings live in Cognitive and
        # are deferred — Cognitive is assembled post-LLM (Step 8), so stress
        # biorhythm would arrive a tick late and is not wired here.
        biorhythm_events = _detect_biorhythm_crossings(
            previous=agent_state.physical,
            current=new_physical,
            agent_id=agent_state.agent_id,
            tick=agent_state.tick,
        )
        if biorhythm_events:
            observations = [*observations, *biorhythm_events]

        # Step 2.5 (M5): ERRE mode FSM transition.
        #
        # Runs BEFORE retrieve / LLM so the sampling at Step 5 reflects the
        # newly-selected mode (zero-tick latency). When no policy is wired the
        # call is a no-op, preserving pre-M5 behaviour.
        #
        # M6-A-1: when a transition occurs, the emitted ERREModeShiftEvent is
        # appended to ``observations`` so Steps 4-10 (retrieve / prompt /
        # reflection) see the mode-shift signal alongside the inputs that
        # caused it. The upstream sequence is not mutated — we build a new
        # list and rebind the local.
        agent_state, shift_event = self._maybe_apply_erre_fsm(
            agent_state,
            observations,
        )
        if shift_event is not None:
            observations = [*observations, shift_event]

        # Step 3: reflection trigger detection (execution is M4+).
        importance_sum = sum(estimate_importance(o) for o in observations)
        entered_reflective = _detect_zone_entry(observations, _REFLECTION_ZONES)
        reflection_triggered = bool(
            importance_sum > self.REFLECTION_IMPORTANCE_THRESHOLD or entered_reflective,
        )
        if reflection_triggered:
            logger.info(
                "Reflection trigger for agent %s (sum=%.2f, zone_entry=%s)",
                agent_state.agent_id,
                importance_sum,
                entered_reflective,
            )

        # Step 4: retrieve memories (Unavailable → proceed with empty list).
        memories = await self._retrieve_safely(agent_state, observations)

        # Step 4.5 (M10-B/M10-C): subjective-world-model synthesis + reconcile.
        # Only runs when the individual layer is enabled; otherwise
        # ``world_model_entries`` stays empty, ``reconciled`` stays ``None`` and
        # the USER prompt is byte-identical to the pre-M10-B contract
        # (DA-M10B-9). Belief records are read via the non-vector
        # ``list_semantic_beliefs`` path because belief promotions carry no
        # embedding (DA-M10B-2); synthesis + reconcile are pure (cycle owns the
        # I/O, mirroring the belief.py boundary).
        #
        # M10-C: the fresh evidence floor is reconciled with the agent's carried
        # state so prior bounded LLM nudges survive while evidence is unchanged
        # and are dropped when it moves (DA-M10C-2). ``exposed_citations`` is the
        # single source the displayed Held entries and the hint verifier share
        # (DA-M10C-3).
        flag_on = self._individual_layer is not None and self._individual_layer.enabled
        world_model_entries: Sequence[WorldModelEntry] = ()
        reconciled: WorldModelRuntimeState | None = None
        exposed_citations: dict[tuple[str, str], frozenset[str]] = {}
        # Initialised before the flag-on block (like ``reconciled``) so the M11-B
        # development evidence builder below can read the belief count/confidence
        # without a second store hit; stays empty flag-off.
        beliefs: list[SemanticMemoryRecord] = []
        if flag_on:
            beliefs = await self._store.list_semantic_beliefs(agent_state.agent_id)
            floor = synthesize_world_model(
                beliefs,
                agent_state.relationships,
                agent_id=agent_state.agent_id,
                current_tick=agent_state.tick,
            )
            reconciled = reconcile_world_model(
                world_model_runtime,
                floor,
                current_tick=agent_state.tick,
                stm_carry=(
                    self._individual_layer is not None
                    and self._individual_layer.stm_carry_enabled
                ),
            )
            world_model_entries = reconciled.modulated.entries
            exposed_citations = visible_entry_citations(world_model_entries)
        # Saturation probe (ADR section 2.1 / 5): snapshot the reconciled SWM
        # **here**, immediately after reconcile and before any adopted hint nudge,
        # so the modulated values are cap-re-clamped. Capturing later (off
        # ``result_runtime`` / the post-hint carry-out) would read values that can
        # transiently sit one step past the cap and over-estimate saturation. The
        # snapshot deep-copies, so a downstream nudge to ``reconciled`` cannot
        # mutate it. ``None`` flag-off, mirroring ``belief_classes`` — it rides out
        # on ``CycleResult`` so the trace sink in ``world`` never imports cognition.
        world_model_saturation = (
            project_world_model_snapshot(reconciled) if reconciled is not None else None
        )
        # M11-C2: full promoted-belief class set for this tick's
        # individual_state_trace row. ``None`` flag-off (beliefs never read); a
        # possibly-empty list flag-on ("whole promoted set"). Carried
        # on CycleResult so the trace sink in ``world`` never imports ``memory``.
        # Weighting unit is the belief, not the tick.
        # M11-C2 + M10-A 段B: flag-on trace substrate (promoted-belief classes +
        # per-dyad raw evidence units), captured here in the cycle's async context
        # so the trace sink in ``world`` never imports ``memory`` (DA-M11C2-2 /
        # DA-SB-1). Both ``None`` flag-off; built from ``beliefs`` already in hand.
        belief_classes, world_model_evidence = self._capture_trace_substrate(
            flag_on=flag_on, beliefs=beliefs, agent_state=agent_state
        )

        # Step 5-6: build prompts and call the LLM. The locomotion delta is the
        # third additive term. ``two_phase_knob=None`` (default) keeps the frozen
        # M13-ES3 ``locomotion_delta`` (divergence-only), so an agent without the
        # channel — and every existing sealed golden — composes bit-identically to
        # the pre-Phase-4 path; an injected ``TwoPhaseKnob`` makes the term
        # phase-signed (aha!/DMN-ECN Phase 4, see :meth:`_locomotion_delta_for`).
        sampling = compose_sampling(
            persona.default_sampling,
            agent_state.erre.sampling_overrides,
            self._locomotion_delta_for(agent_state),
        )
        system_prompt = build_system_prompt(persona, agent_state)
        user_prompt = build_user_prompt(
            observations,
            memories,
            world_model_entries=world_model_entries,
            world_model_update_enabled=flag_on,
            self_other_context=self_other_context or "",
        )
        try:
            resp = await self._llm.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_prompt),
                ],
                sampling=sampling,
            )
        except OllamaUnavailableError as exc:
            logger.warning(
                "LLM unavailable for agent %s: %s — continuing current action",
                agent_state.agent_id,
                exc,
            )
            return self._fallback(
                agent_state,
                new_memory_ids=new_memory_ids,
                reflection_triggered=reflection_triggered,
                new_physical=new_physical,
                world_model_runtime=reconciled,
                belief_classes=belief_classes,
                world_model_evidence=world_model_evidence,
                world_model_saturation=world_model_saturation,
                # Engagement instrument (Codex HIGH-1): this fallback returns before
                # step 7.5, so record a ``not_emitted`` disposition with a non-``ok``
                # ``llm_status`` to keep the per-(agent, tick) census complete. The
                # loader excludes non-``ok`` ticks from the eligible population, so the
                # fallback is provenance only — out of the emission-rate denominator,
                # never an unrecorded gap. ``None`` flag-off (補強 §4).
                world_model_hint_engagement=(
                    build_not_emitted_disposition(
                        llm_status=LLM_STATUS_UNAVAILABLE,
                        exposed_entry_count=len(exposed_citations),
                    )
                    if flag_on
                    else None
                ),
            )

        # Step 7: parse the LLM plan (malformed → same fallback branch).
        plan = parse_llm_plan(resp.content)
        if plan is None:
            logger.warning(
                "LLM returned unparseable plan for agent %s (len=%d) — fallback",
                agent_state.agent_id,
                len(resp.content),
            )
            return self._fallback(
                agent_state,
                new_memory_ids=new_memory_ids,
                reflection_triggered=reflection_triggered,
                new_physical=new_physical,
                world_model_runtime=reconciled,
                belief_classes=belief_classes,
                world_model_evidence=world_model_evidence,
                world_model_saturation=world_model_saturation,
                # Engagement instrument (Codex HIGH-1): unparseable plan also returns
                # before step 7.5 — record ``not_emitted`` with an ``unparseable``
                # status to keep the census complete (provenance only; excluded from
                # the eligible population, as for unavailable). ``None`` flag-off.
                world_model_hint_engagement=(
                    build_not_emitted_disposition(
                        llm_status=LLM_STATUS_UNPARSEABLE,
                        exposed_entry_count=len(exposed_citations),
                    )
                    if flag_on
                    else None
                ),
            )

        # Step 7.5 (M10-C): apply a verified world-model nudge. The LLM is a
        # candidate; ``apply_world_model_update_hint`` is the authority — it
        # rejects (returns ``None``) any hint that targets an entry not shown
        # this turn, cites a belief id outside that entry's displayed list, or
        # would create/flip a value. An adopted nudge bounds at +/- one step;
        # the cumulative cap is re-clamped by next tick's reconcile (DA-M10C-2/4).
        # ``result_runtime`` defaults to the pre-LLM reconciled state, so an
        # un-adopted or absent hint still carries the reconciled SWM forward.
        result_runtime = reconciled
        # Engagement instrument (ADR §3): observe the hint's disposition without
        # changing the frozen authority call. ``None`` flag-off.
        world_model_hint_engagement: WorldModelHintDisposition | None = None
        if flag_on and reconciled is not None:
            hint = plan.world_model_update_hint
            if hint is not None:
                nudged = apply_world_model_update_hint(
                    reconciled.modulated,
                    hint,
                    exposed_citations,
                )
                if nudged is not None:
                    result_runtime = reconciled.model_copy(update={"modulated": nudged})
                # The adopted/rejected headline reads the authority's real return
                # (``nudged``); only the reject reason is the shadow classifier's, and
                # ``adopted_signed_step`` is the measured new-old delta (補強 §1). This
                # is a pure read of ``reconciled.modulated`` / ``nudged`` — the frozen
                # call above (args / order / return) is unchanged.
                world_model_hint_engagement = build_emitted_disposition(
                    hint=hint,
                    exposed_citations=exposed_citations,
                    swm=reconciled.modulated,
                    nudged=nudged,
                    exposed_entry_count=len(exposed_citations),
                )
            else:
                world_model_hint_engagement = build_not_emitted_disposition(
                    llm_status="ok",
                    exposed_entry_count=len(exposed_citations),
                )

        # Slice β: nudge the LLM's destination toward persona preferred_zones
        # so three agents with different preferred lists produce three
        # different spatial trajectories. The helper is a no-op when the
        # destination is already preferred, when preferred_zones is empty,
        # or when the per-tick bias probability does not fire — so the
        # envelope-level contract is unchanged in the common case.
        plan = _bias_target_zone(
            plan,
            persona,
            self._bias_rng,
            self._zone_bias_p,
            agent_id=agent_state.agent_id,
            tick=agent_state.tick,
            bias_sink=self._bias_sink,
        )

        # Step 8: compose Cognitive via pure LLM delta.
        new_cognitive = apply_llm_delta(
            agent_state.cognitive,
            plan,
            config=self._update_config,
            rng=self._rng,
        )

        # Step 8.5 (M6-A-2b): detect stress threshold crossings. Unlike the
        # fatigue / hunger crossings in Step 2.25, stress lives in Cognitive
        # which is only known AFTER the LLM call, so the event arrives one
        # tick late by design. The runtime consumes
        # ``CycleResult.follow_up_observations`` and appends them to the
        # agent's pending buffer so the next tick's prompt sees the signal.
        stress_events = _detect_stress_crossing(
            previous=agent_state.cognitive,
            current=new_cognitive,
            agent_id=agent_state.agent_id,
            tick=agent_state.tick + 1,
        )

        # Step 9: assemble the post-tick state + envelopes. The M13-ES3 live
        # wiring advances the locomotion intensity λ from this tick's movement
        # decision (see :func:`_advance_locomotion`); ``locomotion=None`` stays
        # None, leaving the pre-ES3 behaviour bit-identical.
        new_state = agent_state.model_copy(
            update={
                "tick": agent_state.tick + 1,
                "physical": new_physical,
                "cognitive": new_cognitive,
                "locomotion": _advance_locomotion(
                    agent_state.locomotion,
                    destination_zone=plan.destination_zone,
                    current_zone=agent_state.position.zone,
                ),
            },
        )
        # ECL v0 (Issue 003): resolve the LLM-selected ``destination_zone`` to a
        # history-dependent coordinate before the MoveMsg is built (``None`` flag-off /
        # non-moving tick — ``_build_envelopes`` then takes the byte-identical zone-only
        # path). Delegated so ``step`` stays at its pre-ECL branch count.
        ecl_destination = await self._resolve_ecl_move(new_state, plan)
        envelopes = self._build_envelopes(
            new_state,
            plan,
            persona=persona,
            observations=observations,
            memories=memories,
            ecl_destination=ecl_destination,
        )

        # Steps 9.5 (M11-A diagnostic arc/coherence) + 10 (reflection) are
        # delegated to one collaborator: they share the post-state inputs, and a
        # clearly-incoherent utterance is the single signal allowed to deepen
        # reflection (diagnostic ⊥ control). Appends a ReflectionEventMsg in place.
        (
            reflection_event,
            new_narrative_arc,
            low_coherence,
        ) = await self._diagnose_and_reflect(
            plan=plan,
            persona=persona,
            reconciled=reconciled,
            new_state=new_state,
            new_memory_ids=new_memory_ids,
            observations=observations,
            importance_sum=importance_sum,
            envelopes=envelopes,
            flag_on=flag_on,
            reflection_disabled=(
                self._ecl_mode is not None and self._ecl_mode.reflection_disabled
            ),
        )

        # ECL v0 (Issue 003): pin every emitted envelope's ``sent_at`` to the record
        # mode's fixed clock so Plane 1 is deterministic (design §論点3).
        # Applied after ``_diagnose_and_reflect`` — which appends no envelope in record
        # mode (reflection is disabled) — so the whole list is stamped uniformly.
        envelopes = self._pin_envelope_clock(envelopes)

        # Step 9.6 (M11-B): advance the development stage from this tick's
        # LLM-independent evidence (or carry the prior state forward).
        new_development = self._maybe_advance_development(
            flag_on=flag_on,
            new_narrative_arc=new_narrative_arc,
            new_memory_ids=new_memory_ids,
            beliefs=beliefs,
            development_state=development_state,
        )

        return CycleResult(
            agent_state=new_state,
            envelopes=envelopes,
            new_memory_ids=new_memory_ids,
            reflection_triggered=reflection_triggered or low_coherence,
            llm_fell_back=False,
            reflection_event=reflection_event,
            follow_up_observations=list(stress_events),
            world_model_runtime=result_runtime,
            narrative_arc=new_narrative_arc,
            development_state=new_development,
            belief_classes=belief_classes,
            world_model_evidence=world_model_evidence,
            world_model_saturation=world_model_saturation,
            world_model_hint_engagement=world_model_hint_engagement,
            ecl_destination=ecl_destination,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _locomotion_delta_for(self, agent_state: AgentState) -> SamplingDelta:
        """Phase 4 knob-gated locomotion sampling delta.

        ``two_phase_knob is None`` (the default) → the frozen ES-3
        ``locomotion_delta`` (fixed-sign, divergence-only), byte-identical to the
        pre-Phase-4 live path and to every existing sealed golden. When a
        :class:`~erre_sandbox.erre.two_phase.TwoPhaseKnob` is injected the delta
        becomes **phase-signed** via ``two_phase_delta``, with the phase projected
        from the current ERRE mode (``phase_of_mode``): the same |λ| biases
        divergence in the generation phase and convergence in the evaluation phase
        (Phase 4 impl-design ADR §(3)). The gains are always the pinned module
        constants — injecting the knob is a presence marker, never a per-run tuning
        surface (Codex TASK-POST HIGH). Construction-only — no effect is measured.
        """
        if self._two_phase_knob is None:
            return locomotion_delta(
                agent_state.locomotion,
                gain_t=DEFAULT_LOCO_GAIN_T,
                gain_p=DEFAULT_LOCO_GAIN_P,
            )
        return two_phase_delta(
            agent_state.locomotion,
            phase_of_mode(agent_state.erre.name),
            gain_t=TWO_PHASE_GAIN_T,
            gain_p=TWO_PHASE_GAIN_P,
            gain_r=TWO_PHASE_GAIN_R,
        )

    async def _write_observations(
        self,
        observations: Sequence[Observation],
        *,
        agent_id: str,
        agent_tick: int,
        here: Position,
    ) -> list[str]:
        new_ids: list[str] = []
        ecl_mode = self._ecl_mode
        for i, obs in enumerate(observations):
            content = _observation_content_for_embed(obs)
            try:
                vec = await self._embedding.embed_document(content)
            except EmbeddingUnavailableError as exc:
                logger.warning(
                    "Embedding unavailable for agent %s observation: %s — "
                    "storing memory without embedding",
                    agent_id,
                    exc,
                )
                vec = None
            if ecl_mode is not None:
                # ECL v0 record mode (design §論点3): deterministic id + tick-derived
                # ``created_at``, plus — crucially (Codex HIGH-2) — a formation
                # ``location`` at the agent's current place so the resolver's centroid
                # carries a real spatial signal (pre-ECL rows left ``location=None``,
                # starving the "path" the resolver reads). The bare ``memory_id``
                # matches the frozen ``ecl-{agent_id}-{tick:04d}`` format for the common
                # one-observation tick; a rare multi-observation tick suffixes index > 0
                # to avoid an id collision (the frozen factory takes no ordinal).
                base_id = ecl_mode.memory_id(agent_id, agent_tick)
                mid_id = base_id if i == 0 else f"{base_id}-{i:02d}"
                created_at = ecl_mode.memory_created_at(agent_tick)
                location: SpatialContext | None = SpatialContext(
                    zone=here.zone,
                    x=here.x,
                    y=here.y,
                    z=here.z,
                )
            else:
                # Flag-off / live path: byte-identical to pre-ECL (``location`` defaults
                # to ``None``, so passing it explicitly is equivalent).
                mid_id = str(uuid.uuid4())
                created_at = datetime.now(tz=UTC)
                location = None
            entry = MemoryEntry(
                id=mid_id,
                agent_id=agent_id,
                kind=MemoryKind.EPISODIC,
                content=content,
                importance=estimate_importance(obs),
                created_at=created_at,
                source_observation_id=None,
                location=location,
            )
            mid = await self._store.add(entry, vec)
            new_ids.append(mid)
        return new_ids

    def _maybe_apply_erre_fsm(
        self,
        agent_state: AgentState,
        observations: Sequence[Observation],
    ) -> tuple[AgentState, ERREModeShiftEvent | None]:
        """Apply the optional ERRE mode FSM; return the (possibly) updated state.

        A ``None`` candidate from the policy signals "no transition this
        tick" and is the common case once an agent has settled into a mode;
        the returned tuple is ``(agent_state_unchanged, None)``. A concrete
        :class:`~erre_sandbox.schemas.ERREModeName` forces a fresh
        :class:`~erre_sandbox.schemas.ERREMode` with ``entered_at_tick``
        set to the tick the FSM observed and ``sampling_overrides`` pulled
        from :data:`~erre_sandbox.erre.SAMPLING_DELTA_BY_MODE` so Step 5's
        LLM call in the same tick uses the freshly-selected mode's delta
        via :func:`~erre_sandbox.inference.sampling.compose_sampling`. In
        that case an :class:`~erre_sandbox.schemas.ERREModeShiftEvent` is
        returned alongside the new state so Step 2.5 in :meth:`step` can
        append it to ``observations`` for downstream prompt / reflection.

        The FSM is consulted at Step 2.5, **before** ``new_physical`` is
        folded into ``agent_state``. Today ``advance_physical`` never
        changes ``position.zone`` (it only nudges CSDG half-step fields)
        so the FSM observes the correct zone; if a future milestone lets
        physical update change the zone, move this call after Step 9's
        ``agent_state.model_copy`` or refactor the physical update to
        happen before FSM.

        If the policy violates its Protocol contract and returns a value
        equal to ``current``, we treat it as a no-op (empty tuple tail):
        emitting a fresh :class:`~erre_sandbox.schemas.ERREMode` with a
        new ``entered_at_tick`` in that case would falsely mark a
        transition and confuse downstream dwell-time logic.

        The ``reason`` field on the emitted shift event is inferred from
        the most-recent mode-influencing observation (see
        :func:`_infer_shift_reason`). This approximation aligns with the
        FSM policy's "latest signal wins" semantics; a future milestone
        that needs byte-accurate attribution should extend the
        :class:`~erre_sandbox.schemas.ERREModeTransitionPolicy` Protocol
        to return ``(mode, reason)`` directly rather than reconstructing
        it here.
        """
        if self._erre_policy is None:
            return agent_state, None
        candidate = self._erre_policy.next_mode(
            current=agent_state.erre.name,
            zone=agent_state.position.zone,
            observations=observations,
            tick=agent_state.tick,
        )
        if candidate is None or candidate == agent_state.erre.name:
            return agent_state, None
        previous = agent_state.erre.name
        new_erre = ERREMode(
            name=candidate,
            entered_at_tick=agent_state.tick,
            sampling_overrides=self._erre_sampling_deltas[candidate],
        )
        logger.debug(
            "ERRE mode transition for agent %s: %s → %s (tick=%d)",
            agent_state.agent_id,
            previous,
            candidate,
            agent_state.tick,
        )
        shift_event = ERREModeShiftEvent(
            tick=agent_state.tick,
            agent_id=agent_state.agent_id,
            previous=previous,
            current=candidate,
            reason=_infer_shift_reason(observations),
        )
        return agent_state.model_copy(update={"erre": new_erre}), shift_event

    async def _retrieve_safely(
        self,
        agent_state: AgentState,
        observations: Sequence[Observation],
    ) -> list[RankedMemory]:
        query = _build_retrieval_query(observations, agent_state)
        if not query:
            return []
        try:
            # M13-ES1 SPDM: pass the agent's current place so a spatially-aware
            # retriever (spatial_weight > 0) can bias toward memories formed nearby.
            # With the production default spatial_weight=0 this is a no-op (the
            # ranking stays bit-identical to pre-SPDM).
            return await self._retriever.retrieve(
                agent_state.agent_id,
                query,
                current_location=agent_state.position,
            )
        except (OllamaUnavailableError, EmbeddingUnavailableError) as exc:
            logger.warning(
                "Retrieve failed for agent %s: %s — continuing with no memories",
                agent_state.agent_id,
                exc,
            )
            return []

    async def _coherence_score(
        self,
        utterance: str,
        swm: SubjectiveWorldModel,
    ) -> float | None:
        """Cosine of the utterance and the rendered SWM, or ``None`` (M11-A).

        Owns the (async) embedding I/O so :mod:`cognition.narrative` stays pure
        (DA-M11A-1). Returns ``None`` — never a fabricated score — when the world
        view is empty (skip before embedding, user fix 3), the embedding endpoint
        is unavailable (never raises into the cycle, error-handling skill), or the
        cosine is undefined. Both texts are embedded as ``document`` so the
        comparison is a symmetric similarity, not an asymmetric retrieval;
        the two are batched in one call.
        """
        swm_text = render_swm_for_embedding(swm)
        if not swm_text:
            return None
        try:
            vectors = await self._embedding.embed_many(
                [utterance, swm_text],
                kind="document",
            )
        except EmbeddingUnavailableError as exc:
            logger.warning(
                "M11-A coherence embedding unavailable: %s — skipping arc",
                exc,
            )
            return None
        expected_vectors = 2
        if len(vectors) != expected_vectors:
            return None
        return compute_coherence(vectors[0], vectors[1])

    async def _synthesize_diagnostic_arc(
        self,
        *,
        plan: LLMPlan,
        reconciled: WorldModelRuntimeState | None,
        new_state: AgentState,
        new_memory_ids: list[str],
    ) -> tuple[NarrativeArc | None, bool]:
        """M11-A Step 9.5: ``(narrative_arc, low_coherence)`` for a flag-on tick.

        Coherence is measured against ``reconciled.modulated`` — the SWM that was
        actually shown to the LLM — *not* the post-hint ``result_runtime``:
        otherwise this turn's own ``world_model_update_hint`` could move the
        score that gates reflection, weakening LLM=candidate / Python=authority.

        Returns ``(None, False)`` (no arc, no extra reflection) whenever an honest
        arc cannot be built: a silent turn, an empty / unembeddable world view, an
        embedding outage, or no episodic pointer this tick. ``low_coherence`` is
        ``True`` *only* when an arc was actually built and its score is below
        :data:`LOW_COHERENCE_THRESHOLD` — a skip-degenerate tick must not trip
        reflection on its own (user fix 2).
        """
        if reconciled is None or not plan.utterance:
            return None, False
        coherence = await self._coherence_score(plan.utterance, reconciled.modulated)
        if coherence is None:
            return None, False
        last_episodic_id = new_memory_ids[-1] if new_memory_ids else None
        arc = synthesize_narrative_arc(
            reconciled.modulated,
            synthesized_at_tick=new_state.tick,
            coherence_score=coherence,
            last_episodic_id=last_episodic_id,
        )
        if arc is None:
            logger.debug(
                "M11-A arc skipped (no episodic pointer) for agent %s",
                new_state.agent_id,
            )
            return None, False
        return arc, coherence < self.LOW_COHERENCE_THRESHOLD

    async def _diagnose_and_reflect(
        self,
        *,
        plan: LLMPlan,
        persona: PersonaSpec,
        reconciled: WorldModelRuntimeState | None,
        new_state: AgentState,
        new_memory_ids: list[str],
        observations: Sequence[Observation],
        importance_sum: float,
        envelopes: list[ControlEnvelope],
        flag_on: bool,
        reflection_disabled: bool = False,
    ) -> tuple[ReflectionEvent | None, NarrativeArc | None, bool]:
        """Steps 9.5 + 10: distil the diagnostic arc, then run reflection.

        Step 9.5 (M11-A, flag-on only): synthesise a ``NarrativeArc`` + coherence
        against the prompt-visible SWM and derive the ``low_coherence`` deepening
        signal. Step 10: run the reflector with that signal as an extra OR
        trigger, emitting a ``ReflectionEventMsg`` over *envelopes* when it fires.
        Returns ``(reflection_event, narrative_arc, low_coherence)`` for the
        caller's ``CycleResult``.

        The reflector never raises: outages resolve to ``reflection_event=None``
        (the caller's ``reflection_triggered`` flag still records the trigger).

        ``reflection_disabled`` (ECL v0 record mode, design §論点3 / Codex HIGH-1): the
        reflection LLM is the second non-determinism source, so a record-mode tick
        skips :meth:`Reflector.maybe_reflect` entirely — returning ``reflection_event=
        None`` and appending no ``ReflectionEventMsg`` — leaving the action LLM call the
        only entry in Plane 2. The M11-A arc (embedding-only, flag-on) is orthogonal and
        left untouched; ECL v0 does not enable the individual layer, so it is inert.
        """
        arc, low_coherence = (
            await self._synthesize_diagnostic_arc(
                plan=plan,
                reconciled=reconciled,
                new_state=new_state,
                new_memory_ids=new_memory_ids,
            )
            if flag_on
            else (None, False)
        )
        if reflection_disabled:
            return None, arc, low_coherence
        # M7γ D1: surface up to three recent peer-persona turns so the
        # distillation can react to what *others* just said — a pure read against
        # the dialog-turn log the bootstrap turn-sink chain already populates.
        recent_peer_turns = await self._fetch_recent_peer_turns(persona)
        reflection_event = await self._reflector.maybe_reflect(
            agent_state=new_state,
            persona=persona,
            observations=observations,
            importance_sum=importance_sum,
            recent_dialog_turns=recent_peer_turns,
            low_coherence=low_coherence,
        )
        # M6-A-4: wire the reflection over the envelope stream so the Godot xAI
        # ReasoningPanel can surface the distilled summary.
        if reflection_event is not None:
            envelopes.append(
                ReflectionEventMsg(tick=new_state.tick, event=reflection_event),
            )
        return reflection_event, arc, low_coherence

    def _maybe_advance_development(
        self,
        *,
        flag_on: bool,
        new_narrative_arc: NarrativeArc | None,
        new_memory_ids: list[str],
        beliefs: list[SemanticMemoryRecord],
        development_state: DevelopmentState | None,
    ) -> DevelopmentState | None:
        """Step 9.6 (M11-B): fold this tick's evidence into the development stage.

        Returns ``None`` (carry-forward) flag-off or on any tick without a fresh
        narrative arc — non-observations are never transitions (DA-M11B-10).
        Coherence is read from the *fresh* arc, never the carried
        ``AgentRuntime.narrative_arc`` (HIGH-2). ``beliefs`` / ``new_memory_ids``
        are already in hand, so this adds no store I/O.
        """
        if not flag_on or new_narrative_arc is None:
            return None
        mean_confidence = (
            sum(belief.confidence for belief in beliefs) / len(beliefs)
            if beliefs
            else 0.0
        )
        evidence = DevelopmentEvidence(
            new_episodic_count=len(new_memory_ids),
            fresh_coherence=new_narrative_arc.coherence_score,
            belief_count=len(beliefs),
            mean_belief_confidence=mean_confidence,
            belief_signature=belief_signature(beliefs),
        )
        return maybe_advance_development(
            development_state or DevelopmentState(),
            evidence,
        )

    def _capture_trace_substrate(
        self,
        *,
        flag_on: bool,
        beliefs: list[SemanticMemoryRecord],
        agent_state: AgentState,
    ) -> tuple[list[str] | None, list[PromotedEvidenceUnit] | None]:
        """Project this tick's flag-on individual-state trace substrate (pure).

        Returns ``(belief_classes, world_model_evidence)``, both ``None`` flag-off
        (the layer is inert, beliefs are never read). Flag-on:

        * ``belief_classes`` — every ``belief_kind`` from the promoted set ("whole
          promoted set", DA-M11C2-3); possibly empty.
        * ``world_model_evidence`` — the matched per-dyad ``(record, bond)`` units
          (M10-A 段B H2 substrate), the *same* dyads ``synthesize_world_model`` used
          this tick (single matching impl, no algorithm drift — DA-SB-3); possibly
          empty. Carried on ``CycleResult`` so ``world`` never imports ``memory``.

        Built from *beliefs* already read for the SWM floor, so no extra store I/O.
        """
        if not flag_on:
            return None, None
        belief_classes: list[str] = [
            b.belief_kind for b in beliefs if b.belief_kind is not None
        ]
        world_model_evidence = collect_promoted_evidence_units(
            beliefs,
            agent_state.relationships,
            agent_id=agent_state.agent_id,
        )
        return belief_classes, world_model_evidence

    def _fallback(
        self,
        agent_state: AgentState,
        *,
        new_memory_ids: list[str],
        reflection_triggered: bool,
        new_physical: Physical,
        world_model_runtime: WorldModelRuntimeState | None = None,
        belief_classes: list[str] | None = None,
        world_model_evidence: list[PromotedEvidenceUnit] | None = None,
        world_model_saturation: WorldModelSnapshot | None = None,
        world_model_hint_engagement: WorldModelHintDisposition | None = None,
    ) -> CycleResult:
        """Continue-current-action path for recoverable failures.

        Physical is advanced (wall-clock time still passes), tick is bumped,
        Cognitive is carried over, no Speech/Move/Animation envelopes.

        ``world_model_runtime`` carries the pre-LLM reconciled state on a flag-on
        outage so a transient LLM/parse failure cannot wipe an agent's
        accumulated world-model modulations (DA-M10C-7). ``None`` on flag-off.
        ``belief_classes`` likewise carries the flag-on promoted-belief set read
        before the LLM call, so an outage tick still records the agent's held
        beliefs in ``individual_state_trace`` (M11-C2). ``None`` on flag-off.
        ``world_model_evidence`` carries the flag-on per-dyad raw evidence units
        captured before the LLM call for the same reason (M10-A 段B); ``None``
        flag-off. ``world_model_saturation`` carries the post-reconcile pre-nudge
        SWM snapshot captured before the LLM call so an outage tick still records
        this tick's cap occupancy in the saturation trace (ADR section 2.1); ``None``
        flag-off. ``world_model_hint_engagement`` carries the flag-on ``not_emitted``
        disposition (with ``llm_status`` = ``unavailable`` / ``unparseable``) so an
        outage tick is recorded as provenance rather than left as a silent gap; the
        loader excludes non-``ok`` ticks from the eligible population, so it never
        enters the emission-rate denominator (engagement instrument ADR §3 / Codex
        HIGH-1); ``None`` flag-off.
        """
        new_state = agent_state.model_copy(
            update={
                "tick": agent_state.tick + 1,
                "physical": new_physical,
                # M13-ES3: a fallback tick makes no movement decision, so λ decays
                # with move_t=0 (same as a stay). Freezing λ through outages would
                # leave a walking agent's intensity stuck elevated.
                "locomotion": _advance_locomotion(
                    agent_state.locomotion,
                    destination_zone=None,
                    current_zone=agent_state.position.zone,
                ),
            },
        )
        envelopes: list[ControlEnvelope] = [
            AgentUpdateMsg(tick=new_state.tick, agent_state=new_state),
        ]
        # ECL v0 (Issue 001-α, B-5): a record-mode fallback tick must pin its
        # envelope clocks like the success path (line ~898) does, so the failure
        # branch stays byte-deterministic across bakes. Flag-off is untouched
        # (``_pin_envelope_clock`` returns the list unchanged when ``ecl_mode`` is
        # ``None``), but guard explicitly so the flag-off path is provably a no-op.
        if self._ecl_mode is not None:
            envelopes = self._pin_envelope_clock(envelopes)
        return CycleResult(
            agent_state=new_state,
            envelopes=envelopes,
            new_memory_ids=new_memory_ids,
            reflection_triggered=reflection_triggered,
            llm_fell_back=True,
            world_model_runtime=world_model_runtime,
            belief_classes=belief_classes,
            world_model_evidence=world_model_evidence,
            world_model_saturation=world_model_saturation,
            world_model_hint_engagement=world_model_hint_engagement,
        )

    async def _resolve_ecl_move(
        self,
        new_state: AgentState,
        plan: LLMPlan,
    ) -> EclDestination | None:
        """Resolve the ECL history-dependent MoveMsg target (Issue 003, record mode).

        Returns ``None`` flag-off (``ecl_mode is None``) or when the plan does not move
        (``destination_zone is None``) — the caller then builds the byte-identical
        zone-only MoveMsg. When active, reads the agent's own top-K memories
        (``k_world=0`` / ``mark_recalled=False``, frozen in the resolver) via
        ``self._retriever`` and folds their strength-weighted centroid + jitter into the
        target (policy grammar freeze, design §論点2). The resolved provenance is pushed
        to the record mode's optional move-decision sink and also surfaced on
        ``CycleResult`` so the I4 harness assembles Plane 1 from the logged candidate
        selection (centroid / memory ids / jitter / clamp), never an absolute-target
        replay (design §論点3/§論点4).
        """
        ecl_mode = self._ecl_mode
        if ecl_mode is None or plan.destination_zone is None:
            return None
        ecl_destination = await resolve_destination(
            self._retriever,
            agent_id=new_state.agent_id,
            query=_ECL_FORAGE_QUERY,
            here=new_state.position,
            destination_zone=plan.destination_zone,
            micro_rng=ecl_mode.substream(new_state.agent_id, "micro"),
            k_ecl=ecl_mode.k_ecl,
        )
        if ecl_mode.move_decision_sink is not None:
            ecl_mode.move_decision_sink(ecl_destination)
        return ecl_destination

    def _pin_envelope_clock(
        self,
        envelopes: list[ControlEnvelope],
    ) -> list[ControlEnvelope]:
        """Pin every envelope's clock fields to the record-mode clock (Issue 003).

        Flag-off (``ecl_mode is None``) returns ``envelopes`` unchanged, so the live
        path keeps the wall-clock default factory and stays byte-invariant. In record
        mode each envelope's ``sent_at`` is re-stamped to the fixed ``retrieval_now``
        so Plane 1 is deterministic (design §論点3).

        Nested ``_utc_now`` snapshot fields also leak wall-clock into the committed
        ``decisions.jsonl`` artifact (via ``envelope_provenance``), making a re-bake
        non-deterministic (Codex HIGH-1, B-5 / W). So in record mode this also pins
        the two nested clocks to the same ``retrieval_now``:

        * :class:`AgentUpdateMsg` — ``agent_state.wall_clock``;
        * :class:`ReasoningTraceMsg` — ``trace.created_at``.

        All other envelope kinds carry only the top-level ``sent_at`` and are pinned
        as before.
        """
        ecl_mode = self._ecl_mode
        if ecl_mode is None:
            return envelopes
        pinned = ecl_mode.retrieval_now
        result: list[ControlEnvelope] = []
        for env in envelopes:
            if isinstance(env, AgentUpdateMsg):
                result.append(
                    env.model_copy(
                        update={
                            "sent_at": pinned,
                            "agent_state": env.agent_state.model_copy(
                                update={"wall_clock": pinned}
                            ),
                        }
                    )
                )
            elif isinstance(env, ReasoningTraceMsg):
                result.append(
                    env.model_copy(
                        update={
                            "sent_at": pinned,
                            "trace": env.trace.model_copy(
                                update={"created_at": pinned}
                            ),
                        }
                    )
                )
            else:
                result.append(env.model_copy(update={"sent_at": pinned}))
        return result

    def _build_envelopes(
        self,
        new_state: AgentState,
        plan: LLMPlan,
        *,
        persona: PersonaSpec,
        observations: Sequence[Observation] = (),
        memories: Sequence[RankedMemory] = (),
        ecl_destination: EclDestination | None = None,
    ) -> list[ControlEnvelope]:
        envelopes: list[ControlEnvelope] = [
            AgentUpdateMsg(tick=new_state.tick, agent_state=new_state),
        ]
        if plan.utterance:
            envelopes.append(
                SpeechMsg(
                    tick=new_state.tick,
                    agent_id=new_state.agent_id,
                    utterance=plan.utterance,
                    zone=new_state.position.zone,
                ),
            )
        if plan.destination_zone is not None:
            if ecl_destination is not None:
                # ECL v0 (Issue 003): the LLM chose *which* zone; history chose *where*
                # in it. ``resolve_destination`` already produced a concrete,
                # ``locate_zone``-consistent coordinate, so the world layer's
                # zone-only → spawn resolution (``tick.py`` ``default_spawn`` branch)
                # never fires and the agent transits continuously (design §論点1).
                target = ecl_destination.target
            else:
                # Flag-off / live path (byte-identical to pre-ECL): coordinates are
                # carried over verbatim; the Godot side (T17) performs spatial
                # interpolation via Tween based on the Zone boundary, so we only hand
                # over the semantic destination.
                target = new_state.position.model_copy(
                    update={"zone": plan.destination_zone},
                )
            envelopes.append(
                MoveMsg(
                    tick=new_state.tick,
                    agent_id=new_state.agent_id,
                    target=target,
                    speed=(
                        self.DEFAULT_DESTINATION_SPEED
                        * persona.behavior_profile.movement_speed_factor
                    ),
                ),
            )
        if plan.animation:
            envelopes.append(
                AnimationMsg(
                    tick=new_state.tick,
                    agent_id=new_state.agent_id,
                    animation_name=plan.animation,
                ),
            )
        # M7γ D3+D4: structured rationale carries the observation / memory
        # provenance and an affinity hint so the xAI panel can show *why*
        # the agent decided this way. Even when the LLM did not fill any
        # rationale field, the trace is emitted whenever at least one of
        # the M7γ provenance lists is non-empty *or* there is a recent
        # bond — otherwise downstream consumers would lose the affinity
        # signal entirely on quiet ticks.
        observed_objects = _trace_observed_objects(observations)
        nearby_agents = _trace_nearby_agents(observations)
        retrieved_memories = _trace_retrieved_memories(memories)
        decision = _decision_with_affinity(plan.decision, new_state)
        trigger_event = _pick_trigger_event(observations, new_state.position.zone)
        if (
            plan.salient is not None
            or decision is not None
            or plan.next_intent is not None
            or observed_objects
            or nearby_agents
            or retrieved_memories
            or trigger_event is not None
        ):
            trace = ReasoningTrace(
                agent_id=new_state.agent_id,
                tick=new_state.tick,
                persona_id=new_state.persona_id,
                mode=new_state.erre.name,
                salient=plan.salient,
                decision=decision,
                next_intent=plan.next_intent,
                observed_objects=observed_objects,
                nearby_agents=nearby_agents,
                retrieved_memories=retrieved_memories,
                trigger_event=trigger_event,
            )
            envelopes.append(
                ReasoningTraceMsg(tick=new_state.tick, trace=trace),
            )
        return envelopes

    async def _fetch_recent_peer_turns(
        self,
        persona: PersonaSpec,
    ) -> list[DialogTurnMsg]:
        """Return up to three most-recent dialog turns from *other* personas.

        Reads ``dialog_turns`` rows synchronously off the event loop via
        :func:`asyncio.to_thread` so a slow sqlite scan cannot stall the
        cognition cycle. Returns ``[]`` on any failure — reflection D1 is
        an additive signal, not a blocking dependency.

        M7δ (R3 H3 SQL push): the WHERE / LIMIT push to SQLite via
        :meth:`MemoryStore.iter_dialog_turns(exclude_persona, limit)` so
        the previous full-table-scan-then-Python-filter pattern (which
        does not scale past a few thousand rows at the cycle's
        0.3 calls/s pace) is gone. ``iter_dialog_turns`` returns the most
        recent N rows in DESC order; we ``reversed(...)`` here to emit
        chronologically for the downstream reflection-prompt builder.

        Reconstructs :class:`DialogTurnMsg` from the export-flavoured row
        dicts produced by :meth:`MemoryStore.iter_dialog_turns`. The
        non-wire fields (``schema_version`` / ``sent_at``) take their
        default factories; only the fields the reflection prompt consumes
        are mapped.
        """
        try:
            rows = await asyncio.to_thread(
                lambda: list(
                    self._store.iter_dialog_turns(
                        exclude_persona=persona.persona_id,
                        limit=_PEER_TURNS_LIMIT,
                    ),
                ),
            )
        except sqlite3.OperationalError as exc:
            logger.warning(
                "iter_dialog_turns failed for peer turns (%s); skipping reflection D1",
                exc,
            )
            return []
        # SQL emits DESC (most recent first); reverse for chronological prompt.
        out: list[DialogTurnMsg] = []
        for row in reversed(rows):
            try:
                tick_val = row.get("tick", 0)
                turn_idx_val = row.get("turn_index", 0)
                out.append(
                    DialogTurnMsg(
                        tick=int(tick_val)
                        if isinstance(tick_val, (int, float, str))
                        else 0,
                        dialog_id=str(row.get("dialog_id", "")),
                        speaker_id=str(row.get("speaker_agent_id", "")),
                        addressee_id=str(row.get("addressee_agent_id", "")),
                        utterance=str(row.get("utterance", "")),
                        turn_index=int(turn_idx_val)
                        if isinstance(turn_idx_val, (int, float, str))
                        else 0,
                    ),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                logger.debug(
                    "skipping malformed dialog_turn row in peer fetch: %s",
                    exc,
                )
        return out


# ---------------------------------------------------------------------------
# Module-private helpers (pure)
# ---------------------------------------------------------------------------


def _bias_target_zone(
    plan: LLMPlan,
    persona: PersonaSpec,
    rng: Random,
    bias_p: float,
    *,
    agent_id: str,
    tick: int | None = None,
    bias_sink: Callable[[BiasFiredEvent], None] | None = None,
) -> LLMPlan:
    """Resample ``plan.destination_zone`` toward persona preferred zones.

    With probability ``bias_p``, if the LLM-chosen zone lies outside
    ``persona.preferred_zones``, pick a uniform replacement from that list
    and emit a ``bias.fired`` debug log so the researcher can confirm the
    bias is actually reshaping trajectories in a live run. The plan is
    returned unchanged in every other branch (empty preferred list,
    destination already preferred, destination is ``None``, or the
    probability did not fire), so normal LLM plans — including the
    intentional "stay put" signal — propagate unmodified.

    When ``bias_sink`` is provided (M8 baseline-quality-metric, decisions
    D2/D5), a :class:`BiasFiredEvent` is dispatched on every firing so
    callers can persist the event for post-hoc metric aggregation. The
    sink is called after the debug log so that a persistence failure
    (caught below) does not swallow the operator-visible signal. Sink
    exceptions are logged but never propagate — tearing down the live
    cognition cycle over observability bookkeeping would be worse than
    dropping a metric row.

    The "destination is ``None``" branch is deliberately a no-op in the
    first cut: we respect the LLM's choice to stay in place and let live
    G-GEAR data determine whether the helper should also synthesise a
    destination when the LLM leaves it empty (Open Question #1).
    """
    if not persona.preferred_zones:
        return plan
    if plan.destination_zone is None:
        return plan
    if plan.destination_zone in persona.preferred_zones:
        return plan
    if rng.random() >= bias_p:
        return plan
    new_dest = rng.choice(persona.preferred_zones)
    from_value = plan.destination_zone.value
    to_value = new_dest.value
    logger.debug(
        "bias.fired agent=%s from=%s to=%s bias_p=%.2f",
        agent_id,
        from_value,
        to_value,
        bias_p,
    )
    if bias_sink is not None and tick is not None:
        event = BiasFiredEvent(
            tick=tick,
            agent_id=agent_id,
            from_zone=from_value,
            to_zone=to_value,
            bias_p=bias_p,
        )
        try:
            bias_sink(event)
        except Exception:
            logger.exception(
                "bias_sink raised for agent=%s tick=%s; dropping event",
                agent_id,
                tick,
            )
    return plan.model_copy(update={"destination_zone": new_dest})


def _observation_content_for_embed(obs: Observation) -> str:  # noqa: PLR0911 — discriminator dispatch
    """Render *obs* into a single string suitable for Episodic storage + embed."""
    if obs.event_type == "perception":
        return f"[perception] {obs.content}"
    if obs.event_type == "speech":
        return f"[speech] {obs.speaker_id}: {obs.utterance}"
    if obs.event_type == "zone_transition":
        return f"[zone_transition] {obs.from_zone.value} -> {obs.to_zone.value}"
    if obs.event_type == "erre_mode_shift":
        prev = obs.previous.value
        curr = obs.current.value
        return f"[erre_mode_shift] {prev} -> {curr} ({obs.reason})"
    if obs.event_type == "internal":
        return f"[internal] {obs.content}"
    if obs.event_type == "affordance":
        return (
            f"[affordance] {obs.prop_kind}#{obs.prop_id} in {obs.zone.value} "
            f"(distance={obs.distance:.1f}m, salience={obs.salience:.2f})"
        )
    if obs.event_type == "proximity":
        return (
            f"[proximity {obs.crossing}] other={obs.other_agent_id} "
            f"{obs.distance_prev:.1f}m -> {obs.distance_now:.1f}m"
        )
    if obs.event_type == "temporal":
        return f"[temporal] {obs.period_prev.value} -> {obs.period_now.value}"
    if obs.event_type == "biorhythm":
        return (
            f"[biorhythm {obs.signal}:{obs.threshold_crossed}] "
            f"{obs.level_prev:.2f} -> {obs.level_now:.2f}"
        )
    return "[unknown] (unformatted)"


def _build_retrieval_query(
    observations: Iterable[Observation],
    agent_state: AgentState,
    *,
    include_zone_vocab: bool = True,
) -> str:
    """Render the retrieval query from the agent's state + recent observations.

    ``include_zone_vocab`` (M13-ES1 SPDM, Codex HIGH-3 confound control): the
    default ``True`` keeps the production prefix ``agent at {zone} in {mode} mode``.
    A SPDM apparatus passes ``False`` to drop the explicit zone token, so a measured
    retrieval-landscape divergence cannot ride on the zone *string* matching
    zone-tagged memory content — it must come from the spatial-binding term.
    """
    mode = agent_state.erre.name.value
    parts: list[str] = []
    if include_zone_vocab:
        zone = agent_state.position.zone.value
        parts.append(f"agent at {zone} in {mode} mode")
    else:
        parts.append(f"agent in {mode} mode")
    parts.extend(_observation_content_for_embed(obs) for obs in observations)
    return " | ".join(parts)


def _detect_zone_entry(
    observations: Iterable[Observation],
    trigger_zones: frozenset[Zone],
) -> bool:
    for obs in observations:
        if obs.event_type == "zone_transition" and obs.to_zone in trigger_zones:
            return True
    return False


def _detect_biorhythm_crossings(
    *,
    previous: Physical,
    current: Physical,
    agent_id: str,
    tick: int,
) -> list[BiorhythmEvent]:
    """Emit a :class:`BiorhythmEvent` for every signal that crossed mid-band.

    Compares the agent's fatigue / hunger before and after the CSDG
    half-step advance. The mid-level threshold (:data:`_BIORHYTHM_THRESHOLD`)
    is the only boundary watched in M6-A-2b so we stay inside the "at most
    one biorhythm event per signal per tick" budget documented on the
    threshold constant.

    Returns an empty list when no signal crossed — a fast path that keeps
    the observation-stream allocation pressure off every physics tick.
    """
    events: list[BiorhythmEvent] = []
    for signal, prev_val, curr_val in (
        ("fatigue", previous.fatigue, current.fatigue),
        ("hunger", previous.hunger, current.hunger),
    ):
        crossed_up = prev_val < _BIORHYTHM_THRESHOLD <= curr_val
        crossed_down = curr_val < _BIORHYTHM_THRESHOLD <= prev_val
        if not (crossed_up or crossed_down):
            continue
        events.append(
            BiorhythmEvent(
                tick=tick,
                agent_id=agent_id,
                signal=signal,  # type: ignore[arg-type]
                level_prev=prev_val,
                level_now=curr_val,
                threshold_crossed="up" if crossed_up else "down",
            ),
        )
    return events


def _detect_stress_crossing(
    *,
    previous: Cognitive,
    current: Cognitive,
    agent_id: str,
    tick: int,
) -> list[BiorhythmEvent]:
    """Emit a stress :class:`BiorhythmEvent` if mid-band was crossed.

    Parallel to :func:`_detect_biorhythm_crossings` for the ``stress`` signal
    living on :class:`Cognitive`. Kept as a separate helper because:

    * The watched vector differs (``Cognitive`` vs ``Physical``), so the
      signatures would diverge if merged.
    * Stress crossings are detected *after* the LLM call (Step 8) so the
      emitted tick is ``agent_state.tick + 1`` — the tick the event will
      belong to when the runtime surfaces it via
      :attr:`CycleResult.follow_up_observations`. The fatigue/hunger helper
      uses ``agent_state.tick`` because those events are same-tick inputs.

    The returned list has at most one element (``stress`` is the only
    watched signal on :class:`Cognitive`).
    """
    prev_val = previous.stress
    curr_val = current.stress
    crossed_up = prev_val < _BIORHYTHM_THRESHOLD <= curr_val
    crossed_down = curr_val < _BIORHYTHM_THRESHOLD <= prev_val
    if not (crossed_up or crossed_down):
        return []
    return [
        BiorhythmEvent(
            tick=tick,
            agent_id=agent_id,
            signal="stress",
            level_prev=prev_val,
            level_now=curr_val,
            threshold_crossed="up" if crossed_up else "down",
        ),
    ]


def _infer_shift_reason(
    observations: Sequence[Observation],
) -> Literal["scheduled", "zone", "fatigue", "external", "reflection"]:
    """Heuristically attribute an ERRE mode transition to its trigger.

    The FSM policy (:class:`~erre_sandbox.erre.DefaultERREModePolicy`)
    uses "latest signal wins" semantics, so the most-recent
    mode-influencing observation is the best guess for what caused the
    transition. We scan in reverse and pick the first match.

    ``InternalEvent.content`` prefixes follow the convention established
    by the FSM policy's internal handler: ``"fatigue:*"`` signals a
    fatigue-driven transition, ``"shuhari_promote:*"`` (and any other
    internal hint) is treated as scheduled progression. A stray
    ``ERREModeShiftEvent`` in ``observations`` means an external source
    forced the transition.

    Falls back to ``"external"`` when no mode-influencing observation is
    found — this can happen when a future rule (dwell-time, tick-modulo)
    triggers without a corresponding event.
    """
    for ev in reversed(observations):
        if isinstance(ev, ZoneTransitionEvent):
            return "zone"
        if isinstance(ev, InternalEvent):
            if ev.content.startswith("fatigue:"):
                return "fatigue"
            return "scheduled"
        if isinstance(ev, ERREModeShiftEvent):
            return "external"
    return "external"


def _trace_observed_objects(observations: Sequence[Observation]) -> list[str]:
    """Top-3 ``AffordanceEvent.prop_id`` by salience (M7γ D3).

    Stable ordering: salience descending, then insertion order — so two
    props with equal salience surface in the order the observation stream
    delivered them. Empty input yields an empty list (the trace consumer
    should not need to special-case ``None`` vs ``[]``).
    """
    affordances = [o for o in observations if isinstance(o, AffordanceEvent)]
    affordances.sort(key=lambda o: o.salience, reverse=True)
    return [o.prop_id for o in affordances[:_TRACE_OBSERVED_OBJECTS_LIMIT]]


def _trace_nearby_agents(observations: Sequence[Observation]) -> list[str]:
    """Top-2 ``ProximityEvent.other_agent_id`` with ``crossing="enter"`` (M7γ D3).

    Only ``enter`` crossings are surfaced — a ``leave`` crossing is the
    *absence* of relevance, not a positive signal worth tracing. The cap
    matches typical PIANO co-walking pair sizes; agents in larger crowds
    will see the two who most recently entered proximity.
    """
    enters = [
        o
        for o in observations
        if isinstance(o, ProximityEvent) and o.crossing == "enter"
    ]
    return [o.other_agent_id for o in enters[:_TRACE_NEARBY_AGENTS_LIMIT]]


def _trace_retrieved_memories(memories: Sequence[RankedMemory]) -> list[str]:
    """Top-3 :attr:`MemoryEntry.id` from the ranked retrieval (M7γ D3).

    The retriever already returns memories sorted by combined score, so we
    take the prefix without re-ranking. Empty when retrieval produced no
    rows (LLM unavailable, embedding outage, or no match) — the trace
    field then degrades to ``[]`` rather than papering over the gap.
    """
    return [m.entry.id for m in memories[:_TRACE_RETRIEVED_MEMORIES_LIMIT]]


_TRIGGER_PRIORITY: Final[tuple[str, ...]] = (
    "zone_transition",
    "affordance",
    "proximity",
    "biorhythm",
    "erre_mode_shift",
    "temporal",
    "internal",
    "speech",
    "perception",
)
"""Priority order for :func:`_pick_trigger_event` (M9-A).

Spatial triggers (zone_transition / affordance / proximity) come first
because the user's question "どの zone でどの reasoning が発火したか" is
fundamentally spatial. Biorhythm and erre_mode_shift outrank temporal
because they signal qualitative state shifts in the agent. Internal /
speech / perception sink to the bottom — they are usually background
chatter unless they are the only event that fired."""

_TRIGGER_SECONDARY_LIMIT: Final[int] = 8
"""Cap on :attr:`TriggerEventTag.secondary_kinds` (M9-A).

Bounded to match the schema-side ``max_length=8`` — far above the typical
strong-event count per tick (1-3) but below pathological saturation."""


def _resolve_trigger_zone_and_ref(
    winner_kind: str,
    winners: Sequence[Observation],
    current_zone: Zone,
) -> tuple[Zone | None, str | None]:
    """Resolve ``(zone, ref_id)`` for the winning trigger kind (M9-A helper).

    Spatial kinds (zone_transition / affordance / proximity) populate both;
    non-spatial kinds return ``(None, None)``. Affordance ties break by
    salience desc; proximity prefers ``crossing="enter"`` then falls back
    to the first occurrence (``leave`` crossings won't normally win the
    priority vote, but the helper stays total).
    """
    if winner_kind == "zone_transition":
        first = winners[0]
        if isinstance(first, ZoneTransitionEvent):
            return first.to_zone, first.to_zone.value
        return None, None
    if winner_kind == "affordance":
        affords = sorted(
            (o for o in winners if isinstance(o, AffordanceEvent)),
            key=lambda o: o.salience,
            reverse=True,
        )
        if affords:
            top = affords[0]
            return top.zone, top.prop_id
        return None, None
    if winner_kind == "proximity":
        enters = [
            o
            for o in winners
            if isinstance(o, ProximityEvent) and o.crossing == "enter"
        ]
        chosen: ProximityEvent | None = (
            enters[0]
            if enters
            else (winners[0] if isinstance(winners[0], ProximityEvent) else None)
        )
        if chosen is not None:
            return current_zone, chosen.other_agent_id
    return None, None


def _pick_trigger_event(
    observations: Sequence[Observation],
    current_zone: Zone,
) -> TriggerEventTag | None:
    """Pick the winning event boundary tag from this tick's observations (M9-A).

    Returns ``None`` only when ``observations`` is empty — every tick with
    *any* observation produces a tag so the panel always has a 1-line
    causal hint. Priority order is :data:`_TRIGGER_PRIORITY`; ties within
    the same priority class break to insertion order from the observation
    stream (``AffordanceEvent`` ties additionally break by salience).

    ``ref_id`` mapping: zone_transition → ``to_zone`` (string-equal to
    ``zone``); affordance → highest-salience ``prop_id``; proximity →
    first ``crossing="enter"`` ``other_agent_id``; otherwise ``None``.

    ``zone`` mapping: zone_transition → ``to_zone``; affordance →
    ``AffordanceEvent.zone``; proximity → ``current_zone`` (initiator
    side, since :class:`ProximityEvent` is observed from the receiver's
    POV in :func:`world.tick._fire_proximity_events`); other kinds →
    ``None`` (non-spatial). The Godot ``BoundaryLayer`` only pulses when
    ``zone`` is set *and* ``kind`` is in the spatial set.

    ``secondary_kinds`` lists same-tick observation kinds that lost the
    priority vote, in priority order, deduplicated, capped at 8. Lets the
    UI render a "+N more" hint without overloading ``ref_id``.
    """
    if not observations:
        return None

    by_kind: dict[str, list[Observation]] = {}
    for obs in observations:
        by_kind.setdefault(obs.event_type, []).append(obs)

    winner_kind: str | None = next(
        (k for k in _TRIGGER_PRIORITY if by_kind.get(k)),
        None,
    )
    if winner_kind is None:
        # Defensive: an observation with an event_type outside the nine
        # known kinds would land here. Prefer None over a phantom tag.
        return None

    zone, ref_id = _resolve_trigger_zone_and_ref(
        winner_kind,
        by_kind[winner_kind],
        current_zone,
    )

    secondaries = [
        candidate
        for candidate in _TRIGGER_PRIORITY
        if candidate != winner_kind and by_kind.get(candidate)
    ][:_TRIGGER_SECONDARY_LIMIT]

    return TriggerEventTag(
        kind=winner_kind,  # type: ignore[arg-type]
        zone=zone,
        ref_id=ref_id,
        secondary_kinds=secondaries,  # type: ignore[arg-type]
    )


def _decision_with_affinity(
    decision: str | None,
    new_state: AgentState,
) -> str | None:
    """Append the most salient bond's affinity hint to ``decision`` (M7γ D4 + M7δ M2).

    M7γ ranked bonds by ``last_interaction_tick`` only — so a recently-
    touched but neutral bond would shadow a strongly-charged older one.
    M7δ tightens the rule: rank by ``(|affinity|, last_interaction_tick)``
    descending so the hint surfaces the bond that actually carries
    emotional weight. The Godot :class:`ReasoningPanel` already sorts the
    Relationships foldout by ``|affinity|`` first; this Python-side change
    aligns the LLM's decision-suffix hint with what the user sees on
    screen (R3 M2).

    When there is no bond at all the original decision passes through
    unchanged. When ``decision`` is None and there *is* a bond the hint
    becomes the entire decision — that is intentional, because the γ
    acceptance test asserts the substring ``"affinity"`` is present
    whenever bonds exist, regardless of LLM rationale completeness.

    Format: ``f" affinity={bond.affinity:+.2f} with {bond.other_agent_id}"``
    suffixed to the LLM's decision when present, or used standalone
    otherwise. The ``+.2f`` format matches the Godot ReasoningPanel
    rendering for the relationships foldout (Slice γ Commit 4).
    """
    if not new_state.relationships:
        return decision
    most_salient = max(
        new_state.relationships,
        key=lambda b: (
            abs(b.affinity),
            b.last_interaction_tick if b.last_interaction_tick is not None else -1,
        ),
    )
    hint = f"affinity={most_salient.affinity:+.2f} with {most_salient.other_agent_id}"
    if decision is None:
        return hint
    return f"{decision} ({hint})"


__all__ = [
    "BiasFiredEvent",
    "CognitionCycle",
    "CognitionError",
    "CycleResult",
]
