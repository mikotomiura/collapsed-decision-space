"""History-dependent destination geometry resolver — ECL v0 organ core.

This is the *single new cognition organ* the Embodied Cognition Loop v0 adds
(design-final.md §論点2 / §論点4, ``.steering/20260705-ecl-v0-impl-design/``): a
**pure resolver** that turns an LLM-selected ``destination_zone`` (a *zone tag*,
never coordinates) into a concrete within-zone ``(x, z)`` **derived from the
agent's own movement history** — the strength-weighted centroid of its top-``K``
self memories, jittered inside a disc and reflect-clamped back into the chosen
zone's Voronoi cell. The LLM chooses *which zone*; history chooses *where in it*.

Layer discipline (architecture-rules): ``cognition`` may import ``memory`` +
``contracts`` + ``schemas`` but never ``world``. The geometry primitives
(:func:`~erre_sandbox.contracts.geometry.disc_jitter` /
:func:`~erre_sandbox.contracts.geometry.reflect_clamp` /
:func:`~erre_sandbox.contracts.geometry.default_spawn`) were relocated to
``contracts.geometry`` in Issue 001 precisely so this resolver can live in the
cognition layer; they are **imported**, not re-copied.

Policy grammar freeze (design-final.md §論点2, binding — pinned by
``tests/test_cognition/test_ecl_embodiment.py::test_ecl_v0_policy_grammar_frozen``).
The **only** history features this resolver may read (closed enumeration,
nothing else):

1. ``retrieved`` — the agent's own ``Retriever.retrieve`` result, called with
   ``k_agent=K_ECL``, ``k_world=0`` (binding: cross-agent/world-scope memory
   never enters the centroid — the "self memory only" claim, Codex HIGH-2),
   ``current_location=here`` and ``mark_recalled=False`` (no measurement-order
   recall side effect).
2. each :class:`~erre_sandbox.memory.retrieval.RankedMemory`'s
   ``entry.location.(x, z)`` and its ``strength``.
3. the strength-weighted centroid ``c = Σ wᵢ·pᵢ / Σ wᵢ``.
4. ``here.zone`` (current zone) and ``destination_zone`` (the LLM plan's chosen
   zone tag).

The feature → action transform is a single frozen functional form (frozen P-A
equivalent, design-copied from ``evidence.d0_substrate.running.policy`` L421-436,
*not* imported): ``dest_raw = centroid + disc_jitter(R)`` then
``dest = reflect_clamp(dest_raw, destination_zone)`` — centroid+jitter **then**
clamp. The empty / no-located / non-positive-weight fallback is
``default_spawn(destination_zone)`` (the history-independent baseline that the
continuity **negative control** must equal exactly). The LLM's entire discretion
is ``destination_zone ∈ {5 zones}``; it supplies **no** coordinate, weight, or
per-zone hand-weight — those are frozen here.

**Scope guard (design-final.md §論点4, binding).** The continuity gate this
module feeds is a *construction* check (memory→geometry→movement is wired), **NOT
a structural-floor verdict; verdict は holding**. This module therefore imports no
``evidence`` / ``spdm`` / ``runningness`` machinery and computes/emits no
floor / landscape-divergence / R0-R1 statistic — measurement-line re-entry stays
behind the scoping §4.2 costed superseding-ADR gate. The decision record below
carries only *candidate selection* provenance (centroid / memory ids / jitter /
pre- and post-clamp), never an absolute-target replay key, so the causal ablation
(negative control) actually bites.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Final, Literal, Protocol

from erre_sandbox.contracts import geometry
from erre_sandbox.schemas import Position

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from erre_sandbox.memory.retrieval import RankedMemory
    from erre_sandbox.schemas import SpatialContext, Zone

K_ECL: Final[int] = 8
"""Top-k self memories folded into the ECL destination centroid.

