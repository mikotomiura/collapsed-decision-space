"""Pure state-update functions for the cognition cycle.

The CSDG half-step formula (MASTER-PLAN appendix B.3, adopted as MVP
priority #2) is implemented here as side-effect-free functions so T12
``cycle.py`` can orchestrate without carrying any numeric math. The same
functions are directly unit-testable in :mod:`tests.test_cognition.test_state`
with a deterministic ``Random(seed)`` passed in.

Math (per field, per tick):

    base     = prev * (1 - decay_rate) + Σ (event_impact * event_weight)
    composed = base + clip(llm_delta, ±max_llm_delta) * llm_weight
             + gauss(0, noise_scale)

where ``prev`` is the previous tick's value, ``event_impact`` is an
event-type-specific contribution (0 for perception, negative for stressful
events, …), ``llm_delta`` comes from :class:`cognition.parse.LLMPlan`, and
``gauss(...)`` is deterministic when a seeded ``Random`` is injected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from erre_sandbox.schemas import Cognitive, Physical

if TYPE_CHECKING:
    from collections.abc import Sequence
    from random import Random

    from erre_sandbox.cognition.parse import LLMPlan
    from erre_sandbox.schemas import Observation

# Schema-declared ranges mirrored locally so we can clamp without importing
# them from pydantic (purely arithmetic code path).
_UNIT_MIN: Final[float] = 0.0
_UNIT_MAX: Final[float] = 1.0
_SIGNED_MIN: Final[float] = -1.0
_SIGNED_MAX: Final[float] = 1.0

_EMOTIONAL_CONFLICT_DECAY: Final[float] = 0.02
"""Per-tick decay applied to ``Physical.emotional_conflict`` (M7δ).

