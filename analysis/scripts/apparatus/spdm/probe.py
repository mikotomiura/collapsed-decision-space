"""Deterministic measurement primitives for the M13-ES1 SPDM probe.

This module owns the **metric** side of the apparatus (Codex HIGH-2/HIGH-4 frozen
rules): how a retrieval-landscape divergence ``D`` is computed and how the
cross-seed dispersion the noise gate reads is summarised. It is pure / deterministic
and never imports ``cognition`` (USE-only over ``memory`` + ``schemas``, like the
III-a ``live_carry`` evidence layer).

The landscape divergence is a **Jaccard distance over canonical content ids**
(:data:`erre_sandbox.evidence.spdm.constants.LANDSCAPE_KEY`), never raw
``MemoryEntry.id`` — both path arms form the same logical contents at different
locations, so comparing raw row ids would measure fixture ID separation rather than
the retrieval landscape (Codex HIGH-2).

A landscape battery is run through the real ``memory.retrieval.Retriever``
with ``mark_recalled=False`` (Codex HIGH-3) so the 12-query battery does not perturb
itself via the ``recall_count`` side effect.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from erre_sandbox.evidence.spdm import constants as _c

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from erre_sandbox.memory.retrieval import Retriever
    from erre_sandbox.schemas import Position, SpatialContext


def jaccard_distance(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard distance ``1 - |a∩b| / |a∪b|`` ∈ [0, 1].

    Two empty sets are treated as identical (distance 0): a query that retrieves
    nothing in either arm contributes no divergence.
    """
    union = a | b
    if not union:
        return 0.0
    inter = a & b
    return 1.0 - len(inter) / len(union)


def landscape_divergence(
    arm_a: Sequence[frozenset[str]],
    arm_b: Sequence[frozenset[str]],
) -> float:
    """Mean per-query Jaccard distance between two arms' retrieval landscapes.

    Each element is the canonical-content-id set a query retrieved for that arm;
    ``arm_a`` and ``arm_b`` must be aligned (same query order, same length). ``D`` ∈
    [0, 1] is the mean over the query battery (parent design §3.3).
    """
    if len(arm_a) != len(arm_b):
        msg = f"arm length mismatch: {len(arm_a)} != {len(arm_b)}"
        raise ValueError(msg)
    if not arm_a:
        return 0.0
    return statistics.fmean(
        jaccard_distance(a, b) for a, b in zip(arm_a, arm_b, strict=True)
    )


def iqr(values: Sequence[float]) -> float:
    """Inter-quartile range (the frozen ``SPREAD_STAT``; Codex HIGH-4).

    Returns 0.0 for fewer than two values. Uses the inclusive ``quantiles`` method so
    a handful of deterministic seeds give a stable, outlier-robust spread (the III-a
    freeze used ``max`` over 3 GPU seeds where IQR is ill-defined; see decisions
    DA-SPDM-2).
    """
    min_for_quartiles = 2
    if len(values) < min_for_quartiles:
        return 0.0
    qs = statistics.quantiles(values, n=4, method="inclusive")
    return float(qs[2] - qs[0])


async def run_landscape_battery(
    retriever: Retriever,
    agent_id: str,
    queries: Sequence[str],
    *,
    current_location: SpatialContext | Position | None,
    canonical_of: Mapping[str, str],
    k_agent: int = _c.K_RETRIEVE,
) -> list[frozenset[str]]:
    """Run a query battery through ``retriever`` and return per-query canonical-id sets.

    Retrieval runs with ``mark_recalled=False`` (Codex HIGH-3) so earlier queries do
    not perturb later ones. Each returned set is the ``canonical_content_id`` of the
    top-``k_agent`` retrieved memories (Codex HIGH-2): ``canonical_of`` maps raw
    ``MemoryEntry.id`` → canonical id. A raw id missing from ``canonical_of`` is a
    fixture wiring error and raises (never silently mis-scored).
    """
    landscape: list[frozenset[str]] = []
    for query in queries:
        ranked = await retriever.retrieve(
            agent_id,
            query,
            k_agent=k_agent,
            k_world=0,
            current_location=current_location,
            mark_recalled=False,
        )
        ids: set[str] = set()
        for r in ranked:
            raw = r.entry.id
            if raw not in canonical_of:
                msg = f"raw memory id {raw!r} absent from canonical_of map"
                raise KeyError(msg)
            ids.add(canonical_of[raw])
        landscape.append(frozenset(ids))
    return landscape


@dataclass(frozen=True)
class CosineForensic:
    """Negative / near-zero cosine accounting (Codex MEDIUM-3).

    The multiplicative spatial factor preserves bit-identity but flips meaning on
    negative cosine (it deepens a negative score). Top-k retrieval candidates are
    almost always positive, but the probe surfaces the distribution so a regime where
    negative cosines distort ranking is observable rather than hidden.
    """

    total: int = 0
    negative: int = 0
    near_zero: int = 0
    min_sim: float = 0.0
    max_sim: float = 0.0


@dataclass(frozen=True)
class SeedResult:
    """Per-seed divergence readouts for one fixture instantiation."""

    seed: int
    d_obs: float
    """① == ②-ON: path-A vs path-B, spatial ON, matched terminal location."""
    d_null_permutation: float
    """① path-label permutation null (path structure destroyed), ON."""
    d_null_w0: float
    """④ same-terminal/same-query content-only floor (spatial term OFF)."""
    d_control_same_loc_on: float
    """③ same-location/different-content, spatial ON."""
    d_control_same_loc_off: float
    """③ same-location/different-content, spatial OFF."""
    valid: bool = True
    """False ⇒ apparatus invalid for this seed (excluded from strong verdict)."""
    forensic: CosineForensic = field(default_factory=CosineForensic)

    @property
    def max_verdict_null(self) -> float:
        """``max(D over VERDICT_NULL_KEYS)`` = max(① permutation, ④ w0) (Codex HIGH-1).

        ② (the signal) and ③ (no-spurious control) are deliberately excluded.
        """
        return max(self.d_null_permutation, self.d_null_w0)


__all__ = [
    "CosineForensic",
    "SeedResult",
    "iqr",
    "jaccard_distance",
    "landscape_divergence",
    "run_landscape_battery",
]
