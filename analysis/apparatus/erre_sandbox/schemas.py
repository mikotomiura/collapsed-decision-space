"""Pydantic v2 data contract for ERRE-Sandbox (T05 schemas-freeze).

This module is the Contract-First boundary between MacBook (orchestrator + Godot
viewer) and G-GEAR (inference + simulation + memory). It defines the wire types
exchanged over WebSocket and the in-memory representations shared across layers.

Sections
--------
* §1 Protocol constants
* §2 Enums
* §3 Persona (static, YAML-loaded) — incl. ``AgentSpec`` (M4)
* §4 AgentState (dynamic, per-tick)
* §4.5 Run lifecycle — ``RunLifecycleState`` (M8, run-level epoch phase)
* §5 Observation (event, discriminated by ``event_type``)
* §6 Memory — incl. ``ReflectionEvent`` / ``SemanticMemoryRecord`` (M4)
* §7 ControlEnvelope (message, discriminated by ``kind``) — incl. ``Dialog*`` (M4)
* §7.5 Protocols — DialogScheduler (M4) / ERREModeTransitionPolicy (M5)
  / DialogTurnGenerator (M5), interface-only
* §8 Public surface (``__all__``)

This module MUST NOT import any other ``erre_sandbox.*`` module
(see ``docs/repository-structure.md`` §4 and the ``architecture-rules`` skill).
"""

from __future__ import annotations

from collections.abc import (
    Iterator,  # noqa: TC003 — resolved at runtime by get_type_hints in tests
    Sequence,  # noqa: TC003 — resolved at runtime by get_type_hints in tests
)
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Final, Literal, NamedTuple, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# §1 Protocol constants
# =============================================================================

SCHEMA_VERSION: Final[str] = "0.11.0-m13es3"
"""Semantic version of the wire contract.

Bumped whenever any on-wire model gains or loses a field, or a discriminator
value is added/removed. Consumed by ``HandshakeMsg`` for early mismatch
detection between MacBook / G-GEAR / Godot peers.

M4 bump (0.1.0-m2 → 0.2.0-m4): adds the AgentSpec / ReflectionEvent /
SemanticMemoryRecord primitives and the dialog_initiate / dialog_turn /
dialog_close ControlEnvelope variants required by the 3-agent milestone.

M5 bump (0.2.0-m4 → 0.3.0-m5): adds the dialog_turn budget / ordering fields
(:attr:`Cognitive.dialog_turn_budget`, :attr:`DialogTurnMsg.turn_index`) and
the ``"exhausted"`` close reason required by the ERRE-mode FSM + dialog_turn
LLM-generation milestone. Two new Protocols (:class:`ERREModeTransitionPolicy`,
:class:`DialogTurnGenerator`) are frozen as interfaces so the four parallel
sub-tasks can type-hint against them.

M6 bump (0.3.0-m5 → 0.4.0-m6): adds four new :class:`Observation` variants
(:class:`AffordanceEvent`, :class:`ProximityEvent`, :class:`TemporalEvent`,
:class:`BiorhythmEvent`) and the :class:`TimeOfDay` enum used by
``TemporalEvent``. All four are additive to the discriminated ``Observation``
union — M5 producers that only emit the original five variants remain
wire-compatible. Firing logic lives in ``world/tick.py`` (Affordance /
Proximity / Temporal) and ``cognition/cycle.py`` (Biorhythm) and is wired
in the M6-A-2b sub-task; the schema bump is taken early so the four
M6-A tracks can type-hint against the frozen contract.

M7γ bump (0.5.0-m8 → 0.6.0-m7g): adds :class:`WorldLayoutMsg` (§7) with
its :class:`ZoneLayout` / :class:`PropLayout` row types, plus three new
default-empty list fields on :class:`ReasoningTrace`
(``observed_objects`` / ``nearby_agents`` / ``retrieved_memories``) so the
xAI :class:`ReasoningPanel` can show *why* a tick produced its decision.
The bump is additive and wire-compatible: the new ``world_layout``
discriminator is independent (no other variant changes), and the three
new ``ReasoningTrace`` fields use ``default_factory=list`` so older M8
producers that emit traces without them remain valid. The minor bump is
required because ``HandshakeMsg`` does a strict version match in
``integration/gateway.py`` and will reject 0.5.0-m8 peers against a
0.6.0-m7g gateway.

M7δ bump (0.6.0-m7g → 0.7.0-m7d): three additive field additions tied to
the Slice δ relationship-loop work (CSDG semi-formula + negative affinity +
2-layer memory bridge). On :class:`RelationshipBond`, the new
``last_interaction_zone: Zone | None`` (§4) records *where* a dyad most
recently interacted so the Godot ``ReasoningPanel`` can render
``"<persona> affinity ±0.NN (N turns, last in <zone> @ tick T)"``. On
:class:`SemanticMemoryRecord`, two new fields support the belief-promotion
bridge: ``belief_kind: Literal["trust","clash","wary","curious","ambivalent"]
| None`` (typed enum so m8-affinity-dynamics Critics can query
``WHERE belief_kind='clash'`` without parsing summary prefixes) and
``confidence: float`` (derivative of ``|affinity| / AFFINITY_UPPER``,
clamped to [0,1] at the write site). Both default to None / 1.0 so older
M7γ producers remain wire-compatible. The ``semantic_memory`` SQLite table
gains two columns via the ``_migrate_semantic_schema`` idempotent migration
pattern at ``memory/store.py``. ``RelationshipBond`` lives in
:class:`AgentState` (in-memory, ``model_copy`` mutation), not in a SQLite
table, so no DB migration is required for the bond field.

M8 bump (0.4.0-m6 → 0.5.0-m8): adds :class:`EpochPhase` (§2) and
:class:`RunLifecycleState` (§4.5) for the two-phase methodology adopted in
L6 ADR D3.
Run-level state (``autonomous`` / ``q_and_a`` / ``evaluation``) is owned by
:class:`~erre_sandbox.world.tick.WorldRuntime`; allowed transitions are
``autonomous → q_and_a → evaluation`` with no reverse. Additive: no existing
wire variant changes, and the new ``RunLifecycleState`` is not (yet) carried
by any :class:`ControlEnvelope` member — consumers that ignore it remain
wire-compatible. The new ``EpochPhase`` name is deliberately distinct from
the gateway-layer ``SessionPhase`` at ``integration/protocol.py`` so the two
orthogonal state machines cannot be confused.

M13-ES3 bump (0.10.0-m7h → 0.11.0-m13es3): one additive nested field tied to
the embodiment-substrate arc's locomotion → sampling channel. :class:`AgentState`
gains ``locomotion: LocomotionState | None`` (the kinetic-history EMA intensity λ
that feeds the third additive term of ``inference.sampling.compose_sampling``).
The new :class:`LocomotionState` pins ``ConfigDict(extra="forbid")``;
default-``None`` on :class:`AgentState` keeps pre-ES3 producers wire-compatible
(old payloads deserialise with ``locomotion=None`` → bit-identical composition).
The bump is required because ``HandshakeMsg`` does a strict version match and the
Godot client's ``CLIENT_SCHEMA_VERSION`` must move in lockstep.

M9-A bump (0.9.0-m7z → 0.10.0-m7h): one additive nested field tied to the
event-boundary-observability work. :class:`ReasoningTrace` gains
``trigger_event: TriggerEventTag | None`` so the Godot ``ReasoningPanel``
can render a 1-line "気づきの起点" (kind + zone + ref_id) and the
``BoundaryLayer`` can pulse the originating zone for the focused agent.
The new :class:`TriggerEventTag` carries ``kind`` (Literal of the 9
:class:`Observation` event_types), ``zone: Zone | None``, ``ref_id: str |
None`` (zone_transition→to_zone / affordance→prop_id /
proximity→other_agent_id), and ``secondary_kinds`` ("+N more" hint for
same-tick strong losers). It pins ``model_config =
ConfigDict(extra="forbid")`` so unknown nested keys are rejected at the
wire boundary. Default-None on :class:`ReasoningTrace` keeps M7ζ
producers wire-compatible. The bump from 0.9.0-m7z is required because
``HandshakeMsg`` does a strict version match and the Godot client's
``CLIENT_SCHEMA_VERSION`` must move in lockstep. The minor version is
named ``0.10.0-m7h`` (M7-η) rather than ``0.10.0-m9`` to keep the M7
chronology readable; the M9 namespace is reserved for the LoRA work.

M7ζ bump (0.8.0-m7e → 0.9.0-m7z): two additive fields tied to the Slice ζ
"Live Resonance" panel-context work. :class:`ReasoningTrace` gains
``persona_id: str | None`` so the Godot ``ReasoningPanel`` can render the
persona identity (display_name + 1-line summary) alongside the per-tick
trace without joining to ``AgentState`` at the client. :class:`RelationshipBond`
gains ``latest_belief_kind: Literal[...] | None`` (same value domain as
:attr:`SemanticMemoryRecord.belief_kind`) so the panel can surface the most
recent belief classification (trust / clash / wary / curious / ambivalent)
that was promoted from the dyad's affinity loop, rendered as an icon prefix
next to the bond row. Both default to ``None`` so older M7ε producers remain
wire-compatible. The ``relational_memory`` SQLite table is unaffected
(``RelationshipBond`` is in-memory on :class:`AgentState`).

Compatibility with M6 payloads:

* Additive and wire-compatible for consumers: no existing ``event_type`` /
  ``kind`` / ``reason`` discriminator gains or loses a value.
* Producers that construct :class:`~erre_sandbox.world.tick.WorldRuntime`
  directly need no change — ``RunLifecycleState`` defaults to
  :attr:`EpochPhase.AUTONOMOUS` so the existing run() behaviour is preserved.
"""


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


