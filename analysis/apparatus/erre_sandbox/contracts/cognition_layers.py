"""Two-layer cognition contract (M10-A scaffold, *not yet wired to runtime*).

This module freezes the Pydantic schema for the planned **two-layer cognitive
architecture** (``docs/architecture.md`` §9.2, design-final.md §1):

* :class:`PhilosopherBase` — the **immutable** substrate inherited from the
  Extract/Reverify pipeline (``persona_id`` / cognitive habits / sampling /
  preferred zones). Drift-forbidden per the *不可侵原則* (architecture.md §9.3).
* :class:`IndividualProfile` — the **mutable** runtime individual that grows on
  top of a base: subjective world model, development stage, narrative arc and a
  bounded personality drift offset.

**M10-A is schema-only.** Nothing here is read or written by the cognition
cycle yet — SubjectiveWorldModel synthesis lands in M10-B and the
:class:`WorldModelUpdateHint` ingestion in M10-C. The feature flag
:class:`IndividualLayerConfig` defaults *off* and is **not** injected into
``BootConfig`` / ``CognitionCycle`` at this milestone (declaration only).

Design constraints baked into the schema
-----------------------------------------
* **LLM = candidate, Python = authority** (架构.md §9.3, design-final §1.4):
  the only LLM-facing primitive, :class:`WorldModelUpdateHint`, is a bounded
  3-value ``direction`` with mandatory ``cited_memory_ids`` — never a free-form
  belief blob. State transitions remain a future Python concern (M10-C+).
* **Immutable base = cache-safe prefix**: :class:`PhilosopherBase` is
  ``frozen=True`` *and* uses ``tuple`` collections plus frozen snapshot members
  (:class:`FrozenCognitiveHabit` / :class:`FrozenSamplingParam`) so a base block
  is byte-stable per ``persona_id`` for SGLang RadixAttention prefix sharing.
* **LoRA path is closed**: :attr:`PhilosopherBase.lora_adapter_id` is typed
  ``None`` (not ``str | None``) — the Plan B kant LoRA program was rejected and
  terminated, baseline is no-LoRA / prompt-persona. The field is retained for
  design-final lineage but accepts only ``None`` until a future milestone
  explicitly re-opens it.

Semantic notes that would otherwise live in ``schemas.py``
----------------------------------------------------------
These are recorded here rather than as edits to ``schemas.py``, because
``tests/test_schema_contract.py`` pins the ``json_schema()`` of ``AgentState``
/ ``PersonaSpec`` / ``ControlEnvelope`` (descriptions included) to golden files
and editing those descriptions would force a golden regeneration that conflicts
with the M10-A ``SCHEMA_VERSION`` non-bump:

* ``AgentState.persona_id`` is the **base reference** — it points at the
  :class:`PhilosopherBase` a live agent inherits from and is mirrored by
  :attr:`IndividualProfile.base_persona_id`. No getter is added; the existing
  direct ``str`` field stays the compatibility surface.
* ``Cognitive.shuhari_stage`` means **base-side skill acquisition** (how far an
  individual has internalised the base's cognitive habits, e.g. Kant's walk).
  It is orthogonal to :class:`DevelopmentState`, which tracks the individual's
  *lifecycle* (S1→S3). The two must not be conflated.

Cross-reference: the per-row DuckDB flag
:data:`erre_sandbox.contracts.eval_paths.INDIVIDUAL_LAYER_ENABLED_KEY`
(``"individual_layer_enabled"``) is the **training-egress / contamination
sibling** of the runtime :class:`IndividualLayerConfig`; they share the concept
("is the individual layer active?") but live in different layers and are
intentionally not unified.

Layer rule (``contracts`` package): this module imports only
:mod:`erre_sandbox.schemas`, pydantic and the standard library — never a
heavier layer. The invariant is enforced by
``tests/test_architecture/test_layer_dependencies.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

# HabitFlag / Zone appear in Pydantic field annotations below, so they must be
# importable at runtime (Pydantic resolves them at model-build time). PersonaSpec
# is used only in the ``from_persona_spec`` signature, so it is type-only.
from erre_sandbox.schemas import HabitFlag, Zone  # noqa: TC001

if TYPE_CHECKING:
    from erre_sandbox.schemas import PersonaSpec

# ---------------------------------------------------------------------------
# Shared literal vocabularies
# ---------------------------------------------------------------------------

WorldModelAxis: TypeAlias = Literal["env", "concept", "self", "norm", "temporal"]
"""Five subjective world-model axes (design-final §1.1).

