"""Pure-function affinity computation for the M7 Slice δ relational hook.

The single public function :func:`compute_affinity_delta` returns the
adjustment that should be applied to a :class:`RelationshipBond.affinity`
field when one :class:`DialogTurnMsg` is recorded. It is intentionally a
pure function (no I/O, no side effects, no global state) so:

* the bootstrap-level chain sink in
  :mod:`erre_sandbox.bootstrap` can wrap it without a runtime dependency, and
* unit tests can drive every branch without a live LLM, sqlite store, or
  scheduler.

M7γ (constant +0.02) → M7δ migration
------------------------------------

γ kept the body trivial (constant ``+0.02``) and left the signature
future-proof. δ replaces the body with the CSDG semi-formula

    next_affinity = prev * (1 - decay) + event_impact * event_weight
    delta         = next_affinity - prev

where the three terms are persona-coupled and structural:

* ``decay`` = ``0.02 + 0.06 * neuroticism`` (range 0.032-0.071 across the
  3-persona surface). Couples to neuroticism for observable persona
  contrast in 90-second live runs (Nietzsche decays ~4× Kant).
* ``event_weight`` = ``0.5 + extraversion`` (range 0.5-1.5). Extraverted
  agents accumulate affinity changes faster.
* ``event_impact`` = either the persona-pair antagonism (when one is
  present in :mod:`erre_sandbox.cognition._trait_antagonism`) or the
  structural positive impact ``0.6*addressee_match + 0.4*length_norm``
  derived from the dialog turn alone — no NLP, no language-specific
  lexicon, no MeCab.

The negative path is guaranteed for the kant↔nietzsche pair via
``_trait_antagonism``; positive variation comes from utterance length
and addressee directedness for all other pairs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from erre_sandbox.cognition._trait_antagonism import lookup_antagonism

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.schemas import DialogTurnMsg, PersonaSpec

GAMMA_CONSTANT_DELTA: Final[float] = 0.02
"""γ MVP affinity nudge per recorded :class:`DialogTurnMsg` (always positive).

Retained as a module constant so any caller still wanting the M7γ MVP
behaviour (e.g. a regression test or a downgrade flag) can request it
explicitly. The δ semi-formula does **not** read this value."""

AFFINITY_LOWER: Final[float] = -1.0
AFFINITY_UPPER: Final[float] = 1.0

# δ tunables. Centralised so downstream calibration in m8-affinity-dynamics
# can swap them without touching the formula body.
_DECAY_BASE: Final[float] = 0.02
_DECAY_NEURO_COEFF: Final[float] = 0.06
_WEIGHT_BASE: Final[float] = 0.5
_WEIGHT_EXTRA_COEFF: Final[float] = 1.0
_IMPACT_LENGTH_TARGET: Final[int] = 200
"""Utterance length (in characters) at which ``length_norm`` saturates to 1.0."""
_IMPACT_ADDRESSEE_WEIGHT: Final[float] = 0.08
_IMPACT_LENGTH_WEIGHT: Final[float] = 0.04
"""Per-turn structural impact coefficients (M7δ Axis 1b calibration).