# =============================================================================
# §2 Enums
# =============================================================================


class Zone(StrEnum):
    """Five spatial zones of the world (see ``docs/glossary.md``)."""

    STUDY = "study"
    PERIPATOS = "peripatos"
    CHASHITSU = "chashitsu"
    AGORA = "agora"
    GARDEN = "garden"


class ERREModeName(StrEnum):
    """Eight ERRE cognitive modes (see ``persona-erre`` skill for semantics)."""

    PERIPATETIC = "peripatetic"
    CHASHITSU = "chashitsu"
    ZAZEN = "zazen"
    SHU_KATA = "shu_kata"
    HA_DEVIATE = "ha_deviate"
    RI_CREATE = "ri_create"
    DEEP_WORK = "deep_work"
    SHALLOW = "shallow"


class MemoryKind(StrEnum):
    """Four memory faculties of the agent (CoALA-inspired)."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    RELATIONAL = "relational"


class TimeOfDay(StrEnum):
    """Six simulated time-of-day periods used by :class:`TemporalEvent` (M6).

    The world clock quantises wall-clock into these buckets so the FSM and
    LLM can reason about circadian context without float comparisons. The
    mapping from hour to period is owned by ``world/tick.py``; this enum
    only freezes the vocabulary on the wire.
    """

    DAWN = "dawn"
    MORNING = "morning"
    NOON = "noon"
    AFTERNOON = "afternoon"
    DUSK = "dusk"
    NIGHT = "night"


class HabitFlag(StrEnum):
    """Epistemic status of a cognitive habit attributed to a historical figure."""

    FACT = "fact"
    LEGEND = "legend"
    SPECULATIVE = "speculative"


class ShuhariStage(StrEnum):
    """Three stages of skill acquisition in Japanese arts (shu-ha-ri)."""

    SHU = "shu"
    HA = "ha"
    RI = "ri"


class PlutchikDimension(StrEnum):
    """Plutchik's eight primary emotions."""

    JOY = "joy"
    TRUST = "trust"
    FEAR = "fear"
    SURPRISE = "surprise"
    SADNESS = "sadness"
    DISGUST = "disgust"
    ANGER = "anger"
    ANTICIPATION = "anticipation"


class EpochPhase(StrEnum):
    """Three research epochs of a run (M8, L6 ADR D3 ``two-phase methodology``).

    A ``WorldRuntime`` progresses ``autonomous → q_and_a → evaluation`` with
    no reverse. The goal is to protect the autonomous-emergence claim: the
    ``autonomous`` epoch has no researcher intervention, and any user dialogue
    (``speaker_id="researcher"``) belongs to ``q_and_a``. Offline scoring in
    ``evaluation`` is a stub for M10-11 and carries no runtime effect yet.

    This enum is **orthogonal** to the gateway-layer ``SessionPhase`` at
    ``integration/protocol.py`` (AWAITING_HANDSHAKE / ACTIVE / CLOSING),
    which describes WS handshake progression, not research lifecycle.
    """

    AUTONOMOUS = "autonomous"
    Q_AND_A = "q_and_a"
    EVALUATION = "evaluation"


# Convenience float ranges used repeatedly below.
_Unit = Annotated[float, Field(ge=0.0, le=1.0)]
_Signed = Annotated[float, Field(ge=-1.0, le=1.0)]


# =============================================================================
# §3 Persona (static, YAML-loaded)
# =============================================================================


class CognitiveHabit(BaseModel):
    """One recurring cognitive-behavioural pattern of a historical figure."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., description="Concrete habit, present tense.")
    source: str = Field(..., description="Citation key, e.g. 'kuehn2001'.")
    flag: HabitFlag = Field(..., description="fact / legend / speculative.")
    mechanism: str = Field(
        ...,
        description="Cognitive-neuroscience mechanism hypothesised to underlie it.",
    )
    trigger_zone: Zone | None = Field(
        default=None,
        description="Zone that typically activates this habit, if any.",
    )


class PersonalityTraits(BaseModel):
    """Static personality: Big Five + ERRE-specific Japanese aesthetic traits."""

    model_config = ConfigDict(extra="forbid")

    # Big Five (all [0, 1]).
    openness: _Unit = 0.5
    conscientiousness: _Unit = 0.5
    extraversion: _Unit = 0.5
    agreeableness: _Unit = 0.5
    neuroticism: _Unit = 0.5
    # ERRE-specific (docs/glossary.md).
    wabi: _Unit = Field(default=0.5, description="Acceptance of imperfection.")
    ma_sense: _Unit = Field(default=0.5, description="Tolerance of silence.")


class SamplingBase(BaseModel):
    """Absolute sampling parameters used as the persona's baseline."""

    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: _Unit = 0.9
    repeat_penalty: float = Field(default=1.0, ge=0.5, le=2.0)


class SamplingDelta(BaseModel):
    """Additive overrides applied on top of ``SamplingBase`` per ERRE mode.

    All fields default to ``0.0`` meaning "no override". The ``persona-erre``
    skill tabulates the canonical deltas per mode. Composition
    (``base + delta``) is the caller's responsibility; T11 / T12 must clamp
    the result back into ``SamplingBase``'s valid ranges.
    """

    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.0, ge=-1.0, le=1.0)
    top_p: float = Field(default=0.0, ge=-1.0, le=1.0)
    repeat_penalty: float = Field(default=0.0, ge=-1.0, le=1.0)


