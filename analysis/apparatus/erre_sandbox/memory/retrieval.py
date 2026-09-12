"""2-scope retriever with decay-weighted ranking.

The scoring function

    strength = importance * exp(-λ * age_days) * (1 + β * recall_count) * cosine_sim

matches ``docs/architecture.md §Memory Layer`` for the ``importance`` and
``recall_count`` factors; ``λ`` defaults to ``0.1`` (half-life ≈ 7 days).

``Retriever.retrieve`` is the authoritative retrieval entrypoint used by
``cognition/cycle.py`` (T12): it composes ``k_agent`` per-agent memories
with ``k_world`` cross-agent memories, ranks them by ``score()``, and
bumps ``recall_count`` as a deliberate side effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import numpy as np

from erre_sandbox.schemas import MemoryKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.memory.embedding import EmbeddingClient
    from erre_sandbox.memory.store import MemoryStore
    from erre_sandbox.schemas import MemoryEntry, Position, SpatialContext

_SECONDS_PER_DAY: Final[float] = 86_400.0
DEFAULT_DECAY_LAMBDA: Final[float] = 0.1  # half-life ≈ ln(2)/0.1 ≈ 6.93 days
DEFAULT_RECALL_BOOST: Final[float] = 0.2
DEFAULT_K_AGENT: Final[int] = 8
DEFAULT_K_WORLD: Final[int] = 3
DEFAULT_SPATIAL_WEIGHT: Final[float] = 0.0
"""Default weight of the spatial-proximity term (M13-ES1 SPDM).

``0.0`` ⇒ the spatial factor is exactly ``1.0`` ⇒ the score is **bit-identical** to
the pre-SPDM ranking. Only the SPDM probe / a spatially-aware caller raises it."""

DEFAULT_SPATIAL_GAMMA: Final[float] = 0.5
"""Spatial-proximity decay (mirrors frozen ``evidence.spdm.constants.SPATIAL_GAMMA``).

Kept as a local default so ``memory`` does not import ``evidence`` (dependency
direction); ``tests/test_evidence/test_spdm_scorer_identity.py`` pins the two equal.
Unused when ``spatial_weight == 0`` (the production default)."""

DEFAULT_SPATIAL_COORD_REF: Final[float] = 1.0
"""Reference scale the proximity distance is divided by before the exp decay
(mirrors ``evidence.spdm.constants.SPATIAL_COORD_REF``)."""
DEFAULT_KINDS: Final[tuple[MemoryKind, ...]] = (
    MemoryKind.EPISODIC,
    MemoryKind.SEMANTIC,
)


def score(
    *,
    importance: float,
    age_days: float,
    recall_count: int,
    cosine_sim: float,
    decay_lambda: float = DEFAULT_DECAY_LAMBDA,
    recall_boost: float = DEFAULT_RECALL_BOOST,
    spatial_weight: float = DEFAULT_SPATIAL_WEIGHT,
    proximity: float = 0.0,
) -> float:
    """Combine importance, recency, recall, semantic fit and spatial context.

    Pure function; see ``tests/test_memory/test_retrieval.py`` for the
    invariants this guarantees (monotone decay in ``age_days``, monotone
    boost in ``recall_count``, multiplicative in ``cosine_sim``).

    The spatial term (M13-ES1 SPDM) is a **multiplicative identity**: the factor
    ``1 + spatial_weight * proximity`` collapses to ``1.0`` when
    ``spatial_weight == 0`` (production default) or ``proximity == 0`` (no formation
    location ⇒ no spatial binding), so the pre-SPDM score is reproduced bit-for-bit.
    ``proximity ∈ [0, 1]`` (1 = co-located with the current position, decaying with
    distance); a positive ``spatial_weight`` boosts memories formed near where the
    agent now is, making *which* memories surface depend on the movement history.
    """
    decay = math.exp(-decay_lambda * max(age_days, 0.0))
    boost = 1.0 + recall_boost * max(recall_count, 0)
    spatial = 1.0 + spatial_weight * proximity
    return importance * decay * boost * cosine_sim * spatial


def spatial_proximity(
    now: SpatialContext | Position | None,
    formed: SpatialContext | None,
    *,
    gamma: float = DEFAULT_SPATIAL_GAMMA,
    coord_ref: float = DEFAULT_SPATIAL_COORD_REF,
) -> float:
    """Proximity ∈ [0, 1] between the agent's current place and a formation place.

    ``exp(-gamma * euclidean(now, formed) / coord_ref)``: 1.0 when co-located,
    decaying to 0 with distance. Returns ``0.0`` (⇒ spatially neutral, score
    bit-identical) when either place is ``None`` — so a memory without a formation
    location, or retrieval issued without a current position, receives no spatial
    boost. The distance is normalised by ``coord_ref`` so ``gamma`` is invariant to
    the arbitrary scale of the world coordinate frame (SPDM Codex MEDIUM-2).
    """
    if now is None or formed is None:
        return 0.0
    dx = now.x - formed.x
    dy = now.y - formed.y
    dz = now.z - formed.z
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    ref = coord_ref if coord_ref > 0.0 else 1.0
    return math.exp(-gamma * dist / ref)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity ∈ [-1, 1]. Returns 0.0 if either vector is zero."""
    av = np.asarray(a, dtype=np.float64)
    bv = np.asarray(b, dtype=np.float64)
    na = float(np.linalg.norm(av))
    nb = float(np.linalg.norm(bv))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(av, bv) / (na * nb))