Sized so a single high-engagement turn contributes
``≈ 0.08 + 0.04 = 0.12`` to ``event_impact``. Together with the
extraversion-coupled weight (range 0.5-1.5) this yields per-turn deltas
around 0.06-0.18, so the recurrence ``next = prev*(1-decay) + impact*weight``
saturates past the belief-promotion threshold (``0.45``) around turn 7-12
for non-antagonistic dyads. The matching simulation regression test
lives at ``tests/test_cognition/test_relational_simulation.py``."""


def clamp_affinity_delta(delta: float) -> float:
    """Clamp ``delta`` to the :class:`RelationshipBond.affinity` ``_Signed`` range.

    Mirrors the field constraint on :class:`RelationshipBond.affinity`
    (``ge=-1.0`` / ``le=1.0``). Centralised here so future δ deltas that
    add or subtract multiple terms cannot accidentally bypass the bound.
    """
    if delta < AFFINITY_LOWER:
        return AFFINITY_LOWER
    if delta > AFFINITY_UPPER:
        return AFFINITY_UPPER
    return delta


def _compute_decay(persona: PersonaSpec) -> float:
    """Per-turn decay coefficient ``∈ [_DECAY_BASE, _DECAY_BASE + _DECAY_NEURO_COEFF]``.

    Couples to neuroticism so volatile personas (Nietzsche) lose remembered
    affinity faster than stoic ones (Kant). Half-life is ``ln(2)/decay``;
    values land in ``[14, 31]`` turns for the 3-persona production surface.
    """
    return _DECAY_BASE + _DECAY_NEURO_COEFF * persona.personality.neuroticism


def _compute_weight(persona: PersonaSpec) -> float:
    """Event weight ``∈ [_WEIGHT_BASE, _WEIGHT_BASE + _WEIGHT_EXTRA_COEFF]``.

    Couples to extraversion so socially-oriented personas accumulate
    affinity changes faster. The wider 0.5-1.5 range (vs the v2 proposal
    of 0.5-1.0) preserves the Kant ↔ Nietzsche/Rikyu contrast that the
    δ acceptance gate observes in live runs.
    """
    return _WEIGHT_BASE + _WEIGHT_EXTRA_COEFF * persona.personality.extraversion


def _compute_impact_structural(turn: DialogTurnMsg) -> float:
    """Positive ``event_impact`` ∈ [0, 1] from structural turn features.

    Two language-agnostic signals:

    * ``addressee_match`` — 1.0 when the turn carries a non-empty
      ``addressee_id``, 0.0 otherwise. Defensive against malformed turns
      where the field somehow ends up blank; the production scheduler
      always sets it.
    * ``length_norm`` — ``min(len(utterance) / _IMPACT_LENGTH_TARGET, 1.0)``.
      Saturates around the typical LLM-generated reply length so
      effort/engagement is captured without over-rewarding rambling.

    No NLP, no lexicon, no MeCab — JP-keyword sentiment is brittle on 2-3
    sentence LLM utterances, so a keyword-based approach was deliberately avoided.
    """
    addressee_match = 1.0 if turn.addressee_id else 0.0
    length_norm = min(len(turn.utterance) / float(_IMPACT_LENGTH_TARGET), 1.0)
    return (
        _IMPACT_ADDRESSEE_WEIGHT * addressee_match + _IMPACT_LENGTH_WEIGHT * length_norm
    )


def _select_event_impact(
    speaker_persona_id: str,
    addressee_persona_id: str | None,
    structural: float,
) -> float:
    """Antagonism overrides structural impact when present.

    The v1 ``_TRAIT_ANTAGONISM`` table fires a strongly-negative impact
    that dominates the structural positive contribution; otherwise the
    structural value carries the sign. This keeps the live-fire guarantee
    for kant↔nietzsche while letting the formula stay smooth (no abrupt
    discontinuity within the positive regime).
    """
    antagonism = lookup_antagonism(speaker_persona_id, addressee_persona_id)
    if antagonism != 0.0:
        return antagonism
    return structural


def compute_affinity_delta(
    turn: DialogTurnMsg,
    recent_transcript: Sequence[DialogTurnMsg],
    persona: PersonaSpec,
    *,
    prev: float = 0.0,
    addressee_persona: PersonaSpec | None = None,
) -> float:
    """Return affinity adjustment for one recorded :class:`DialogTurnMsg`.

    The CSDG semi-formula

        next_affinity = prev * (1 - decay) + event_impact * event_weight
        delta         = next_affinity - prev

    is evaluated with persona-coupled ``decay`` and ``event_weight`` and
    structural / antagonism-derived ``event_impact``. The result is
    clamped to the legal :class:`RelationshipBond.affinity` range.

    Args:
        turn: The dialog turn that was just recorded by the scheduler.
            ``utterance`` length and ``addressee_id`` drive the structural
            positive impact.
        recent_transcript: Reserved for δ+ extensions (e.g. trend-based
            modifiers in m8-affinity-dynamics). Currently unused; kept on
            the signature so the M7γ → M7δ migration was the only change
            to call sites that already passed it.
        persona: The speaker's persona. Drives the decay and weight terms.
        prev: The bond's affinity *before* this turn. Default 0.0 covers
            the "first interaction" / "no bond yet" case.
        addressee_persona: The addressee's persona, used by the antagonism
            lookup in
            :func:`erre_sandbox.cognition._trait_antagonism.lookup_antagonism`.
            ``None`` disables antagonism (positive-only path).

    Returns:
        A clamped affinity delta to add to :class:`RelationshipBond.affinity`.
    """
    del recent_transcript  # reserved for δ+ extensions; not consumed today.
    decay = _compute_decay(persona)
    weight = _compute_weight(persona)
    structural = _compute_impact_structural(turn)
    addressee_id = (
        addressee_persona.persona_id if addressee_persona is not None else None
    )
    event_impact = _select_event_impact(persona.persona_id, addressee_id, structural)
    next_affinity = prev * (1.0 - decay) + event_impact * weight
    delta = next_affinity - prev
    return clamp_affinity_delta(delta)


def apply_affinity(current: float, delta: float) -> float:
    """Add ``delta`` to ``current`` and clamp to the legal range.

    Convenience wrapper used at every call site that needs to mutate a
    :class:`RelationshipBond.affinity` so the clamp logic is not repeated.
    """
    return clamp_affinity_delta(current + delta)


__all__ = [
    "AFFINITY_LOWER",
    "AFFINITY_UPPER",
    "GAMMA_CONSTANT_DELTA",
    "apply_affinity",
    "clamp_affinity_delta",
    "compute_affinity_delta",
]
