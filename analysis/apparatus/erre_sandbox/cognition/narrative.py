"""Diagnostic narrative-arc distillation + utterance↔world-model coherence (M11-A).

Periodically distils an agent's *prompt-visible* subjective world model into a
bounded, structured :class:`~erre_sandbox.contracts.cognition_layers.NarrativeArc`
and measures how well the agent's latest utterance *coheres* with that world
model (cosine similarity of their embeddings).

**Diagnostic only.** The arc and its
``coherence_score`` are *measured and recorded* — they never drive a
``DevelopmentState`` transition (M11-B), sampling, or personality drift (M11-C).
The single permitted behavioural effect lives in the *caller* (the cognition
cycle): a clearly-negative coherence may add one extra reflection-deepening
signal. Nothing here reads or mutates control state.

Design constraints:

* **Pure ⊥ I/O.** Every function here is pure: embeddings and the
  coherence score arrive as arguments. The async embedding I/O is owned by the
  caller, mirroring the ``belief.py`` / ``world_model.py`` boundary. This keeps
  the arc deterministic and unit-testable without a live embedding endpoint.
* **Honesty is a *composition* invariant.**
  :func:`synthesize_narrative_arc` copies each segment's ``cited_memory_ids``
  verbatim from a :class:`WorldModelEntry`. The deeper guarantee that those ids
  are a subset of the agent's belief-record ids is provided *upstream* by
  :func:`erre_sandbox.cognition.world_model.synthesize_world_model` /
  :func:`~erre_sandbox.cognition.world_model.reconcile_world_model`. Callers
  **must** pass a SWM produced by that path; passing an arbitrary SWM only
  preserves the weaker "cited ⊆ entry.cited" invariant.
* **Structured, not prose.** Segments are an *update-point list*: each is
  a point-in-time (``start_tick == end_tick``) snapshot of one salient
  world-model entry, never a free-form narrative paragraph (``summary`` stays
  ``None``). Prose distillation is deferred to M12+.
* **Coherence is symmetric.** The caller embeds *both* the utterance
  and the rendered SWM as ``document`` (same prefix), so the cosine here is an
  un-biased symmetric similarity, not an asymmetric query→document retrieval.

Layer rule: this module imports only :mod:`erre_sandbox.contracts`,
:mod:`erre_sandbox.schemas` (type-only) and the standard library.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from erre_sandbox.contracts.cognition_layers import ArcSegment, NarrativeArc

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.contracts.cognition_layers import SubjectiveWorldModel

_MAX_ARC_SEGMENTS: Final[int] = 5
"""Hard upper bound on retained segments (mirrors ``NarrativeArc`` schema max)."""

_MAX_SEGMENT_LABEL: Final[int] = 120
"""Max ``ArcSegment.segment_label`` length (mirrors the schema bound)."""

_COHERENCE_FLOOR: Final[float] = -1.0
_COHERENCE_CEIL: Final[float] = 1.0


def render_swm_for_embedding(swm: SubjectiveWorldModel) -> str:
    """Render a SWM as deterministic text for symmetric coherence embedding.

    One line per entry, in the SWM's existing salience order (the synthesis in
    :func:`~erre_sandbox.cognition.world_model.synthesize_world_model` sorts the
    entries, so a fixed SWM yields a byte-stable string). An empty SWM renders to
    ``""`` so the caller can skip embedding an empty world view: an empty
    render must never reach the embedder.

    ``cited_memory_ids`` are **deliberately excluded**: they are
    opaque random ids that carry no semantic signal and would only pollute the
    cosine. Only the semantic content (axis / key / value / confidence) and the
    recency tick are rendered, at fixed precision for stability.
    """
    return "\n".join(
        f"{e.axis}/{e.key} value={e.value:+.2f} confidence={e.confidence:.2f} "
        f"tick={e.last_updated_tick}"
        for e in swm.entries
    )


def compute_coherence(
    utterance_vec: Sequence[float],
    swm_vec: Sequence[float],
) -> float | None:
    """Cosine similarity of two embeddings, or ``None`` when undefined.

    Pure. Returns a value in ``[-1.0, 1.0]`` (clamped to absorb floating-point
    overshoot) so the result is always a valid ``NarrativeArc.coherence_score``.

    ``None`` (not a fabricated number) is returned whenever the score is not
    honestly defined: mismatched / empty vectors, any non-finite
    element, a zero-norm vector, or a non-finite score. The caller maps ``None``
    to "skip the arc this tick" rather than recording a dishonest value.
    """
    length = len(utterance_vec)
    if length == 0 or length != len(swm_vec):
        return None
    if not all(math.isfinite(x) for x in utterance_vec):
        return None
    if not all(math.isfinite(x) for x in swm_vec):
        return None

    dot = math.fsum(a * b for a, b in zip(utterance_vec, swm_vec, strict=True))
    norm_u = math.sqrt(math.fsum(a * a for a in utterance_vec))
    norm_v = math.sqrt(math.fsum(b * b for b in swm_vec))
    if norm_u == 0.0 or norm_v == 0.0:
        return None

    score = dot / (norm_u * norm_v)
    if not math.isfinite(score):
        return None
    return max(_COHERENCE_FLOOR, min(_COHERENCE_CEIL, score))


def synthesize_narrative_arc(
    swm: SubjectiveWorldModel,
    *,
    synthesized_at_tick: int,
    coherence_score: float,
    last_episodic_id: str | None,
    max_segments: int = _MAX_ARC_SEGMENTS,
) -> NarrativeArc | None:
    """Distil a SWM into a bounded structured :class:`NarrativeArc`, or ``None``.

    Pure. The caller owns the embedding I/O that produced *coherence_score* and
    the persistence of the returned arc.

    Returns ``None`` (skip) when an honest arc cannot be built:

    * *last_episodic_id* is ``None`` / empty — there is no pointer to anchor the
      arc, and ``NarrativeArc.last_episodic_pointer`` forbids an empty string
      (never fabricated);
    * *swm* has no entries — there is nothing to segment.

    Otherwise the top ``max_segments`` entries (by the SWM's salience order) are
    taken, then re-ordered chronologically by ``last_updated_tick`` to read as a
    trajectory of *update points*. Each becomes one point-in-time
    :class:`ArcSegment` (``start_tick == end_tick == last_updated_tick``) whose
    ``cited_memory_ids`` are copied verbatim from the entry — see the module
    docstring for why that preserves the honesty invariant only when *swm* came
    from the ``world_model`` synthesis path.

    *max_segments* is clamped to ``[1, 5]`` so an over-large request
    cannot raise a :class:`pydantic.ValidationError` from the schema's max-5 bound.
    """
    if not last_episodic_id or not swm.entries:
        return None

    keep = max(1, min(max_segments, _MAX_ARC_SEGMENTS))
    selected = sorted(
        swm.entries[:keep],
        key=lambda e: (e.last_updated_tick, e.axis, e.key),
    )
    segments = [
        ArcSegment(
            segment_label=f"{e.axis}/{e.key}"[:_MAX_SEGMENT_LABEL],
            start_tick=e.last_updated_tick,
            end_tick=e.last_updated_tick,
            cited_memory_ids=tuple(sorted(e.cited_memory_ids)),
            summary=None,
        )
        for e in selected
    ]
    return NarrativeArc(
        synthesized_at_tick=synthesized_at_tick,
        arc_segments=segments,
        coherence_score=max(_COHERENCE_FLOOR, min(_COHERENCE_CEIL, coherence_score)),
        last_episodic_pointer=last_episodic_id,
    )


__all__ = [
    "compute_coherence",
    "render_swm_for_embedding",
    "synthesize_narrative_arc",
]
