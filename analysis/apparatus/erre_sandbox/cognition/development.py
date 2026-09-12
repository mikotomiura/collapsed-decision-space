"""Evidence-driven ``DevelopmentState`` stage transitions (M11-B).

This is the first time an individual's *lifecycle stage* (``S1_seed`` →
``S2_exploring`` → ``S3_consolidated``) is driven by control logic rather than
merely measured. Everything here is built so that **the LLM cannot fire a
transition** (design-final §1.4, §2.6): the only inputs are Python-computed
observables and the prior :class:`DevelopmentState`.

Design constraints:

* **LLM = candidate / Python = authority.** ``maturity_score`` is the
  ``min`` of two *LLM-independent* axes only — memory volume (episodic writes,
  Python) and belief stability (belief promotions from ``RelationshipBond``,
  Python). Coherence is derived from the LLM's utterance, so it is **never** a
  magnitude axis (an LLM could otherwise inflate it by reciting its world model).
  It enters solely as a *necessary, non-inflatable gate*: low
  coherence blocks, high coherence cannot advance without genuine volume +
  stability.
* **AND via ``min``.** ``min`` is a strict conjunction —
  a strong axis can never compensate for a weak one — unlike a geometric mean.
* **Continuous lifetime gauge.** The maturity axes accumulate over the
  individual's life and are *not* reset on a transition, so the gauge does not
  artificially drop when a stage advances. Lifecycle monotonicity (no regression)
  is enforced on the discrete ``stage`` (latched), not the gauge.
* **Stage-local coherence gate.** Sustained coherence is required
  *within the destination stage* (``stage_high_coherence_ticks``, reset on a
  transition), so S1-era coherence cannot push an S2→S3 advance.
* **Pure ⊥ I/O.** Every function is pure and total: the caller (the
  cognition cycle) owns the embedding / store I/O and persistence, and decides the
  *skip* (``None``) case at its boundary — mirroring ``belief.py`` /
  ``narrative.py``. ``maybe_advance_development`` never mutates its input.

The transition clock is the *fresh-evidence tick* — a tick on which the caller
synthesised a fresh narrative arc (so a fresh coherence exists). Silent / outage
ticks are non-observations: they neither advance dwell counters nor reset the
stability streak.

Layer rule: this module imports only :mod:`erre_sandbox.contracts`,
:mod:`erre_sandbox.schemas` (type-only) and the standard library.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from erre_sandbox.contracts.cognition_layers import DevelopmentState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.contracts.cognition_layers import DevelopmentStage
    from erre_sandbox.schemas import SemanticMemoryRecord

# ---------------------------------------------------------------------------
# Preregistered constants (do not post-hoc
# tune — recalibrate against a live coherence distribution in M11-C).
# ---------------------------------------------------------------------------

DEVELOPMENT_COHERENCE_THRESHOLD: Final[float] = 0.25
"""Stage-gate coherence floor — a *separate* constant from
``CognitionCycle.LOW_COHERENCE_THRESHOLD`` (0.0, reflection-only).