class BehaviorProfile(BaseModel):
    """Per-persona observable behavior knobs (M7ζ-3, additive).

    Drives runtime divergence between agents (movement speed, cognition tick
    cadence, post-MoveMsg dwell, separation radius) so that the same
    cognition cycle code can produce visibly different "creatures" in live
    observation. Server-side only — never flows over the wire, so
    ``SCHEMA_VERSION`` is not bumped when fields are added here.
    """

    model_config = ConfigDict(extra="forbid")

    movement_speed_factor: float = Field(
        default=1.0,
        ge=0.3,
        le=2.5,
        description=(
            "Multiplier applied to ``CognitionCycle.DEFAULT_DESTINATION_SPEED`` "
            "(1.3 m/s) when emitting MoveMsg. Yields the persona's distinctive "
            "gait rhythm in the live ``MoveMsg.speed`` histogram."
        ),
    )
    cognition_period_s: float = Field(
        default=10.0,
        ge=3.0,
        le=120.0,
        description=(
            "Base period of this agent's cognition tick. The 10 s global "
            "scheduler in ``world/tick.py`` runs unchanged, but each agent's "
            "``next_cognition_due`` is advanced by this value (phase wheel) "
            "so Nietzsche-like bursts and Rikyū-like slow cadences emerge."
        ),
    )
    dwell_time_s: float = Field(
        default=0.0,
        ge=0.0,
        le=600.0,
        description=(
            "Extra delay added once after a MoveMsg fires (seiza-like dwell). "
            "Suppresses cognition ticks for this duration before the phase "
            "wheel resumes — Rikyū's ≥20 min seiza is the headline use case."
        ),
    )
    separation_radius_m: float = Field(
        default=1.5,
        ge=0.0,
        le=5.0,
        description=(
            "Pair distance (XZ plane) below which the backend nudges this "
            "agent and its peer apart by 0.4 m per physics tick. Stays well "
            "inside ``_PROXIMITY_THRESHOLD_M = 5.0`` so dialog scheduler "
            "proximity events keep firing."
        ),
    )


class PersonaSpec(BaseModel):
    """Root schema for a persona YAML (one file per historical figure)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    persona_id: str = Field(..., description="kebab-case id, e.g. 'kant'.")
    display_name: str
    era: str = Field(..., description="Dates, e.g. '1724-1804'.")
    primary_corpus_refs: list[str] = Field(default_factory=list)
    personality: PersonalityTraits
    cognitive_habits: list[CognitiveHabit]
    preferred_zones: list[Zone]
    default_sampling: SamplingBase = Field(default_factory=SamplingBase)
    behavior_profile: BehaviorProfile = Field(default_factory=BehaviorProfile)


class AgentSpec(BaseModel):
    """Boot-time minimal agent declaration (M4 foundation).

    Carries only the two values the composition root needs to instantiate an
    agent at startup: which persona YAML to load and where on the map to spawn
    it. Joined with :class:`PersonaSpec` (by ``persona_id``) and expanded into a
    full :class:`AgentState` by ``m4-multi-agent-orchestrator``.
    """

    model_config = ConfigDict(extra="forbid")

    persona_id: str = Field(
        ...,
        description="Must match a ``PersonaSpec.persona_id`` loaded from YAML.",
    )
    initial_zone: Zone


class AgentView(NamedTuple):
    """Narrow read-only projection of a live agent.

    Used by cross-cutting observers (M4 :class:`DialogScheduler`, future
    ERRE mode FSM in M5) that should only see ``(agent_id, zone, tick)``.
    Living in ``schemas`` keeps the type below both ``world/`` (which
    produces these projections from its :class:`AgentRuntime`) and
    ``integration/`` (which consumes them), avoiding a layer violation.
    """

    agent_id: str
    zone: Zone
    tick: int


# =============================================================================
# §4 AgentState (dynamic, per-tick)
# =============================================================================


class Position(BaseModel):
    """3D position within the world, annotated with the containing zone."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float
    zone: Zone
    yaw: float = Field(default=0.0, description="Facing angle in radians.")
    pitch: float = Field(default=0.0, description="Head tilt in radians (bow, gaze).")


class SpatialContext(BaseModel):
    """Canonical formation-location of a memory (M13-ES1 SPDM).

    The ``MemoryEntry`` / ``SemanticMemoryRecord`` *formation* place — where the
    agent was when the memory was laid down — recorded as zone + world
    coordinates. This is the canonical spatial binding the retrieval scorer's
    spatial term reads (``memory/retrieval.py``), the substrate that was missing
    when the core thesis closed (no ``location`` on memory rows → no "path" for
    path-dependence to accumulate along).

    Additive and **nullable** on the memory types: existing rows / wire payloads
    carry ``location=None`` and the scorer treats them as spatially neutral
    (proximity factor 1.0), so the pre-SPDM behaviour stays bit-identical.

    ``source_count`` is provenance for the **semantic** path: a reflection-derived
    record's location is the centroid (mean ``x/y/z``, modal ``zone``) of its
    source episodic locations, and ``source_count`` records how many were folded
    in (``None`` for a directly-formed episodic location). Holding a single
    centroid keeps the scorer uniform (one record → one proximity); the source
    distribution itself is an ES-2 concern.
    """

    model_config = ConfigDict(extra="forbid")

    zone: Zone
    x: float
    y: float
    z: float
    source_count: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Number of source episodic locations aggregated into this centroid "
            "(semantic records only); None for a directly-formed episodic location."
        ),
    )


class Physical(BaseModel):
    """Long-timescale somatic state (CSDG HumanCondition adopted as skeleton).

    All fields move on a daily / half-life scale. Instantaneous affect lives in
    :class:`Cognitive` (``valence`` / ``arousal``) instead.
    """

    model_config = ConfigDict(extra="forbid")

    sleep_quality: _Unit = 0.7
    physical_energy: _Unit = 0.7
    mood_baseline: _Signed = 0.0
    cognitive_load: _Unit = 0.2
    emotional_conflict: _Unit = 0.0
    fatigue: _Unit = 0.0
    hunger: _Unit = 0.0
    breath_rate: _Unit = Field(
        default=0.25,
        description="Normalised respiration; varies during walk / zazen.",
    )


class Cognitive(BaseModel):
    """Short-timescale mental state (tick-level)."""

    model_config = ConfigDict(extra="forbid")

    # Russell circumplex (immediate affect).
    valence: _Signed = 0.0
    arousal: _Signed = 0.0
    # Plutchik dominant emotion, if any.
    dominant_emotion: PlutchikDimension | None = None
    # CSDG CharacterState-inspired drives.
    motivation: _Unit = 0.5
    stress: _Unit = 0.0
    curiosity: _Unit = 0.5
    # ERRE-specific cognitive facets.
    shuhari_stage: ShuhariStage = ShuhariStage.SHU
    dmn_activation: _Unit = Field(
        default=0.3,
        description="Default Mode Network activation proxy.",
    )
    active_goals: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Free-form short goal strings; promoted to a structured Goal type "
            "in M4 (this is a planned breaking change)."
        ),
    )
    dialog_turn_budget: int = Field(
        default=6,
        ge=0,
        description=(
            "Remaining dialog turns before the agent auto-closes its current "
            "dialog with ``DialogCloseMsg.reason='exhausted'``. Default 6 was "
            "validated empirically in the M5 LLM spike. "
            "0 means 'no more turns permitted'."
        ),
    )


