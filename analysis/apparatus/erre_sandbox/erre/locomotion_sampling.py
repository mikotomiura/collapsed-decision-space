"""Pure locomotion → :class:`SamplingDelta` mapping (M13-ES3).

The ES-3 locomotion channel's **third additive term** for
:func:`erre_sandbox.inference.sampling.compose_sampling`. It turns an agent's
kinetic-history intensity λ (:attr:`erre_sandbox.schemas.LocomotionState.lam`)
into a **divergence-specific** sampling offset: temperature and top_p rise with
λ, while ``repeat_penalty`` (a convergence parameter) is held at 0 — Oppezzo
2014's "walking lifts divergent, not convergent, production" rendered as a
sampling shape (design ADR §1.2).

The map is deliberately a **fixed-sign linear gain** (``temperature =
gain_t·λ``): per the ADR (Codex M1) ``corr(λ, E) > 0`` is an algebraic
*implementation invariant* of ``gain > 0``, not evidence — the effective
modulation is judged downstream by the headroom-normalised amplitude and the
``repeat_penalty`` zero-variance control, never by the sign here.

**Ablation identity** (ADR §1.2, Codex L2): ``loco=None`` ∨ ``lam=0`` ∨
``gain=0`` all yield the all-zero :class:`SamplingDelta`, so a
``loco_delta=None`` composition and a ``gain=0`` composition are bit-identical.

This module is pure (``erre → schemas`` only): no I/O, no mutable state, no
inference backend. The frozen ES-3 gains live in
:mod:`erre_sandbox.evidence.es3_locomotion.constants`; this function takes them
as arguments so the apparatus and the live wiring share one implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from erre_sandbox.schemas import SamplingDelta

if TYPE_CHECKING:
    from erre_sandbox.schemas import LocomotionState

# --- live-wiring defaults (cognition/cycle.py) --------------------------------
#
# The live cognition loop reuses the *same scale* the ES-3 apparatus freezes in
# ``evidence.es3_locomotion.constants`` (α / LOCO_GAIN_T / LOCO_GAIN_P), but the
# apparatus is deliberately **independent** of the live wiring: it has its own
# blind scenario generator and reads its own frozen constants. These live
# defaults are pinned equal to the apparatus constants by
# ``tests/test_evidence/test_es3_constants.py`` so the two cannot silently drift,
# the same mirror-and-pin discipline the world geometry uses.

DEFAULT_LOCO_ALPHA: Final[float] = 0.3
"""λ EMA smoothing α for the live loop (= apparatus ``ALPHA``; ~3-4 step window)."""

DEFAULT_LOCO_GAIN_T: Final[float] = 0.3
"""Live temperature gain (= apparatus ``LOCO_GAIN_T``)."""

DEFAULT_LOCO_GAIN_P: Final[float] = 0.1
"""Live top_p gain (= apparatus ``LOCO_GAIN_P``)."""


def advance_lambda(prev_lam: float, move_t: int, alpha: float) -> float:
    """EMA update ``λ_t = (1-α)·λ_{t-1} + α·move_t`` (ADR §1.1).

    ``move_t ∈ {0, 1}`` is "did the containing zone change this tick". With
    ``prev_lam ∈ [0, 1]``, ``move_t ∈ {0, 1}`` and ``alpha ∈ [0, 1]`` the result
    stays in ``[0, 1]`` (inside :attr:`LocomotionState.lam`'s bounds).
    """
    return (1.0 - alpha) * prev_lam + alpha * float(move_t)


def locomotion_delta(
    loco: LocomotionState | None,
    *,
    gain_t: float,
    gain_p: float,
) -> SamplingDelta:
    """Map locomotion intensity λ to a divergence-specific additive delta.

    Args:
        loco: The agent's :class:`~erre_sandbox.schemas.LocomotionState`, or
            ``None`` for an agent with no locomotion channel.
        gain_t: Temperature gain (λ=1 → ``+gain_t`` temperature). The ES-3
            frozen value is ``LOCO_GAIN_T = 0.3`` (= the ``peripatetic`` static
            bump in scale, but **state-dependent** rather than zone-constant).
        gain_p: top_p gain (λ=1 → ``+gain_p`` top_p). The ES-3 frozen value is
            ``LOCO_GAIN_P = 0.1`` (secondary; headroom-gated downstream).

    Returns:
        A :class:`~erre_sandbox.schemas.SamplingDelta` with
        ``temperature = gain_t·λ``, ``top_p = gain_p·λ``, ``repeat_penalty = 0``.
        ``loco is None`` or ``λ == 0`` (or both gains 0) ⇒ the all-zero delta —
        the ablation identity, bit-identical to ``loco_delta=None``.

    Note:
        With the frozen ES-3 gains and λ ∈ [0, 1] the products stay inside
        :class:`SamplingDelta`'s ``[-1, 1]`` field bounds; a caller passing a
        gain large enough to exceed them would (correctly) raise at construction.
    """
    if loco is None:
        return SamplingDelta()
    lam = loco.lam
    return SamplingDelta(
        temperature=gain_t * lam,
        top_p=gain_p * lam,
        repeat_penalty=0.0,
    )


__all__ = [
    "DEFAULT_LOCO_ALPHA",
    "DEFAULT_LOCO_GAIN_P",
    "DEFAULT_LOCO_GAIN_T",
    "advance_lambda",
    "locomotion_delta",
]
