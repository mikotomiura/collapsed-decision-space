"""Event-type heuristic for assigning importance to fresh observations.

An MVP-era placeholder for the LLM-scored importance pipeline that will
replace it at M4+ (see MASTER-PLAN appendix B.2). The contract stays the
same — ``estimate_importance(observation) -> float in [0, 1]`` — so swapping
the implementation should not require touching :mod:`cognition.cycle`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from erre_sandbox.schemas import Observation

# Base importance per event_type. Values chosen so that ordinary perception
# stays out of the reflection window (peripatos/chashitsu) while distinctive
# events (mode shifts, internal prompts) cross into it.
#
# M6-A-2b additions (affordance / proximity / temporal / biorhythm):
# * affordance — environmental salience, tuned just under speech because a
#   named interactable inside a deep zone (tea bowl in chashitsu) is the
#   event the FSM listens for when promoting chashitsu-mode dwell time.
# * proximity — social presence crossing, between perception and speech.
# * temporal — time-of-day roll, mostly scene-setting; per-tick it should
#   not dominate the reflection window by itself.
# * biorhythm — threshold crossing signals a shift in the agent's own body;
#   set equal to speech so sustained fatigue participates in reflection.
_BASE_IMPORTANCE: Final[dict[str, float]] = {
    "perception": 0.3,
    "speech": 0.6,
    "zone_transition": 0.5,
    "erre_mode_shift": 0.8,
    "internal": 0.4,
    "affordance": 0.5,
    "proximity": 0.4,
    "temporal": 0.3,
    "biorhythm": 0.6,
}

_PERCEPTION_INTENSITY_WEIGHT: Final[float] = 0.3
_SPEECH_IMPACT_WEIGHT: Final[float] = 0.3
_INTERNAL_HINT_WEIGHT: Final[float] = 0.4
_IMPORTANCE_MIN: Final[float] = 0.0
_IMPORTANCE_MAX: Final[float] = 1.0


def _clamp(
    value: float, lo: float = _IMPORTANCE_MIN, hi: float = _IMPORTANCE_MAX
) -> float:
    return max(lo, min(hi, value))


def estimate_importance(observation: Observation) -> float:
    """Map an :class:`Observation` to its importance in ``[0.0, 1.0]``.

    The heuristic is: pick a per-event-type base, then add a small correction
    from fields that the event exposes (``intensity`` on perception events,
    the absolute ``emotional_impact`` on speech, the ``importance_hint`` on
    internal prompts). Zone transitions and ERRE mode shifts use their base
    alone — they are already categorical signals.
    """
    event_type = observation.event_type
    base = _BASE_IMPORTANCE.get(event_type, _BASE_IMPORTANCE["perception"])

    if observation.event_type == "perception":
        return _clamp(
            base + _PERCEPTION_INTENSITY_WEIGHT * (observation.intensity - 0.5),
        )
    if observation.event_type == "speech":
        return _clamp(base + _SPEECH_IMPACT_WEIGHT * abs(observation.emotional_impact))
    if observation.event_type == "internal":
        return _clamp(
            base + _INTERNAL_HINT_WEIGHT * (observation.importance_hint - 0.5)
        )
    return _clamp(base)


__all__ = ["estimate_importance"]
