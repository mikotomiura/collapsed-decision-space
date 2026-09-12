"""Pure ERRE sampling composition — base + delta, clamp, hand off.

This module is the **single place** where :class:`~erre_sandbox.schemas.SamplingBase`
(the persona's absolute baseline) and :class:`~erre_sandbox.schemas.SamplingDelta`
(the ERRE mode's additive override, see the ``persona-erre`` skill §ルール 2)
are combined into a concrete :class:`ResolvedSampling` ready to hand to an
inference backend.

Putting the composition here — rather than inside each inference adapter or,
worse, inside each caller (T12 cognition cycle, T14 gateway) — keeps a hard
invariant: no code path outside this module can produce an out-of-range
``temperature`` / ``top_p`` / ``repeat_penalty`` that the LLM backend would
then have to defensively validate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from erre_sandbox.schemas import SamplingBase, SamplingDelta

# ---------------------------------------------------------------------------
# Clamp ranges — mirror SamplingBase field constraints and the persona-erre
# skill §ルール 2 delta table. Kept module-private so callers go through
# :func:`compose_sampling` rather than re-deriving limits ad hoc.
# ---------------------------------------------------------------------------

_TEMPERATURE_MIN: Final[float] = 0.01
_TEMPERATURE_MAX: Final[float] = 2.0
_TOP_P_MIN: Final[float] = 0.01
_TOP_P_MAX: Final[float] = 1.0
_REPEAT_PENALTY_MIN: Final[float] = 0.5
_REPEAT_PENALTY_MAX: Final[float] = 2.0


class ResolvedSampling(BaseModel):
    """Concrete sampling parameters ready to hand to an inference backend.

    Construct via :func:`compose_sampling`, not directly — hand-building a
    :class:`ResolvedSampling` bypasses the clamp invariant and defeats the
    whole purpose of this module.

    The three fields share the same names and ranges as the underlying Ollama
    ``options`` keys so that the adapter can emit them verbatim. ``frozen`` is
    set so a resolved value cannot be mutated in place after composition —
    any adjustment must go through a fresh :func:`compose_sampling` call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(..., ge=_TEMPERATURE_MIN, le=_TEMPERATURE_MAX)
    top_p: float = Field(..., ge=_TOP_P_MIN, le=_TOP_P_MAX)
    repeat_penalty: float = Field(..., ge=_REPEAT_PENALTY_MIN, le=_REPEAT_PENALTY_MAX)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compose_sampling(
    base: SamplingBase,
    mode_delta: SamplingDelta,
    loco_delta: SamplingDelta | None = None,
) -> ResolvedSampling:
    """Compose ``base + mode_delta + loco_delta`` per field and clamp.

    Each field is the plain **sum** of ``base`` (the persona's absolute
    parameter), ``mode_delta`` (the ERRE mode's signed additive offset), and
    ``loco_delta`` (the M13-ES3 locomotion offset; see
    :func:`erre_sandbox.erre.locomotion_sampling.locomotion_delta`), then clamped
    into the ranges declared on :class:`ResolvedSampling`. Misconfigured personas
    or ERRE / locomotion tables therefore cannot produce an invalid payload — the
    worst case is a saturated boundary value.

    ``loco_delta`` defaults to ``None`` and is then treated as the all-zero
    delta, so ``compose_sampling(base, mode_delta)`` and
    ``compose_sampling(base, mode_delta, None)`` are **bit-identical** to the
    pre-ES3 two-argument composition (backward-compatibility invariant, Codex
    M4 / L2 — pinned across every call path in
    ``tests/test_inference/test_sampling.py``).

    Args:
        base: The persona's default sampling (``PersonaSpec.default_sampling``).
        mode_delta: The ERRE mode's sampling overrides
            (``AgentState.erre.sampling_overrides``).
        loco_delta: The locomotion sampling offset, or ``None`` (= all-zero, the
            pre-ES3 behaviour). Produced by ``locomotion_delta`` from
            ``AgentState.locomotion``.

    Returns:
        A frozen :class:`ResolvedSampling` containing the three post-clamp
        values.
    """
    loco_t = loco_delta.temperature if loco_delta is not None else 0.0
    loco_p = loco_delta.top_p if loco_delta is not None else 0.0
    loco_r = loco_delta.repeat_penalty if loco_delta is not None else 0.0
    return ResolvedSampling(
        temperature=_clamp(
            base.temperature + mode_delta.temperature + loco_t,
            _TEMPERATURE_MIN,
            _TEMPERATURE_MAX,
        ),
        top_p=_clamp(
            base.top_p + mode_delta.top_p + loco_p,
            _TOP_P_MIN,
            _TOP_P_MAX,
        ),
        repeat_penalty=_clamp(
            base.repeat_penalty + mode_delta.repeat_penalty + loco_r,
            _REPEAT_PENALTY_MIN,
            _REPEAT_PENALTY_MAX,
        ),
    )


__all__ = ["ResolvedSampling", "compose_sampling"]