``env`` (environment), ``concept`` (abstract ideas), ``self`` (self-model),
``norm`` (values / oughts) and ``temporal`` (time horizon). Dyadic relational
belief is *not* an axis here — that stays in
``SemanticMemoryRecord.belief_kind`` (class-wise vs dyadic orthogonality).
"""

UpdateDirection: TypeAlias = Literal["strengthen", "weaken", "no_change"]
"""Bounded 3-value direction an LLM may *request* for a world-model entry.

Free-form belief assertions are deliberately impossible to express; the LLM is
a candidate, Python is the authority (M10-C will verify ``cited_memory_ids``
before applying anything).
"""

DevelopmentStage: TypeAlias = Literal["S1_seed", "S2_exploring", "S3_consolidated"]
"""Individual lifecycle stages S1–S3 only.

S4/S5 are deferred to an M12+ research gate; the late-stage analogue is covered
by confidence saturation instead.
"""


# ---------------------------------------------------------------------------
# Frozen snapshot members of the immutable base
# ---------------------------------------------------------------------------


class FrozenSamplingParam(BaseModel):
    """Immutable mirror of :class:`erre_sandbox.schemas.SamplingBase`.

    A deep-copied, frozen snapshot so a :class:`PhilosopherBase` cannot have its
    sampling drift after construction (the live ``SamplingBase`` is mutable and
    reused elsewhere). Bounds mirror ``SamplingBase`` exactly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.0, ge=0.5, le=2.0)


class FrozenCognitiveHabit(BaseModel):
    """Immutable mirror of :class:`erre_sandbox.schemas.CognitiveHabit`.

    Frozen snapshot of one recurring cognitive-behavioural pattern so the base
    layer is deeply immutable (the source ``CognitiveHabit`` is a mutable
    Pydantic model). The field set *and constraints* mirror ``CognitiveHabit``
    exactly (bare required strings, no ``min_length``) so a ``model_dump()``
    round-trips without remapping and :meth:`PhilosopherBase.from_persona_spec`
    never rejects an input that ``CognitiveHabit`` itself accepts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str
    source: str
    flag: HabitFlag
    mechanism: str
    trigger_zone: Zone | None = None


# ---------------------------------------------------------------------------
# Layer 1 — immutable PhilosopherBase
# ---------------------------------------------------------------------------


class PhilosopherBase(BaseModel):
    """Immutable inheritance from the Extract/Reverify pipeline.

    Deeply immutable (``frozen=True`` + ``tuple`` collections + frozen members)
    so a base block is byte-stable per ``persona_id`` for SGLang RadixAttention
    prefix sharing. The individual layer never mutates it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    persona_id: str
    display_name: str
    era: str
    cognitive_habits: tuple[FrozenCognitiveHabit, ...] = Field(min_length=1)
    default_sampling: FrozenSamplingParam = Field(default_factory=FrozenSamplingParam)
    preferred_zones: tuple[Zone, ...] = ()
    primary_corpus_refs: tuple[str, ...] = ()
    lora_adapter_id: None = Field(
        default=None,
        description=(
            "LoRA path is closed (Plan B kant rejected + terminated). Typed "
            "``None`` so the schema rejects any adapter id until a future "
            "milestone explicitly re-opens the field."
        ),
    )

    @classmethod
    def from_persona_spec(cls, spec: PersonaSpec) -> PhilosopherBase:
        """Project a loaded :class:`PersonaSpec` into an immutable base.

        A narrow, deep-copying projection: ``personality`` / ``behavior_profile``
        / ``schema_version`` are dropped, mutable members are snapshotted into
        their frozen mirrors (breaking any aliasing with *spec*), and
        ``lora_adapter_id`` is pinned to ``None``.

        Args:
            spec: A persona loaded from ``personas/*.yaml`` (no YAML rename;
                ``schema_version 0.10.0-m7h`` is preserved on the source).

        Returns:
            A frozen :class:`PhilosopherBase` that shares no mutable state with
            *spec*.
        """
        return cls(
            persona_id=spec.persona_id,
            display_name=spec.display_name,
            era=spec.era,
            cognitive_habits=tuple(
                FrozenCognitiveHabit(**habit.model_dump())
                for habit in spec.cognitive_habits
            ),
            default_sampling=FrozenSamplingParam(**spec.default_sampling.model_dump()),
            preferred_zones=tuple(spec.preferred_zones),
            primary_corpus_refs=tuple(spec.primary_corpus_refs),
            lora_adapter_id=None,
        )


# ---------------------------------------------------------------------------
# Layer 2 — mutable IndividualProfile and its parts
# ---------------------------------------------------------------------------