class ERREMode(BaseModel):
    """The agent's current ERRE mode with its sampling overrides."""

    model_config = ConfigDict(extra="forbid")

    name: ERREModeName
    dmn_bias: _Signed = 0.0
    sampling_overrides: SamplingDelta = Field(default_factory=SamplingDelta)
    entered_at_tick: int = Field(..., ge=0)
    zone_trigger: Zone | None = None


class RelationshipBond(BaseModel):
    """Per-other-agent relational state."""

    model_config = ConfigDict(extra="forbid")

    other_agent_id: str
    affinity: _Signed = 0.0
    familiarity: _Unit = 0.0
    ichigo_ichie_count: int = Field(default=0, ge=0)
    last_interaction_tick: int | None = Field(default=None, ge=0)
    last_interaction_zone: Zone | None = Field(
        default=None,
        description=(
            "Zone where the most recent dyad interaction occurred. M7δ-added; "
            "older bonds (pre-0.7.0-m7d) deserialise as None. Written by "
            "``WorldRuntime.apply_affinity_delta`` and read by Godot's "
            "``ReasoningPanel`` to render ``'last in <zone>'`` next to affinity."
        ),
    )
    latest_belief_kind: (
        Literal[
            "trust",
            "clash",
            "wary",
            "curious",
            "ambivalent",
        ]
        | None
    ) = Field(
        default=None,
        description=(
            "Most-recent typed classification promoted from this bond's "
            "affinity loop (M7ζ). Same value domain as "
            ":attr:`SemanticMemoryRecord.belief_kind` — kept here so the "
            "Godot ``ReasoningPanel`` can render an icon prefix "
            "(``◯△✕？◇``) next to the bond row without joining to the "
            "semantic_memory table at every panel refresh. Written by "
            "``WorldRuntime.apply_belief_promotion`` from the bootstrap "
            "relational sink the moment ``cognition.belief.maybe_promote_belief`` "
            "graduates the bond past its ``|affinity| × N`` gates. Older "
            "bonds (pre-0.9.0-m7z) deserialise as None; once set, the value "
            "is overwritten only by a subsequent successful promotion of the "
            "same dyad — an affinity drop below threshold does not clear it."
        ),
    )


class LocomotionState(BaseModel):
    """Kinetic-history locomotion intensity (M13-ES3 歩行→sampling 変調).

    The agent's **movement history** as an EMA intensity ``lam`` ∈ [0, 1],
    deliberately distinct from the *location* channel (the ``peripatetic`` ERRE
    mode's zone-triggered static +0.3 temperature bump). ``lam`` rises on a
    walking streak (a zone change this tick) and decays on stay, per
    ``lam_t = (1-α)·lam_{t-1} + α·move_t`` where ``move_t ∈ {0, 1}`` is "did the
    zone change this tick" (see
    :func:`erre_sandbox.erre.locomotion_sampling.locomotion_delta`). It is the
    input to the locomotion sampling delta — the **third additive term** of
    :func:`erre_sandbox.inference.sampling.compose_sampling`.

    Additive and **nullable** on :class:`AgentState`: an agent with
    ``locomotion=None`` produces no locomotion delta, so the pre-ES3 sampling
    composition stays **bit-identical** (backward compatible; existing rows /
    wire payloads deserialise with ``locomotion=None``). ``gait`` is an optional
    free-form forensic/observer descriptor (e.g. ``"walk"`` / ``"stay"``); it
    never enters the sampling math.
    """

    model_config = ConfigDict(extra="forbid")

    lam: _Unit = Field(
        default=0.0,
        description=(
            "Locomotion intensity EMA λ ∈ [0,1]: (1-α)·λ_prev + α·move_t, "
            "move_t∈{0,1} = did the containing zone change this tick. "
            "0 = at rest; rises on a walking streak, decays on stay."
        ),
    )
    gait: str | None = Field(
        default=None,
        description="Optional forensic gait label (walk/stay); never enters sampling.",
    )


class AgentState(BaseModel):
    """Snapshot of an agent at a given tick.

    Static persona information (traits, cognitive habits) lives in
    :class:`PersonaSpec` and is joined at read time via ``persona_id``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    agent_id: str
    persona_id: str
    tick: int = Field(..., ge=0)
    wall_clock: datetime = Field(default_factory=_utc_now)
    position: Position
    physical: Physical = Field(default_factory=Physical)
    cognitive: Cognitive = Field(default_factory=Cognitive)
    erre: ERREMode
    locomotion: LocomotionState | None = Field(
        default=None,
        description=(
            "Kinetic-history locomotion intensity (M13-ES3). None → no "
            "locomotion sampling delta → pre-ES3 composition bit-identical."
        ),
    )
    relationships: list[RelationshipBond] = Field(default_factory=list)


# =============================================================================
# §4.5 Run lifecycle (run-level, owned by WorldRuntime)
# =============================================================================


class RunLifecycleState(BaseModel):
    """Run-level epoch state for the two-phase methodology (M8, L6 ADR D3).

    Distinct from per-agent :class:`AgentState` (which is per-tick) and from
    ``BootConfig`` (which is immutable startup config). Owned by
    :class:`~erre_sandbox.world.tick.WorldRuntime` and mutated only via its
    ``transition_to_q_and_a()`` / ``transition_to_evaluation()`` methods —
    never direct field assignment from outside the runtime.

    Serialisable so runtime state can be logged or (in a future spike)
    carried on a :class:`ControlEnvelope` variant for observers.
    """

    model_config = ConfigDict(extra="forbid")

    epoch_phase: EpochPhase = EpochPhase.AUTONOMOUS
    epoch_started_at: datetime = Field(default_factory=_utc_now)


# =============================================================================
# §5 Observation (discriminated by ``event_type``)
# =============================================================================


class _ObservationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tick: int = Field(..., ge=0)
    agent_id: str = Field(..., description="The observing agent.")
    wall_clock: datetime = Field(default_factory=_utc_now)


class PerceptionEvent(_ObservationBase):
    """Something the agent sees / hears / smells / feels."""

    event_type: Literal["perception"] = "perception"
    modality: Literal["sight", "sound", "smell", "touch", "proprioception"]
    source_agent_id: str | None = Field(
        default=None,
        description=(
            "``None`` when the source is environmental (weather, ambient sound, etc.)."
        ),
    )
    source_zone: Zone
    content: str
    intensity: _Unit = 0.5


class SpeechEvent(_ObservationBase):
    """An utterance heard (or spoken) by the agent."""

    event_type: Literal["speech"] = "speech"
    speaker_id: str
    utterance: str
    emotional_impact: _Signed = 0.0


class ZoneTransitionEvent(_ObservationBase):
    """The agent moved from one zone to another."""

    event_type: Literal["zone_transition"] = "zone_transition"
    from_zone: Zone
    to_zone: Zone


class ERREModeShiftEvent(_ObservationBase):
    """The agent's ERRE mode changed."""

    event_type: Literal["erre_mode_shift"] = "erre_mode_shift"
    previous: ERREModeName
    current: ERREModeName
    reason: Literal["scheduled", "zone", "fatigue", "external", "reflection"]


class InternalEvent(_ObservationBase):
    """A self-generated reflective prompt (peripatos / chashitsu entry etc.)."""

    event_type: Literal["internal"] = "internal"
    content: str
    importance_hint: _Unit = 0.5


