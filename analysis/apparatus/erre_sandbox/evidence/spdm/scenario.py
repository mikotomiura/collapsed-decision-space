"""Non-circular scenario generator for the M13-ES1 SPDM definitive verdict run.

The frozen apparatus (:mod:`erre_sandbox.evidence.spdm.probe` /
:mod:`erre_sandbox.evidence.spdm.verdict_report`) can *discriminate* a
path-distinct fixture — that is what ``tests/test_evidence/test_spdm_probe.py``
proves. But that fixture is **circular for a verdict**: it hand-assigns
``a_near = first half`` / ``b_near = second half`` (the disjoint nearest-set *is*
the answer the metric then "discovers"). A scientific verdict needs the path-A /
path-B formation-location binding to **emerge from a verdict-blind movement
model**, not to be planted.

This module builds exactly that. Two same-base individuals take a **uniform
random walk over the real world adjacency graph** (mirrored from
``erre_sandbox.world.zones`` and pinned to it in the scenario test). The only
free quantity is the seed; there is **no** stickiness / dwell / bias knob that a
designer could turn to manufacture divergence. Start and terminal zones are drawn
by the same blind RNG and **shared by both arms** (terminal-location match,
frozen nuisance). Both arms form the *same* canonical contents in the same order;
**only where each content was formed differs, and that is a consequence of the
walk** — the designer never assigns a content to a location.

What the frozen verdict then reads (see the package design note): because both
arms form identical canonical contents, the ``spatial_weight=0`` ablation (④) and
the path-label-permutation null (①, both arms given arm-A's trajectory) collapse
to **0** on a deterministic apparatus, so ``max_verdict_null = 0`` and the ratio
gate is satisfied via the degenerate-null fallback (Codex HIGH-5). The verdict
therefore reduces to: *does the blind path-A/path-B divergence clear the
practical floor (median ``D_obs`` ≥ ``DEGENERATE_NULL_FLOOR``) reliably (one-sided
bootstrap CI lower > 0, cross-seed ``IQR(D_obs)`` not noisy)?* — with the ②
positive control and ③ no-spurious control supplied from the same generator.

This makes the run a **necessary-substrate conformance diagnostic**, *not* a
matched-null path-dependence test (Codex HIGH-1 of the scenario review, accepted):
because ① is the apparatus-validity floor (not a chance-divergence null), a GO
means only that the spatial binding **reliably wires movement history into the
retrieval landscape, attributable to the spatial term** (the substrate missing at
core-thesis close) — i.e. *eligible for ES-2*. Testing path-A/B divergence against
a matched permutation null is deferred to ES-2, where path-recombination and
semantic competition re-enter. The claim is deliberately the frozen claim boundary
(necessary substrate), nothing stronger.

The ③ no-spurious control compares the **retrieved position set** (which trajectory
indices surface) under the same trajectory, not a content Jaccard (Codex ruling C
of the ③ review; the run-1 partial-content-overlap Jaccard was a parity-confounded
artifact). Under the content-blind spatial term this collapses to 0 (no content
leakage) — a clean, non-confounded reading.

Nothing here re-tunes a frozen constant or alters an apparatus decision rule; the
module only *feeds* the frozen probe/verdict from a blind movement model. The
GO / NO_GO / INCONCLUSIVE outcome is whatever emerges and is recorded verbatim by
``scripts/spdm_verdict_run.py`` — it is deliberately **not** pinned in a test
(pinning the verdict would re-bake the answer into the apparatus).

Architecture: this module stays inside the ``evidence`` USE-surface
(``schemas`` + ``memory``); the world geometry is **mirrored** as local constants
rather than imported, and the scenario test asserts byte-equality with
``erre_sandbox.world.zones`` so the mirror cannot silently drift.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from erre_sandbox.evidence.spdm import constants as _c
from erre_sandbox.evidence.spdm.probe import (
    CosineForensic,
    SeedResult,
    iqr,
    landscape_divergence,
    run_landscape_battery,
)
from erre_sandbox.evidence.spdm.verdict_report import (
    Gate1Result,
    Gate2Verdict,
    evaluate_gate2,
)
from erre_sandbox.memory.embedding import EmbeddingClient
from erre_sandbox.memory.retrieval import Retriever
from erre_sandbox.memory.store import MemoryStore
from erre_sandbox.schemas import MemoryEntry, MemoryKind, SpatialContext, Zone

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- world-geometry mirror (pinned to erre_sandbox.world.zones in the test) ----

ZONES: tuple[Zone, ...] = (
    Zone.STUDY,
    Zone.PERIPATOS,
    Zone.CHASHITSU,
    Zone.AGORA,
    Zone.GARDEN,
)
"""The five zones in ``Zone`` declaration order (deterministic across interpreters)."""

NORMALIZED_ZONE_CENTERS: dict[Zone, tuple[float, float, float]] = {
    Zone.STUDY: (-1.0, 0.0, -1.0),
    Zone.PERIPATOS: (0.0, 0.0, 0.0),
    Zone.CHASHITSU: (1.0, 0.0, -1.0),
    Zone.AGORA: (0.0, 0.0, 1.0),
    Zone.GARDEN: (1.0, 0.0, 1.0),
}
"""Zone centroids on a **unit reference lattice** = ``world.zones.ZONE_CENTERS``
divided by ``world.zones._ZONE_OFFSET`` (= ``WORLD_SIZE_M / 3``).