class WorldModelEntry(BaseModel):
    """One bounded, evidence-cited belief on a subjective world-model axis."""

    model_config = ConfigDict(extra="forbid")

    axis: WorldModelAxis
    key: str = Field(min_length=1)
    value: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    cited_memory_ids: tuple[str, ...] = Field(min_length=1)
    last_updated_tick: int = Field(ge=0)
    decay_half_life_ticks: int = Field(default=1000, ge=1)


class SubjectiveWorldModel(BaseModel):
    """A bounded 5-axis subjective world view (≤ 50 entries / individual)."""

    model_config = ConfigDict(extra="forbid")

    entries: list[WorldModelEntry] = Field(default_factory=list, max_length=50)


class WorldModelSnapshot(BaseModel):
    """Immutable read-model of a per-agent world-model runtime state (M11-C1).

    The contracts-layer twin of ``cognition.world_model.WorldModelRuntimeState``:
    it carries the same ``base_floor`` + ``modulated`` pair, but holds **no
    reconcile logic** — it is a pure snapshot captured for eval / persist /
    cross-layer hand-off. The runtime type stays in ``cognition/``
    (moving it into ``contracts`` would force a ``contracts → cognition`` import).
    ``cognition.world_model.project_world_model_snapshot`` deep-copies the live
    state into this type so a snapshot can never alias — and therefore never
    mutate — the single-source ``AgentRuntime`` (owner single source).

    The matching field *shape* is intentional and not a harmful duplication: the
    responsibilities differ (runtime = cognition reconcile carrier, snapshot =
    contracts read-model).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_floor: SubjectiveWorldModel
    modulated: SubjectiveWorldModel


class PromotedEvidenceUnit(BaseModel):
    """One promoted dyad's raw evidence — the H2 conformance substrate (M10-A 段B).

    A serialisable projection of the ``(SemanticMemoryRecord, RelationshipBond)``
    pair that ``cognition.world_model.synthesize_world_model`` distils per dyad.
    The synthesised :class:`SubjectiveWorldModel` aggregates dyads away
    (``_derive_env`` zone-means, ``_derive_self`` dyad-means), so the per-dyad
    raw value cannot be recovered from the entries; the H2 value-aware
    conformance gate (stage-A ADR §6) needs the *raw* unit to recompute both the
    observed ``(axis,key)``-intersection distance and the owner-shuffle null.

    Field names are the **canonical** ``RelationshipBond`` / ``SemanticMemoryRecord``
    names (no abbreviation) so the persisted JSON stays readable for the future
    recompute / owner-shuffle-reconstruction invariant (stage-A ADR §6, null-control
    §4.1): a null re-synthesis re-owners each unit while keeping ``other_agent_id``
    fixed and rebuilding ``record.id = belief_record_id(new_owner, other_agent_id)``.
    ``other_agent_id`` is therefore the only identity field the unit must carry
    (the owner is the trace row's ``individual_id``; ``record.id`` is deterministic).

    All fields mirror their source bounds. ``belief_kind`` / ``last_interaction_zone``
    / ``last_interaction_tick`` are optional (the bond may have no last zone/tick);
    a promoted record always carries a non-``None`` ``belief_kind`` but the type
    stays ``str | None`` to mirror :attr:`SemanticMemoryRecord.belief_kind`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    other_agent_id: str = Field(min_length=1)
    belief_kind: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    affinity: float = Field(ge=-1.0, le=1.0)
    familiarity: float = Field(ge=0.0, le=1.0)
    last_interaction_zone: Zone | None = None
    last_interaction_tick: int | None = Field(default=None, ge=0)


class DevelopmentState(BaseModel):
    """Individual lifecycle stage with a hidden continuous maturity score.

    ``stage`` is a view; the continuous ``maturity_score`` and the
    ``transition_evidence`` counts are what an (M11-B) Python transition would
    read. S1–S3 only.
    """

    model_config = ConfigDict(extra="forbid")

    stage: DevelopmentStage = "S1_seed"
    maturity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    transition_evidence: dict[str, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict,
        description=(
            "Non-negative observable-evidence counts keyed by free-form "
            "evidence-type labels (the exact key vocabulary is fixed by the "
            "M11-B transition machinery, not constrained here)."
        ),
    )


class ArcSegment(BaseModel):
    """One evidence-backed segment of a :class:`NarrativeArc`.

    Structured trajectory, *not* free-form prose: the label and optional
    diagnostic summary are length-bounded and every segment must cite memory.
    ``end_tick == start_tick`` is permitted (a point-in-time segment).
    """

    model_config = ConfigDict(extra="forbid")

    segment_label: str = Field(min_length=1, max_length=120)
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    cited_memory_ids: tuple[str, ...] = Field(min_length=1)
    summary: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_tick_order(self) -> ArcSegment:
        if self.end_tick < self.start_tick:
            msg = (
                f"ArcSegment.end_tick ({self.end_tick}) must be >= start_tick "
                f"({self.start_tick})"
            )
            raise ValueError(msg)
        return self


class NarrativeArc(BaseModel):
    """A periodically distilled structured trajectory (≤ 5 segments).

    ``coherence_score`` is the cosine similarity between recent utterance
    embeddings and the SWM (design-final §1.4); it is diagnostic only until
    M11-A measures its false-positive rate.
    """

    model_config = ConfigDict(extra="forbid")

    synthesized_at_tick: int = Field(ge=0)
    arc_segments: list[ArcSegment] = Field(default_factory=list, max_length=5)
    coherence_score: float = Field(ge=-1.0, le=1.0)
    last_episodic_pointer: str = Field(min_length=1)


class PersonalityDrift(BaseModel):
    """Bounded Big-Five drift offset (± 0.1 per axis, evidence-driven).

    ERRE-specific aesthetic traits (``wabi`` / ``ma_sense``) are intentionally
    excluded to keep the drift boundary crisp.
    """

    model_config = ConfigDict(extra="forbid")

    openness: float = Field(default=0.0, ge=-0.1, le=0.1)
    conscientiousness: float = Field(default=0.0, ge=-0.1, le=0.1)
    extraversion: float = Field(default=0.0, ge=-0.1, le=0.1)
    agreeableness: float = Field(default=0.0, ge=-0.1, le=0.1)
    neuroticism: float = Field(default=0.0, ge=-0.1, le=0.1)


class IndividualProfile(BaseModel):
    """Immutable snapshot read-model of a live individual (M11-C1).

    Built on top of an immutable :class:`PhilosopherBase`. The **live home** of
    the per-agent state stays on ``world.tick.AgentRuntime`` (mutable fields, hot
    loop); this profile is a *derived* snapshot produced by
    ``AgentRuntime.snapshot_profile()`` for capture / eval / persist — the state
    is never duplicated as a second source of truth (owner single source).

    The three carried fields are all ``... | None``:
    ``None`` faithfully records "not yet present" — flag-off, or a flag-on tick
    before the first synthesis / advance — and is **not** materialised into a
    default (which would fabricate an unobserved state, e.g. a phantom S1_seed).
    An empty :class:`SubjectiveWorldModel` is a valid "no beliefs yet" state, so
    only ``None`` can mean "not yet synthesised" — hence ``world_model`` is also
    optional rather than defaulting to an empty model.
    """

    model_config = ConfigDict(extra="forbid")

    individual_id: str = Field(min_length=1)
    base_persona_id: str = Field(min_length=1)
    world_model: WorldModelSnapshot | None = None
    development_state: DevelopmentState | None = None
    narrative_arc: NarrativeArc | None = None
    personality_drift_offset: PersonalityDrift = Field(default_factory=PersonalityDrift)


# ---------------------------------------------------------------------------
# LLM-facing bounded primitive (defined now, ingested in M10-C)
# ---------------------------------------------------------------------------


class WorldModelUpdateHint(BaseModel):
    """A bounded request from the LLM to nudge a world-model entry.

    The LLM proposes; Python disposes. ``direction`` is a closed 3-value set and
    ``cited_memory_ids`` is mandatory so M10-C can verify the cited ids are a
    subset of the turn's retrieved memories before applying anything.
    """

    model_config = ConfigDict(extra="forbid")

    axis: WorldModelAxis
    # Bounded lengths fail-fast at parse on the untrusted LLM boundary (M10-C
    # security review MEDIUM-1/2): they cap set-construction cost for the cited
    # subset check and keep a malformed key out of any log/render path. The real
    # authority is still the entry-local citation subset check in
    # ``world_model.apply_world_model_update_hint`` — these are defence in depth.
    key: str = Field(min_length=1, max_length=64)
    direction: UpdateDirection
    cited_memory_ids: tuple[str, ...] = Field(min_length=1, max_length=16)


HintDisposition: TypeAlias = Literal[
    "not_emitted",
    "adopted",
    "rejected_not_displayed",
    "rejected_citation",
    "rejected_no_change",
    "rejected_no_effect",
]
"""Per-tick disposition of a world-model update hint (engagement instrument ADR §2).

A closed vocabulary that mirrors the authority function's reachable outcomes:
``not_emitted`` (the LLM produced no hint this tick, layer-1 state (a)),
``adopted`` (``apply_world_model_update_hint`` returned a nudged SWM), and the four
mutually-exclusive ``rejected_*`` reasons that subdivide a ``None`` return (the
authority's four reject predicates, in order; layer-2 state (b)). The shadow
classifier in ``cognition.hint_engagement`` assigns the reason; the loader never
re-runs it — it aggregates the stored label (faithfulness fixed at cycle time)."""


class WorldModelHintDisposition(BaseModel):
    """Observed disposition of this tick's world-model update hint (instrument ADR §3).

    A pure read-model carried out on :class:`~erre_sandbox.cognition.cycle.CycleResult`
    so the ``world`` trace sink can persist it without importing ``cognition`` or
    ``evidence``. It records *what happened* to the hint — never drives control. The
    ``adopted`` headline mirrors the authority function's real return
    (``apply_world_model_update_hint is not None``); the ``rejected_*`` subdivision is
    the shadow classifier's, pinned to the authority by a conformance property test.

    ``frozen`` + ``extra='forbid'``: an instrument carrier is immutable substrate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_status: Literal["ok", "unavailable", "unparseable"]
    """Whether the LLM produced a parseable plan this tick (Codex HIGH-1).

    ``ok`` on the normal path; ``unavailable`` / ``unparseable`` on the two fallback
    ticks that return before step 7.5. The loader counts emission only over
    ``llm_status='ok'`` eligible ticks so a transient outage cannot inflate the
    emission-rate denominator."""
    emitted: bool
    """Layer-1: the LLM emitted a hint this tick (``plan.world_model_update_hint is
    not None``). Always ``False`` when ``disposition='not_emitted'``."""
    disposition: HintDisposition
    """Layer-2 outcome — the closed disposition vocabulary."""
    target_axis: WorldModelAxis | None
    """The hinted entry's axis, or ``None`` iff ``disposition='not_emitted'``."""
    target_key: str | None
    """The hinted entry's key, or ``None`` iff ``disposition='not_emitted'``."""
    direction: UpdateDirection | None
    """The hint's requested direction, or ``None`` iff ``disposition='not_emitted'``."""
    adopted_signed_step: float
    """Measured ``new_value - old_value`` of the nudged entry (instrument ADR §4 /
    補強 §1).

    The real delta the authority applied — **not** a hardcoded ``+/-VALUE_STEP``:
    ``_nudge_value``'s ``weaken`` clamps at 0, so a near-zero entry (e.g. ``0.03 ->
    0.0``) adopts with a sub-``VALUE_STEP`` step. ``0.0`` on every non-adopted tick."""
    exposed_entry_count: int
    """How many SWM entries were displayed this tick — eligibility / stratification,
    **not** a denominator (Codex LOW-3). Taken from the flag-on ``exposed_citations``
    size, available on both the normal and fallback paths."""


# ---------------------------------------------------------------------------
# Feature flag (declaration only at M10-A — not wired into runtime)
# ---------------------------------------------------------------------------


class IndividualLayerConfig(BaseModel):
    """Runtime toggle for the individual layer (``default off``).

    Declared as a frozen model (rather than a bare constant) so M10-B+ can add
    sibling knobs (decay overrides, injection top-K) additively. At M10-A it is
    **not** injected into ``BootConfig`` / ``CognitionCycle`` — wiring belongs
    to the milestone that actually consumes it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False

    stm_carry_enabled: bool = False
    """Fork III-a STM arm gate: carry a bounded LLM offset across a floor-fingerprint
    change for a bounded horizon (``reconcile_world_model(stm_carry=...)``).

    A sub-knob of :attr:`enabled` — only meaningful when the individual layer is on
    (the reconcile step runs only in the flag-on block). ``default off`` so an
    ``enabled=True`` run with this unset keeps the frozen drop-on-churn behaviour
    (the OFF arm / control). The eval CLI does not yet surface this flag (it is set
    by direct config injection for the arm contrast); CLI wiring is a later task."""


__all__ = [
    "ArcSegment",
    "DevelopmentStage",
    "DevelopmentState",
    "FrozenCognitiveHabit",
    "FrozenSamplingParam",
    "HintDisposition",
    "IndividualLayerConfig",
    "IndividualProfile",
    "NarrativeArc",
    "PersonalityDrift",
    "PhilosopherBase",
    "PromotedEvidenceUnit",
    "SubjectiveWorldModel",
    "UpdateDirection",
    "WorldModelAxis",
    "WorldModelEntry",
    "WorldModelHintDisposition",
    "WorldModelSnapshot",
    "WorldModelUpdateHint",
]