Value-identical to ``evidence.d0_substrate.constants.K_RETRIEVE`` (= the frozen
``memory.retrieval.DEFAULT_K_AGENT``), mirrored — not re-derived — from the
frozen ``running/policy.py`` forage query (``k_agent=_c.K_RETRIEVE``). Frozen by
grill G-3; never an independent tunable (that would be a tune-to-pass hole).
"""


class SupportsRetrieve(Protocol):
    """Structural type for the retrieval handle :func:`resolve_destination` uses.

    Matches the keyword surface of ``Retriever.retrieve`` that the resolver
    actually calls, so both the production ``Retriever`` and a test spy/fake
    satisfy it without the resolver importing the concrete class.
    """

    async def retrieve(
        self,
        agent_id: str,
        query: str,
        *,
        k_agent: int = ...,
        k_world: int = ...,
        current_location: SpatialContext | Position | None = ...,
        mark_recalled: bool = ...,
    ) -> list[RankedMemory]: ...


@dataclass(frozen=True, slots=True)
class EclDestination:
    """One resolved move decision's candidate-selection trail (design §論点4).

    Records *how* the destination was chosen — the strength-weighted
    ``centroid`` of history, the ``provenance`` memory ids folded into it, the
    ``jitter`` offset drawn, and the ``pre_clamp`` / ``post_clamp`` points — so a
    replay/continuity check re-runs the frozen transform rather than trusting an
    absolute target. ``resolved_from`` is ``"spawn"`` on the history-independent
    fallback (empty retrieval / nothing located / non-positive total weight),
    where ``target == default_spawn(zone)`` exactly and ``provenance`` is empty.
    """

    target: Position
    resolved_from: Literal["memory_centroid", "spawn"]
    centroid: tuple[float, float]
    provenance: tuple[str, ...]
    jitter: tuple[float, float]
    pre_clamp: tuple[float, float]
    post_clamp: tuple[float, float]
    clamp_fired: bool


@dataclass(frozen=True, slots=True)
class EclRecordMode:
    """A record-mode runtime object holding the ECL driver's deterministic handles.

    Not a pure config value: it owns per-``(agent_id, stream)`` RNG handles whose
    draw sequences advance across the run (the ``_rng_cache`` memoize below), so
    the record/replay driver (Issue 003) and integration harness (Issue 004) can
    pin Plane 1 (design-final.md §論点3, grill G-2 / G-7). Carries **only** the
    deterministic handles: a fixed retrieval clock, a deterministic memory
    ``created_at`` base, named RNG substream + id factories, ``k_ecl``, the
    reflection-disable flag, and an optional move-decision callback.

    Deliberately **excludes** trace / manifest / checksum types (Codex TASK-PRE
    MEDIUM: those belong to the integration layer, not the cognition config) —
    the only non-primitive it references is :class:`EclDestination`, a
    cognition-layer decision record.
    """

    run_id: str
    retrieval_now: datetime
    base_ts: datetime
    k_ecl: int = K_ECL
    reflection_disabled: bool = True
    move_decision_sink: Callable[[EclDestination], None] | None = None
    _rng_cache: dict[tuple[str, str], random.Random] = field(
        default_factory=dict, compare=False, repr=False
    )

    def substream(
        self, agent_id: str, stream: Literal["micro", "tie"]
    ) -> random.Random:
        """Named RNG substream ``ecl-{run_id}-{agent_id}-{stream}`` (grill G-7).

        Never the global RNG. Memoized per ``(agent_id, stream)``: the **first**
        call seeds ``random.Random(f"ecl-{run_id}-{agent_id}-{stream}")`` and every
        later call with the same key returns that *same* handle, so its draws form
        a single run-sequence (frozen ``running/policy.py`` §2.4 idiom: one RNG
        made once per run, its sequence then consumed) rather than restarting from
        the seed each tick. A re-run with the same ``run_id`` reproduces a
        byte-identical draw sequence. Mutating this frozen dataclass's cache dict
        in place is legal (the dict *identity* never changes); ``_rng_cache`` is
        ``compare=False`` / ``repr=False`` so it stays out of equality and repr.

        Uses get-then-assign, not ``dict.setdefault``: ``setdefault`` would
        evaluate a fresh ``random.Random(...)`` on every call, defeating the
        memoize.
        """
        key = (agent_id, stream)
        rng = self._rng_cache.get(key)
        if rng is None:
            rng = random.Random(f"ecl-{self.run_id}-{agent_id}-{stream}")  # noqa: S311
            self._rng_cache[key] = rng
        return rng

    def memory_id(self, agent_id: str, agent_tick: int) -> str:
        """Deterministic memory id ``ecl-{agent_id}-{agent_tick:04d}`` (§論点3)."""
        return f"ecl-{agent_id}-{agent_tick:04d}"

    def memory_created_at(self, agent_tick: int) -> datetime:
        """Tick-derived ``created_at`` = ``base_ts + agent_tick·1s`` (§論点3)."""
        return self.base_ts + timedelta(seconds=agent_tick)


def strength_weighted_centroid(
    located: list[RankedMemory],
) -> tuple[float, float] | None:
    """Strength-weighted centroid of ``located`` memories, or ``None`` on fallback.

    ``c = Σ wᵢ·pᵢ / Σ wᵢ`` over each memory's ``entry.location.(x, z)`` with
    ``wᵢ = strength`` (design-copied from the frozen ``_forage_centroid``, not
    imported). Returns ``None`` when ``located`` is empty or the total weight is
    non-positive, signalling the caller to take the ``default_spawn`` fallback.

    ``located`` must contain only memories whose ``entry.location is not None``
    and should already be in the binding ``(-strength, created_at, id)`` order
    (see :func:`resolve_destination`); the centroid itself is order-independent.
    """
    if not located:
        return None
    weights = [r.strength for r in located]
    total = sum(weights)
    if total <= 0.0:
        return None
    cx = 0.0
    cz = 0.0
    for w, r in zip(weights, located, strict=True):
        loc = r.entry.location
        assert loc is not None  # caller filters located; narrows for the type checker
        cx += w * loc.x
        cz += w * loc.z
    return cx / total, cz / total


async def resolve_destination(
    retriever: SupportsRetrieve,
    *,
    agent_id: str,
    query: str,
    here: Position,
    destination_zone: Zone,
    micro_rng: random.Random,
    k_ecl: int = K_ECL,
) -> EclDestination:
    """Resolve the LLM's ``destination_zone`` to a history-dependent target.

    Reads the agent's own top-``k_ecl`` memories (``k_world=0``,
    ``mark_recalled=False``), takes their strength-weighted centroid, adds a
    ``disc_jitter`` offset drawn from ``micro_rng`` and reflect-clamps the sum
    into ``destination_zone`` — centroid+jitter **then** clamp, matching the
    frozen policy order exactly. With no located memory / non-positive weight the
    target is ``default_spawn(destination_zone)`` (the negative-control baseline),
    and ``micro_rng`` is left untouched so the fallback is exactly the spawn point.

    The LLM controls only ``destination_zone`` (a :class:`~erre_sandbox.schemas.Zone`);
    this function accepts no coordinate or weight from it — the policy-grammar
    freeze the docstring pins.
    """
    ranked = await retriever.retrieve(
        agent_id,
        query,
        k_agent=k_ecl,
        k_world=0,
        current_location=here,
        mark_recalled=False,
    )
    located = sorted(
        (r for r in ranked if r.entry.location is not None),
        key=lambda r: (-r.strength, r.entry.created_at, r.entry.id),
    )
    centroid = strength_weighted_centroid(located)
    if centroid is None:
        spawn = geometry.default_spawn(destination_zone)
        return EclDestination(
            target=spawn,
            resolved_from="spawn",
            centroid=(spawn.x, spawn.z),
            provenance=(),
            jitter=(0.0, 0.0),
            pre_clamp=(spawn.x, spawn.z),
            post_clamp=(spawn.x, spawn.z),
            clamp_fired=False,
        )

    cx, cz = centroid
    jitter = geometry.disc_jitter(micro_rng)
    pre_x, pre_z = cx + jitter[0], cz + jitter[1]
    post_x, post_z, clamp_fired = geometry.reflect_clamp(pre_x, pre_z, destination_zone)
    target = Position(
        x=post_x,
        y=0.0,
        z=post_z,
        zone=geometry.locate_zone(post_x, 0.0, post_z),
    )
    return EclDestination(
        target=target,
        resolved_from="memory_centroid",
        centroid=(cx, cz),
        provenance=tuple(r.entry.id for r in located),
        jitter=jitter,
        pre_clamp=(pre_x, pre_z),
        post_clamp=(post_x, post_z),
        clamp_fired=clamp_fired,
    )


__all__ = [
    "K_ECL",
    "EclDestination",
    "EclRecordMode",
    "SupportsRetrieve",
    "resolve_destination",
    "strength_weighted_centroid",
]