nomic document/document cosines cluster strongly positive, so ``0.0`` is
meaningless as a *positive* gate. ``0.25`` sits above the merely-on-topic floor
and below typical strong coherence (~0.4-0.7). First-principles preregister — no
live M11-A distribution exists (mock tests only)."""

THRESH_S2: Final[float] = 0.45
THRESH_S3: Final[float] = 0.70
"""``min(m_vol, m_stab)`` floor to leave S1 / S2."""

MIN_TICKS_S2: Final[int] = 20
MIN_TICKS_S3: Final[int] = 40
"""Fresh-evidence dwell ticks required in S1 / S2 (also the cooldown refractory)."""

MIN_COHERENT_TICKS_S2: Final[int] = 10
MIN_COHERENT_TICKS_S3: Final[int] = 20
"""Stage-local high-coherence ticks required to leave S1 / S2."""

MIN_BELIEFS_S2: Final[int] = 2
MIN_BELIEFS_S3: Final[int] = 3
"""Minimum belief count to leave S1 / S2 — closes the single-belief
``m_stab == 1`` false positive."""

MEMORY_VOLUME_TARGET: Final[int] = 50
"""``episodic_seen_count`` at which ``m_vol`` saturates."""

STABILITY_TARGET: Final[int] = 8
"""``stable_streak`` at which ``m_stab`` saturates."""

STABILITY_CONFIDENCE_FLOOR: Final[float] = 0.5
"""Mean belief confidence below which a tick cannot extend the stability streak."""

CONFIDENCE_BUCKET: Final[float] = 0.1
"""Quantisation width for the belief-signature confidence bucket. Deliberate
noise tolerance: sub-bucket confidence drift must not reset the streak."""

_SIGNATURE_DIGEST_BYTES: Final[int] = 6
"""blake2s digest size for :func:`belief_signature` — 48 bits, JSON-safe
(< 2**53) with negligible collision probability."""

# transition_evidence keys (the M11-B vocabulary; the schema leaves these
# free-form, dict[str, int>=0]).
_EP_SEEN: Final[str] = "episodic_seen_count"
_STABLE_STREAK: Final[str] = "stable_streak"
_LAST_SIG: Final[str] = "last_belief_signature"
_TICKS_IN_STAGE: Final[str] = "ticks_in_stage"
_STAGE_HIGH_COH: Final[str] = "stage_high_coherence_ticks"

_NO_PRIOR_SIGNATURE: Final[int] = -1
"""Sentinel for "no signature recorded yet" — can never equal a real (>= 0)
signature, so the first fresh-evidence tick is correctly treated as non-stable."""


@dataclass(frozen=True, slots=True)
class DevelopmentEvidence:
    """One fresh-evidence tick's resolved, LLM-independent observables.

    Has **no text field** (and no ``Observation`` / utterance), so
    :func:`maybe_advance_development` structurally cannot read LLM output. The
    one utterance-derived quantity, ``fresh_coherence``, is used only as a gate,
    never as a maturity magnitude.

    ``__post_init__`` rejects non-finite / out-of-range / negative inputs with a
    :class:`ValueError` rather than fabricating a clamped score.
    """

    new_episodic_count: int
    """Episodic rows written this tick (``len(new_memory_ids)``). Accumulated into
    a lifetime ``episodic_seen_count`` — never a ``COUNT(*)`` (eviction-proof)."""
    fresh_coherence: float
    """This tick's fresh ``NarrativeArc.coherence_score`` in ``[-1, 1]``."""
    belief_count: int
    """``len(beliefs)`` from ``list_semantic_beliefs`` this tick."""
    mean_belief_confidence: float
    """Mean belief confidence in ``[0, 1]`` (``0.0`` when there are no beliefs)."""
    belief_signature: int
    """:func:`belief_signature` digest — a 48-bit churn fingerprint."""

    def __post_init__(self) -> None:
        if self.new_episodic_count < 0:
            msg = f"new_episodic_count must be >= 0, got {self.new_episodic_count}"
            raise ValueError(msg)
        if not math.isfinite(self.fresh_coherence) or not (
            -1.0 <= self.fresh_coherence <= 1.0
        ):
            msg = (
                f"fresh_coherence must be finite in [-1, 1], got {self.fresh_coherence}"
            )
            raise ValueError(msg)
        if self.belief_count < 0:
            msg = f"belief_count must be >= 0, got {self.belief_count}"
            raise ValueError(msg)
        if not math.isfinite(self.mean_belief_confidence) or not (
            0.0 <= self.mean_belief_confidence <= 1.0
        ):
            msg = (
                "mean_belief_confidence must be finite in [0, 1], got "
                f"{self.mean_belief_confidence}"
            )
            raise ValueError(msg)
        if self.belief_signature < 0:
            msg = f"belief_signature must be >= 0, got {self.belief_signature}"
            raise ValueError(msg)


def belief_signature(beliefs: Sequence[SemanticMemoryRecord]) -> int:
    """Deterministic 48-bit churn fingerprint of a belief set.

    Folds each belief's ``(id, belief_kind, bucketed confidence)`` — sorted for
    order-independence — through ``blake2s``. Detects *same-count* churn (a belief
    swapped for another) that a bare count would miss.
    Independent of ``PYTHONHASHSEED`` (no built-in ``hash``). The confidence is
    bucketed by :data:`CONFIDENCE_BUCKET` so sub-bucket drift does not reset the
    stability streak.
    """
    items = sorted(
        (
            record.id,
            record.belief_kind or "",
            round(record.confidence / CONFIDENCE_BUCKET),
        )
        for record in beliefs
    )
    canonical = "\n".join(f"{rid}|{kind}|{bucket}" for rid, kind, bucket in items)
    digest = hashlib.blake2s(
        canonical.encode("utf-8"),
        digest_size=_SIGNATURE_DIGEST_BYTES,
    ).digest()
    return int.from_bytes(digest, "big")


def _eligible(
    *,
    maturity: float,
    maturity_threshold: float,
    fresh_coherence: float,
    coherence_threshold: float,
    stage_high_coherence_ticks: int,
    min_coherent_ticks: int,
    belief_count: int,
    min_beliefs: int,
    ticks_in_stage: int,
    min_ticks: int,
) -> bool:
    """The 5-condition AND gate for one stage transition (design.md state machine)."""
    return (
        maturity >= maturity_threshold
        and fresh_coherence >= coherence_threshold
        and stage_high_coherence_ticks >= min_coherent_ticks
        and belief_count >= min_beliefs
        and ticks_in_stage >= min_ticks
    )


