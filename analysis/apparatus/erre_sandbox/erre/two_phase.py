"""λ↔two-phase (DMN↔ECN) sampling knob (aha!/DMN-ECN Phase 4).

Construction-only. Extends the M13-ES3 locomotion channel (fixed-sign,
divergence-only :func:`~erre_sandbox.erre.locomotion_sampling.locomotion_delta`)
into a **phase-signed** modulation: the same locomotion magnitude λ biases toward
divergence (DMN) in the *generation* phase and toward convergence (ECN) in the
*evaluation* phase — the salience-switch ("調合スイッチ") rendered as a sign
vector σ(phase) over the sampling delta.

This is a **boolean causal-wiring** construction (Phase 2 door-scoping ADR
§反証条件3 / Phase 4 impl-design ADR): the knob makes the two-phase bias *fire*;
it does **not** measure any effect size / detectability / divergence / floor /
aha proxy (= C-proper 第2リンク = frozen measurement line; door② UNMET, door
CLOSED). Pure (``erre → schemas`` + ``erre.locomotion_sampling``): no I/O, no
scorer, no verdict.

Grounding (Phase 4 ADR §(1), Codex MED-1 — do not over-claim table parity):

* ``temperature`` / ``top_p`` signs are grounded in the ``sampling_table`` DMN/ECN
  spectrum — generation follows the ``peripatetic`` temp+/top_p+ direction,
  evaluation the ``chashitsu`` / ``zazen`` temp−/top_p− direction.
* ``repeat_penalty`` is **not** claimed to match the whole table: the generation
  ``rp=0`` inherits the ES-3 ``locomotion_delta`` zero-control (walking lifts
  *divergence only*, Oppezzo 2014); the evaluation ``rp=+`` is grounded in the
  ``chashitsu`` (+0.1) / ``shu_kata`` (+0.2) convergence direction.

flag-gate: this module is dormant unless a :class:`TwoPhaseKnob` is injected into
:class:`~erre_sandbox.cognition.cycle.CognitionCycle` (the ``self_other``-style
optional-collaborator idiom). With ``two_phase_knob=None`` (the cycle default) the
live loop keeps calling the frozen ``locomotion_delta`` and stays byte-identical
to the existing sealed golden.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erre_sandbox.erre.locomotion_sampling import (
    DEFAULT_LOCO_GAIN_P,
    DEFAULT_LOCO_GAIN_T,
)
from erre_sandbox.schemas import ERREModeName, SamplingDelta

if TYPE_CHECKING:
    from collections.abc import Mapping

    from erre_sandbox.schemas import LocomotionState


class TwoPhase(StrEnum):
    """The two DMN/ECN phases the salience switch alternates between."""

    GENERATION = "generation"
    """DMN 生成相 — divergence (temperature/top_p ↑)."""
    EVALUATION = "evaluation"
    """ECN 評価相 — convergence (temperature/top_p ↓, repeat_penalty ↑)."""


# Sign vector σ(phase) = (temperature, top_p, repeat_penalty). The *same* |λ|
# magnitude, blended in opposite directions by phase — the "調合" of the salience
# switch. Signs grounded in ``sampling_table`` (temp/top_p) and the ES-3
# zero-control / convergent modes (rp); see the module docstring.
_PHASE_SIGN: Final[Mapping[TwoPhase, tuple[float, float, float]]] = MappingProxyType(
    {
        TwoPhase.GENERATION: (1.0, 1.0, 0.0),
        TwoPhase.EVALUATION: (-1.0, -1.0, 1.0),
    },
)

# Pinned gains (Final; env/CLI/persona override forbidden — Codex HIGH-3,
# tune-to-pass 封鎖). temp/top_p inherit the ES-3 frozen gains; the evaluation
# repeat_penalty gain is a new pin grounded in chashitsu's +0.1 rp override.
TWO_PHASE_GAIN_T: Final[float] = DEFAULT_LOCO_GAIN_T
"""Temperature gain (= ES-3 ``DEFAULT_LOCO_GAIN_T`` = 0.3)."""
TWO_PHASE_GAIN_P: Final[float] = DEFAULT_LOCO_GAIN_P
"""top_p gain (= ES-3 ``DEFAULT_LOCO_GAIN_P`` = 0.1)."""
TWO_PHASE_GAIN_R: Final[float] = 0.1
"""Evaluation-phase repeat_penalty gain (new pin; grounded in chashitsu rp +0.1)."""

# Explicit phase partition over ALL ERRE modes — no ``else`` fallback so a future
# mode cannot silently drift into a phase (Codex MED-3). Divergent (DMN; the only
# temp>0 modes in ``sampling_table``) → generation; convergent + neutral →
# evaluation (frozen decision, Codex MED-2: deep_work/shallow are non-generative).
GENERATION_MODES: Final[frozenset[ERREModeName]] = frozenset(
    {
        ERREModeName.PERIPATETIC,
        ERREModeName.RI_CREATE,
        ERREModeName.HA_DEVIATE,
    },
)
EVALUATION_MODES: Final[frozenset[ERREModeName]] = frozenset(
    {
        ERREModeName.ZAZEN,
        ERREModeName.CHASHITSU,
        ERREModeName.SHU_KATA,
        ERREModeName.DEEP_WORK,
        ERREModeName.SHALLOW,
    },
)

# Import-time exhaustiveness guard (fail-fast, not ``assert`` so ``-O`` cannot
# strip it): every ERRE mode is classified into exactly one phase.
if not GENERATION_MODES.isdisjoint(EVALUATION_MODES) or set(ERREModeName) != (
    GENERATION_MODES | EVALUATION_MODES
):
    msg = (
        "two_phase mode partition drifted from ERREModeName: every mode must be "
        "classified into exactly one of GENERATION_MODES / EVALUATION_MODES."
    )
    raise RuntimeError(msg)


@dataclass(frozen=True, slots=True)
class TwoPhaseKnob:
    """Presence-only marker that activates the two-phase locomotion knob.

    Inject ``CognitionCycle(two_phase_knob=TwoPhaseKnob())`` to activate the
    phase-signed locomotion modulation; ``None`` (the cycle default) keeps the
    byte-identical ``locomotion_delta`` path. It deliberately **carries no gains**:
    the live modulation always uses the pinned module constants
    (:data:`TWO_PHASE_GAIN_T` / :data:`TWO_PHASE_GAIN_P` / :data:`TWO_PHASE_GAIN_R`),
    so injecting a knob is *not* a per-run tuning / clamp-escape surface (Codex
    TASK-POST HIGH — a marker, not a parameter bag). The ablation identity is
    exercised directly against the pure ``two_phase_delta`` helper in tests.
    """


def phase_of_mode(mode: ERREModeName) -> TwoPhase:
    """Project an ERRE mode onto its DMN/ECN two-phase (salience-switch analog).

    Divergent (DMN) modes → :attr:`TwoPhase.GENERATION`; convergent + neutral modes
    → :attr:`TwoPhase.EVALUATION` (the frozen partition above). Raises on an
    unclassified mode so a future :class:`~erre_sandbox.schemas.ERREModeName` cannot
    silently fall into a phase (Codex MED-3).
    """
    if mode in GENERATION_MODES:
        return TwoPhase.GENERATION
    if mode in EVALUATION_MODES:
        return TwoPhase.EVALUATION
    msg = f"ERRE mode {mode!r} is not classified into a two-phase"
    raise ValueError(msg)


def two_phase_delta(
    loco: LocomotionState | None,
    phase: TwoPhase,
    *,
    gain_t: float,
    gain_p: float,
    gain_r: float,
) -> SamplingDelta:
    """Map locomotion intensity λ to a **phase-signed** additive sampling delta.

    ``loco is None`` (or ``λ == 0``, or all gains 0) → the all-zero delta: the
    ablation identity inherited from ``locomotion_delta``, bit-identical to a
    knob-off / no-locomotion composition.

    Generation phase = divergence bias ``(+gain_t·λ, +gain_p·λ, 0)`` — the frozen
    ES-3 ``locomotion_delta`` shape. Evaluation phase = convergence bias
    ``(-gain_t·λ, -gain_p·λ, +gain_r·λ)``: the same |λ| magnitude with inverted
    temperature/top_p and a positive repeat_penalty. Boolean causal-wiring only —
    no effect size / detectability / divergence / floor is produced.

    Args:
        loco: The agent's :class:`~erre_sandbox.schemas.LocomotionState`, or
            ``None`` (→ all-zero delta).
        phase: The current :class:`TwoPhase` (typically ``phase_of_mode(mode)``).
        gain_t: Temperature gain (pinned :data:`TWO_PHASE_GAIN_T` in production).
        gain_p: top_p gain (pinned :data:`TWO_PHASE_GAIN_P`).
        gain_r: Evaluation repeat_penalty gain (pinned :data:`TWO_PHASE_GAIN_R`).

    Returns:
        A :class:`~erre_sandbox.schemas.SamplingDelta`; with λ ∈ [0, 1] and the
        pinned gains its fields stay well inside the ``[-1, 1]`` bounds.
    """
    if loco is None:
        return SamplingDelta()
    lam = loco.lam
    s_t, s_p, s_r = _PHASE_SIGN[phase]
    return SamplingDelta(
        temperature=s_t * gain_t * lam,
        top_p=s_p * gain_p * lam,
        repeat_penalty=s_r * gain_r * lam,
    )


__all__ = [
    "EVALUATION_MODES",
    "GENERATION_MODES",
    "TWO_PHASE_GAIN_P",
    "TWO_PHASE_GAIN_R",
    "TWO_PHASE_GAIN_T",
    "TwoPhase",
    "TwoPhaseKnob",
    "phase_of_mode",
    "two_phase_delta",
]