class AffordanceEvent(_ObservationBase):
    """The agent noticed an interactable environmental element (M6).

    Emitted by ``world/tick.py`` when the agent enters the salient radius of
    a named prop (e.g. a tea bowl within the chashitsu, a lectern in the
    study). The open-vocabulary ``prop_kind`` keeps the wire contract stable
    as new assets are added — downstream code should treat unknown kinds as
    generic environmental salience rather than switching exhaustively.
    """

    event_type: Literal["affordance"] = "affordance"
    prop_id: str = Field(..., description="Stable scene-level identifier.")
    prop_kind: str = Field(
        ...,
        description=(
            'Free-form kind label (e.g. "tea_bowl", "lectern", "stone_lantern"). '
            "Downstream code should not switch exhaustively on this value."
        ),
    )
    zone: Zone
    distance: float = Field(
        ...,
        ge=0.0,
        description="Distance in metres from the agent to the prop.",
    )
    salience: _Unit = 0.5


class ProximityEvent(_ObservationBase):
    """The agent's distance to another agent crossed a threshold (M6).

    Emitted once per crossing edge — entering or leaving a radius — rather
    than continuously, so the observation stream is not flooded by co-walking
    pairs. ``distance_prev`` and ``distance_now`` both refer to the current
    physics tick's pair distance and its immediately prior reading.
    """

    event_type: Literal["proximity"] = "proximity"
    other_agent_id: str
    distance_prev: float = Field(..., ge=0.0)
    distance_now: float = Field(..., ge=0.0)
    crossing: Literal["enter", "leave"]


class TemporalEvent(_ObservationBase):
    """The simulated time-of-day period rolled over (M6).

    Rolled once per period boundary (e.g. ``morning`` → ``noon``). The FSM
    may use this to bias dwell-time or trigger circadian-scheduled mode
    shifts; the LLM prompt surfaces it so the agent can reason about the
    phase of the day (e.g. Kant's regular afternoon walk).
    """

    event_type: Literal["temporal"] = "temporal"
    period_prev: TimeOfDay
    period_now: TimeOfDay


class BiorhythmEvent(_ObservationBase):
    """A fatigue / hunger / stress signal crossed a threshold (M6).

    Emitted by ``cognition/cycle.py`` when the CSDG half-step physical /
    cognitive update pushes one of the tracked signals across a policy
    threshold. Unlike :class:`InternalEvent`, this variant is structured:
    downstream code can switch on ``signal`` and ``threshold_crossed`` to
    drive UI / FSM reactions without parsing the freeform ``content`` of
    an ``InternalEvent``.
    """

    event_type: Literal["biorhythm"] = "biorhythm"
    signal: Literal["fatigue", "hunger", "stress"]
    level_prev: _Unit
    level_now: _Unit
    threshold_crossed: Literal["up", "down"]


Observation: TypeAlias = Annotated[
    PerceptionEvent
    | SpeechEvent
    | ZoneTransitionEvent
    | ERREModeShiftEvent
    | InternalEvent
    | AffordanceEvent
    | ProximityEvent
    | TemporalEvent
    | BiorhythmEvent,
    Field(discriminator="event_type"),
]
"""Discriminated union of all observation event types."""


# =============================================================================
# §6 Memory
# =============================================================================


class MemoryEntry(BaseModel):
    """A single memory row in the agent's Memory Stream.

    Pure domain type: embedding vectors and search scores are the memory-store
    layer's concern (T10) and intentionally absent here so backends can be
    swapped (sqlite-vec → Qdrant) without breaking the wire contract.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    agent_id: str
    kind: MemoryKind
    content: str
    importance: _Unit
    created_at: datetime = Field(default_factory=_utc_now)
    last_recalled_at: datetime | None = None
    recall_count: int = Field(default=0, ge=0)
    source_observation_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    location: SpatialContext | None = Field(
        default=None,
        description=(
            "Formation location (M13-ES1 SPDM). None for pre-SPDM rows and "
            "wire payloads without a spatial binding; the retrieval scorer then "
            "treats the row as spatially neutral (bit-identical to pre-SPDM)."
        ),
    )


class ReflectionEvent(BaseModel):
    """Snapshot of one reflection step (M4 foundation).

    The cognition cycle distils a window of recent episodic entries into a
    single summary at reflection-trigger time. This struct is the on-wire /
    in-process record of that event, independent of both the trigger policy
    and the semantic-memory storage backend.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    tick: int = Field(..., ge=0)
    summary_text: str = Field(
        ...,
        description="LLM-distilled reflection content; UTF-8, not length-capped here.",
    )
    src_episodic_ids: list[str] = Field(
        default_factory=list,
        description="Source ``MemoryEntry.id`` values folded into the summary.",
    )
    created_at: datetime = Field(default_factory=_utc_now)


class TriggerEventTag(BaseModel):
    """1-line "起点 event" tag attached to a :class:`ReasoningTrace` (M9-A).

    Lets the Godot ``ReasoningPanel`` show "this trace was a reaction to X"
    and the ``BoundaryLayer`` pulse the originating zone, without forcing
    consumers to scan the raw observation stream. Cognition cycle picks one
    winner per tick by priority (zone_transition > affordance > proximity >
    biorhythm > erre_mode_shift > temporal > internal > speech > perception);
    same-tick losers in the spatial set are surfaced as ``secondary_kinds``
    for a "+N more" UI hint.

    Wire contract: ``ref_id`` is structured (zone_transition→``to_zone``,
    affordance→``prop_id``, proximity→``other_agent_id``, otherwise ``None``).
    Display text (e.g. "Linden-Allee に入った") is composed *client-side* in
    ``godot_project/scripts/i18n/Strings.gd`` so backend stays free of i18n.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "zone_transition",
        "affordance",
        "proximity",
        "temporal",
        "biorhythm",
        "erre_mode_shift",
        "internal",
        "speech",
        "perception",
    ] = Field(
        ...,
        description=(
            "Event_type of the winning observation that triggered this "
            "trace. Must match one of the nine :class:`Observation` "
            "discriminator values."
        ),
    )
    zone: Zone | None = Field(
        default=None,
        description=(
            "Zone where the trigger occurred. None for non-spatial kinds "
            "(temporal / biorhythm / internal / speech / perception / "
            "erre_mode_shift). The Godot ``BoundaryLayer`` only pulses "
            "when zone is set AND kind is in the spatial set "
            "{zone_transition, affordance, proximity}."
        ),
    )
    ref_id: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Structured reference id of the trigger. Mapping by kind: "
            "zone_transition→``to_zone`` (string-equal to ``zone``), "
            "affordance→``prop_id``, proximity→``other_agent_id``. "
            "None for kinds without a stable reference."
        ),
    )
    secondary_kinds: list[
        Literal[
            "zone_transition",
            "affordance",
            "proximity",
            "temporal",
            "biorhythm",
            "erre_mode_shift",
            "internal",
            "speech",
            "perception",
        ]
    ] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Same-tick strong losers (kinds that were observed but did not "
            "win the priority vote). UI may render as '+N more'. Order "
            "follows priority descending; bounded to 8 to cap envelope size."
        ),
    )


class ReasoningTrace(BaseModel):
    """One tick of structured reasoning rationale (M6-A-3).

    Produced alongside an :class:`LLMPlan` by the cognition cycle's Step 5
    when the LLM fills the optional ``salient`` / ``decision`` /
    ``next_intent`` fields. Unlike :class:`ReflectionEvent` (which distils
    many ticks into one stored memory), this trace captures per-tick
    self-explanation — primarily for xAI observability in the Godot UI.

    All three narrative fields are optional because stable Ollama output is
    never 100%; downstream consumers must tolerate ``None``. The trace is
    safe to discard if missing — :class:`LLMPlan` parsing is independent,
    so a persona can produce a valid plan without producing a trace.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    tick: int = Field(..., ge=0)
    persona_id: str | None = Field(
        default=None,
        description=(
            "Persona this trace belongs to (matches ``PersonaSpec.persona_id``). "
            "M7ζ-added so the Godot ``ReasoningPanel`` can render the persona "
            "identity alongside the trace without joining ``AgentState``. Older "
            "M7ε producers (pre-0.9.0-m7z) deserialise as ``None``; consumers "
            "must tolerate the missing case and fall back to ``agent_id``."
        ),
    )
    mode: ERREModeName
    salient: str | None = Field(
        default=None,
        description="What the agent noticed as most salient this tick.",
    )
    decision: str | None = Field(
        default=None,
        description="The one-sentence rationale behind the chosen action.",
    )
    next_intent: str | None = Field(
        default=None,
        description="Forward-looking intent surfaced for upcoming ticks.",
    )
    observed_objects: list[str] = Field(
        default_factory=list,
        description=(
            "Top-3 ``AffordanceEvent.prop_id`` values by salience that informed "
            "this tick's decision (M7γ). Empty list means the tick had no "
            "affordance signal worth surfacing — not a missing field."
        ),
    )
    nearby_agents: list[str] = Field(
        default_factory=list,
        description=(
            "Up to two ``ProximityEvent.other_agent_id`` values with "
            'crossing="enter" that informed this tick (M7γ). Order is '
            "insertion order from the observation stream."
        ),
    )
    retrieved_memories: list[str] = Field(
        default_factory=list,
        description=(
            "Top-3 ``MemoryEntry.id`` values surfaced by recall calls during "
            "this tick (M7γ). Lets the xAI panel link the decision back to the "
            "specific memory rows it leaned on."
        ),
    )
    trigger_event: TriggerEventTag | None = Field(
        default=None,
        description=(
            "M9-A: the event-boundary tag picked from this tick's "
            "observations by priority. Lets the Godot ``ReasoningPanel`` "
            "show the trigger 1-liner and the ``BoundaryLayer`` pulse the "
            "originating zone for the focused agent. Older M7ζ producers "
            "(pre-0.10.0-m7h) deserialise as ``None``; consumers must "
            "tolerate the missing case."
        ),
    )
    created_at: datetime = Field(default_factory=_utc_now)