def maybe_advance_development(
    current: DevelopmentState,
    evidence: DevelopmentEvidence,
    *,
    coherence_threshold: float = DEVELOPMENT_COHERENCE_THRESHOLD,
    thresh_s2: float = THRESH_S2,
    thresh_s3: float = THRESH_S3,
    min_ticks_s2: int = MIN_TICKS_S2,
    min_ticks_s3: int = MIN_TICKS_S3,
    min_coherent_ticks_s2: int = MIN_COHERENT_TICKS_S2,
    min_coherent_ticks_s3: int = MIN_COHERENT_TICKS_S3,
    min_beliefs_s2: int = MIN_BELIEFS_S2,
    min_beliefs_s3: int = MIN_BELIEFS_S3,
    memory_volume_target: int = MEMORY_VOLUME_TARGET,
    stability_target: int = STABILITY_TARGET,
    stability_confidence_floor: float = STABILITY_CONFIDENCE_FLOOR,
) -> DevelopmentState:
    """Fold one fresh-evidence tick into a new :class:`DevelopmentState`.

    Pure and total: updates the accumulators, recomputes the maturity gauge, and
    advances the stage by *at most one step* when the 5-condition gate
    (:func:`_eligible`) holds. Never mutates ``current`` (a fresh
    ``transition_evidence`` dict is built). The caller invokes this only on a
    fresh-evidence tick; the *skip* / flag-off case is the caller's ``None``
    carry-forward (DA-M11B-10).

    Module constants are exposed as keyword defaults so tests can override gates
    without rewriting the constant (mirrors ``belief.py``).
    """
    evidence_counts = current.transition_evidence

    # --- lifetime accumulators (never reset on a transition, DA-M11B-3) ---
    episodic_seen = evidence_counts.get(_EP_SEEN, 0) + evidence.new_episodic_count
    is_stable = (
        evidence.belief_signature == evidence_counts.get(_LAST_SIG, _NO_PRIOR_SIGNATURE)
        and evidence.belief_count >= 1
        and evidence.mean_belief_confidence >= stability_confidence_floor
    )
    stable_streak = evidence_counts.get(_STABLE_STREAK, 0) + 1 if is_stable else 0

    # --- stage-local accumulators (reset on a transition) ---
    ticks_in_stage = evidence_counts.get(_TICKS_IN_STAGE, 0) + 1
    stage_high_coherence_ticks = evidence_counts.get(_STAGE_HIGH_COH, 0) + (
        1 if evidence.fresh_coherence >= coherence_threshold else 0
    )

    # --- maturity gauge: LLM-independent axes, strict AND (min), DA-M11B-1/2 ---
    m_vol = min(1.0, episodic_seen / memory_volume_target)
    m_stab = min(1.0, stable_streak / stability_target)
    maturity = min(m_vol, m_stab)

    # --- single-step, regression-forbidden stage transition ---
    stage: DevelopmentStage = current.stage
    new_stage: DevelopmentStage = stage
    if stage == "S1_seed" and _eligible(
        maturity=maturity,
        maturity_threshold=thresh_s2,
        fresh_coherence=evidence.fresh_coherence,
        coherence_threshold=coherence_threshold,
        stage_high_coherence_ticks=stage_high_coherence_ticks,
        min_coherent_ticks=min_coherent_ticks_s2,
        belief_count=evidence.belief_count,
        min_beliefs=min_beliefs_s2,
        ticks_in_stage=ticks_in_stage,
        min_ticks=min_ticks_s2,
    ):
        new_stage = "S2_exploring"
    elif stage == "S2_exploring" and _eligible(
        maturity=maturity,
        maturity_threshold=thresh_s3,
        fresh_coherence=evidence.fresh_coherence,
        coherence_threshold=coherence_threshold,
        stage_high_coherence_ticks=stage_high_coherence_ticks,
        min_coherent_ticks=min_coherent_ticks_s3,
        belief_count=evidence.belief_count,
        min_beliefs=min_beliefs_s3,
        ticks_in_stage=ticks_in_stage,
        min_ticks=min_ticks_s3,
    ):
        new_stage = "S3_consolidated"
    # S3_consolidated is terminal (S4/S5 deferred to M12+).

    if new_stage != stage:
        # Reset stage-local dwell + coherence; lifetime axes are preserved so the
        # gauge does not artificially drop.
        ticks_in_stage = 0
        stage_high_coherence_ticks = 0

    return DevelopmentState(
        stage=new_stage,
        maturity_score=maturity,
        transition_evidence={
            _EP_SEEN: episodic_seen,
            _STABLE_STREAK: stable_streak,
            _LAST_SIG: evidence.belief_signature,
            _TICKS_IN_STAGE: ticks_in_stage,
            _STAGE_HIGH_COH: stage_high_coherence_ticks,
        },
    )