@dataclass(frozen=True)
class RankedMemory:
    """A retrieval result paired with its computed strength."""

    entry: MemoryEntry
    strength: float
    cosine_sim: float


class Retriever:
    """Composes :class:`MemoryStore` and :class:`EmbeddingClient`.

    The retrieve pipeline is:

    1. Embed the query with :meth:`EmbeddingClient.embed_query`
       (``search_query:`` prefix).
    2. Pull up to ``limit_candidates`` per-agent entries (from ``kinds``)
       and ``limit_candidates`` world-scope entries.
    3. Compute ``cosine_sim`` for every candidate that has an embedding
       (candidates missing an embedding fall back to ``0.0``).
    4. Apply :func:`score` with the configured ``decay_lambda`` and
       ``recall_boost``.
    5. Take the top ``k_agent`` per-agent + top ``k_world`` world-scope.
    6. Bump ``recall_count`` for every returned memory.
    """

    def __init__(
        self,
        store: MemoryStore,
        embedding: EmbeddingClient,
        *,
        decay_lambda: float = DEFAULT_DECAY_LAMBDA,
        recall_boost: float = DEFAULT_RECALL_BOOST,
        limit_candidates: int = 50,
        now_factory: (datetime | None) = None,
        spatial_weight: float = DEFAULT_SPATIAL_WEIGHT,
        spatial_gamma: float = DEFAULT_SPATIAL_GAMMA,
        spatial_coord_ref: float = DEFAULT_SPATIAL_COORD_REF,
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._decay_lambda = decay_lambda
        self._recall_boost = recall_boost
        self._limit_candidates = limit_candidates
        # ``now_factory`` is optionally a fixed datetime for deterministic tests;
        # ``None`` means "use real wall clock" (see :meth:`_now`).
        self._fixed_now = now_factory
        # M13-ES1 SPDM spatial term. ``spatial_weight=0`` (default) ⇒ the score is
        # bit-identical to pre-SPDM; the spatial factor only engages when a caller
        # raises the weight *and* passes a ``current_location`` to :meth:`retrieve`.
        self._spatial_weight = spatial_weight
        self._spatial_gamma = spatial_gamma
        self._spatial_coord_ref = spatial_coord_ref

    def _now(self) -> datetime:
        return self._fixed_now if self._fixed_now is not None else datetime.now(tz=UTC)

    async def retrieve(
        self,
        agent_id: str,
        query: str,
        *,
        k_agent: int = DEFAULT_K_AGENT,
        k_world: int = DEFAULT_K_WORLD,
        kinds: Sequence[MemoryKind] = DEFAULT_KINDS,
        current_location: SpatialContext | Position | None = None,
        mark_recalled: bool = True,
    ) -> list[RankedMemory]:
        """Rank the agent's memories for ``query``.

        ``current_location`` (M13-ES1 SPDM) is the agent's place *now*; combined
        with each memory's formation location and a non-zero ``spatial_weight`` it
        makes which memories surface depend on the movement history. ``None`` ⇒ no
        spatial boost (bit-identical to pre-SPDM).

        ``mark_recalled`` (SPDM Codex HIGH-3): when ``False`` the ``recall_count``
        side effect is skipped, so a multi-query measurement battery does not let
        earlier queries perturb later ones (a measurement-order artifact). Defaults
        to ``True`` (production behaviour bit-identical).
        """
        q_vec = await self._embedding.embed_query(query)
        now = self._now()

        agent_ranked = await self._rank_scope(
            q_vec=q_vec,
            now=now,
            kinds=kinds,
            agent_id=agent_id,
            world=False,
            current_location=current_location,
        )
        world_ranked = await self._rank_scope(
            q_vec=q_vec,
            now=now,
            kinds=kinds,
            agent_id=agent_id,
            world=True,
            current_location=current_location,
        )

        top_agent = agent_ranked[:k_agent]
        top_world = world_ranked[:k_world]
        combined = [*top_agent, *top_world]

        if combined and mark_recalled:
            await self._store.mark_recalled([r.entry.id for r in combined])
        return combined

    async def _rank_scope(
        self,
        *,
        q_vec: list[float],
        now: datetime,
        kinds: Sequence[MemoryKind],
        agent_id: str,
        world: bool,
        current_location: SpatialContext | Position | None = None,
    ) -> list[RankedMemory]:
        """Rank one scope's candidate pool, fully ordered before truncation.

        The returned list is **totally ordered** by
        ``(-strength, created_at, id)`` — the strength-tie break by
        ``created_at`` then ``id`` is applied *here*, before the caller
        (:meth:`retrieve`) slices ``[:k_agent]`` / ``[:k_world]``. This makes
        the top-K selection reproducible for equal-strength ties (e.g. equal
        importance / recall_count / cosine_sim) instead of depending on the
        store's fetch order (B-3 determinism hardening).

        **Candidate-pool bound — not a silent cap (Codex MEDIUM-3 / TASK-PRE
        L-1).** The ordering is a *top-K over the candidate pool*, not over all
        matching memories. The pool is the **union of one ``limit_candidates``
        (default 50) fetch per ``kind`` (episodic/semantic) × per scope
        (agent/world)** — i.e. the cap is *per (kind, scope)*, not a flat 50
        across the whole retrieve. The store returns the most-recent
        ``limit_candidates`` rows per kind (``ORDER BY created_at DESC``), so an
        equal-strength but older memory that falls past that per-(kind, scope)
        fetch limit is **not** surfaced even though it would sort ahead by
        ``created_at``. Raise ``limit_candidates`` to widen the pool.
        """
        candidates: list[MemoryEntry] = []
        for kind in kinds:
            batch = (
                await self._store.list_world_scope(
                    exclude_agent_id=agent_id,
                    kind=kind,
                    limit=self._limit_candidates,
                )
                if world
                else await self._store.list_by_agent(
                    agent_id=agent_id,
                    kind=kind,
                    limit=self._limit_candidates,
                )
            )
            candidates.extend(batch)
        if not candidates:
            return []
        scored: list[RankedMemory] = []
        for entry in candidates:
            vec = await self._store.get_embedding(entry.id)
            sim = cosine_similarity(vec, q_vec) if vec is not None else 0.0
            age = _age_days(entry.created_at, now)
            prox = (
                spatial_proximity(
                    current_location,
                    entry.location,
                    gamma=self._spatial_gamma,
                    coord_ref=self._spatial_coord_ref,
                )
                if self._spatial_weight != 0.0
                else 0.0
            )
            strength = score(
                importance=entry.importance,
                age_days=age,
                recall_count=entry.recall_count,
                cosine_sim=sim,
                decay_lambda=self._decay_lambda,
                recall_boost=self._recall_boost,
                spatial_weight=self._spatial_weight,
                proximity=prox,
            )
            scored.append(RankedMemory(entry=entry, strength=strength, cosine_sim=sim))
        # Full total order over the candidate pool BEFORE the caller truncates
        # to ``[:k]`` (B-3): descending strength, then ``created_at`` then ``id``
        # to break equal-strength ties deterministically. See the docstring for
        # the per-(kind, scope) candidate-pool bound.
        scored.sort(key=lambda r: (-r.strength, r.entry.created_at, r.entry.id))
        return scored


def _age_days(created_at: datetime, now: datetime) -> float:
    delta_s = (now - created_at).total_seconds()
    return max(delta_s / _SECONDS_PER_DAY, 0.0)


__all__ = [
    "DEFAULT_DECAY_LAMBDA",
    "DEFAULT_KINDS",
    "DEFAULT_K_AGENT",
    "DEFAULT_K_WORLD",
    "DEFAULT_RECALL_BOOST",
    "DEFAULT_SPATIAL_COORD_REF",
    "DEFAULT_SPATIAL_GAMMA",
    "DEFAULT_SPATIAL_WEIGHT",
    "RankedMemory",
    "Retriever",
    "cosine_similarity",
    "score",
    "spatial_proximity",
]