class SemanticMemoryRecord(BaseModel):
    """Long-term semantic memory row distilled from reflection (M4 foundation).

    Minimal shape: the sqlite-vec schema (index configuration, embedding
    dimensionality, composite keys) is deferred to
    ``m4-memory-semantic-layer``. ``embedding`` is permitted to be empty so
    fixture files and unit tests can roundtrip without shipping a real vector.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    agent_id: str
    embedding: list[float] = Field(
        default_factory=list,
        description=(
            "Row-level vector. Expected non-empty at runtime; empty allowed for "
            "fixture payloads so contract tests do not pin a particular dim."
        ),
    )
    # TODO(m4-memory-semantic-layer): pin embedding dimensionality once the
    # sqlite-vec index schema chooses between multilingual-e5-small (384) and
    # ruri-v3-30m (256); add field_validator to reject wrong-length vectors.
    summary: str
    origin_reflection_id: str | None = Field(
        default=None,
        description="``ReflectionEvent`` this row was distilled from, if any.",
    )
    belief_kind: (
        Literal[
            "trust",
            "clash",
            "wary",
            "curious",
            "ambivalent",
        ]
        | None
    ) = Field(
        default=None,
        description=(
            "Typed classification of the belief this record represents (M7δ). "
            "Set when ``cognition/belief.py::maybe_promote_belief`` distils a "
            "RelationshipBond past the ``|affinity|`` × interaction-count "
            "threshold; left None for non-belief reflections distilled by "
            "``cognition/reflection.py``. Critics query "
            "``WHERE belief_kind='clash'`` etc. without parsing summary text."
        ),
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Belief strength in [0,1]. Defaults to 1.0 for legacy rows and for "
            "non-belief semantic records (where the field is unused). "
            "Belief-promotion path computes "
            "``min(1.0, |affinity|/AFFINITY_UPPER * (interactions/min_interactions))``."
        ),
    )
    created_at: datetime = Field(default_factory=_utc_now)
    location: SpatialContext | None = Field(
        default=None,
        description=(
            "Formation location (M13-ES1 SPDM): the centroid of the source "
            "episodic locations folded into this reflection-derived record "
            "(``source_count`` provenance). None for pre-SPDM rows; the scorer "
            "then treats the row as spatially neutral (bit-identical to pre-SPDM)."
        ),
    )


# =============================================================================
# §7 ControlEnvelope (discriminated by ``kind``)
# =============================================================================


class _EnvelopeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    tick: int = Field(..., ge=0)
    sent_at: datetime = Field(default_factory=_utc_now)


class HandshakeMsg(_EnvelopeBase):
    """First message exchanged on a new WebSocket connection."""

    kind: Literal["handshake"] = "handshake"
    peer: Literal["g-gear", "macbook", "godot"]
    capabilities: list[str] = Field(default_factory=list)


class AgentUpdateMsg(_EnvelopeBase):
    """Bulk snapshot of an agent (G-GEAR → MacBook)."""

    kind: Literal["agent_update"] = "agent_update"
    agent_state: AgentState


class SpeechMsg(_EnvelopeBase):
    """An agent uttered something (G-GEAR → MacBook → Godot speech bubble)."""

    kind: Literal["speech"] = "speech"
    agent_id: str
    utterance: str
    zone: Zone
    emotion: PlutchikDimension | None = None


class MoveMsg(_EnvelopeBase):
    """Locomotion intent for an agent (G-GEAR → MacBook → Godot nav)."""

    kind: Literal["move"] = "move"
    agent_id: str
    target: Position
    speed: float = Field(..., ge=0.0, description="Metres per second.")


class AnimationMsg(_EnvelopeBase):
    """Animation state change (walk / idle / sit_seiza / bow …)."""

    kind: Literal["animation"] = "animation"
    agent_id: str
    animation_name: str
    loop: bool = False


class WorldTickMsg(_EnvelopeBase):
    """Global clock pulse (G-GEAR → MacBook, heartbeat)."""

    kind: Literal["world_tick"] = "world_tick"
    wall_clock: datetime = Field(default_factory=_utc_now)
    active_agents: int = Field(..., ge=0)


class ErrorMsg(_EnvelopeBase):
    """Structured error for observability."""

    kind: Literal["error"] = "error"
    code: str
    detail: str


class DialogInitiateMsg(_EnvelopeBase):
    """An agent requests to start a dialog with another agent (M4 foundation).

    The scheduler decides whether to admit the request (backpressure, zone
    constraints, existing dialog state). Admission logic lives in
    ``m4-multi-agent-orchestrator``; this envelope only captures the intent.
    """

    kind: Literal["dialog_initiate"] = "dialog_initiate"
    initiator_agent_id: str
    target_agent_id: str
    zone: Zone


class DialogTurnMsg(_EnvelopeBase):
    """A single turn inside an ongoing dialog (M4 foundation).

    ``speaker_id`` and ``addressee_id`` are both carried so Godot can drive
    the correct animations (speech bubble / head-turn) without re-deriving
    orientation from world state.

    ``turn_index`` was added in M5 (0.3.0-m5) so consumers can (a) detect
    out-of-order delivery over WebSocket and (b) correlate with
    :attr:`Cognitive.dialog_turn_budget` for exhaustion close-out. The first
    turn of a dialog is ``turn_index=0`` and the value increases by 1 per
    emitted :class:`DialogTurnMsg`.
    """

    kind: Literal["dialog_turn"] = "dialog_turn"
    dialog_id: str
    speaker_id: str
    addressee_id: str
    utterance: str
    turn_index: int = Field(
        ...,
        ge=0,
        description=(
            "Monotonic 0-based index within the dialog. Increments by 1 per "
            "emitted turn across both speakers. Paired with "
            "``Cognitive.dialog_turn_budget`` to drive the exhaustion close."
        ),
    )


class ReasoningTraceMsg(_EnvelopeBase):
    """The cognition cycle emitted structured reasoning for this agent (M6-A-3).

    Carries a :class:`ReasoningTrace` over the wire to the Godot xAI
    visualisation (``ReasoningPanel`` / ``SynapseGraph``). Independent of
    :class:`AgentUpdateMsg` because the trace may be absent on any given
    tick (the LLM is free to fill or omit the rationale fields); bundling
    it into ``AgentUpdateMsg`` would force every tick to pay the schema
    cost of always-optional fields.
    """

    kind: Literal["reasoning_trace"] = "reasoning_trace"
    trace: ReasoningTrace


class ReflectionEventMsg(_EnvelopeBase):
    """A reflection distillation fired for this agent (M6-A-4).

    :class:`ReflectionEvent` is an internal domain type that
    :class:`~erre_sandbox.cognition.reflection.Reflector` has been producing
    since M4, but it was never routed over the wire — Godot had no way to
    show the researcher *"this is the summary the agent wrote of the last
    few minutes"*. M6-A-4 wraps the same domain object in this envelope so
    the xAI :class:`ReasoningPanel` can present it in a collapsible section
    without Godot having to replicate the trigger / distillation policy.

    The wrapped :class:`ReflectionEvent` is unchanged on the wire; existing
    Python consumers that already handle the domain type do not need to
    change. Only the envelope discriminator value ``reflection_event`` is
    new (and covered by the ``SCHEMA_VERSION`` bump to 0.4.0-m6).
    """

    kind: Literal["reflection_event"] = "reflection_event"
    event: ReflectionEvent


class ZoneLayout(BaseModel):
    """One zone centroid in :class:`WorldLayoutMsg` (M7γ).

    Mirrors the in-process ``ZONE_CENTERS`` table from
    :mod:`erre_sandbox.world.zones`. Sent once per WS connection so the Godot
    :class:`BoundaryLayer` can replace its hard-coded ``zone_rects`` with
    server-authored coordinates without polling.
    """

    model_config = ConfigDict(extra="forbid")

    zone: Zone
    x: float
    y: float
    z: float


class PropLayout(BaseModel):
    """One static prop row in :class:`WorldLayoutMsg` (M7γ).

    Mirrors :class:`~erre_sandbox.world.zones.PropSpec` over the wire and
    matches the affordance fields of :class:`AffordanceEvent` so Godot can
    place the prop without a separate prop-catalogue lookup.
    """

    model_config = ConfigDict(extra="forbid")

    prop_id: str
    prop_kind: str
    zone: Zone
    x: float
    y: float
    z: float
    salience: _Unit = 0.5


class WorldLayoutMsg(_EnvelopeBase):
    """Per-session single-shot world layout snapshot (M7γ, on-connect).

    Carries the static zone centroids and prop coordinates that the Godot
    :class:`BoundaryLayer` and ``BaseTerrain`` need to draw the world. In γ
    the layout is immutable per run, so the gateway emits exactly one
    :class:`WorldLayoutMsg` immediately before the handshake-completing
    ``registry.add(...)`` call; differential updates are out of scope until
    a runtime mutates :data:`~erre_sandbox.world.zones.ZONE_CENTERS`.

    ``tick=0`` is conventional (the snapshot logically belongs to session
    setup, not to any in-progress tick) and is asserted by the
    ``test_envelope_fixtures.py`` shared-invariant test.
    """

    kind: Literal["world_layout"] = "world_layout"
    zones: list[ZoneLayout] = Field(
        default_factory=list,
        description="One row per :class:`Zone` enum member, in declaration order.",
    )
    props: list[PropLayout] = Field(
        default_factory=list,
        description=(
            "Flattened ``ZONE_PROPS`` rows — one entry per prop, "
            "iterated zone-by-zone. Empty when no zone declares props."
        ),
    )


class DialogCloseMsg(_EnvelopeBase):
    """A dialog has ended (M4 foundation).

    ``reason`` is a closed literal set so the gateway and the scheduler can
    dispatch on it without string matching.

    M5 adds ``"exhausted"`` to signal that the agent hit its
    :attr:`Cognitive.dialog_turn_budget` cap (distinct from the
    scheduler's ``"timeout"``, which is driven by wall-clock).
    """

    kind: Literal["dialog_close"] = "dialog_close"
    dialog_id: str
    reason: Literal["completed", "interrupted", "timeout", "exhausted"]


ControlEnvelope: TypeAlias = Annotated[
    HandshakeMsg
    | AgentUpdateMsg
    | SpeechMsg
    | MoveMsg
    | AnimationMsg
    | WorldTickMsg
    | ErrorMsg
    | DialogInitiateMsg
    | DialogTurnMsg
    | DialogCloseMsg
    | ReasoningTraceMsg
    | ReflectionEventMsg
    | WorldLayoutMsg,
    Field(discriminator="kind"),
]
"""Discriminated union of all WebSocket envelope kinds."""


# =============================================================================
# §7.x InboundEnvelope (client -> server only, separate from ControlEnvelope)
# =============================================================================


class WorldPerturbationMsg(_EnvelopeBase):
    """Bounded inbound world stimulus from Godot (client -> server only).

    Deliberately **not** a member of :data:`ControlEnvelope` (HIGH-3,
    ``design-final.md`` DA-2) — see :data:`InboundEnvelope` for why. Carries
    a *world stimulus* that the gateway's inbound sink maps to a
    :class:`PerceptionEvent` (``integration.inbound.world_perturbation_to_perception``);
    it is never a direct knob/mode/destination override, so a client cannot
    use it to bypass the cognition loop.

    ``correlation_id`` is owned here — not added to :class:`PerceptionEvent`
    — so the closure's reachability witness can trace a perturbation across
    seams (perturbation -> perception -> capture -> emitted envelope)
    without widening any existing observation/outbound schema (grill G2).
    Empty string (the default) means "the inbound sink assigns one on
    enqueue"; a client may also supply its own.
    """

    kind: Literal["world_perturbation"] = "world_perturbation"
    target_agent_id: str = Field(
        ...,
        description=(
            "The agent this stimulus is aimed at. Existence against the "
            "live agent registry is validated by the gateway/loop wiring "
            "(a later issue), not by this schema."
        ),
    )
    modality: Literal["sight", "sound", "smell", "touch", "proprioception"]
    source_zone: Zone
    content: str = Field(..., max_length=512)
    intensity: _Unit = 0.5
    correlation_id: str = Field(default="", max_length=64)


InboundEnvelope: TypeAlias = WorldPerturbationMsg
"""Client -> server inbound union — a separate system from :data:`ControlEnvelope`.

Deliberately kept out of ``ControlEnvelope`` (HIGH-3, ``design-final.md``
DA-2): that union is outbound-only (server -> client, 13 kinds) and
``test_envelope_kind_sync.py`` pins its kind set 1:1 against
``EnvelopeRouter.gd``'s hand-coded ``match`` block. Folding an inbound kind
into it would force a Godot-side receive branch for a message Godot only
ever *sends*, plus a wire-protocol / ``SCHEMA_VERSION`` review this closure
does not need (outbound protocol is unchanged).

Only one member today, so this is a plain alias rather than
``Annotated[X | Y, Field(discriminator=...)]`` — pydantic's discriminated
union needs an actual multi-member ``Union`` to dispatch on, and there is
nothing to discriminate between yet. ``pydantic.TypeAdapter(InboundEnvelope)``
still validates and rejects correctly today: a plain alias resolves to
``TypeAdapter(WorldPerturbationMsg)``, whose inherited
``model_config = ConfigDict(extra="forbid")`` (from ``_EnvelopeBase``)
already rejects any payload that isn't a well-formed
``WorldPerturbationMsg`` — including one tagged with an outbound ``kind``
such as ``"move"``. When a second inbound kind is added, promote this alias
to the ``Annotated`` discriminated-union form.
"""


# =============================================================================
# §7.5 DialogScheduler (interface only, M4 foundation)
# =============================================================================


class DialogScheduler(Protocol):
    """Interface for agent-to-agent dialog orchestration (M4 foundation).

    Contract-only: the concrete turn-taking policy, backpressure, and timeout
    handling is the responsibility of ``m4-multi-agent-orchestrator``. This
    Protocol is frozen here so that ``cognition`` and ``world`` can type-hint
    against it in parallel tasks without waiting for the implementation.

    Methods return envelope messages (or ``None``) so the gateway can
    broadcast them over WebSocket without an additional marshalling layer.
    """

    def schedule_initiate(
        self,
        initiator_id: str,
        target_id: str,
        zone: Zone,
        tick: int,
    ) -> DialogInitiateMsg | None:
        """Decide whether to admit a new dialog and emit the initiate envelope.

        ``None`` means the scheduler rejected the request (e.g. existing
        dialog, cooldown, zone mismatch). Non-``None`` is the envelope to
        broadcast.
        """
        ...

    def record_turn(self, turn: DialogTurnMsg) -> None:
        """Record a turn in the dialog's transcript for later close/replay."""
        ...

    def close_dialog(
        self,
        dialog_id: str,
        reason: Literal["completed", "interrupted", "timeout", "exhausted"],
        *,
        tick: int | None = None,
    ) -> DialogCloseMsg:
        """Close an open dialog and emit the close envelope.

        ``tick`` is a non-breaking optional keyword-only extension added
        2026-04-28 (codex review F1) so callers that know the current world
        tick (timeout sweep, exhausted budget) can record the actual close
        tick instead of falling back to ``last_activity_tick``. Implementations
        that ignore ``tick`` keep the M4 frozen behaviour, so the wire
        contract is unchanged.
        """
        ...

    def transcript_of(self, dialog_id: str) -> list[DialogTurnMsg]:
        """Return the accumulated transcript of ``dialog_id``.

        Added for M5 ``m5-orchestrator-integration``: the tick-level turn
        driver in :class:`~erre_sandbox.world.tick.WorldRuntime` reads the
        transcript length to derive ``turn_index`` and alternate the
        speaker. Returns an empty list for unknown / closed dialogs so
        callers can iterate without guarding on membership. The
        interface-only addition does **not** bump the wire contract
        (``SCHEMA_VERSION``): no on-wire field gained/lost.
        """
        ...

    def iter_open_dialogs(self) -> Iterator[tuple[str, str, str, Zone]]:
        """Yield ``(dialog_id, initiator_id, target_id, zone)`` for each open dialog.

        Added for M5 ``m5-orchestrator-integration`` alongside
        :meth:`transcript_of`. Lets the runtime's turn driver enumerate
        live dialogs without querying ``(a, b) → dialog_id`` for every
        registered pair. Implementations must not expose closed dialogs.
        Read-only: callers must mutate state only through
        :meth:`record_turn` / :meth:`close_dialog`.
        """
        ...


class ERREModeTransitionPolicy(Protocol):
    """Interface for the ERRE-mode finite-state machine (M5 foundation).

    Contract-only: the concrete transition table (zone entry, fatigue, shuhari
    promotion, manual override, …) is the responsibility of
    ``m5-erre-mode-fsm``. This Protocol is frozen here so ``cognition`` and
    ``world`` can type-hint against it in parallel sub-tasks without waiting
    for the implementation.

    Implementations decide at each world tick whether the agent should leave
    its current :class:`ERREMode`. Returning ``None`` means "no change";
    returning a mode value means the caller must emit
    :class:`ERREModeShiftEvent` and update :attr:`AgentState.erre`.
    """

    def next_mode(
        self,
        *,
        current: ERREModeName,
        zone: Zone,
        observations: Sequence[Observation],
        tick: int,
    ) -> ERREModeName | None:
        """Decide whether to transition the agent's ERRE mode this tick.

        ``None`` = keep ``current``. A non-``None`` value is the new mode and
        must differ from ``current`` (callers should skip emitting a shift
        event when the values match).
        """
        ...


class DialogTurnGenerator(Protocol):
    """Interface for LLM-driven dialog turn generation (M5 foundation).

    Contract-only: the concrete LLM call, prompt builder, sampling overrides,
    and exhausted-close handling live in ``m5-dialog-turn-generator`` per the
    empirical findings of the M5 LLM spike.
    Freezing this Protocol in the schemas module lets the M5 orchestrator
    wire arbitrary implementations (Ollama adapter, mocked generator) without
    depending on the inference layer.

    Returning ``None`` signals that the implementation declined to produce a
    turn (for instance, the LLM returned an empty string after sanitisation).
    The caller is expected to treat that as a soft close and fall back to
    :class:`DialogCloseMsg`.
    """

    async def generate_turn(
        self,
        *,
        dialog_id: str,
        speaker_state: AgentState,
        speaker_persona: PersonaSpec,
        addressee_state: AgentState,
        transcript: Sequence[DialogTurnMsg],
        world_tick: int,
    ) -> DialogTurnMsg | None:
        """Produce the next turn for ``speaker_state`` or ``None`` to decline."""
        ...


# =============================================================================
# §8 Public surface
# =============================================================================

__all__ = [
    "SCHEMA_VERSION",
    "AffordanceEvent",
    "AgentSpec",
    "AgentState",
    "AgentUpdateMsg",
    "AgentView",
    "AnimationMsg",
    "BiorhythmEvent",
    "Cognitive",
    "CognitiveHabit",
    "ControlEnvelope",
    "DialogCloseMsg",
    "DialogInitiateMsg",
    "DialogScheduler",
    "DialogTurnGenerator",
    "DialogTurnMsg",
    "ERREMode",
    "ERREModeName",
    "ERREModeShiftEvent",
    "ERREModeTransitionPolicy",
    "EpochPhase",
    "ErrorMsg",
    "HabitFlag",
    "HandshakeMsg",
    "InboundEnvelope",
    "InternalEvent",
    "LocomotionState",
    "MemoryEntry",
    "MemoryKind",
    "MoveMsg",
    "Observation",
    "PerceptionEvent",
    "PersonaSpec",
    "PersonalityTraits",
    "Physical",
    "PlutchikDimension",
    "Position",
    "PropLayout",
    "ProximityEvent",
    "ReasoningTrace",
    "ReasoningTraceMsg",
    "ReflectionEvent",
    "ReflectionEventMsg",
    "RelationshipBond",
    "RunLifecycleState",
    "SamplingBase",
    "SamplingDelta",
    "SemanticMemoryRecord",
    "ShuhariStage",
    "SpatialContext",
    "SpeechEvent",
    "SpeechMsg",
    "TemporalEvent",
    "TimeOfDay",
    "TriggerEventTag",
    "WorldLayoutMsg",
    "WorldPerturbationMsg",
    "WorldTickMsg",
    "Zone",
    "ZoneLayout",
    "ZoneTransitionEvent",
]