Pairs with the relational-sink write at
``world/tick.py::apply_affinity_delta`` (``+abs(delta)*0.5`` on negative
delta past ``-0.05``). A single -0.30 antagonism event raises
emotional_conflict by 0.15; with this decay it returns to baseline in
~7-8 ticks if no further negative event reinforces it.
"""

# Event-impact lookups. Keys are ``Observation.event_type`` literals.
# ``speech`` impact is ``|emotional_impact|`` taken from the event itself
# (see ``_event_impact``), so the lookup value is the scaling weight only.
#
# M6-A-2b additions (affordance / proximity / temporal / biorhythm):
# * affordance — positive scaled by salience (high-salience props pull the
#   agent's mood baseline up when noticed)
# * proximity — sign flips with ``crossing`` (enter → mild positive pull,
#   leave → mild negative)
# * temporal — flat tiny positive (a new time-of-day bucket is a fresh
#   stimulus; the FSM rather than mood is the primary consumer)
# * biorhythm — 0.0: the event is itself a readout of ``Physical``, feeding
#   it back would double-count. Present in the dict for discover-by-grep
#   completeness, not for numeric use.
_PHYSICAL_EVENT_IMPACT: Final[dict[str, float]] = {
    "perception": 0.0,
    "speech": 0.05,
    "zone_transition": 0.02,
    "erre_mode_shift": 0.03,
    "internal": 0.01,
    "affordance": 0.02,
    "proximity": 0.02,
    "temporal": 0.01,
    "biorhythm": 0.0,
}


@dataclass(frozen=True)
class StateUpdateConfig:
    """Knobs for CSDG half-step and LLM-delta composition.

    Defaults are MVP-calibrated (10-second tick, Kant in peripatos). M4+
    reflection will re-tune these after empirical runs — change via
    ``CognitionCycle(update_config=...)`` without touching this module.
    """

    decay_rate: float = 0.05
    event_weight: float = 0.15
    max_llm_delta: float = 0.3
    llm_weight: float = 0.7
    noise_scale: float = 0.02


DEFAULT_CONFIG: Final[StateUpdateConfig] = StateUpdateConfig()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _clamp_unit(value: float) -> float:
    return _clamp(value, _UNIT_MIN, _UNIT_MAX)


def _clamp_signed(value: float) -> float:
    return _clamp(value, _SIGNED_MIN, _SIGNED_MAX)


def _clip(value: float, bound: float) -> float:
    return _clamp(value, -bound, bound)


def _noise(rng: Random | None, scale: float) -> float:
    if rng is None or scale == 0.0:
        return 0.0
    return rng.gauss(0.0, scale)


def _event_impact(event: Observation) -> float:  # noqa: PLR0911 — discriminator dispatch
    """Signed impact of *event* on physical/mood baselines.

    Positive values nudge mood / energy up, negative down. Kept tiny so a
    single event never dominates the decay term within one tick.
    """
    if event.event_type == "speech":
        return _PHYSICAL_EVENT_IMPACT["speech"] * event.emotional_impact
    if event.event_type == "zone_transition":
        # Moving into a calmer zone has a tiny positive impact; direction is
        # not encoded in MVP so use the weight as-is (positive).
        return _PHYSICAL_EVENT_IMPACT["zone_transition"]
    if event.event_type == "erre_mode_shift":
        return _PHYSICAL_EVENT_IMPACT["erre_mode_shift"]
    if event.event_type == "internal":
        # importance_hint ∈ [0, 1] — pivot around 0.5 so low-importance
        # internal nudges slightly negative, high-importance slightly positive.
        return _PHYSICAL_EVENT_IMPACT["internal"] * (event.importance_hint - 0.5) * 2.0
    if event.event_type == "affordance":
        # salience ∈ [0, 1] — pivot around 0.5 so a mundane prop is neutral
        # and a highly salient one nudges mood upward (curiosity pull).
        return _PHYSICAL_EVENT_IMPACT["affordance"] * (event.salience - 0.5) * 2.0
    if event.event_type == "proximity":
        # Entering a peer's radius is a mild positive social pull; leaving
        # subtracts the same amount. Direction: "enter" → +, "leave" → −.
        sign = 1.0 if event.crossing == "enter" else -1.0
        return _PHYSICAL_EVENT_IMPACT["proximity"] * sign
    if event.event_type == "temporal":
        # Flat positive: a fresh time-of-day bucket is a weak arousal bump.
        # The FSM, not mood, is the primary consumer of TemporalEvent.
        return _PHYSICAL_EVENT_IMPACT["temporal"]
    # BiorhythmEvent deliberately returns 0.0 to avoid feeding ``Physical``
    # back into itself — it is a readout of the same vector being updated.
    return 0.0


def advance_physical(
    prev: Physical,
    events: Sequence[Observation],
    *,
    config: StateUpdateConfig = DEFAULT_CONFIG,
    rng: Random | None = None,
) -> Physical:
    """Apply one CSDG half-step to :class:`Physical` and derive 4 elements.

    Derivations (MVP, calibrated for 10-second ticks):

    * ``sleep_quality``   — decay towards 0.5 under fatigue+stress load + drift
    * ``physical_energy`` — 0.6 * sleep_quality + 0.4 * (1 - fatigue)
    * ``mood_baseline``   — decay towards 0.0 + Σ event_impact + drift
    * ``cognitive_load``  — decay + stress contribution + cumulative negative
      speech / internal impact, clamped to ``[0, 1]``
    * ``fatigue``           — unchanged by pure time in MVP (updated by
      world physics in T13). Included so the pure function is idempotent.
    * ``hunger``            — unchanged in MVP (T13 drives it from walking
      distance).
    * ``breath_rate``       — unchanged in MVP.
    * ``emotional_conflict``— carried over; mutated by the reflection
      pipeline (M4+) rather than this tick-level step.
    """
    event_term = sum(_event_impact(e) for e in events) * config.event_weight

    sleep_penalty = prev.fatigue * 0.1 + prev.emotional_conflict * 0.05
    sleep_base = (prev.sleep_quality - 0.5) * (1.0 - config.decay_rate) + 0.5
    sleep_quality = _clamp_unit(
        sleep_base - sleep_penalty + _noise(rng, config.noise_scale)
    )

    physical_energy = _clamp_unit(0.6 * sleep_quality + 0.4 * (1.0 - prev.fatigue))

    mood_base = prev.mood_baseline * (1.0 - config.decay_rate)
    mood_baseline = _clamp_signed(
        mood_base + event_term + _noise(rng, config.noise_scale),
    )

    load_decay = prev.cognitive_load * (1.0 - config.decay_rate)
    # Stress lives in ``Cognitive``; :func:`advance_physical` only consumes the
    # observation-driven term. Per-agent stress carry-over is handled by
    # :func:`apply_llm_delta` one step later in the cycle.
    negative_speech = 0.0
    for e in events:
        if e.event_type == "speech":
            negative_speech += max(0.0, -e.emotional_impact)
    cognitive_load = _clamp_unit(
        load_decay
        + config.event_weight * negative_speech
        + _noise(rng, config.noise_scale),
    )

    # M7δ: emotional_conflict decays toward 0 each tick. Writes happen at
    # the relational sink (``world/tick.py::apply_affinity_delta``) when a
    # negative affinity delta crosses the trigger threshold; this decay
    # provides the matching down-slope so a momentary clash fades over
    # ~50 ticks if no further negative event reinforces it.
    emotional_conflict = max(0.0, prev.emotional_conflict - _EMOTIONAL_CONFLICT_DECAY)

    return Physical(
        sleep_quality=sleep_quality,
        physical_energy=physical_energy,
        mood_baseline=mood_baseline,
        cognitive_load=cognitive_load,
        emotional_conflict=emotional_conflict,
        fatigue=prev.fatigue,
        hunger=prev.hunger,
        breath_rate=prev.breath_rate,
    )


def apply_llm_delta(
    prev: Cognitive,
    plan: LLMPlan,
    *,
    config: StateUpdateConfig = DEFAULT_CONFIG,
    rng: Random | None = None,
) -> Cognitive:
    """Compose the prior :class:`Cognitive` with the LLM-supplied deltas.

    Applied to the 4 short-timescale affect fields (``valence`` / ``arousal``
    / ``motivation`` / ``stress``). Structural fields (``shuhari_stage``,
    ``dmn_activation``, ``active_goals``, ``dominant_emotion``,
    ``curiosity``) carry over unchanged — those transitions are M4+ (ERRE
    mode FSM) work.
    """
    vd = _clip(plan.valence_delta, config.max_llm_delta)
    ad = _clip(plan.arousal_delta, config.max_llm_delta)
    md = _clip(plan.motivation_delta, config.max_llm_delta)

    valence = _clamp_signed(
        prev.valence + vd * config.llm_weight + _noise(rng, config.noise_scale),
    )
    arousal = _clamp_signed(
        prev.arousal + ad * config.llm_weight + _noise(rng, config.noise_scale),
    )
    motivation = _clamp_unit(
        prev.motivation + md * config.llm_weight + _noise(rng, config.noise_scale),
    )
    # MVP: stress decays slightly each tick absent explicit LLM input.
    stress = _clamp_unit(
        prev.stress * (1.0 - config.decay_rate) + _noise(rng, config.noise_scale),
    )

    return prev.model_copy(
        update={
            "valence": valence,
            "arousal": arousal,
            "motivation": motivation,
            "stress": stress,
        },
    )


__all__ = [
    "DEFAULT_CONFIG",
    "StateUpdateConfig",
    "advance_physical",
    "apply_llm_delta",
]