Normalising to a unit lattice keeps ``d_norm`` in a stable range so the frozen
``SPATIAL_GAMMA`` / ``SPATIAL_COORD_REF`` (=1.0) give a *graded* (not binary)
proximity (Codex MEDIUM-2 of the freeze). The scenario test pins these to the
real world centroids so the geometry is faithful, not invented."""

ADJACENCY: dict[Zone, tuple[Zone, ...]] = {
    Zone.STUDY: (Zone.PERIPATOS,),
    Zone.PERIPATOS: (Zone.STUDY, Zone.CHASHITSU, Zone.AGORA, Zone.GARDEN),
    Zone.CHASHITSU: (Zone.PERIPATOS, Zone.GARDEN),
    Zone.AGORA: (Zone.PERIPATOS, Zone.GARDEN),
    Zone.GARDEN: (Zone.PERIPATOS, Zone.CHASHITSU, Zone.AGORA),
}
"""Walkable adjacency mirrored from ``world.zones.ADJACENCY`` (neighbour tuples in
``ZONES`` order so ``random.choice`` is reproducible). Pinned in the test."""

_EMBED_DIM = 8
_BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)
_PROBE_NOW = _BASE_TS + timedelta(days=1)


class _FixedUnitEmbedding(EmbeddingClient):
    """Embed every content and query to one shared unit vector (cosine ties).

    With cosine tied, the **spatial term**, not semantics, decides which memories
    surface. This is the apparatus's deliberate "hold semantics constant to isolate
    the spatial variable" control (the same device ``test_spdm_probe`` uses); it
    does **not** decide *which* contents are near the terminal — the blind walk does.
    """

    def __init__(self) -> None:
        self.model = "spdm-fixed"
        self.endpoint = "http://fixed"
        self.dim = _EMBED_DIM
        self._vec = [1.0] + [0.0] * (_EMBED_DIM - 1)

    async def embed(self, _text: str) -> list[float]:
        return list(self._vec)

    async def embed_query(self, _text: str) -> list[float]:
        return list(self._vec)

    async def embed_document(self, _text: str) -> list[float]:
        return list(self._vec)

    async def embed_many(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "document"],  # noqa: ARG002
    ) -> list[list[float]]:
        return [list(self._vec) for _ in texts]

    async def close(self) -> None:
        return None


def uniform_walk(start: Zone, steps: int, rng: random.Random) -> list[Zone]:
    """A length-``steps`` uniform random walk over :data:`ADJACENCY` from ``start``.

    ``trajectory[i]`` is the zone occupied when content ``i`` is formed: the
    current zone is recorded *then* the walker moves to a uniformly-random
    adjacent zone (no self-loop, no dwell — the graph has no self-edges). The walk
    is fully determined by ``rng``; ``trajectory[0] == start`` always, so two arms
    sharing a start co-locate content 0 (a conservative matched element).
    """
    here = start
    trajectory: list[Zone] = []
    for _ in range(steps):
        trajectory.append(here)
        here = rng.choice(ADJACENCY[here])
    return trajectory


def _loc(zone: Zone) -> SpatialContext:
    x, y, z = NORMALIZED_ZONE_CENTERS[zone]
    return SpatialContext(zone=zone, x=x, y=y, z=z)


def _content_ids(prefix: str) -> list[str]:
    return [f"{prefix}{i:02d}" for i in range(_c.M_MEMORIES)]


def _position_canonical(prefix: str) -> dict[str, str]:
    """Map an arm's raw row ids → their **trajectory-position** id (``p00``..).

    The ③ no-spurious control compares the **retrieved position set** (which
    trajectory indices surfaced), not the canonical *content* set (Codex ruling C,
    suggestion i). Mapping both the ``c..`` arm and the disjoint ``x..`` arm onto a
    shared ``p{i}`` position key turns ③ into a content-leakage test: under the
    content-blind spatial term (``retrieval.spatial_proximity`` depends only on
    location), two arms on the *same* trajectory must retrieve the *same* positions,
    so ``D(③)`` collapses to 0 both ON and OFF. A non-zero margin would mean content
    leaked into which positions surface — the genuine spurious-separation signal,
    free of the parity confound a partial content-overlap Jaccard introduces
    (run-1 artifact; see ``codex-review-control3.md``).
    """
    return {f"{prefix}{i:02d}-row": f"p{i:02d}" for i in range(_c.M_MEMORIES)}


def _zone_free_queries() -> list[str]:
    """``Q_BATTERY_MIN`` zone-vocabulary-free queries (no zone token; Codex HIGH-3).

    Under the fixed-unit embedding the queries embed identically, so the battery's
    role is the frozen count gate; cross-instance variance is carried by the seeds.
    """
    return [f"reflection prompt {i}" for i in range(_c.Q_BATTERY_MIN)]


async def _build_arm(
    contents: Sequence[str],
    trajectory: Sequence[Zone],
) -> tuple[MemoryStore, dict[str, str]]:
    """Build one arm: content ``i`` formed at ``trajectory[i]``'s centroid.

    ``M_MEMORIES`` memories are formed; returns the store and the raw-id →
    canonical-id map. The canonical id is the content string (Codex HIGH-2): both
    arms form the same
    canonical contents, so the landscape Jaccard measures *which* contents surface,
    not per-arm row-id separation.
    """
    store = MemoryStore(":memory:", embed_dim=_EMBED_DIM)
    store.create_schema()
    canonical_of: dict[str, str] = {}
    vec = [1.0] + [0.0] * (_EMBED_DIM - 1)
    for i, (content, zone) in enumerate(zip(contents, trajectory, strict=True)):
        raw_id = f"{content}-row"
        await store.add(
            MemoryEntry(
                id=raw_id,
                agent_id="spdm",
                kind=MemoryKind.EPISODIC,
                content=content,
                importance=0.5,
                created_at=_BASE_TS + timedelta(seconds=i),
                location=_loc(zone),
            ),
            embedding=vec,
        )
        canonical_of[raw_id] = content
    return store, canonical_of


async def _arm_landscape(
    store: MemoryStore,
    canonical_of: dict[str, str],
    terminal: SpatialContext,
    *,
    spatial_weight: float,
) -> list[frozenset[str]]:
    retriever = Retriever(
        store,
        _FixedUnitEmbedding(),
        spatial_weight=spatial_weight,
        spatial_gamma=_c.SPATIAL_GAMMA,
        spatial_coord_ref=_c.SPATIAL_COORD_REF,
        now_factory=_PROBE_NOW,
    )
    return await run_landscape_battery(
        retriever,
        "spdm",
        _zone_free_queries(),
        current_location=terminal,
        canonical_of=canonical_of,
        k_agent=_c.K_RETRIEVE,
    )


async def _cosine_forensic(
    store: MemoryStore,
    terminal: SpatialContext,
) -> tuple[CosineForensic, float]:
    """Cosine distribution + rank-k cutoff margin for one ON retrieval (forensic).

    Codex MEDIUM-3 (surface the cosine distribution so a negative-cosine regime is
    observable) and LOW-1 (a cutoff-margin diagnostic since the top-k Jaccard is
    cutoff-sensitive). Forensic only — never feeds the verdict.
    """
    retriever = Retriever(
        store,
        _FixedUnitEmbedding(),
        spatial_weight=1.0,
        spatial_gamma=_c.SPATIAL_GAMMA,
        spatial_coord_ref=_c.SPATIAL_COORD_REF,
        now_factory=_PROBE_NOW,
    )
    ranked = await retriever.retrieve(
        "spdm",
        "reflection prompt 0",
        k_agent=_c.M_MEMORIES,
        k_world=0,
        current_location=terminal,
        mark_recalled=False,
    )
    sims = [r.cosine_sim for r in ranked]
    near = 1e-9
    forensic = CosineForensic(
        total=len(sims),
        negative=sum(1 for s in sims if s < 0.0),
        near_zero=sum(1 for s in sims if abs(s) < near),
        min_sim=min(sims) if sims else 0.0,
        max_sim=max(sims) if sims else 0.0,
    )
    # Cutoff margin = strength gap straddling the top-k boundary (rank k-1 vs k).
    k = _c.K_RETRIEVE
    margin = (
        ranked[k - 1].strength - ranked[k].strength if len(ranked) > k else float("nan")
    )
    return forensic, margin


@dataclass(frozen=True)
class SeedForensic:
    """Per-seed blind-generator provenance + the LOW-1/MEDIUM-3 diagnostics."""

    seed: int
    start_zone: Zone
    terminal_zone: Zone
    d_obs: float
    d_null_permutation: float
    d_null_w0: float
    d_control_same_loc_on: float
    d_control_same_loc_off: float
    rank_weighted_overlap: float
    cutoff_margin: float
    cosine: CosineForensic


def _draw_zone(rng: random.Random) -> Zone:
    return ZONES[rng.randrange(len(ZONES))]


def _rank_weighted_overlap(
    arm_a: Sequence[frozenset[str]],
    arm_b: Sequence[frozenset[str]],
) -> float:
    """Mean set overlap across the battery (LOW-1 companion to Jaccard distance).

    ``mean |a∩b| / |a∪b|`` over the query battery; 1.0 = identical landscapes,
    0.0 = disjoint. Forensic only — never feeds the verdict.
    """
    if not arm_a:
        return 1.0
    return 1.0 - landscape_divergence(arm_a, arm_b)


async def build_seed_result(seed: int) -> tuple[SeedResult, SeedForensic]:
    """One blind apparatus instantiation: walks → real retrieval → ``SeedResult``.

    The two arms differ **only** by their random-walk RNG sub-stream; start,
    terminal, contents, count, query battery and seed are matched. ① and ④ collapse
    to 0 by construction on this deterministic apparatus (apparatus-valid), so the
    verdict reads the blind ``d_obs`` against the practical floor.
    """
    base = random.Random(f"spdm-seed-{seed}")  # noqa: S311 — deterministic science RNG
    start = _draw_zone(base)
    terminal_zone = _draw_zone(base)
    terminal = _loc(terminal_zone)

    rng_a = random.Random(f"spdm-seed-{seed}-armA")  # noqa: S311 — deterministic RNG
    rng_b = random.Random(f"spdm-seed-{seed}-armB")  # noqa: S311 — deterministic RNG
    traj_a = uniform_walk(start, _c.M_MEMORIES, rng_a)
    traj_b = uniform_walk(start, _c.M_MEMORIES, rng_b)

    contents = _content_ids("c")
    alt_contents = _content_ids("x")  # disjoint content; ③ compares positions, not ids

    store_a, can_a = await _build_arm(contents, traj_a)
    store_b, can_b = await _build_arm(contents, traj_b)
    # ① permutation: destroy the A/B path structure by giving *both* compared arms
    # arm-A's trajectory (frozen-apparatus degeneration) ⇒ identical ⇒ 0. This is
    # the apparatus-validity floor, not a matched chance-divergence null; the
    # verdict therefore reads D_obs against the absolute practical floor (a
    # necessary-substrate conformance check), not against a permutation null — the
    # matched-null path-dependence test is ES-2's job (Codex HIGH-1, accepted).
    store_p, can_p = await _build_arm(contents, traj_a)
    # ③ same-location / different-content: arm-A's trajectory, disjoint content. The
    # control compares the retrieved *position* set (Codex ruling C, suggestion i),
    # so a non-zero margin means content leaked into which positions surface — free
    # of the parity confound a partial content-overlap Jaccard caused in run 1.
    store_c, _ = await _build_arm(alt_contents, traj_a)
    pos_a = _position_canonical("c")
    pos_c = _position_canonical("x")

    obs_a = await _arm_landscape(store_a, can_a, terminal, spatial_weight=1.0)
    obs_b = await _arm_landscape(store_b, can_b, terminal, spatial_weight=1.0)
    d_obs = landscape_divergence(obs_a, obs_b)

    off_a = await _arm_landscape(store_a, can_a, terminal, spatial_weight=0.0)
    off_b = await _arm_landscape(store_b, can_b, terminal, spatial_weight=0.0)
    d_w0 = landscape_divergence(off_a, off_b)

    perm_a = await _arm_landscape(store_a, can_a, terminal, spatial_weight=1.0)
    perm_b = await _arm_landscape(store_p, can_p, terminal, spatial_weight=1.0)
    d_perm = landscape_divergence(perm_a, perm_b)

    # ③ compares the retrieved *position* sets (``pos_a`` / ``pos_c`` map each arm's
    # rows onto a shared p{i} key), so D collapses to 0 unless content leaks.
    sl_on_a = await _arm_landscape(store_a, pos_a, terminal, spatial_weight=1.0)
    sl_on_c = await _arm_landscape(store_c, pos_c, terminal, spatial_weight=1.0)
    d_sl_on = landscape_divergence(sl_on_a, sl_on_c)
    sl_off_a = await _arm_landscape(store_a, pos_a, terminal, spatial_weight=0.0)
    sl_off_c = await _arm_landscape(store_c, pos_c, terminal, spatial_weight=0.0)
    d_sl_off = landscape_divergence(sl_off_a, sl_off_c)

    cosine, margin = await _cosine_forensic(store_a, terminal)
    rwo = _rank_weighted_overlap(obs_a, obs_b)

    for s in (store_a, store_b, store_p, store_c):
        await s.close()

    result = SeedResult(
        seed=seed,
        d_obs=d_obs,
        d_null_permutation=d_perm,
        d_null_w0=d_w0,
        d_control_same_loc_on=d_sl_on,
        d_control_same_loc_off=d_sl_off,
        forensic=cosine,
    )
    forensic = SeedForensic(
        seed=seed,
        start_zone=start,
        terminal_zone=terminal_zone,
        d_obs=d_obs,
        d_null_permutation=d_perm,
        d_null_w0=d_w0,
        d_control_same_loc_on=d_sl_on,
        d_control_same_loc_off=d_sl_off,
        rank_weighted_overlap=rwo,
        cutoff_margin=margin,
        cosine=cosine,
    )
    return result, forensic


@dataclass(frozen=True)
class VerdictRun:
    """The frozen Gate-2 verdict plus the full blind-generator forensic trail."""

    verdict: Gate2Verdict
    gate1: Gate1Result
    seeds: tuple[SeedForensic, ...]
    median_d_obs: float
    iqr_d_obs: float


async def run_verdict(seed_bank: Sequence[int]) -> VerdictRun:
    """Run the blind generator over ``seed_bank`` and render the frozen verdict.

    Gate 1 (single-query apparatus health) is read from the first seed: because
    the fixed-unit embedding makes every battery query identical, the per-query
    distance equals the battery mean, so ``d_obs`` / ``d_null_permutation`` /
    ``d_null_w0`` of seed 0 are the exact single-query readouts. The queries are
    already zone-vocabulary-free, so the zone-free pair repeats them. Nothing here
    re-tunes a constant; it only feeds :func:`evaluate_gate2`.
    """
    results: list[SeedResult] = []
    forensics: list[SeedForensic] = []
    for seed in seed_bank:
        result, forensic = await build_seed_result(seed)
        results.append(result)
        forensics.append(forensic)

    first = results[0]
    gate1 = Gate1Result(
        single_query_distance=first.d_obs,
        location_shuffle_null=first.d_null_permutation,
        ablation_w0_distance=first.d_null_w0,
        zone_free_distance=first.d_obs,
        zone_free_null=first.d_null_permutation,
    )
    verdict = evaluate_gate2(results, gate1, n_queries=_c.Q_BATTERY_MIN)

    d_obs_values = [r.d_obs for r in results]
    median_d_obs = statistics.median(d_obs_values) if d_obs_values else 0.0
    return VerdictRun(
        verdict=verdict,
        gate1=gate1,
        seeds=tuple(forensics),
        median_d_obs=median_d_obs,
        iqr_d_obs=iqr(d_obs_values),
    )


def default_seed_bank() -> tuple[int, ...]:
    """The pre-registered blind seed bank: ``range(N_SEED)`` (= 0..7).

    Fixed before the run; no seed is added or dropped after seeing a divergence
    (forking-paths guard). A superseding ADR is required to change it.
    """
    return tuple(range(_c.N_SEED))


__all__ = [
    "ADJACENCY",
    "NORMALIZED_ZONE_CENTERS",
    "ZONES",
    "SeedForensic",
    "VerdictRun",
    "build_seed_result",
    "default_seed_bank",
    "run_verdict",
    "uniform_walk",
]
